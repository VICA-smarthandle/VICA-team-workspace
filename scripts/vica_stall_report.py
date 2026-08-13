#!/usr/bin/env python3
"""주행이 멈춰 있던 구간을 길이순으로 늘어놓고, 그때 무슨 로그가 났는지 붙인다.

    source /opt/ros/humble/setup.bash
    python3 scripts/vica_stall_report.py ~/vica_data/bags/run1_nospin_0810
    python3 scripts/vica_stall_report.py ~/vica_data/bags/run1 --top 5 --min 3

왜 만들었나
    "마지막 목적지 앞에서 오래 멈춰 있었다"를 사람이 bag 을 뒤져 확인하고
    있었다. 멈춘 시각을 알아도 그때의 로그를 따로 찾아야 하므로 두 번 일한다.
    이 도구는 정지 구간과 그 구간의 로그를 한 화면에 붙여 놓는다.

    vica_drive_compare.py 는 회차 전체를 요약한다. 이쪽은 한 회차 안에서
    '어디가 문제였나'를 본다. 둘은 목적이 다르다.

무엇을 정지로 보나
    `/cmd_vel_safe` 의 vx·wz 가 모두 문턱 아래인 구간이다. 명령이 0 이라는
    뜻이지 바퀴가 안 돌았다는 뜻이 아니다 — 그 둘의 구분은 `/wheel/odom` 이
    한다(knob 0 사고, 2026-08-11).
"""

import math
import os
import sys

try:
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
except ImportError:
    sys.exit('ROS 2 환경이 필요하다:  source /opt/ros/humble/setup.bash')

VX_STOP = 0.01
WZ_TURN = 0.05

# 정지 구간에 붙일 로그. 이유를 말해 주는 것만 고른다.
INTERESTING = [
    'No valid trajectories', 'lethal space', 'Failed to create plan',
    'No valid path', 'Collision Ahead', 'aborting', 'Abort', 'failed',
    'recovery', 'Recovery', 'Wait', 'Clearing', 'Costmap', 'timed out',
    'Goal', 'goal', 'stuck', 'out of map bounds',
]

TOPICS = {'/cmd_vel_safe', '/rosout', '/amcl_pose', '/wheel/odom', '/plan'}


def read_bag(path):
    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=path, storage_id='sqlite3'),
        rosbag2_py.ConverterOptions('', ''),
    )
    types = {t.name: t.type for t in reader.get_all_topics_and_types()}
    out = {k: ([] if k in types else None) for k in TOPICS}
    cache = {}
    while reader.has_next():
        topic, data, stamp = reader.read_next()
        if topic not in TOPICS:
            continue
        if topic not in cache:
            cache[topic] = get_message(types[topic])
        out[topic].append((stamp * 1e-9, deserialize_message(data, cache[topic])))
    return out


def twist_of(msg):
    return msg.twist if hasattr(msg, 'twist') else msg


def find_stalls(samples, min_len):
    """vx·wz 가 모두 0 인 구간을 찾는다."""
    stalls, start, last = [], None, None
    for t, msg in samples:
        tw = twist_of(msg)
        idle = abs(tw.linear.x) < VX_STOP and abs(tw.angular.z) < WZ_TURN
        if idle and start is None:
            start = t
        elif not idle and start is not None:
            if last - start >= min_len:
                stalls.append((start, last))
            start = None
        last = t
    if start is not None and last - start >= min_len:
        stalls.append((start, last))
    return stalls


def pose_at(poses, t):
    if not poses:
        return None
    best = min(poses, key=lambda p: abs(p[0] - t))
    p = best[1].pose.pose.position
    return (p.x, p.y)


def wheel_moved(odom, t0, t1):
    """정지 명령 구간에 바퀴가 실제로 움직였는가. 명령 0 과 구동계 고장을 가른다."""
    seg = [m for t, m in odom if t0 <= t <= t1] if odom else []
    if not seg:
        return None
    return max(abs(m.twist.twist.linear.x) for m in seg)


def logs_in(rosout, t0, t1, limit=8):
    if rosout is None:
        return ['(bag 에 /rosout 이 없다)']
    seen, out = set(), []
    for t, m in rosout:
        if not (t0 - 1.0 <= t <= t1 + 0.5):
            continue
        msg = m.msg.strip()
        if not any(k in msg for k in INTERESTING):
            continue
        key = (m.name, msg[:60])
        if key in seen:
            continue
        seen.add(key)
        out.append(f'{t - t0:+6.1f}s [{m.name}] {msg[:110]}')
        if len(out) >= limit:
            out.append('  … (같은 종류 반복은 접었다)')
            break
    return out or ['(이 구간에 설명이 되는 로그가 없다 — 조용히 서 있었다)']


def main():
    args = sys.argv[1:]
    top, min_len = 5, 3.0
    for flag, setter in (('--top', 'top'), ('--min', 'min')):
        if flag in args:
            i = args.index(flag)
            val = float(args[i + 1])
            if setter == 'top':
                top = int(val)
            else:
                min_len = val
            del args[i:i + 2]
    if not args:
        sys.exit('bag 경로를 달라.')

    path = args[0]
    bag = read_bag(path)
    cmd = bag['/cmd_vel_safe'] or []
    if len(cmd) < 2:
        sys.exit('/cmd_vel_safe 가 비었다.')

    t_start, t_end = cmd[0][0], cmd[-1][0]
    stalls = find_stalls(cmd, min_len)
    total = sum(b - a for a, b in stalls)

    print(f'\n{os.path.basename(path.rstrip("/"))}  ·  주행 {t_end - t_start:.0f} s')
    print(f'{min_len:.0f} 초 이상 멈춘 구간 {len(stalls)} 개 · 합계 {total:.0f} s '
          f'({total / (t_end - t_start) * 100:.0f} %)\n')

    ranked = sorted(stalls, key=lambda s: s[1] - s[0], reverse=True)[:top]
    for a, b in ranked:
        rel_a, rel_b = a - t_start, b - t_start
        tail = ''
        if t_end - b < 5.0:
            tail = '   <-- 기록 끝까지 이어짐'
        print('─' * 72)
        print(f'{rel_a:6.0f}s ~ {rel_b:6.0f}s   길이 {b - a:5.1f} s{tail}')
        pos = pose_at(bag['/amcl_pose'], (a + b) / 2)
        if pos:
            print(f'  위치  x={pos[0]:6.2f}  y={pos[1]:6.2f}')
        mv = wheel_moved(bag['/wheel/odom'], a, b)
        if mv is not None:
            note = '바퀴도 정지' if mv < 0.02 else f'바퀴는 돌았다 (최대 {mv:.3f} m/s)'
            print(f'  실제  {note}')
        for line in logs_in(bag['/rosout'], a, b):
            print(f'  {line}')
    print('─' * 72)
    print('\n명령이 0 인 구간이다. 바퀴가 돌았는데 명령이 0 이면 구동계가 아니라')
    print('기록·배선을 먼저 본다. 명령도 바퀴도 0 이면 Nav2 가 명령을 못 만든 것이다.')


if __name__ == '__main__':
    main()
