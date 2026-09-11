#!/usr/bin/env python3
"""주행 회차를 같은 자로 재서 나란히 놓는다."""

import glob
import math
import os
import statistics
import sys

try:
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
except ImportError:
    sys.exit('ROS 2 환경이 필요하다:  source /opt/ros/humble/setup.bash')

BAG_DIR = os.path.expanduser('~/vica_data/bags')
CPU_DIR = os.path.expanduser('~/vica_data/cpu')

VX_STOP = 0.01
WZ_TURN = 0.05
MOVING = 0.01

ROWS = [
    ('duration_s',        '주행 시간',              'info', 's'),
    ('goals_ok',          'Goal 성공',              'up',   '회'),
    ('goals_fail',        'Goal 실패·취소',         'down', '회'),
    ('vx_max',            '최고 속도',              'info', 'm/s'),
    ('vx_corner',         '코너 최소 속도(p5)',     'info', 'm/s'),
    ('vx_peaks',          '속도 봉우리 수',         'info', '개'),
    ('spin_count',        '제자리 회전',            'down', '회'),
    ('spin_time_s',       '제자리 회전 시간',       'down', 's'),
    ('stop_count',        '정지 구간',              'down', '회'),
    ('stop_time_s',       '정지 시간 합',           'down', 's'),
    ('stop_max_s',        '최장 정지',              'down', 's'),
    ('arrival_count',     '목적지 도착',            'info', '회'),
    ('arrival_wait_mean', '도착 후 대기 평균',      'down', 's'),
    ('arrival_wait_max',  '도착 후 대기 최대',      'down', 's'),
    ('scan_min_m',        '벽 최소 이격',           'up',   'm'),
    ('path_ratio',        '이동거리 ÷ 직선거리',    'down', '배'),
    ('missed_rate',       '제어주기 놓침',          'down', '회'),
    ('collision_stop',    'collision_monitor 발동', 'down', '회'),
    ('lethal',            'lethal space',           'down', '회'),
    ('no_valid',          'No valid trajectories',  'down', '회'),
    ('out_of_bounds',     '지도 밖 발산',           'down', '회'),
    ('cpu_total_avg',     'CPU 전체 평균',          'down', '%'),
    ('cpu_ctrl_avg',      'controller CPU 평균',    'down', '%'),
    ('cpu_amcl_avg',      'amcl CPU 평균',          'down', '%'),
    ('cpu_nvblox_avg',    'nvblox CPU 평균',        'down', '%'),
    ('cpu_ekf_avg',       'ekf_node CPU 평균',      'down', '%'),
    ('cpu_enc_avg',       'encoder CPU 평균',       'down', '%'),
    ('load1_max',         'load average 최대',      'down', ''),
]

CPU_COLS = {
    'controller_serv': 'cpu_ctrl_avg',
    'amcl': 'cpu_amcl_avg',
    'nvblox_node': 'cpu_nvblox_avg',
    'ekf_node': 'cpu_ekf_avg',
    'encoder_feedbac': 'cpu_enc_avg',
}


def read_bag(path, trim_tail=0.0):
    """bag 을 한 번만 훑어 필요한 토픽을 모은다."""
    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=path, storage_id='sqlite3'),
        rosbag2_py.ConverterOptions('', ''),
    )
    types = {t.name: t.type for t in reader.get_all_topics_and_types()}
    want = {
        '/cmd_vel_safe', '/amcl_pose', '/scan', '/rosout',
        '/navigate_to_pose/_action/status',
    }
    out = {k: ([] if k in types else None) for k in want}
    cache = {}
    while reader.has_next():
        topic, data, stamp = reader.read_next()
        if topic not in want:
            continue
        if topic not in cache:
            cache[topic] = get_message(types[topic])
        out[topic].append((stamp * 1e-9, deserialize_message(data, cache[topic])))

    if trim_tail > 0:
        last = max((s[-1][0] for s in out.values() if s), default=None)
        if last is not None:
            cutoff = last - trim_tail
            for topic, samples in out.items():
                if samples is not None:
                    out[topic] = [s for s in samples if s[0] <= cutoff]
    return out


def twist_of(msg):
    """Twist 와 TwistStamped 를 함께 받는다."""
    return msg.twist if hasattr(msg, 'twist') else msg


def analyse_motion(samples):
    """/cmd_vel_safe 에서 속도·정지·제자리 회전을 뽑는다."""
    r = {'vx_max': 0.0, 'vx_corner': 0.0, 'vx_peaks': 0,
         'spin_count': 0, 'spin_time_s': 0.0,
         'stop_count': 0, 'stop_time_s': 0.0, 'stop_max_s': 0.0,
         'hist': {}}
    if len(samples) < 2:
        return r

    moving = []
    prev_state, run_start, run_end = None, None, None
    for i, (t, msg) in enumerate(samples):
        tw = twist_of(msg)
        vx, wz = abs(tw.linear.x), abs(tw.angular.z)
        if vx > MOVING:
            moving.append(vx)

        if vx < VX_STOP and wz > WZ_TURN:
            state = 'spin'
        elif vx < VX_STOP and wz <= WZ_TURN:
            state = 'stop'
        else:
            state = 'drive'

        if state != prev_state:
            if prev_state in ('spin', 'stop'):
                dur = run_end - run_start
                if prev_state == 'spin':
                    r['spin_count'] += 1
                    r['spin_time_s'] += dur
                else:
                    r['stop_count'] += 1
                    r['stop_time_s'] += dur
                    r['stop_max_s'] = max(r['stop_max_s'], dur)
            run_start = t
            prev_state = state
        run_end = t

    if prev_state in ('spin', 'stop') and run_start is not None:
        dur = run_end - run_start
        if prev_state == 'spin':
            r['spin_count'] += 1
            r['spin_time_s'] += dur
        else:
            r['stop_count'] += 1
            r['stop_time_s'] += dur
            r['stop_max_s'] = max(r['stop_max_s'], dur)

    if moving:
        moving.sort()
        r['vx_max'] = moving[-1]
        r['vx_corner'] = moving[max(0, int(len(moving) * 0.05))]
        for v in moving:
            b = int(v * 10)
            r['hist'][b] = r['hist'].get(b, 0) + 1
        r['vx_peaks'] = sum(1 for n in r['hist'].values() if n >= len(moving) * 0.10)
    return r


def analyse_pose(samples):
    """이동거리 ÷ 직선거리. 우회 정도(지표 7)."""
    pts = [(m.pose.pose.position.x, m.pose.pose.position.y) for _, m in samples]
    if len(pts) < 2:
        return {'path_ratio': 0.0, 'path_len_m': 0.0}
    total = sum(math.dist(pts[i - 1], pts[i]) for i in range(1, len(pts)))
    straight = math.dist(pts[0], pts[-1])
    return {'path_ratio': total / straight if straight > 0.1 else 0.0,
            'path_len_m': total}


def analyse_scan(samples):
    """벽 최소 이격. inf·nan·range_min 미만을 버린다."""
    best = float('inf')
    for _, m in samples:
        lo = m.range_min
        for d in m.ranges:
            if lo < d < best and math.isfinite(d):
                best = d
    return {'scan_min_m': 0.0 if best == float('inf') else best}


def analyse_rosout(samples):
    """로그 문자열을 센다. ~/.ros/log 는 덮이지만 bag 은 남는다."""
    keys = {
        'missed_rate': 'missed its desired rate',
        'collision_stop': 'Robot to stop due to',
        'lethal': 'lethal space',
        'no_valid': 'No valid trajectories',
        'out_of_bounds': 'out of map bounds',
    }
    r = {k: 0 for k in keys}
    for _, m in samples:
        msg = m.msg
        for k, needle in keys.items():
            if needle in msg:
                r[k] += 1
    return r


def analyse_arrival_wait(rosout):
    """목적지에 닿은 뒤 다음 주행이 시작될 때까지 로봇이 서 있는 시간."""
    marks = []
    for t, m in rosout:
        msg = m.msg
        if 'Reached the goal' in msg or 'Goal succeeded' in msg:
            marks.append((t, 'reach'))
        elif 'Navigating to goal' in msg or 'Received a goal' in msg:
            marks.append((t, 'start'))

    waits, pending = [], None
    for t, kind in marks:
        if kind == 'reach':
            if pending is None:
                pending = t
        elif pending is not None:
            gap = t - pending
            if gap > 0.5:
                waits.append(gap)
            pending = None

    if not waits:
        return {'arrival_count': len(waits)}
    return {'arrival_count': len(waits),
            'arrival_wait_mean': statistics.mean(waits),
            'arrival_wait_max': max(waits)}


def analyse_status(samples):
    """action status. 4=SUCCEEDED, 5=ABORTED, 6=CANCELED."""
    seen = {}
    for _, m in samples:
        for s in m.status_list:
            seen[bytes(s.goal_info.goal_id.uuid)] = s.status
    return {'goals_ok': sum(1 for v in seen.values() if v == 4),
            'goals_fail': sum(1 for v in seen.values() if v in (5, 6))}


def analyse_cpu(name, trim_tail=0.0):
    """같은 이름의 CPU csv 가 있으면 함께 읽는다. 기록 간격은 1초다."""
    import csv
    path = os.path.join(CPU_DIR, name + '.csv')
    if not os.path.exists(path):
        return {}
    rows = list(csv.DictReader(open(path)))
    if trim_tail > 0:
        rows = rows[:-int(trim_tail)] if int(trim_tail) < len(rows) else []
    if not rows:
        return {}

    def col(k):
        v = [float(r[k]) for r in rows if r.get(k) not in (None, '')]
        return v or [0.0]

    r = {'cpu_total_avg': statistics.mean(col('cpu_total_pct')),
         'load1_max': max(col('load1'))}
    for column, key in CPU_COLS.items():
        if column in rows[0]:
            r[key] = statistics.mean(col(column))
    skip = {'time', 'load1', 'cpu_total_pct', 'mem_used_gb'}
    procs = []
    for n in rows[0]:
        if n in skip:
            continue
        v = col(n)
        if max(v) > 0:
            procs.append((statistics.mean(v), max(v), n))
    r['cpu_procs'] = sorted(procs, reverse=True)
    return r


def measure(path, trim_tail=0.0):
    name = os.path.basename(path.rstrip('/'))
    bag = read_bag(path, trim_tail)
    r = {'name': name, 'missing': [t for t, v in bag.items() if v is None]}
    cmd = bag['/cmd_vel_safe'] or []
    r['duration_s'] = (cmd[-1][0] - cmd[0][0]) if len(cmd) > 1 else 0.0
    r.update(analyse_motion(cmd))
    if bag['/amcl_pose'] is not None:
        r.update(analyse_pose(bag['/amcl_pose']))
    if bag['/scan'] is not None:
        r.update(analyse_scan(bag['/scan']))
    if bag['/rosout'] is not None:
        r.update(analyse_rosout(bag['/rosout']))
        r.update(analyse_arrival_wait(bag['/rosout']))
    if bag['/navigate_to_pose/_action/status'] is not None:
        r.update(analyse_status(bag['/navigate_to_pose/_action/status']))
    r.update(analyse_cpu(name, trim_tail))
    return r


def fmt(v):
    if v is None:
        return '—'
    if isinstance(v, float):
        return f'{v:.2f}' if abs(v) < 100 else f'{v:.0f}'
    return str(v)


def verdict(direction, a, b):
    """b 가 a 보다 나아졌는지. 판정을 눈대중으로 하지 않게 한다."""
    if direction == 'info' or a is None or b is None:
        return ''
    if abs(a - b) < 1e-9:
        return '='
    better = (b < a) if direction == 'down' else (b > a)
    return '좋아짐' if better else '나빠짐'


def show_hist(runs):
    print('\n속도 분포 (0.1 m/s 칸, 이동 중 표본만)')
    print('  곡률 감속이 걸리면 직선 0.5 와 코너 0.28 근처에 봉우리가 둘 생긴다.')
    for r in runs:
        hist = r.get('hist') or {}
        if not hist:
            continue
        total = sum(hist.values())
        print(f'\n  [{r["name"]}]')
        for b in sorted(hist):
            n = hist[b]
            bar = '#' * min(50, int(n / total * 100))
            print(f'    {b/10:.1f}~{(b+1)/10:.1f}  {n:6d}  {bar}')


def show_cpu(runs):
    """프로세스별 CPU 점유. 코어 1개 = 100 %."""
    have = [r for r in runs if r.get('cpu_procs')]
    if not have:
        print('\nCPU csv 가 없다. 회차 이름을 bag 과 같게 두면 함께 읽는다:')
        print('  bash scripts/vica_cpu_record.sh <bag 과 같은 이름>')
        return
    print('\nCPU 점유 (평균 / 최대, 코어 1개 = 100 %)')
    print('  경합 상대를 함께 봐야 해석이 된다. 순위가 바뀐 것이 곧 원인 후보다.')
    for r in have:
        print(f'\n  [{r["name"]}]')
        for avg, mx, n in r['cpu_procs'][:10]:
            bar = '#' * min(40, int(avg / 5))
            print(f'    {n:18} {avg:6.1f} / {mx:6.1f}  {bar}')


def main():
    args = sys.argv[1:]
    trim_tail = 0.0
    if '--trim-tail' in args:
        i = args.index('--trim-tail')
        trim_tail = float(args[i + 1])
        del args[i:i + 2]
    if not args:
        args = sorted(glob.glob(os.path.join(BAG_DIR, '*')),
                      key=os.path.getmtime)[-2:]
        if not args:
            sys.exit(f'{BAG_DIR} 에 회차가 없다.')
    runs = [measure(p, trim_tail) for p in args]
    if trim_tail:
        print(f'끝에서 {trim_tail:.0f} 초를 잘라내고 잰다.\n')

    w = max(len(n) for _, n, _, _ in ROWS) + 2
    head = f'{"지표":<{w}}' + ''.join(f'{r["name"]:>16}' for r in runs)
    if len(runs) == 2:
        head += '   판정'
    print(head)
    print('-' * len(head))
    for key, label, direction, unit in ROWS:
        vals = [r.get(key) for r in runs]
        if all(v is None for v in vals):
            continue
        line = f'{label:<{w}}' + ''.join(f'{fmt(v):>16}' for v in vals)
        if len(runs) == 2:
            line += f'   {verdict(direction, vals[0], vals[1])}'
        if unit:
            line += f'  [{unit}]'
        print(line)

    show_hist(runs)
    show_cpu(runs)

    for r in runs:
        if r.get('missing'):
            print(f'\n[주의] {r["name"]}: bag 에 없는 토픽 {", ".join(r["missing"])}')
            print('       해당 지표는 0 이 아니라 — 로 비어 있다. 측정되지 않았다는 뜻이다.')
        ratio = r.get('path_ratio') or 0
        if ratio > 10:
            print(f'\n[무효 의심] {r["name"]}: 이동거리가 직선거리의 {ratio:.0f}배다.')
            print('       위치추정이 발산했을 때 나오는 값이다(2026-08-12: 오도메트리')
            print('       중복 발행). 이 회차의 나머지 지표는 판정에 쓰지 않는다.')

    print('\n최종 판정은 지표 10(사용자 체감)이다. 위 숫자는 참고치다.')
    print('  — 코너에서 끌려갔는가 / 다음 동작이 예측됐는가 /')
    print('    멈춘 이유를 알 수 있었는가 / 두 번 걸었을 때 같은 느낌이었는가')


if __name__ == '__main__':
    main()
