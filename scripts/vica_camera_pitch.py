#!/usr/bin/env python3
"""D455 마스트의 기울기와 높이를 실측한다 — 탈부착 후 반드시 돌릴 것."""
import math
import re
import sys
import time
from pathlib import Path

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import PointCloud2
from tf2_ros import Buffer, TransformListener

CLOUD_TOPIC = '/camera/camera/depth/color/points'
TARGET_FRAME = 'base_footprint'
BASE_LINK_Z = 0.190
RANSAC_ITERS = 600
INLIER_M = 0.025
rng = np.random.default_rng(0)


class Collector(Node):
    def __init__(self, nframe):
        super().__init__('vica_camera_pitch')
        self.nframe = nframe
        self.buf = Buffer()
        self.tl = TransformListener(self.buf, self)
        self.create_subscription(PointCloud2, CLOUD_TOPIC, self.cb,
                                 qos_profile_sensor_data)
        self.frames = []
        self.camz = None
        self.warned = False

    def cb(self, msg):
        if len(self.frames) >= self.nframe:
            return
        try:
            tf = self.buf.lookup_transform(TARGET_FRAME, msg.header.frame_id,
                                           rclpy.time.Time())
        except Exception as exc:
            if not self.warned:
                print(f'  TF 대기 중: {exc}')
                self.warned = True
            return
        off = {f.name: f.offset for f in msg.fields}
        if not {'x', 'y', 'z'} <= off.keys():
            return
        raw = np.frombuffer(msg.data, dtype=np.uint8).reshape(-1, msg.point_step)

        def col(name):
            o = off[name]
            return raw[:, o:o + 4].copy().view(np.float32).ravel()

        x, y, z = col('x'), col('y'), col('z')
        ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
        if not ok.any():
            return
        p = np.stack([x[ok], y[ok], z[ok]])
        q = tf.transform.rotation
        t = tf.transform.translation
        qx, qy, qz, qw = q.x, q.y, q.z, q.w
        rot = np.array([
            [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
            [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
            [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)],
        ])
        w = rot @ p + np.array([[t.x], [t.y], [t.z]])
        self.frames.append(np.stack([w[0] - t.x, w[1] - t.y, w[2] - t.z]))
        self.camz = t.z


def fit_once(node, nframe, timeout=25.0):
    node.frames.clear()
    t0 = time.time()
    while len(node.frames) < nframe and time.time() - t0 < timeout:
        rclpy.spin_once(node, timeout_sec=0.3)
    if not node.frames:
        return None
    P = np.concatenate(node.frames, axis=1)
    sel = (P[0] > 0.5) & (P[0] < 4.0) & (np.abs(P[1]) < 1.5) & (P[2] < 0.2)
    P = P[:, sel]
    if P.shape[1] < 500:
        return None
    if P.shape[1] > 40000:
        P = P[:, rng.choice(P.shape[1], 40000, replace=False)]

    best = (0, None)
    for _ in range(RANSAC_ITERS):
        i = rng.choice(P.shape[1], 3, replace=False)
        a, b, c = P[:, i[0]], P[:, i[1]], P[:, i[2]]
        nv = np.cross(b - a, c - a)
        ln = np.linalg.norm(nv)
        if ln < 1e-6:
            continue
        nv = nv / ln
        if abs(nv[2]) < 0.90:
            continue
        d = float(-nv @ a)
        if not (0.85 < abs(d) < 1.20):
            continue
        k = int((np.abs(nv @ P + d) < INLIER_M).sum())
        if k > best[0]:
            best = (k, (nv, d))
    if best[1] is None:
        return None
    nv, d = best[1]
    inl = np.abs(nv @ P + d) < INLIER_M
    Q = P[:, inl]
    cen = Q.mean(axis=1, keepdims=True)
    u, s, _ = np.linalg.svd(Q - cen)
    nv = u[:, 2]
    if nv[2] < 0:
        nv = -nv
    d = float(-nv @ cen.ravel())
    return {
        'pitch': math.degrees(math.atan2(nv[0], nv[2])),
        'roll': math.degrees(math.atan2(nv[1], nv[2])),
        'height': abs(d),
        'points': int(inl.sum()),
        'thick': float(s[2] / math.sqrt(Q.shape[1])),
    }


def current_urdf_pitch():
    """URDF 에 지금 들어 있는 camera_pitch 를 rad 로 읽는다."""
    here = Path(__file__).resolve().parent.parent
    for cand in (here / 'vica_ros2_ws' / 'src' / 'vica_description' / 'urdf'
                 / 'VICA.xacro',):
        try:
            txt = cand.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        m = re.search(r'"camera_pitch"\s+value="(-?[0-9.]+)"', txt)
        if m:
            return float(m.group(1)), cand
    return None, None


def main():
    nframe = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    rclpy.init()
    node = Collector(nframe)
    out = []
    print(f'\n  {CLOUD_TOPIC} 에서 {nframe} 장씩 {rounds} 회 잽니다.')
    print('  앞이 3 m 쯤 트인 평평한 바닥에 세워 두세요.\n')
    for r in range(rounds):
        res = fit_once(node, nframe)
        if res is None:
            print(f'  {r+1}회  바닥 평면을 못 찾았다 (앞이 막혔거나 카메라가 없다)')
            continue
        out.append(res)
        print(f'  {r+1}회  기울기 {res["pitch"]:+6.2f}도   높이 {res["height"]:.3f} m'
              f'   좌우 {res["roll"]:+5.2f}도   평면 {res["points"]:,}점'
              f' 두께 {res["thick"]*1000:.1f} mm')
    rclpy.shutdown()

    if not out:
        print('\n  측정 실패. 카메라(run_d455_cloud.sh)와 robot_state_publisher 를'
              ' 확인하세요.')
        return 1
    pit = np.array([o['pitch'] for o in out])
    hei = np.array([o['height'] for o in out])
    urdf_z = node.camz if node.camz else 1.025
    print('\n  ── 결과 ──')
    print(f'  기울기  {pit.mean():+.2f} 도  (편차 {pit.std():.2f}, {len(out)}회)')
    print(f'  높이    {hei.mean():.3f} m   (URDF 는 {urdf_z:.3f} m,'
          f' 차이 {hei.mean()-urdf_z:+.3f} m)')
    if pit.std() > 0.4:
        print('  주의: 회차마다 흩어진다. 앞이 더 트인 곳에서 다시 재라.')
    print()
    cur, src = current_urdf_pitch()
    delta = math.radians(-pit.mean())
    if cur is None:
        print('  주의: URDF 에서 camera_pitch 를 못 읽었다. 아래는 URDF 가 0 일 때의 값이다.')
        cur = 0.0
    else:
        print(f'  지금 URDF 값   {cur:+.4f} rad ({math.degrees(cur):+.2f} 도)')
        print(f'  잰 잔여 오차   {math.radians(pit.mean()):+.4f} rad'
              f' ({pit.mean():+.2f} 도)')
    new = cur + delta
    print()
    print('  URDF 에 넣을 값 (vica_description/urdf/VICA.xacro)')
    print(f'    <xacro:property name="camera_pitch" value="{new:.4f}" />'
          f'   <!-- {abs(math.degrees(new)):.1f} 도,'
          f' {"아래로" if new > 0 else "위로"} -->')
    print()
    print('  계약 시험도 함께 (vica_nav2/test/test_depth_voxel_contract.py)')
    print(f'    CAMERA_PITCH_DEG = {math.degrees(new):.2f}')
    if abs(pit.mean()) < 0.5:
        print()
        print('  잔여 오차가 0.5도 안이다. 지금 값을 그대로 둬도 된다.')
    print()
    print('  높이 차이가 3 cm 를 넘으면 camera_z 도 다시 본다'
          f'  (지금 {abs(hei.mean()-urdf_z)*100:.1f} cm)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
