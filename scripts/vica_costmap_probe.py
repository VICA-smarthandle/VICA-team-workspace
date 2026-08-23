#!/usr/bin/env python3
"""local costmap 을 스냅샷으로 떠서 두 장을 비교한다. nvblox 기여도와 잔상을 함께 판정한다.

    source /opt/ros/humble/setup.bash
    python3 scripts/vica_costmap_probe.py --snapshot nvblox_on     # nvblox 켠 상태
    # nvblox_node 만 종료하고 10초 기다린다 (Nav2 는 재기동하지 않는다)
    python3 scripts/vica_costmap_probe.py --snapshot nvblox_off    # nvblox 없는 상태
    python3 scripts/vica_costmap_probe.py --compare nvblox_on nvblox_off

    python3 scripts/vica_costmap_probe.py --list       # 저장된 스냅샷 목록
    python3 scripts/vica_costmap_probe.py --selftest   # 계산이 맞는지 확인

왜 만들었나
    local costmap 의 plugins 에 `nvblox_layer` 가 들어 있다. 그런데 그것이 비용을
    실제로 넣고 있는지 아무도 모른다. 관찰이 둘로 갈린다 — "nvblox 를 끄면 코너에서
    더 붙어서 간다"(그러면 기여가 있다)와 "세그멘테이션이 비활성이라 작동 안 하는
    것과 같다"(그러면 기여가 없다)가 같이 있다. 둘 다 느낌이고, 느낌으로는
    plugins 에서 뺄지 말지를 정할 수 없다.

    그래서 숫자로 판정한다. Nav2 를 그대로 둔 채 `nvblox_node` 만 죽이면 plugins 는
    남고 입력만 끊긴다. 그 전후의 costmap 차이가 곧 nvblox 의 기여분이다.
    절차는 `docs/handoff_jetson_camera_and_yolo.md` §2-2 가 정본이다.

        ① 로봇을 코너나 벽 가까이 세운다 (이후 움직이지 않는다)
        ② --snapshot nvblox_on      <- nvblox 켜진 상태
        ③ nvblox_node 만 종료
        ④ 10초 대기 후 --snapshot nvblox_off
        ⑤ --compare nvblox_on nvblox_off

    되도록 ② 를 두 번 한다(--snapshot base0 / base1). 둘 다 nvblox 를 켠 채이므로
    차이가 0 이어야 하는데 실제로는 라이다가 흔들려 몇십 칸이 오간다. 그 폭이
    "얼마부터 의미 있는 차이인가"의 답이다. --compare base0 base1 로 재서
    --noise 로 넘기면 ⑤ 의 판정이 짐작이 아니게 된다.

    한 번의 실험으로 두 가지가 동시에 판정된다.

        칸 수가 거의 같다   nvblox 는 무해하다. 꺼도 잃을 것이 없다
                            (단, §2-1 에서 slice 가 내용을 갖고 있었어야 한다.
                             빈 slice 였다면 애초에 넣을 것이 없었던 것이다)
        칸 수가 줄어든다    nvblox 가 벽 근처에 비용을 넣고 있었다. 코너 관찰이 사실
        껐는데도 그대로     nvblox_layer 가 마지막 slice 를 붙잡고 있다. 잔상 문제다

[함정] 값 범위 — 0~100 인가 0~255 인가
    이 스크립트가 읽는 것은 `/local_costmap/costmap` (`nav_msgs/OccupancyGrid`) 이고
    값은 **0~100 과 -1** 이다. costmap_2d 내부값(0~255)이 아니다. 같은 costmap 을
    `/local_costmap/costmap_raw` (`nav2_msgs/Costmap`) 로도 내보내는데 그쪽이 0~255 다.

    2026-08-15 오전에 "costmap 최댓값이 100인데 왜 253이라 하나"로 반나절을 쓴 것이
    이 두 값 범위를 섞은 탓이다(devlog/2026-08-15-people-mode-와-planner-교착.md §3.1).
    nav2 의 `Costmap2DPublisher` 가 아래 표대로 옮겨 발행한다.

        내부값 0        ->    0     FREE_SPACE
        내부값 1~252    ->   1~98   1 + 97*(v-1)/251 (정수 나눗셈)
        내부값 253      ->   99     INSCRIBED_INFLATED_OBSTACLE
        내부값 254      ->  100     LETHAL_OBSTACLE
        내부값 255      ->   -1     NO_INFORMATION (미탐색)

    따라서 **"253 이상" 은 OccupancyGrid 에서 99 이상**이다. 99 는 내부값 253 하나만,
    100 은 254 하나만 뜻한다. 뭉개지는 것은 1~252 구간뿐이고 판정에는 그 구간을
    쓰지 않으므로, 0~255 를 굳이 받을 이유가 없다. 253 을 지표로 쓰는 이유는
    planner 가 253 이상이면 **footprint 모양을 보지도 않고 거부**하기 때문이다.

    -1(미탐색)은 0 과 다르다. 따로 센다. 둘을 섞으면 "비어 있다"와 "모른다"가
    한 칸에 들어간다.

로봇 0.3 m 안 최댓값을 왜 같이 재나
    2026-08-15 조사에서 "로봇이 자기 자리를 막는" 교착을 이 값으로 잡아냈다. 로봇이
    좁은 자리에 들어가면 라이다가 벽을 더 가까이 보고, inflation 이 로봇이 선 자리를
    덮는다. 그러면 planner 가 출발점을 거부하고, 벗어나려면 움직여야 하는데 경로가
    없다. 전체 칸 수는 멀쩡한데 그 자리만 막히는 형태라 총량만 봐서는 안 보인다.

스냅샷은 파일로 남는다
    ~/vica_data/costmap/<이름>.json (bag·CPU 기록과 같은 자리다). JSON 이므로 나중에
    다시 비교할 수 있고, --compare 는 rclpy 없이 돈다 — 젯슨에서 뜬 스냅샷을 노트북에
    가져와 비교해도 된다. 스냅샷을 뜨는 --snapshot 만 ROS 2 환경을 요구한다.

    로봇 위치는 TF 로 얻는다(costmap 의 frame -> base_footprint). local costmap 의
    global_frame 은 `odom` 이다. TF 를 못 잡으면 로봇 주변 지표만 비고 나머지는 남는다.
"""

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime

SNAP_DIR = os.path.expanduser('~/vica_data/costmap')
TOPIC = '/local_costmap/costmap'
SLICE_TOPIC = '/nvblox_node/static_map_slice'
BASE_FRAME = 'base_footprint'

# OccupancyGrid 로 옮겨진 뒤의 경계값이다. 위 [함정] 항목의 환산표를 그대로 쓴다.
OG_INSCRIBED = 99      # costmap_2d 내부값 253. planner 가 여기서부터 무조건 거부한다
OG_LETHAL = 100        # 내부값 254
OG_UNKNOWN = -1        # 내부값 255

NEAR_RADIUS = 0.3      # m. 2026-08-15 조사가 쓴 반경이다
FORMAT = 'vica_costmap_snapshot/1'

# 판정을 눈대중으로 하지 않게 문턱을 박아 둔다. 라이다는 가만히 서 있어도 칸 수가
# 몇십 칸씩 흔들리므로 그만큼은 '같다'로 본다.
#
# 이 기본값은 근거가 약하다. 벽 가까이 세우면 INSCRIBED 총량은 벽이 차지하고,
# 그 총량에 비례한 문턱은 정작 재려는 변화를 덮어 버린다. 그래서 그 자리의
# 흔들림 폭을 직접 재는 길을 열어 둔다 — nvblox 를 **켠 채로** 두 장을 연속으로
# 떠서 --compare 하면 그 값이 나온다(0점 측정). 그것을 --noise 로 넣는다.
SAME_ABS = 20          # 칸
SAME_REL = 0.01        # 1 %


# ---------------------------------------------------------------------------
# 값 환산 — 위 [함정] 항목의 표를 코드로 옮긴 것이다. --selftest 가 검사한다
# ---------------------------------------------------------------------------
def raw_to_og(raw):
    """costmap_2d 내부값(0~255) -> OccupancyGrid 값(-1, 0~100).

    nav2_costmap_2d 의 Costmap2DPublisher 가 만드는 변환표와 같다. 이 스크립트가
    쓰지는 않는다 — 우리가 무엇을 세고 있는지 증명하고, 0~255 로 적힌 옛 기록을
    이 스냅샷과 맞춰 볼 때 쓴다.
    """
    if raw == 0:
        return 0
    if raw == 253:
        return OG_INSCRIBED
    if raw == 254:
        return OG_LETHAL
    if raw == 255:
        return OG_UNKNOWN
    return 1 + (97 * (raw - 1)) // 251


# ---------------------------------------------------------------------------
# 스냅샷 입출력
# ---------------------------------------------------------------------------
def snapshot_path(name):
    if name.endswith('.json') or os.sep in name:
        return os.path.expanduser(name)
    return os.path.join(SNAP_DIR, name + '.json')


def save_snapshot(snap, path):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(snap, f, ensure_ascii=False, separators=(',', ':'))
    return path


def load_snapshot(path):
    with open(os.path.expanduser(path), encoding='utf-8') as f:
        snap = json.load(f)
    if snap.get('format') != FORMAT:
        raise ValueError(f'{path}: 모르는 형식이다 ({snap.get("format")})')
    if len(snap['data']) != snap['width'] * snap['height']:
        raise ValueError(f'{path}: 칸 수가 width*height 와 다르다')
    return snap


def make_snapshot(name, width, height, resolution, origin, data,
                  frame_id='odom', stamp=0.0, robot=None, topic=TOPIC,
                  slice_publishers=None, slice_type=None, note=''):
    """스냅샷 하나를 만든다. rclpy 가 없어도 부를 수 있어야 시험이 된다."""
    return {
        'format': FORMAT,
        'name': name,
        'saved_at': datetime.now().isoformat(timespec='seconds'),
        'topic': topic,
        'msg_type': 'nav_msgs/msg/OccupancyGrid',
        # 값이 0~100/-1 이라는 사실을 파일 안에도 적어 둔다. 0~255 로 읽는 사고를 막는다
        'value_scale': 'occupancy_grid(-1, 0..100)',
        'frame_id': frame_id,
        'stamp': stamp,
        'width': width,
        'height': height,
        'resolution': resolution,
        'origin': {'x': origin[0], 'y': origin[1],
                   'yaw': origin[2] if len(origin) > 2 else 0.0},
        'robot': robot,
        'nvblox': {'slice_topic': SLICE_TOPIC,
                   'publishers': slice_publishers,
                   'type': slice_type},
        'note': note,
        'data': list(data),
    }


# ---------------------------------------------------------------------------
# 순수 계산 — 여기서부터 아래는 ROS 2 없이 돈다
# ---------------------------------------------------------------------------
def cell_center(snap, ix, iy):
    """격자 칸의 중심 좌표(월드). 원점은 칸의 모서리이므로 반 칸을 더한다."""
    res = snap['resolution']
    return (snap['origin']['x'] + (ix + 0.5) * res,
            snap['origin']['y'] + (iy + 0.5) * res)


def value_at_world(snap, wx, wy):
    """월드 좌표의 칸 값. 격자 밖이면 None 이다."""
    res = snap['resolution']
    ix = int(math.floor((wx - snap['origin']['x']) / res))
    iy = int(math.floor((wy - snap['origin']['y']) / res))
    if not (0 <= ix < snap['width'] and 0 <= iy < snap['height']):
        return None
    return snap['data'][iy * snap['width'] + ix]


def cells_within(snap, cx, cy, radius):
    """(cx, cy) 에서 반경 radius m 안에 중심이 들어오는 칸 값들."""
    res = snap['resolution']
    lo_x = int(math.floor((cx - radius - snap['origin']['x']) / res))
    hi_x = int(math.ceil((cx + radius - snap['origin']['x']) / res))
    lo_y = int(math.floor((cy - radius - snap['origin']['y']) / res))
    hi_y = int(math.ceil((cy + radius - snap['origin']['y']) / res))
    out = []
    for iy in range(max(0, lo_y), min(snap['height'], hi_y + 1)):
        for ix in range(max(0, lo_x), min(snap['width'], hi_x + 1)):
            wx, wy = cell_center(snap, ix, iy)
            if math.hypot(wx - cx, wy - cy) <= radius:
                out.append(snap['data'][iy * snap['width'] + ix])
    return out


def count_cells(values):
    """칸 값 묶음을 세어 준다. -1(미탐색)은 0 과 갈라서 센다."""
    r = {'total': len(values), 'inscribed': 0, 'lethal': 0, 'exact_253': 0,
         'positive': 0, 'unknown': 0, 'max': None}
    for v in values:
        if v == OG_UNKNOWN:
            r['unknown'] += 1
            continue
        if v > 0:
            r['positive'] += 1
        if v >= OG_INSCRIBED:
            r['inscribed'] += 1
            if v == OG_INSCRIBED:
                r['exact_253'] += 1
        if v >= OG_LETHAL:
            r['lethal'] += 1
        if r['max'] is None or v > r['max']:
            r['max'] = v
    return r


def summarize(snap, radius=NEAR_RADIUS):
    """스냅샷 한 장의 지표. 로봇 위치를 모르면 주변 지표만 비운다."""
    r = count_cells(snap['data'])
    r['name'] = snap.get('name', '?')
    r['near_radius'] = radius
    robot = snap.get('robot')
    if robot:
        near = cells_within(snap, robot['x'], robot['y'], radius)
        n = count_cells(near)
        r['near'] = {'max': n['max'], 'inscribed': n['inscribed'],
                     'unknown': n['unknown'], 'total': n['total']}
    else:
        r['near'] = None
    return r


def align(a, b):
    """두 스냅샷을 같은 월드 좌표 위에 겹친다.

    local costmap 은 rolling window 라 로봇이 조금만 움직여도(또는 odom 이 흘러도)
    원점이 옮겨 간다. 칸 번호로 그냥 빼면 엉뚱한 자리끼리 빼게 된다. 그래서 원점
    차이를 칸 수로 환산해 겹치는 영역만 비교한다.

    반환은 (dx, dy, 잔차 m, a 좌표계에서의 겹침 사각형)이다. B 의 칸 (bx, by) 가
    A 의 칸 (bx+dx, by+dy) 에 대응한다.
    """
    if abs(a['resolution'] - b['resolution']) > 1e-9:
        raise ValueError('해상도가 다르다. 같은 costmap 이 아니다.')
    for s in (a, b):
        if abs(s['origin'].get('yaw', 0.0)) > 1e-6:
            raise ValueError('원점이 회전해 있다. 평행이동만으로는 못 겹친다.')
    res = a['resolution']
    fx = (b['origin']['x'] - a['origin']['x']) / res
    fy = (b['origin']['y'] - a['origin']['y']) / res
    dx, dy = int(round(fx)), int(round(fy))
    residual = max(abs(fx - dx), abs(fy - dy)) * res
    x0, x1 = max(0, dx), min(a['width'], b['width'] + dx)
    y0, y1 = max(0, dy), min(a['height'], b['height'] + dy)
    if x0 >= x1 or y0 >= y1:
        raise ValueError('두 스냅샷이 겹치는 영역이 없다. 로봇이 크게 움직였다.')
    return dx, dy, residual, (x0, y0, x1, y1)


def compare(a, b, radius=NEAR_RADIUS):
    """A(먼저) 와 B(나중)를 겹쳐 놓고 차이를 센다."""
    dx, dy, residual, (x0, y0, x1, y1) = align(a, b)

    over_a, over_b = [], []
    rose = fell = 0
    gained = lost = 0          # INSCRIBED 문턱을 넘어온 칸 / 내려간 칸
    unknown_only_a = unknown_only_b = 0
    max_rise = max_fall = 0
    for ay in range(y0, y1):
        for ax in range(x0, x1):
            va = a['data'][ay * a['width'] + ax]
            vb = b['data'][(ay - dy) * b['width'] + (ax - dx)]
            over_a.append(va)
            over_b.append(vb)
            if va == OG_UNKNOWN or vb == OG_UNKNOWN:
                if va == OG_UNKNOWN and vb != OG_UNKNOWN:
                    unknown_only_a += 1
                elif vb == OG_UNKNOWN and va != OG_UNKNOWN:
                    unknown_only_b += 1
                continue
            if vb > va:
                rose += 1
                max_rise = max(max_rise, vb - va)
            elif vb < va:
                fell += 1
                max_fall = max(max_fall, va - vb)
            if va < OG_INSCRIBED <= vb:
                gained += 1
            elif vb < OG_INSCRIBED <= va:
                lost += 1

    return {
        'a': summarize(a, radius),
        'b': summarize(b, radius),
        'shift_cells': (dx, dy),
        'shift_m': (dx * a['resolution'], dy * a['resolution']),
        'residual_m': residual,
        'overlap_cells': len(over_a),
        'overlap_a': count_cells(over_a),
        'overlap_b': count_cells(over_b),
        'rose': rose,
        'fell': fell,
        'inscribed_gained': gained,
        'inscribed_lost': lost,
        'unknown_only_a': unknown_only_a,
        'unknown_only_b': unknown_only_b,
        'max_rise': max_rise,
        'max_fall': max_fall,
    }


def verdict(cmp, noise=None):
    """handoff §2-2 의 판정 표 중 어느 줄인지 고른다. A=켠 상태, B=끈 상태로 본다.

    돌려주는 것은 (코드, 한 줄 설명)이다. 코드는 same / decreased / increased 다.
    same 은 '무해'와 '잔상' 둘 다일 수 있어 여기서 갈라내지 못한다 — §2-1 이 필요하다.

    noise 는 0점 측정으로 잰 그 자리의 흔들림 폭(칸)이다. 주면 그것을 문턱으로
    쓴다. 안 주면 근거가 약한 기본값을 쓰고, 그렇다고 화면에 적는다.
    """
    ia = cmp['overlap_a']['inscribed']
    ib = cmp['overlap_b']['inscribed']
    delta = ib - ia
    if noise is not None:
        limit, source = int(noise), '0점 측정으로 준 값'
    else:
        limit, source = max(SAME_ABS, int(ia * SAME_REL)), '기본값 — 0점 측정을 안 했다'
    head = f'INSCRIBED 칸이 {ia} -> {ib} ({delta:+d}).'
    if abs(delta) <= limit:
        return 'same', f'{head} 흔들림으로 보는 범위(+-{limit} 칸, {source}) 안이다.'
    if delta < 0:
        return 'decreased', f'{head} 문턱 {limit} 칸({source})을 넘어 줄었다.'
    return 'increased', f'{head} 문턱 {limit} 칸({source})을 넘어 늘었다.'


# ---------------------------------------------------------------------------
# 화면 출력
# ---------------------------------------------------------------------------
def pct(n, total):
    return f'{100.0 * n / total:.1f} %' if total else '—'


def print_summary(snap, radius=NEAR_RADIUS, indent='  '):
    s = summarize(snap, radius)
    o = snap['origin']
    print(f'{indent}{snap["topic"]}  nav_msgs/OccupancyGrid  (값 -1, 0~100)')
    print(f'{indent}격자 {snap["width"]} x {snap["height"]} · '
          f'{snap["resolution"]} m/셀 · frame {snap["frame_id"]} · '
          f'원점 ({o["x"]:.2f}, {o["y"]:.2f})')
    robot = snap.get('robot')
    if robot:
        print(f'{indent}로봇 x={robot["x"]:.2f} y={robot["y"]:.2f} '
              f'yaw={math.degrees(robot["yaw"]):.0f}도  '
              f'({snap["frame_id"]} -> {robot["frame"]})')
    else:
        print(f'{indent}로봇 위치 없음 — TF 를 못 잡았다. 주변 지표는 비어 있다')
    nv = snap.get('nvblox') or {}
    if nv.get('publishers') is not None:
        state = '켜짐' if nv['publishers'] > 0 else '꺼짐(발행자 없음)'
        print(f'{indent}nvblox slice {state}  {nv["slice_topic"]}  '
              f'발행자 {nv["publishers"]} 개')
    if snap.get('note'):
        print(f'{indent}메모: {snap["note"]}')

    total = s['total']
    print()
    print(f'{indent}253이상(INSCRIBED, og>=99)  {s["inscribed"]:7d} 칸   '
          f'{pct(s["inscribed"], total)}')
    print(f'{indent}  그중 254(LETHAL, og=100)  {s["lethal"]:7d} 칸')
    print(f'{indent}0 초과                      {s["positive"]:7d} 칸   '
          f'{pct(s["positive"], total)}')
    print(f'{indent}미탐색(-1)                  {s["unknown"]:7d} 칸')
    print(f'{indent}최댓값                      '
          f'{"—" if s["max"] is None else s["max"]:>7}')
    if s['near']:
        n = s['near']
        print(f'{indent}로봇 {radius:.1f} m 안 최댓값      '
              f'{"—" if n["max"] is None else n["max"]:>7}   '
              f'(INSCRIBED {n["inscribed"]} / {n["total"]} 칸, '
              f'미탐색 {n["unknown"]} 칸)')
        if n['max'] is not None and n['max'] >= OG_INSCRIBED:
            print(f'{indent}  [주의] 로봇이 선 자리가 INSCRIBED 다. '
                  'planner 는 여기서 출발을 거부한다')


def row(label, va, vb, unit=''):
    def f(v):
        return '—' if v is None else (f'{v:.2f}' if isinstance(v, float) else str(v))
    delta = ''
    if isinstance(va, (int, float)) and isinstance(vb, (int, float)) \
            and not isinstance(va, bool):
        d = vb - va
        delta = f'{d:+.0f}' if d else '0'
    print(f'  {label:<28}{f(va):>12}{f(vb):>12}{delta:>12}  {unit}')


CHARS = [(0, ' '), (1, '.'), (50, '+'), (OG_INSCRIBED, '#'), (OG_LETHAL, '@')]


def to_char(v):
    if v is None:
        return ' '
    if v == OG_UNKNOWN:
        return '?'
    c = ' '
    for lo, ch in CHARS:
        if v >= lo:
            c = ch
    return c


def block_max(snap, x0, y0, x1, y1):
    """월드 사각형 안에 중심이 든 칸들의 최댓값. (값, 미탐색을 봤나)를 준다.

    한 글자가 여러 칸을 덮으므로 최댓값을 쓴다. 평균을 쓰면 벽 한 줄이 묻힌다.
    """
    res = snap['resolution']
    ix0 = int(math.floor((x0 - snap['origin']['x']) / res))
    ix1 = int(math.ceil((x1 - snap['origin']['x']) / res))
    iy0 = int(math.floor((y0 - snap['origin']['y']) / res))
    iy1 = int(math.ceil((y1 - snap['origin']['y']) / res))
    best, unknown = None, False
    for iy in range(max(0, iy0), min(snap['height'], iy1)):
        for ix in range(max(0, ix0), min(snap['width'], ix1)):
            v = snap['data'][iy * snap['width'] + ix]
            if v == OG_UNKNOWN:
                unknown = True
            elif best is None or v > best:
                best = v
    return best, unknown


def _blocks(cx, cy, half_m, cols):
    """글자 하나가 덮는 월드 사각형을 위에서 아래로(=+y 가 위) 훑는다."""
    step = 2.0 * half_m / cols
    for j in range(cols - 1, -1, -1):
        row_boxes = []
        for i in range(cols):
            x0 = cx - half_m + i * step
            y0 = cy - half_m + j * step
            row_boxes.append((x0, y0, x0 + step, y0 + step))
        yield row_boxes


def render(snap, cx, cy, half_m, cols):
    """로봇 주변을 글자 그림으로 만든다."""
    rows = []
    for row_boxes in _blocks(cx, cy, half_m, cols):
        line = ''
        for box in row_boxes:
            best, unknown = block_max(snap, *box)
            line += ('?' if unknown else ' ') if best is None else to_char(best)
        rows.append(line)
    return rows


def render_diff(a, b, cx, cy, half_m, cols):
    """값이 오른 곳 '+' · 내린 곳 '-' · INSCRIBED 가 붙고 풀린 곳 '^' 'v'.

    표본을 뜨는 방식은 render 와 같아야 한다. 다르면 두 그림과 차이 그림이
    서로 다른 것을 보여 주고, 눈으로 대조할 수가 없다.
    """
    rows = []
    for row_boxes in _blocks(cx, cy, half_m, cols):
        line = ''
        for box in row_boxes:
            va, _ = block_max(a, *box)
            vb, _ = block_max(b, *box)
            if va is None or vb is None:
                line += ' '
            elif va >= OG_INSCRIBED > vb:
                line += 'v'
            elif vb >= OG_INSCRIBED > va:
                line += '^'
            elif vb > va:
                line += '+'
            elif vb < va:
                line += '-'
            else:
                line += '.'
        rows.append(line)
    return rows


def show_maps(a, b, half_m=1.5, cols=24):
    """A · B · 차이를 나란히 놓는다. 총 칸 수만 보면 '자기 자리만 막힌' 형태를 놓친다."""
    robot = a.get('robot') or b.get('robot')
    if robot:
        cx, cy = robot['x'], robot['y']
        where = '로봇 중심'
    else:
        cx = a['origin']['x'] + a['width'] * a['resolution'] / 2
        cy = a['origin']['y'] + a['height'] * a['resolution'] / 2
        where = '격자 중심(로봇 위치를 몰라 대신 쓴다)'
    ma = render(a, cx, cy, half_m, cols)
    mb = render(b, cx, cy, half_m, cols)
    md = render_diff(a, b, cx, cy, half_m, cols)

    print(f'\n{where} ±{half_m:.1f} m  '
          f'(한 글자 {2 * half_m / cols * 100:.0f} cm, 여러 칸의 최댓값)')
    print("  ' '=0  '.'=1~49  '+'=50~98  '#'=99(INSCRIBED)  '@'=100(LETHAL)"
          "  '?'=미탐색")
    print("  차이:  '.'=같음  '+'=올랐다  '-'=내렸다  '^'=INSCRIBED 됨  'v'=INSCRIBED 풀림")
    head = f'  {a["name"][:cols]:<{cols}}   {b["name"][:cols]:<{cols}}   차이(B-A)'
    print(head)
    for i in range(cols):
        print(f'  |{ma[i]}| |{mb[i]}| |{md[i]}|')


def show_compare(a, b, radius=NEAR_RADIUS, maps=True, noise=None):
    cmp = compare(a, b, radius)
    sa, sb = cmp['a'], cmp['b']

    print(f'\nA {a["name"]}   ({a.get("saved_at", "?")})')
    print(f'B {b["name"]}   ({b.get("saved_at", "?")})')
    nva = (a.get('nvblox') or {}).get('publishers')
    nvb = (b.get('nvblox') or {}).get('publishers')
    if nva is not None and nvb is not None:
        ordered = nva > 0 and nvb == 0
        tail = '   (A=켠 상태, B=끈 상태로 읽는다)' if ordered else ''
        print(f'nvblox slice 발행자   A {nva} 개  ->  B {nvb} 개{tail}')
        if not ordered:
            print('  [주의] A 는 켜져 있고 B 는 꺼져 있어야 §2-2 의 판정 표를 '
                  '그대로 쓸 수 있다')

    if a.get('stamp') and a['stamp'] == b.get('stamp'):
        print('[주의] 두 스냅샷의 costmap 시각이 같다. 같은 격자를 두 번 저장했을 수'
              ' 있다.\n       그러면 차이가 0 인 것은 당연하고 판정에 쓸 수 없다.')

    dx, dy = cmp['shift_cells']
    if dx or dy:
        print(f'원점이 {cmp["shift_m"][0]:+.2f}, {cmp["shift_m"][1]:+.2f} m 옮겨 갔다 '
              f'({dx:+d}, {dy:+d} 칸). 겹치는 {cmp["overlap_cells"]} 칸만 비교한다')
        if abs(cmp['shift_m'][0]) > 0.1 or abs(cmp['shift_m'][1]) > 0.1:
            print('  [주의] 로봇이 움직였을 수 있다. §2-2 는 로봇을 세워 둔 채로 재는 절차다')
    if cmp['residual_m'] > 0.1 * a['resolution']:
        print(f'  [주의] 격자가 칸 단위로 안 맞는다(잔차 {cmp["residual_m"] * 100:.1f} cm). '
              '차이가 그만큼 부풀 수 있다')

    print(f'\n  {"지표":<28}{"A":>12}{"B":>12}{"B-A":>12}')
    print('  ' + '-' * 64)
    oa, ob = cmp['overlap_a'], cmp['overlap_b']
    row('253이상(INSCRIBED)', oa['inscribed'], ob['inscribed'], '칸')
    row('  그중 254(LETHAL)', oa['lethal'], ob['lethal'], '칸')
    row('  99 정확히', oa['exact_253'], ob['exact_253'], '칸')
    row('0 초과', oa['positive'], ob['positive'], '칸')
    row('미탐색(-1)', oa['unknown'], ob['unknown'], '칸')
    row('최댓값', oa['max'], ob['max'], '')
    na = sa['near'] or {}
    nb = sb['near'] or {}
    row(f'로봇 {radius:.1f} m 안 최댓값', na.get('max'), nb.get('max'), '')
    row(f'로봇 {radius:.1f} m 안 INSCRIBED',
        na.get('inscribed'), nb.get('inscribed'), '칸')
    print('  ' + '-' * 64)
    print(f'  겹친 {cmp["overlap_cells"]} 칸 중')
    print(f'    비용이 올라간 칸   {cmp["rose"]:6d}   (최대 +{cmp["max_rise"]})')
    print(f'    비용이 내려간 칸   {cmp["fell"]:6d}   (최대 -{cmp["max_fall"]})')
    print(f'    INSCRIBED 가 된 칸 {cmp["inscribed_gained"]:6d}')
    print(f'    INSCRIBED 가 풀린 칸 {cmp["inscribed_lost"]:6d}')
    if cmp['unknown_only_a'] or cmp['unknown_only_b']:
        print(f'    미탐색이 채워진 칸 {cmp["unknown_only_a"]:6d} · '
              f'새로 미탐색이 된 칸 {cmp["unknown_only_b"]}')

    if maps:
        show_maps(a, b)

    code, line = verdict(cmp, noise)
    print('\n' + '─' * 66)
    print('판정  (docs/handoff_jetson_camera_and_yolo.md §2-2)')
    print('─' * 66)
    print(f'  {line}')
    if code == 'same':
        print('  -> 칸 수가 거의 같다. 두 가지 중 하나다.')
        print('     (가) nvblox 가 애초에 아무것도 안 넣고 있었다 -> 꺼도 잃을 것이 없다')
        print('     (나) nvblox_layer 가 마지막 slice 를 붙잡고 있다 -> 잔상 문제다')
        print('     가르는 방법: §2-1 에서 slice 의 width x height 가 0 이었으면 (가) 다.')
        print('     0 이 아니었는데 여기서 안 줄었으면 (나) 이고, 그것도 중요한 발견이다.')
    elif code == 'decreased':
        print('  -> nvblox 가 벽 근처에 비용을 넣고 있었다. "끄면 코너에서 더 붙어서 간다"는')
        print('     관찰이 사실이다. nvblox 는 유지하고 §2-4 / §2-5 로 암전 원인을 좁힌다.')
    else:
        print('  -> 껐는데 오히려 늘었다. nvblox 기여 판정이 아니다. 라이다가 본 것이')
        print('     바뀌었거나(사람·문 열림) 로봇이 움직였다. 세워 둔 채로 다시 잰다.')
    if noise is None:
        print()
        print('  문턱을 짐작으로 쓰고 있다. 이 자리의 흔들림 폭을 재려면 nvblox 를')
        print('  켠 채로 두 장을 연속으로 뜬 뒤 비교한다(0점 측정). 거기서 나온')
        print('  INSCRIBED 차이를 --noise 로 넣으면 판정이 짐작이 아니게 된다.')
    print()
    print('  이 스크립트가 세는 것은 local costmap 이다. planner 의 "Starting point in')
    print('  lethal space" 는 global costmap 을 본다. 거기엔 nvblox_layer 가 없다')
    print('  (2026-08-15 §3.2). 이 판정으로 planner 정체를 설명하지 않는다.')
    return cmp


# ---------------------------------------------------------------------------
# 스냅샷 뜨기 — 여기서만 ROS 2 가 필요하다
# ---------------------------------------------------------------------------
def quat_yaw(q):
    """사원수에서 yaw 만 뽑는다. costmap 도 로봇도 평면 위에 있다."""
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                      1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def capture(name, topic, base_frame, timeout, note):
    try:
        import rclpy
        from rclpy.time import Time
        from nav_msgs.msg import OccupancyGrid
        import tf2_ros
    except ImportError:
        sys.exit('ROS 2 환경이 필요하다:  source /opt/ros/humble/setup.bash\n'
                 '(--compare 와 --selftest 는 ROS 2 없이도 된다)')

    rclpy.init()
    node = rclpy.create_node('vica_costmap_probe')
    got = []
    # QoS 는 기본값(reliable · volatile)을 쓴다. costmap 발행자가 transient_local 이어도
    # volatile 구독자는 붙지만 그 반대는 안 붙는다. 2 Hz 로 계속 나오므로 기다리면 된다.
    node.create_subscription(OccupancyGrid, topic, got.append, 1)
    buf = tf2_ros.Buffer()
    # 변수로 잡아 둔다. 참조를 놓으면 TF 구독이 사라져 lookup 이 늘 실패한다
    listener = tf2_ros.TransformListener(buf, node)

    # 두 장째를 쓴다. 첫 장은 구독이 붙는 순간 밀려 있던 것일 수 있고, 그러면
    # nvblox 를 죽이기 전의 costmap 을 죽인 뒤의 것으로 착각한 채 판정하게 된다.
    # 그 한 번의 착오로 실험 전체가 무효가 된다.
    deadline = time.time() + timeout
    while rclpy.ok() and time.time() < deadline and len(got) < 2:
        rclpy.spin_once(node, timeout_sec=0.1)
    if not got:
        node.destroy_node()
        rclpy.shutdown()
        sys.exit(f'{timeout:.0f} 초 동안 {topic} 이 안 왔다. Nav2 local_costmap 이 '
                 f'떠 있는지,\n토픽 이름이 맞는지 본다:  ros2 topic hz {topic}')
    if len(got) < 2:
        print(f'[주의] {timeout:.0f} 초 동안 한 장만 왔다. 밀려 있던 옛 costmap 일 수'
              ' 있다.\n       publish_frequency(2 Hz)를 확인하고 다시 뜨는 것이 안전하다.')
    grid = got[-1]

    # TF 버퍼가 채워질 시간을 준다. 바로 물으면 첫 조회가 자주 실패한다
    fill = time.time() + 1.0
    while rclpy.ok() and time.time() < fill:
        rclpy.spin_once(node, timeout_sec=0.05)

    robot = None
    try:
        tr = buf.lookup_transform(grid.header.frame_id, base_frame, Time()).transform
        robot = {'frame': base_frame, 'x': tr.translation.x,
                 'y': tr.translation.y, 'yaw': quat_yaw(tr.rotation)}
    except Exception as exc:                       # TF 는 여러 예외를 낸다
        print(f'[주의] TF {grid.header.frame_id} -> {base_frame} 를 못 잡았다: {exc}')
        print('       로봇 주변 지표만 비고 나머지는 그대로 남는다.')

    # nvblox 가 살아 있는지도 함께 적어 둔다. 나중에 두 스냅샷 중 어느 쪽이
    # '켠 상태' 였는지 사람 기억에 의존하지 않게 한다
    try:
        infos = node.get_publishers_info_by_topic(SLICE_TOPIC)
        slice_pub, slice_type = len(infos), (infos[0].topic_type if infos else None)
    except Exception:
        slice_pub, slice_type = None, None

    o = grid.info.origin
    snap = make_snapshot(
        name=name,
        width=grid.info.width, height=grid.info.height,
        resolution=grid.info.resolution,
        origin=(o.position.x, o.position.y, quat_yaw(o.orientation)),
        data=[int(v) for v in grid.data],
        frame_id=grid.header.frame_id,
        stamp=grid.header.stamp.sec + grid.header.stamp.nanosec * 1e-9,
        robot=robot, topic=topic,
        slice_publishers=slice_pub, slice_type=slice_type, note=note)

    del listener
    node.destroy_node()
    rclpy.shutdown()
    return snap


# ---------------------------------------------------------------------------
# 자체 검사 — 틀린 계산으로 nvblox 존폐를 정하면 더 위험하다
# ---------------------------------------------------------------------------
def selftest():
    assert raw_to_og(0) == 0
    assert raw_to_og(1) == 1
    assert raw_to_og(252) == 98, '내부값 252 는 98 이어야 한다(99 가 아니다)'
    assert raw_to_og(253) == OG_INSCRIBED
    assert raw_to_og(254) == OG_LETHAL
    assert raw_to_og(255) == OG_UNKNOWN

    # 98 은 INSCRIBED 가 아니다. 이 한 칸 차이가 planner 의 거부/통과를 가른다
    c = count_cells([0, 1, 98, 99, 100, -1])
    assert c == {'total': 6, 'inscribed': 2, 'lethal': 1, 'exact_253': 1,
                 'positive': 4, 'unknown': 1, 'max': 100}, c

    # 반경 안에 든 칸만 센다. 0.3 m 밖의 벽이 섞여 들어오면 '자기 자리를 막는다'는
    # 판정이 거짓이 된다
    robot = {'frame': 'base_footprint', 'x': 0.5, 'y': 0.5, 'yaw': 0.0}
    snap = make_snapshot('t', 5, 5, 0.2, (0.0, 0.0), [0] * 25, robot=robot)
    snap['data'][2 * 5 + 2] = 50           # 중심 (0.5, 0.5) — 로봇이 선 칸
    snap['data'][4 * 5 + 2] = 100          # 중심 (0.5, 0.9) — 0.40 m 떨어져 있다
    assert count_cells(cells_within(snap, 0.5, 0.5, 0.3))['max'] == 50
    assert count_cells(cells_within(snap, 0.5, 0.5, 0.45))['max'] == 100
    assert summarize(snap, 0.3)['near']['max'] == 50

    # 원점이 옮겨 가도 같은 월드 좌표끼리 뺀다
    a = make_snapshot('a', 4, 4, 0.5, (0.0, 0.0), [0] * 16)
    b = make_snapshot('b', 4, 4, 0.5, (0.5, 0.0), [0] * 16)
    dx, dy, residual, box = align(a, b)
    assert (dx, dy) == (1, 0) and residual < 1e-9, (dx, dy, residual)
    assert box == (1, 0, 4, 4), box

    print('자체 검사 통과. 값 환산·칸 세기·정렬이 맞다.')


def cmd_list():
    if not os.path.isdir(SNAP_DIR):
        print(f'{SNAP_DIR} 가 아직 없다. --snapshot 으로 하나 뜨면 만들어진다.')
        return 0
    names = sorted(n for n in os.listdir(SNAP_DIR) if n.endswith('.json'))
    if not names:
        print(f'{SNAP_DIR} 가 비었다.')
        return 0
    print(f'{SNAP_DIR}')
    for n in names:
        path = os.path.join(SNAP_DIR, n)
        try:
            s = load_snapshot(path)
        except Exception as exc:
            print(f'  {n:<28} (못 읽었다: {exc})')
            continue
        c = count_cells(s['data'])
        nv = (s.get('nvblox') or {}).get('publishers')
        state = '' if nv is None else ('nvblox 켜짐' if nv > 0 else 'nvblox 꺼짐')
        print(f'  {n[:-5]:<28} {s.get("saved_at", "?"):<20} '
              f'INSCRIBED {c["inscribed"]:5d} 칸  {state}')
    return 0


def main():
    p = argparse.ArgumentParser(
        description='local costmap 스냅샷을 뜨고 비교한다 (nvblox 기여도·잔상 판정).',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split('왜 만들었나')[0])
    p.add_argument('--snapshot', metavar='이름', help='지금 costmap 을 파일로 저장한다')
    p.add_argument('--compare', nargs=2, metavar=('A', 'B'),
                   help='두 스냅샷을 비교한다. A 가 먼저(nvblox 켠 상태) 뜬 것이다')
    p.add_argument('--list', action='store_true', help='저장된 스냅샷 목록')
    p.add_argument('--selftest', action='store_true', help='계산이 맞는지 확인한다')
    p.add_argument('--topic', default=TOPIC, help=f'기본 {TOPIC}')
    p.add_argument('--base-frame', default=BASE_FRAME, help=f'기본 {BASE_FRAME}')
    p.add_argument('--radius', type=float, default=NEAR_RADIUS,
                   help=f'로봇 주변 판정 반경 m (기본 {NEAR_RADIUS})')
    p.add_argument('--timeout', type=float, default=10.0, help='costmap 을 기다릴 초')
    p.add_argument('--note', default='', help='스냅샷에 남길 한 줄 메모')
    p.add_argument('--no-map', action='store_true', help='글자 그림을 생략한다')
    p.add_argument('--noise', type=int, default=None, metavar='칸',
                   help='0점 측정으로 잰 이 자리의 INSCRIBED 흔들림 폭. 판정 문턱이 된다')
    args = p.parse_args()

    if args.selftest:
        selftest()
        return 0
    if args.list:
        return cmd_list()

    if args.snapshot:
        snap = capture(args.snapshot, args.topic, args.base_frame,
                       args.timeout, args.note)
        path = save_snapshot(snap, snapshot_path(args.snapshot))
        print(f'\n저장했다: {path}')
        print_summary(snap, args.radius)
        print('\n다음 단계 (docs/handoff_jetson_camera_and_yolo.md §2-2)')
        print('  로봇을 움직이지 말 것. nvblox_node 만 종료하고 10초 뒤 다시 뜬다.')
        print('  python3 scripts/vica_costmap_probe.py '
              f'--compare <먼저> {args.snapshot}')
        print('  흔들림 폭을 모르면 nvblox 를 켠 채 두 장을 먼저 떠서 비교한다(0점 측정).')
        return 0

    if args.compare:
        try:
            a = load_snapshot(snapshot_path(args.compare[0]))
            b = load_snapshot(snapshot_path(args.compare[1]))
        except (OSError, ValueError) as exc:
            sys.exit(f'스냅샷을 못 읽었다: {exc}\n'
                     '  저장된 것을 보려면:  '
                     'python3 scripts/vica_costmap_probe.py --list')
        show_compare(a, b, args.radius, maps=not args.no_map, noise=args.noise)
        return 0

    p.print_help()
    return 1


if __name__ == '__main__':
    sys.exit(main())
