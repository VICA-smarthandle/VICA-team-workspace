#!/usr/bin/env python3
"""두 회차의 AMCL 측정을 나란히 놓고 본다.

    python3 vica_amcl_compare.py ~/vica_amcl_logs/before_0812_1930 \
                                 ~/vica_amcl_logs/after_0812_2010

인자를 주지 않으면 ~/vica_amcl_logs 의 최근 두 회차를 자동으로 고른다.

판정을 사람이 눈대중으로 하지 않게 하려고 만들었다. 표만 보고 결론을 내릴 수
있어야 한다. 그래서 각 항목에 "어느 쪽이 좋은가"를 미리 박아 두었다.
"""

import glob
import json
import os
import sys

# (키, 표시이름, 방향, 단위)
#   방향 down = 작을수록 좋다,  up = 클수록 좋다,  info = 판정 대상 아님
ROWS = [
    ('effective_update_min_d', '실효 update_min_d', 'info', 'm'),
    ('updates_per_meter', '1 m 당 갱신 횟수', 'up', '회'),
    ('gap_moving_max_s', '최악 무갱신(이동 중)', 'down', 's'),
    ('gap_moving_p95_s', '무갱신 p95', 'down', 's'),
    ('gap_moving_median_s', '무갱신 중앙값', 'down', 's'),
    ('blind_over_2s_count', '2 s 넘는 무갱신 구간', 'down', '개'),
    ('blind_total_s', '무갱신 시간 합계', 'down', 's'),
    ('correction_mean_m', '갱신당 평균 보정량', 'down', 'm'),
    ('correction_max_m', '최대 보정량', 'down', 'm'),
    ('spin_invocations', 'Spin 복구 호출', 'down', '회'),
    ('wait_invocations', 'Wait 복구 호출', 'down', '회'),
    ('clearing_invocations', 'Costmap 초기화', 'down', '회'),
    ('amcl_updates', '총 갱신 횟수', 'info', '회'),
    ('moving_time_s', '이동 시간', 'info', 's'),
    ('odom_distance_m', '이동 거리', 'info', 'm'),
]

GREEN, RED, DIM, OFF = '\033[32m', '\033[31m', '\033[2m', '\033[0m'


def load(d):
    with open(os.path.join(d, 'summary.json')) as f:
        return json.load(f)


def fmt(v):
    if v is None:
        return '-'
    return f'{v:g}' if isinstance(v, (int, float)) else str(v)


def main():
    if len(sys.argv) >= 3:
        dirs = [sys.argv[1], sys.argv[2]]
    else:
        found = sorted(glob.glob(os.path.expanduser('~/vica_amcl_logs/*/summary.json')))
        if len(found) < 2:
            print('회차가 두 개 미만이다. 경로를 직접 주거나 한 번 더 재라.')
            print(f'찾은 것: {len(found)}개')
            return 1
        dirs = [os.path.dirname(p) for p in found[-2:]]

    a, b = load(dirs[0]), load(dirs[1])
    na, nb = a['label'], b['label']

    print()
    print(f'  A = {na:12s} {os.path.basename(dirs[0])}')
    print(f'  B = {nb:12s} {os.path.basename(dirs[1])}')
    print()

    # 오도메트리가 튄 회차는 아래 숫자가 전부 허구다. 표를 보기 전에 막는다.
    for name, s in ((na, a), (nb, b)):
        jumps = s.get('odom_jumps')
        if jumps:
            print(f'  {RED}[{name}] 오도메트리가 {jumps}회 튀었다'
                  f"(최대 {s.get('odom_jump_max_m')} m). "
                  f'이 회차는 판정에 쓸 수 없다.{OFF}')
        elif jumps is None:
            print(f'  {DIM}[{name}] 오도메트리 건전성 기록이 없는 옛 회차다.{OFF}')

    # 파라미터가 정말 달랐는지부터 본다. 같으면 아래 표는 볼 필요가 없다.
    pa, pb = a.get('amcl_params') or {}, b.get('amcl_params') or {}
    changed = [k for k in set(pa) | set(pb) if pa.get(k) != pb.get(k)]
    print('  ─ AMCL 파라미터 ' + '─' * 44)
    if not changed:
        print(f'  {RED}두 회차의 파라미터가 같다. 비교가 성립하지 않는다.{OFF}')
    for k in sorted(changed):
        print(f'  {k:22s} {fmt(pa.get(k)):>12s}  ->  {fmt(pb.get(k)):>12s}')
    print()

    print('  ─ 측정 ' + '─' * 53)
    print(f'  {"":26s} {"A":>12s} {"B":>12s}   {"변화":>10s}')
    for key, name, direction, unit in ROWS:
        va, vb = a.get(key), b.get(key)
        line = f'  {name:26s} {fmt(va):>12s} {fmt(vb):>12s}'
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)) and va:
            ratio = vb / va
            mark = f'{ratio:>9.2f}x'
            if direction == 'up':
                col = GREEN if ratio > 1.05 else (RED if ratio < 0.95 else DIM)
            elif direction == 'down':
                col = GREEN if ratio < 0.95 else (RED if ratio > 1.05 else DIM)
            else:
                col = DIM
            line += f'   {col}{mark}{OFF}'
        print(line)
    print()

    # 결론을 한 줄로 뽑는다. 표를 잘못 읽는 것을 막는다.
    print('  ─ 판정 ' + '─' * 53)
    worst_a, worst_b = a.get('gap_moving_max_s'), b.get('gap_moving_max_s')
    upm_a, upm_b = a.get('updates_per_meter'), b.get('updates_per_meter')

    if isinstance(upm_a, float) and isinstance(upm_b, float) and upm_b > upm_a * 1.3:
        print(f'  {GREEN}갱신 빈도가 실제로 올랐다{OFF} '
              f'({upm_a:.1f} -> {upm_b:.1f} 회/m). 설정이 먹혔다.')
    else:
        print(f'  {RED}갱신 빈도가 뚜렷이 오르지 않았다.{OFF} '
              f'파라미터가 반영됐는지부터 확인하라.')

    if isinstance(worst_a, float) and isinstance(worst_b, float):
        if worst_b < worst_a * 0.7:
            print(f'  {GREEN}눈 감는 최악 구간이 줄었다{OFF} '
                  f'({worst_a:.1f}s -> {worst_b:.1f}s). NAV2-B1 1 단계의 목표다.')
        elif worst_b > worst_a * 1.2:
            print(f'  {RED}오히려 늘었다{OFF} ({worst_a:.1f}s -> {worst_b:.1f}s). '
                  f'CPU 포화를 의심하라.')
        else:
            print(f'  차이가 뚜렷하지 않다 ({worst_a:.1f}s -> {worst_b:.1f}s). '
                  f'같은 경로를 달렸는지 확인하라.')

    da, db = a.get('odom_distance_m') or 0, b.get('odom_distance_m') or 0
    if da and db and not (0.6 < db / da < 1.7):
        print(f'  {RED}주행 거리가 많이 다르다{OFF} ({da:.0f}m vs {db:.0f}m). '
              f'절대 횟수 대신 "1 m 당" 항목만 믿어라.')

    print()
    print(f'  {DIM}제어주기 결손은 따로 센다:{OFF}')
    print('    grep -c "missed its desired rate" ~/.ros/log/*/controller_server*.log')
    print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
