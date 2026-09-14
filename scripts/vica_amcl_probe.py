#!/usr/bin/env python3
"""AMCL 이 얼마나 자주 눈을 뜨는지 재는 진단 노드 (NAV2-B1 before/after 비교용).

왜 이 도구가 필요한가 — update_min_d/a 변경의 판정 기준은 "완주했는가"가 아니다.
완주는 그날의 사람·짐·조명에 따라 흔들린다. 봐야 하는 것은 AMCL 이 위치를 다시
계산하는 간격이고, 그건 눈으로 볼 수 없다.

핵심 지표 두 가지:

  gap_dist_m 의 중앙값 = 실효 update_min_d
      AMCL 은 로봇이 update_min_d 만큼 움직여야 필터를 갱신한다. 갱신과 갱신
      사이의 실제 이동거리를 재면 설정값이 정말 먹혔는지가 숫자로 나온다.
      0.25 -> 0.10 이면 이 값도 그만큼 내려가야 한다. 안 내려갔다면 파라미터가
      반영되지 않은 것이므로, 그 회차의 다른 모든 숫자는 무의미하다.

  gap_moving_s 의 최댓값 = 최악의 눈 감은 시간
      정지 중에는 갱신이 없는 게 정상이다. 그래서 벽시계가 아니라 "움직이는
      중이었던 시간"만 센다. 좁은 곳에서 로봇이 조금씩 더듬을 때 이 값이 커진다.
      NAV2-B1 이 고치려는 것이 정확히 그 구간이다.

사용법:
    python3 vica_amcl_probe.py <라벨>            # 예: before / after
    Ctrl+C 로 끝내면 요약을 출력하고 JSON·CSV 를 남긴다.

로그 위치: ~/vica_amcl_logs/<라벨>_<시각>/
"""

import csv
import json
import math
import os
import signal
import sys
import time
from datetime import datetime

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import Odometry
from nav2_msgs.msg import BehaviorTreeLog
from rcl_interfaces.srv import GetParameters
from rclpy.node import Node

# 이동 판정 문턱. EKF 가 내는 /odom 의 twist 를 본다.
# 0.02 m/s 는 정지한 로봇의 엔코더 잡음보다 크고, 가장 느린 접근 속도보다 작다.
MOVING_LIN = 0.02
MOVING_ANG = 0.05

# 이 시간(이동 중 기준)을 넘긴 무갱신 구간을 "눈 감은 구간"으로 센다.
BLIND_THRESHOLD_S = 2.0

# 한 메시지 사이에 이만큼 넘게 움직였으면 오도메트리가 깨진 것이다.
# 상한 속도가 0.408 m/s 이고 /odom 은 30 Hz 이므로 정상값은 0.014 m 언저리다.
# 2026-08-12 무효 회차에서는 한 메시지에 21.3 m 가 찍혔다.
ODOM_JUMP_M = 0.5

# 발행자가 둘 이상이면 노드가 중복 실행된 것이다. 2026-08-12 회차가 이것 때문에
# 통째로 무효가 됐다 — encoder_feedback 두 개가 각자의 누적값을 같은 토픽에
# 쏟아서 /wheel/odom 이 (20.32,-5.15) 와 (0,0) 을 번갈아 냈다.
SINGLE_PUBLISHER_TOPICS = ['/odom', '/wheel/odom', '/scan', '/cmd_vel_safe']

# 데이터를 잃지 않기 위한 저장 주기. SIGTERM 을 못 받고 죽어도 여기까지는 남는다.
AUTOSAVE_SEC = 30.0

# CPU 경합 조사(NAV2-B1 2단계). max_beams 를 올리면 AMCL 이 CPU 를 3배 쓰는데,
# Jetson 은 nvblox·STT 와 그 CPU 를 다툰다(2026-07-30 GPU 경합 조사). 제어주기
# 결손만 세면 "누가 먹었는지"를 못 가리므로 프로세스별로 함께 본다.
# /proc/<pid>/comm 은 15자에서 잘리므로 이름도 15자 안이다.
CPU_SAMPLE_SEC = 5.0
WATCHED_PROCS = ['amcl', 'controller_serv', 'planner_server', 'nvblox_node',
                 'cartographer_no', 'rviz2']

# 회차마다 반드시 기록해 둘 AMCL 파라미터. 나중에 비교표의 근거가 된다.
WATCHED_PARAMS = [
    'update_min_d',
    'update_min_a',
    'max_beams',
    'alpha1',
    'alpha2',
    'alpha3',
    'alpha4',
    'laser_model_type',
    'resample_interval',
]


def yaw_of(q):
    """쿼터니언에서 yaw 만 뽑는다. 2D 로봇이라 roll/pitch 는 보지 않는다."""
    siny = 2.0 * (q.w * q.z + q.x * q.y)
    cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny, cosy)


def angdiff(a, b):
    """두 각의 차이를 -pi..pi 로 접는다."""
    return math.atan2(math.sin(a - b), math.cos(a - b))


def _cpu_total():
    """전체 CPU 시간(jiffies)과 그중 놀고 있던 시간을 돌려준다."""
    with open('/proc/stat') as f:
        vals = [int(x) for x in f.readline().split()[1:9]]
    return sum(vals), vals[3] + vals[4]     # (전체, idle + iowait)


def _proc_cpu(pid):
    """그 프로세스가 쓴 CPU 시간(jiffies). 죽었으면 None."""
    try:
        with open(f'/proc/{pid}/stat') as f:
            parts = f.read().rsplit(') ', 1)[-1].split()
        return int(parts[11]) + int(parts[12])   # utime + stime
    except (OSError, IndexError, ValueError):
        return None


def find_pids(names):
    """comm 으로 프로세스를 찾는다. 같은 이름이 둘이면 먼저 찾은 것을 쓴다."""
    found = {}
    for entry in os.listdir('/proc'):
        if not entry.isdigit():
            continue
        try:
            with open(f'/proc/{entry}/comm') as f:
                comm = f.read().strip()
        except OSError:
            continue
        if comm in names and comm not in found:
            found[comm] = int(entry)
    return found


def pct(values, p):
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p / 100.0
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    if lo == hi:
        return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


class AmclProbe(Node):

    def __init__(self, label, outdir):
        super().__init__('vica_amcl_probe')
        self.label = label
        self.outdir = outdir

        self.t0 = time.monotonic()
        self.moving_time = 0.0        # 로봇이 실제로 움직인 누적 시간
        self.odom_dist = 0.0          # odom 기준 누적 이동거리
        self.odom_rot = 0.0           # odom 기준 누적 회전량
        self.is_moving = False
        self.last_tick = self.t0

        self.odom_xy = None
        self.odom_yaw = None

        # 직전 amcl_pose 시점의 스냅샷
        self.prev = None              # dict(t, moving_time, dist, rot, x, y, yaw)
        self.rows = []
        self.first_pose_t = None

        # 오도메트리 건전성. 이 값이 0 이 아니면 그 회차는 판정에 쓸 수 없다.
        self.odom_jumps = 0
        self.odom_jump_max = 0.0

        # 복구 동작 집계. Spin 제거 축은 이 숫자로 판정한다.
        self.bt_counts = {}
        self.params = None

        # CPU 경합. max_beams 를 올린 회차에서 "누가 CPU 를 먹었는가"를 가린다.
        self.ncpu = os.cpu_count() or 1
        self.cpu_pids = find_pids(WATCHED_PROCS)
        self.cpu_prev = _cpu_total()
        self.cpu_prev_proc = {n: _proc_cpu(p) for n, p in self.cpu_pids.items()}
        self.cpu_samples = []                    # 전체 사용률 [%]
        self.proc_samples = {n: [] for n in self.cpu_pids}   # 코어 1개 기준 [%]

        # /odom 은 EKF 출력이다. odom -> base_footprint TF 의 유일한 발행자이므로
        # Nav2 가 도는 동안 반드시 살아 있다.
        self.create_subscription(Odometry, '/odom', self.on_odom, 20)
        self.create_subscription(
            PoseWithCovarianceStamped, '/amcl_pose', self.on_amcl, 20)
        # BT 로그는 Nav2 가 복구를 실제로 몇 번 불렀는지 알려주는 유일한 통로다.
        self.create_subscription(
            BehaviorTreeLog, '/behavior_tree_log', self.on_bt_log, 20)

        # AMCL 은 필터를 갱신했을 때만 amcl_pose 를 낸다. 그래서 이 토픽의
        # 도착 간격이 곧 "눈 뜬 간격"이다. 주기 발행이 아니다.
        self.create_timer(0.05, self.tick)
        self.create_timer(15.0, self.report_progress)
        self.create_timer(AUTOSAVE_SEC, self.autosave)
        self.create_timer(CPU_SAMPLE_SEC, self.sample_cpu)

    # -- 수집 -----------------------------------------------------------------

    def on_odom(self, msg):
        v = msg.twist.twist.linear
        w = msg.twist.twist.angular
        self.is_moving = (
            math.hypot(v.x, v.y) > MOVING_LIN or abs(w.z) > MOVING_ANG)

        p = msg.pose.pose.position
        y = yaw_of(msg.pose.pose.orientation)
        if self.odom_xy is not None:
            d = math.hypot(p.x - self.odom_xy[0], p.y - self.odom_xy[1])
            if d < ODOM_JUMP_M:
                self.odom_dist += d
                self.odom_rot += abs(angdiff(y, self.odom_yaw))
            else:
                # 조용히 버리면 안 된다. 2026-08-12 에 이 점프가 21 m 씩 났는데
                # 아무 표시가 없어서 13 분을 달린 뒤에야 회차가 무효임을 알았다.
                self.odom_jumps += 1
                self.odom_jump_max = max(self.odom_jump_max, d)
                # 판정은 5회째에 이미 끝난다. 그 뒤로도 계속 찍으면 다른 로그를
                # 묻어버리므로 드물게만 남긴다.
                if self.odom_jumps <= 3 or self.odom_jumps % 500 == 0:
                    self.get_logger().error(
                        f'오도메트리 점프 {d:.2f} m (누적 {self.odom_jumps}회). '
                        f'노드 중복을 의심하라: ros2 topic info /wheel/odom')
                if self.odom_jumps == 5:
                    self.get_logger().error(
                        '=' * 62 + '\n'
                        '  이 회차는 판정에 쓸 수 없다. 주행을 멈추고 노드 중복을\n'
                        '  잡아라. /odom 과 /wheel/odom 의 발행자가 각각 1개여야 한다.\n'
                        + '=' * 62)
        self.odom_xy = (p.x, p.y)
        self.odom_yaw = y

    def sample_cpu(self):
        """직전 표본 이후의 CPU 점유율을 잰다. 순간값이 아니라 구간 평균이다."""
        total, idle = _cpu_total()
        d_total = total - self.cpu_prev[0]
        d_idle = idle - self.cpu_prev[1]
        if d_total > 0:
            self.cpu_samples.append(100.0 * (d_total - d_idle) / d_total)
        for name, pid in self.cpu_pids.items():
            now = _proc_cpu(pid)
            was = self.cpu_prev_proc.get(name)
            if now is not None and was is not None and d_total > 0:
                # 코어 1개를 100 % 로 본다. top 의 %CPU 와 같은 척도다.
                self.proc_samples[name].append(
                    100.0 * self.ncpu * (now - was) / d_total)
            self.cpu_prev_proc[name] = now
        self.cpu_prev = (total, idle)

    def on_bt_log(self, msg):
        """복구 동작 호출 횟수를 센다. RUNNING 으로 들어간 것만 1회로 본다."""
        for ev in msg.event_log:
            if ev.current_status == 'RUNNING' and ev.previous_status != 'RUNNING':
                self.bt_counts[ev.node_name] = self.bt_counts.get(ev.node_name, 0) + 1

    def tick(self):
        now = time.monotonic()
        if self.is_moving:
            self.moving_time += now - self.last_tick
        self.last_tick = now

    def on_amcl(self, msg):
        now = time.monotonic()
        p = msg.pose.pose.position
        yaw = yaw_of(msg.pose.pose.orientation)
        snap = dict(t=now, moving_time=self.moving_time, dist=self.odom_dist,
                    rot=self.odom_rot, x=p.x, y=p.y, yaw=yaw)

        if self.first_pose_t is None:
            self.first_pose_t = now

        if self.prev is not None:
            gap_dist = snap['dist'] - self.prev['dist']
            map_move = math.hypot(snap['x'] - self.prev['x'],
                                  snap['y'] - self.prev['y'])
            self.rows.append({
                't': round(now - self.t0, 3),
                'gap_wall_s': round(now - self.prev['t'], 3),
                'gap_moving_s': round(snap['moving_time'] - self.prev['moving_time'], 3),
                'gap_dist_m': round(gap_dist, 4),
                'gap_rot_rad': round(snap['rot'] - self.prev['rot'], 4),
                # 같은 구간을 지도는 얼마로, 바퀴는 얼마로 봤는가. 이 차이가
                # 그동안 쌓였다가 한꺼번에 반영된 보정량이다.
                'correction_m': round(abs(map_move - gap_dist), 4),
                'x': round(p.x, 4),
                'y': round(p.y, 4),
                'yaw_deg': round(math.degrees(yaw), 2),
                'moving': int(self.is_moving),
            })
        self.prev = snap

    # -- 출력 -----------------------------------------------------------------

    def report_progress(self):
        el = time.monotonic() - self.t0
        moving_rows = [r for r in self.rows if r['gap_moving_s'] > 0.001]
        med = pct([r['gap_dist_m'] for r in moving_rows], 50)
        worst = max((r['gap_moving_s'] for r in moving_rows), default=0.0)
        bad = f"  \033[31m점프 {self.odom_jumps}회\033[0m" if self.odom_jumps else ""
        spin = sum(v for k, v in self.bt_counts.items() if 'Spin' in k)
        cpu = _mean(self.cpu_samples)
        amcl_cpu = _mean(self.proc_samples.get('amcl', []))
        self.get_logger().info(
            f"[{self.label}] {el:5.0f}s  이동 {self.moving_time:5.0f}s / "
            f"{self.odom_dist:5.1f}m  갱신 {len(self.rows):4d}회  "
            f"실효 update_min_d {med if med is None else round(med, 3)}  "
            f"최악 무갱신 {worst:.1f}s  Spin {spin}  "
            f"CPU {0 if cpu is None else cpu:.0f}% "
            f"(amcl {0 if amcl_cpu is None else amcl_cpu:.0f}%){bad}")

    def summarize(self, params):
        moving_rows = [r for r in self.rows if r['gap_moving_s'] > 0.001]
        gaps = [r['gap_moving_s'] for r in moving_rows]
        dists = [r['gap_dist_m'] for r in moving_rows]
        corrs = [r['correction_m'] for r in moving_rows]
        blind = [g for g in gaps if g >= BLIND_THRESHOLD_S]

        return {
            'label': self.label,
            'started': datetime.now().isoformat(timespec='seconds'),
            # 맨 위에 둔다. 이 둘이 0 이 아니면 아래 숫자는 전부 의미가 없다.
            'odom_jumps': self.odom_jumps,
            'odom_jump_max_m': _r(self.odom_jump_max),
            'valid': self.odom_jumps == 0,
            'amcl_params': params,
            'duration_s': round(time.monotonic() - self.t0, 1),
            'moving_time_s': round(self.moving_time, 1),
            'odom_distance_m': round(self.odom_dist, 2),
            'odom_rotation_rad': round(self.odom_rot, 2),
            'amcl_updates': len(self.rows),
            'updates_while_moving': len(moving_rows),
            # 핵심 1 — 설정이 정말 먹혔는지
            'effective_update_min_d': _r(pct(dists, 50)),
            'gap_dist_mean_m': _r(_mean(dists)),
            # 핵심 2 — 눈 감은 최악 구간
            'gap_moving_max_s': _r(max(gaps, default=0.0)),
            'gap_moving_p95_s': _r(pct(gaps, 95)),
            'gap_moving_median_s': _r(pct(gaps, 50)),
            f'blind_over_{BLIND_THRESHOLD_S:g}s_count': len(blind),
            'blind_total_s': _r(sum(blind)),
            # 이동량으로 정규화 — 주행 길이가 달라도 비교된다
            'updates_per_meter': _r(
                len(moving_rows) / self.odom_dist if self.odom_dist > 0.1 else None),
            'updates_per_moving_min': _r(
                len(moving_rows) / (self.moving_time / 60.0)
                if self.moving_time > 1 else None),
            # 갱신 때마다 얼마나 크게 튀었는가
            'correction_mean_m': _r(_mean(corrs)),
            'correction_max_m': _r(max(corrs, default=0.0)),
            # 복구 축. Spin 을 제거했다면 spin_invocations 가 0 이어야 한다.
            'spin_invocations': sum(
                v for k, v in self.bt_counts.items() if 'Spin' in k),
            'wait_invocations': sum(
                v for k, v in self.bt_counts.items() if 'Wait' in k),
            'clearing_invocations': sum(
                v for k, v in self.bt_counts.items() if 'Clear' in k),
            'bt_nodes': dict(sorted(self.bt_counts.items(),
                                    key=lambda kv: -kv[1])[:12]),
            # CPU 축. max_beams 를 올린 회차는 이 숫자로 대가를 판정한다.
            'cpu_cores': self.ncpu,
            'cpu_mean_pct': _r(_mean(self.cpu_samples)),
            'cpu_p95_pct': _r(pct(self.cpu_samples, 95)),
            'cpu_max_pct': _r(max(self.cpu_samples, default=0.0)),
            'proc_cpu_mean_pct': {
                n: _r(_mean(v)) for n, v in sorted(self.proc_samples.items())
                if v and _mean(v) and _mean(v) > 1.0
            },
        }

    def autosave(self):
        """주기적으로 디스크에 남긴다.

        요약을 종료 신호에서만 저장하면, 세션이 끊기거나 프로세스가 강제로 죽을 때
        회차가 통째로 사라진다. 2026-08-12 에 13 분 주행이 그렇게 없어졌다.
        """
        if self.rows or self.moving_time > 1.0:
            self.save()

    def save(self, params=None):
        os.makedirs(self.outdir, exist_ok=True)
        summary = self.summarize(self.params if params is None else params)

        with open(os.path.join(self.outdir, 'summary.json'), 'w') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        if self.rows:
            with open(os.path.join(self.outdir, 'updates.csv'), 'w', newline='') as f:
                w = csv.DictWriter(f, fieldnames=list(self.rows[0].keys()))
                w.writeheader()
                w.writerows(self.rows)
        return summary


def _mean(v):
    return sum(v) / len(v) if v else None


def _r(v, n=3):
    return round(v, n) if isinstance(v, float) else v


def fetch_params(node, timeout=None):
    """AMCL 이 실제로 들고 있는 값을 읽어 둔다.

    파일을 고쳤든 ros2 param set 을 했든, 그 회차에 진짜로 쓰인 값이 무엇인지는
    노드에게 물어봐야 안다. 이 기록이 없으면 두 회차의 비교가 근거를 잃는다.
    """
    # 기본 10 분. 도구를 시험할 때만 VICA_PROBE_WAIT 로 줄인다.
    if timeout is None:
        timeout = float(os.environ.get('VICA_PROBE_WAIT', '600'))
    cli = node.create_client(GetParameters, '/amcl/get_parameters')
    node.get_logger().info('AMCL 을 기다린다...')
    if not cli.wait_for_service(timeout_sec=timeout):
        node.get_logger().warn(
            'AMCL 파라미터 서비스를 못 찾았다. 값 기록 없이 계속한다.')
        return None
    req = GetParameters.Request()
    req.names = WATCHED_PARAMS
    fut = cli.call_async(req)
    rclpy.spin_until_future_complete(node, fut, timeout_sec=timeout)
    res = fut.result()
    if res is None:
        return None
    out = {}
    for name, val in zip(WATCHED_PARAMS, res.values):
        if val.type == 3:
            out[name] = val.double_value
        elif val.type == 2:
            out[name] = val.integer_value
        elif val.type == 4:
            out[name] = val.string_value
        else:
            out[name] = None
    return out


def check_publishers(node, settle=5.0):
    """토픽마다 발행자가 정확히 하나인지 본다.

    같은 노드가 두 번 뜨면 각자의 누적값을 같은 토픽에 쏟는다. 구독자는 두 값을
    번갈아 받아 위치가 수십 m 씩 튄다. 2026-08-12 회차가 이것 때문에 무효가 됐고,
    13 분을 달린 뒤에야 알았다. discovery 가 자리잡을 시간을 준 뒤 센다.
    """
    end = time.monotonic() + settle
    while time.monotonic() < end:
        rclpy.spin_once(node, timeout_sec=0.1)
    counts = {t: node.count_publishers(t) for t in SINGLE_PUBLISHER_TOPICS}
    return counts, {t: c for t, c in counts.items() if c > 1}


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else 'run'
    stamp = datetime.now().strftime('%m%d_%H%M')
    outdir = os.path.expanduser(f'~/vica_amcl_logs/{label}_{stamp}')

    rclpy.init()
    node = AmclProbe(label, outdir)

    params = fetch_params(node)
    if params:
        node.get_logger().info('=' * 62)
        node.get_logger().info(f'회차 [{label}] 의 AMCL 실제 값:')
        for k in WATCHED_PARAMS:
            node.get_logger().info(f'    {k:20s} = {params.get(k)}')
        node.get_logger().info('=' * 62)
    node.params = params

    counts, dup = check_publishers(node)
    node.get_logger().info('토픽 발행자 수 (각 1개여야 한다):')
    for topic, cnt in counts.items():
        mark = 'OK' if cnt == 1 else ('*** 중복 ***' if cnt > 1 else '없음')
        node.get_logger().info(f'    {topic:16s} {cnt}  {mark}')
    if dup:
        node.get_logger().error(
            '=' * 62 + '\n'
            f'  노드가 중복 실행됐다: {", ".join(dup)}\n'
            '  이대로 달리면 오도메트리가 뒤섞여 회차 전체가 무효가 된다.\n'
            '  중복된 노드를 끄고 다시 시작하라 (ps 로 PID 확인 후 개별 kill).\n'
            '  그래도 진행하려면: VICA_PROBE_FORCE=1 을 붙여 실행한다.\n'
            + '=' * 62)
        if not os.environ.get('VICA_PROBE_FORCE'):
            node.destroy_node()
            rclpy.shutdown()
            sys.exit(2)
    node.get_logger().info(f'기록 시작. 로그: {outdir}')

    stop = {'now': False}

    def on_sigint(_sig, _frm):
        stop['now'] = True

    signal.signal(signal.SIGINT, on_sigint)
    signal.signal(signal.SIGTERM, on_sigint)

    try:
        while rclpy.ok() and not stop['now']:
            rclpy.spin_once(node, timeout_sec=0.2)
    finally:
        summary = node.save(params)
        print('\n' + '=' * 62)
        print(f'  회차 [{label}] 요약')
        print('=' * 62)
        for k, v in summary.items():
            if k == 'amcl_params':
                continue
            print(f'  {k:32s} {v}')
        print('=' * 62)
        if not summary.get('valid'):
            print('  \033[31m이 회차는 판정에 쓸 수 없다.\033[0m '
                  f"오도메트리가 {summary['odom_jumps']}회 튀었다 "
                  f"(최대 {summary['odom_jump_max_m']} m).")
            print('  노드 중복을 잡고 다시 재라.')
        print(f'  저장: {outdir}')
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
