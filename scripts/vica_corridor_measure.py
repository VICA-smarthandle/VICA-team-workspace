#!/usr/bin/env python3
"""지도에서 통로 폭을 재고, 시험 상수에 넣을 값을 뽑는다.

    python3 scripts/vica_corridor_measure.py                # maps/CURRENT_MAP
    python3 scripts/vica_corridor_measure.py vica_map_0812_1

왜 필요한가 — test_footprint_contract.py 와 test_planner_contract.py 에는 그 건물을
줄자와 지도로 잰 상수가 박혀 있다. 건물이 바뀌면 그 값들이 거짓이 되는데, 시험은
여전히 통과하므로 아무도 눈치채지 못한다. 그러다 실주행에서 드러난다.

무엇을 재는가 — free 셀마다 가장 가까운 벽까지의 거리(여유)를 구한다. 여유가
로봇 내접반경 이상이면 로봇 중심이 거기 설 수 있고, 통로 폭은 여유의 2배다.

미탐색(unknown)은 벽으로 친다. Nav2 global_costmap 도 기본적으로 그렇게 보고,
무엇보다 로봇이 가 본 적 없는 곳을 free 로 세면 통로가 실제보다 넓게 나온다.

거리 변환은 직접 구현한다. 이 장비의 scipy·cv2 는 numpy 2.x 와 ABI 가 맞지 않아
import 부터 실패하고, numpy 를 내리는 것은 ROS 전체를 건드리는 일이라 하지 않는다.
Felzenszwalb & Huttenlocher 의 정확한 EDT 이며 근사가 아니다. 자체 검증이 붙어 있다.
"""
import os
import sys
from pathlib import Path

import numpy as np
import yaml
from PIL import Image

# 사람을 반경 25 cm 원으로 본다(어깨너비 50 cm). 뒤따르는 안내 대상이다.
HUMAN_R = 0.25


# ---------------------------------------------------------------------------
# 거리 변환
# ---------------------------------------------------------------------------
def _edt1d(f):
    """1차원 제곱거리 변환. 아래 포물선 포락선을 훑는다."""
    n = len(f)
    d = np.empty(n)
    v = np.zeros(n, dtype=np.int64)
    z = np.empty(n + 1)
    k = 0
    z[0], z[1] = -np.inf, np.inf
    for q in range(1, n):
        s = ((f[q] + q * q) - (f[v[k]] + v[k] * v[k])) / (2.0 * q - 2.0 * v[k])
        while s <= z[k]:
            k -= 1
            s = ((f[q] + q * q) - (f[v[k]] + v[k] * v[k])) / (2.0 * q - 2.0 * v[k])
        k += 1
        v[k], z[k], z[k + 1] = q, s, np.inf
    k = 0
    for q in range(n):
        while z[k + 1] < q:
            k += 1
        d[q] = (q - v[k]) ** 2 + f[v[k]]
    return d


def edt(mask):
    """mask=True 인 곳에서 mask=False 인 가장 가까운 곳까지의 거리(픽셀)."""
    f = np.where(mask, 1e12, 0.0)
    out = np.empty_like(f)
    for i in range(f.shape[0]):
        out[i] = _edt1d(f[i])
    for j in range(f.shape[1]):
        out[:, j] = _edt1d(out[:, j])
    return np.sqrt(out)


def _self_check():
    """구현이 맞는지 매 실행마다 확인한다. 틀린 거리로 상수를 바꾸면 더 위험하다."""
    t = np.ones((5, 7), dtype=bool)
    t[0, :] = False
    assert np.allclose(edt(t)[:, 3], [0, 1, 2, 3, 4]), 'EDT 직선 거리가 틀렸다'
    t2 = np.ones((7, 7), dtype=bool)
    t2[3, 3] = False
    assert abs(edt(t2)[0, 0] - np.hypot(3, 3)) < 1e-9, 'EDT 대각 거리가 틀렸다'


# ---------------------------------------------------------------------------
# footprint
# ---------------------------------------------------------------------------
def robot_radii(ws):
    """nav2_params.yaml 에서 내접·외접반경을 계산한다.

    여기서 값을 다시 적지 않는다. 설정과 이 스크립트가 어긋나면 측정이 거짓이 된다.
    """
    cfg = ws / 'src' / 'vica_nav2' / 'config' / 'nav2_params.yaml'
    params = yaml.safe_load(cfg.read_text(encoding='utf-8'))
    cm = params['local_costmap']['local_costmap']['ros__parameters']
    poly = np.array(yaml.safe_load(cm['footprint']), dtype=float)
    pad = float(cm['footprint_padding'])

    # costmap_2d 의 padFootprint 와 같다 — 각 좌표에 부호대로 더한다.
    poly[:, 0] += np.sign(poly[:, 0]) * pad
    poly[:, 1] += np.sign(poly[:, 1]) * pad

    outer = float(np.hypot(poly[:, 0], poly[:, 1]).max())
    inner = 1e9
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        ab = b - a
        t = float(np.clip(-a @ ab / (ab @ ab), 0, 1))
        inner = min(inner, float(np.hypot(*(a + t * ab))))
    return inner, outer, pad


# ---------------------------------------------------------------------------
def main():
    ws = Path(os.environ.get('VICA_ROS_WS', '')) if os.environ.get('VICA_ROS_WS') \
        else Path(__file__).resolve().parents[1] / 'vica_ros2_ws'
    maps = ws / 'maps'

    name = sys.argv[1] if len(sys.argv) > 1 else None
    if not name:
        current = maps / 'CURRENT_MAP'
        if not current.exists():
            print(f'지도 이름을 주거나 {current} 를 만드세요.')
            return 1
        name = current.read_text().strip()
    name = name.replace('.yaml', '').replace('.pgm', '')

    yaml_path, pgm_path = maps / f'{name}.yaml', maps / f'{name}.pgm'
    if not yaml_path.exists() or not pgm_path.exists():
        print(f'지도를 찾을 수 없습니다: {yaml_path}')
        return 1

    _self_check()
    inner, outer, pad = robot_radii(ws)

    meta = yaml.safe_load(yaml_path.read_text())
    res = float(meta['resolution'])
    img = np.array(Image.open(pgm_path))

    free = img > 250          # trinary 모드에서 free 는 254
    occupied = img < 100
    unknown = ~free & ~occupied

    clearance = edt(~(occupied | unknown)) * res
    c = clearance[free]
    cell = res * res

    print(f'=== 지도 {name} ===')
    print(f'  {img.shape[1]} x {img.shape[0]} px, 해상도 {res} m/px')
    print(f'  free {free.sum() * cell:.1f} m2   점유 {occupied.sum() * cell:.1f} m2')
    print(f'  로봇 내접 {inner:.3f} m · 외접 {outer:.3f} m (padding {pad})')
    print()

    print('통로 여유 분포 (폭은 2배)')
    for p in (5, 10, 25, 50, 75, 90):
        v = np.percentile(c, p)
        print(f'   {p:2d}%tile   여유 {v:.3f} m   폭 {2 * v:.2f} m')
    print()

    total = free.sum()
    print('면적')
    for label, r in (('로봇이 설 수 있는 곳', inner),
                     ('제자리 회전 가능한 곳', outer),
                     ('로봇 옆에 사람이 설 수 있는 곳', inner + 2 * HUMAN_R)):
        n = int((c >= r).sum())
        print(f'   {label:30s} {n * cell:6.1f} m2  ({100 * n / total:4.1f} %)')
    stuck = 100 * ((c >= inner).sum() - (c >= outer).sum()) / total
    print(f'   {"들어가면 제자리 회전을 못 하는 곳":30s} {stuck:20.1f} %')
    print()

    # 넓은 방 한가운데가 분포를 끌어올린다. 로봇이 실제로 설 수 있는 곳만 통로로 센다.
    drivable = c[c >= inner]
    if len(drivable) == 0:
        print('로봇이 설 수 있는 자리가 없습니다. 지도나 footprint 를 확인하세요.')
        return 1
    median = float(np.percentile(drivable, 50))

    print('─' * 62)
    print('시험 상수에 넣을 값')
    print('─' * 62)
    print(f'  src/vica_nav2/test/test_footprint_contract.py')
    print(f'      CORRIDOR_HALF_WIDTH_MEDIAN = {median:.3f}')
    print()
    print('  이 값은 inflation_radius 의 상한이다. 넘으면 협착부가 아니라 일반')
    print('  통로에서도 비용 0 인 중앙선이 사라져 우회가 아니라 전면 정체가 된다.')
    print()
    print('  아래 둘은 이 스크립트로 못 구한다. 사람이 정해야 한다:')
    print('      MEASURED_NARROWEST_CORRIDOR  (test_planner_contract.py)')
    print('        로봇이 "반드시 지나야 하는" 가장 좁은 곳의 폭이다. 지도 통계는')
    print('        좁은 데가 어딘가 있다는 것만 알려주지, 그곳을 꼭 지나야 하는지는')
    print('        모른다. 안내 경로를 따라 걸으며 줄자로 재는 것이 맞다.')
    print(f'        참고: 이 지도에서 로봇이 다닐 수 있는 곳의 10%tile 폭은 '
          f'{2 * np.percentile(drivable, 10):.2f} m 다.')
    print('      SCAN_VALID_RETURNS  (test_amcl_contract.py)')
    print('        로봇을 켜고: ros2 topic echo /scan --once --full-length')
    print('        ranges 중 inf 가 아닌 개수. 넓은 홀일수록 적다.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
