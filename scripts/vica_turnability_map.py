#!/usr/bin/env python3
"""회전 가능 지도 — 지도의 어디서 제자리로 돌 수 있는지 칠한다.

왜 필요한가
    이 로봇은 차동구동이고 사용자가 뒤쪽 손잡이를 잡고 따라 걷는다. 그래서
    유턴은 제자리 회전으로만 할 수 있는데(후진은 뒤에 사람이 있어 금지),
    제자리 회전에는 외접반경의 두 배만큼 폭이 필요하다.

    2026-09-15 에 base_link 원점을 구동륜 축으로 옮기면서 그 필요 폭이
    0.945 m 에서 1.250 m 로 늘었다. 그 결과 로봇이 설 수 있는 자리의 절반
    가까이가 "들어갈 수는 있는데 돌아 나올 수 없는" 곳이 됐다.

    그런데 좁은 곳이 전부 위험한 것은 아니다. 그냥 지나가는 복도는 돌 필요가
    없다. 진짜 위험한 것은 **막다른 좁은 곳**이다 - 들어가면 돌아서 나와야만
    하는 자리다. 이 도구는 그 둘을 갈라 준다.

무엇을 내놓나
    1. 지도 그림 한 장 (색으로 구분)
    2. 등록된 목적지마다 "여기 도착하면 나올 수 있나" 판정표
    3. 통계

    이 결과는 사람이 보는 자료다. 로봇이 읽지 않는다. 이걸 보고 사람이
    금지구역을 칠하거나 목적지를 옮기거나 레일의 회전 지점을 정한다.

어떻게 가르나
    free 셀마다 가장 가까운 벽까지의 거리(여유)를 구한다.

        여유 <  내접반경          로봇이 서지도 못한다
        내접 <= 여유 <  외접반경   설 수는 있는데 제자리로 못 돈다  (좁은 곳)
        여유 >= 외접반경          제자리 회전 가능

    좁은 곳을 '덩어리 모양'으로 가르려 해 봤으나 실패했다(2026-09-16). 사무실
    지도에서 좁은 구역은 복도 몇 개가 아니라 **모든 벽과 장애물을 두르는 띠
    하나**로 이어져 있다. 실제로 재 보니 35.45 m2 가 입구 353개짜리 덩어리
    하나였다. 모양으로는 못 가른다.

    그래서 질문을 바꿨다. "이 자리가 막다른 곳인가"가 아니라
    **"여기서 돌 수 있는 곳까지 얼마나 가야 하나"** 를 잰다. 벽을 통과하지 않고
    실제로 걸어가는 거리(측지 거리)다.

        0 m        여기서 바로 돌 수 있다
        짧다        조금 나가면 돌 수 있다. 통과형 복도가 여기 해당한다
        멀다        한참 가야 돌 수 있다. 되돌아 나와야 할 때 곤란하다
        못 감       진짜 함정이다. 들어가면 영영 못 돈다

    반경은 nav2_params.yaml 에서 읽는다. 여기 숫자를 다시 적지 않는다 -
    설정과 어긋나면 이 지도가 거짓말을 한다.

쓰는 법
    python3 scripts/vica_turnability_map.py vica_map_0630
    python3 scripts/vica_turnability_map.py vica_map_0630 --out /tmp/t.png
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import yaml
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vica_corridor_measure import robot_radii  # noqa: E402  설정과 한 곳에서 읽는다

WS = Path(__file__).resolve().parent.parent / 'vica_ros2_ws'

# '돌 수 있는 곳까지 얼마나 가야 하나'로 색을 나눈다.
NEAR_M = 2.0   # 이 안이면 조금만 나가면 돈다
COLORS = {
    'wall':      (0.20, 0.20, 0.22),
    'unknown':   (0.55, 0.55, 0.57),
    'tootight':  (0.88, 0.88, 0.90),
    'turnable':  (0.35, 0.70, 0.55),   # 초록 - 여기서 바로 돈다
    'near':      (0.98, 0.84, 0.45),   # 노랑 - 2 m 안에 돌 곳이 있다
    'far':       (0.93, 0.52, 0.25),   # 주황 - 한참 가야 돈다
    'trap':      (0.85, 0.20, 0.35),   # 빨강 - 영영 못 돈다
}


def load_map(name: str):
    base = WS / 'maps' / name
    meta = yaml.safe_load((base.with_suffix('.yaml')).read_text(encoding='utf-8'))
    img = np.array(Image.open(str(base) + '.pgm'))
    return img, meta


def geodesic_to_turnable(standable, turnable, res):
    """standable 안을 걸어서 가장 가까운 turnable 까지 가는 거리(m).

    직선거리가 아니다. 벽을 돌아가는 실제 거리다. 닿을 수 없으면 inf.
    대각선은 sqrt(2) 로 센다.
    """
    import heapq
    h, w = standable.shape
    INF = np.inf
    dist = np.full((h, w), INF)
    pq = []
    rs, cs = np.nonzero(turnable)
    for r, c in zip(rs, cs):
        dist[r, c] = 0.0
        pq.append((0.0, r, c))
    heapq.heapify(pq)
    nb = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
          (-1, -1, 1.4142), (-1, 1, 1.4142), (1, -1, 1.4142), (1, 1, 1.4142)]
    while pq:
        d, r, c = heapq.heappop(pq)
        if d > dist[r, c]:
            continue
        for dr, dc, cost in nb:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < h and 0 <= nc < w) or not standable[nr, nc]:
                continue
            nd = d + cost
            if nd < dist[nr, nc]:
                dist[nr, nc] = nd
                heapq.heappush(pq, (nd, nr, nc))
    return dist * res


def classify(img, meta, inner, outer):
    """지도를 갈래로 나눈다."""
    res = float(meta['resolution'])
    # trinary 지도: 밝으면 free, 어두우면 점유, 중간이 미탐색.
    free = img > 250
    unknown = (img > 100) & (img <= 250)
    # 미탐색은 벽으로 친다. 라이다가 못 본 곳을 통과 가능으로 세면 안 된다.
    clearance = ndimage.distance_transform_edt(free) * res

    standable = free & (clearance >= inner)
    turnable = free & (clearance >= outer)
    narrow = standable & ~turnable

    # 돌 수 있는 곳까지 실제로 가야 하는 거리.
    to_turn = geodesic_to_turnable(standable, turnable, res)
    # 영영 못 도는 곳 = 그 덩어리 안에 회전 가능 셀이 하나도 없다.
    trap = standable & np.isinf(to_turn)

    return {
        'res': res, 'free': free, 'unknown': unknown, 'clearance': clearance,
        'standable': standable, 'turnable': turnable, 'narrow': narrow,
        'trap': trap, 'to_turn': to_turn,
    }


def to_pixel(x, y, meta, shape):
    """지도 좌표(m) -> 픽셀 (row, col). 원점은 이미지 왼쪽 아래다."""
    ox, oy = float(meta['origin'][0]), float(meta['origin'][1])
    res = float(meta['resolution'])
    col = int(round((x - ox) / res))
    row = int(round(shape[0] - 1 - (y - oy) / res))
    return row, col


def destinations(name):
    p = WS / 'location' / name / 'locations.json'
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return []


def draw(c, meta, dests, out_path, name, inner, outer):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    # 한글이 깨지면 그림이 쓸모없다. 젯슨에 나눔고딕이 깔려 있다.
    for cand in ('NanumGothic', 'NanumBarunGothic', 'Noto Sans CJK JP'):
        try:
            matplotlib.font_manager.findfont(cand, fallback_to_default=False)
            matplotlib.rcParams['font.family'] = cand
            break
        except Exception:
            continue
    matplotlib.rcParams['axes.unicode_minus'] = False

    h, w = c['free'].shape
    rgb = np.zeros((h, w, 3))
    rgb[:] = COLORS['wall']
    rgb[c['unknown']] = COLORS['unknown']
    rgb[c['free'] & ~c['standable']] = COLORS['tootight']
    far = c['standable'] & ~c['turnable'] & np.isfinite(c['to_turn'])
    rgb[far & (c['to_turn'] > NEAR_M)] = COLORS['far']
    rgb[far & (c['to_turn'] <= NEAR_M)] = COLORS['near']
    rgb[c['trap']] = COLORS['trap']
    rgb[c['turnable']] = COLORS['turnable']

    fig_w = max(8.0, w / 90)
    fig, ax = plt.subplots(figsize=(fig_w, fig_w * h / w + 1.4), dpi=150)
    ax.imshow(rgb, interpolation='nearest')
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)

    for d in dests:
        r, col = to_pixel(d['x'], d['y'], meta, (h, w))
        if not (0 <= r < h and 0 <= col < w):
            continue
        ok = bool(c['turnable'][r, col])
        ax.plot(col, r, marker='o', ms=9, mfc='white',
                mec=('#2E7D5B' if ok else '#A2337E'), mew=2.4, zorder=5)
        ax.annotate(d['name'], (col, r), textcoords='offset points',
                    xytext=(9, 6), fontsize=9, color='#14181D', zorder=6,
                    bbox=dict(boxstyle='round,pad=0.22', fc='white', ec='none', alpha=0.85))

    ax.set_title(
        f'{name} — 회전 가능 지도   (내접 {inner:.3f} m · 외접 {outer:.3f} m ·'
        f' 제자리 회전 필요 폭 {2*outer:.3f} m)', fontsize=11, pad=12)
    ax.legend(handles=[
        Patch(fc=COLORS['turnable'], label='여기서 바로 돈다'),
        Patch(fc=COLORS['near'],     label=f'{NEAR_M:.0f} m 안에 돌 곳이 있다'),
        Patch(fc=COLORS['far'],      label=f'{NEAR_M:.0f} m 넘게 가야 돈다'),
        Patch(fc=COLORS['trap'],     label='영영 못 돈다 (함정)'),
        Patch(fc=COLORS['tootight'], label='로봇이 못 섬'),
        Patch(fc=COLORS['unknown'],  label='미탐색'),
    ], loc='upper center', bbox_to_anchor=(0.5, -0.01), ncol=3, frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches='tight', facecolor='white')
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description='회전 가능 지도를 만든다')
    ap.add_argument('map', help='지도 이름 (예: vica_map_0630)')
    ap.add_argument('--out', help='그림 저장 경로 (기본: maps/<이름>_turnability.png)')
    ap.add_argument('--json', help='판정 결과를 JSON 으로도 저장')
    args = ap.parse_args()

    inner, outer, pad = robot_radii(WS)
    img, meta = load_map(args.map)
    c = classify(img, meta, inner, outer)

    cell = c['res'] ** 2
    free_n = int(c['free'].sum())
    stand_n = int(c['standable'].sum())
    print(f'=== {args.map} 회전 가능 지도 ===')
    print(f'  {img.shape[1]} x {img.shape[0]} px · {c["res"]} m/px')
    print(f'  내접 {inner:.3f} m · 외접 {outer:.3f} m (padding {pad}) '
          f'· 제자리 회전 필요 폭 {2*outer:.3f} m')
    print()
    tt = c['to_turn']
    fin = c['standable'] & np.isfinite(tt)
    rows = [
        ('로봇이 설 수 있는 곳', stand_n),
        ('  여기서 바로 돈다', int(c['turnable'].sum())),
        (f'  {NEAR_M:.0f} m 안에 돌 곳', int((fin & (tt > 0) & (tt <= NEAR_M)).sum())),
        (f'  {NEAR_M:.0f} m 넘게 가야 함', int((fin & (tt > NEAR_M)).sum())),
        ('  영영 못 돈다 (함정)', int(c['trap'].sum())),
    ]
    for label, n in rows:
        base = stand_n if label.startswith('  ') else free_n
        print(f'  {label:<26}{n*cell:7.1f} m2   ({100*n/max(base,1):5.1f} %)')
    print()

    d = tt[fin & (tt > 0)]
    if d.size:
        print('  돌 수 있는 곳까지 가야 하는 거리 (바로 못 도는 자리들)')
        for q in (50, 75, 90, 99):
            print(f'    {q:>2}%tile  {np.percentile(d, q):.2f} m')
        print(f'    최대      {d.max():.2f} m')
        print()

    dests = destinations(args.map)
    verdicts = []
    if dests:
        print('  목적지 판정')
        print(f'  {"이름":<10}{"여유":>8}{"설 수":>7}{"돌 수":>7}{"자리 성격":>14}'
              f'{"가장 가까운 회전 지점":>20}')
        print('  ' + '-' * 66)
        for d in sorted(dests, key=lambda q: q['name']):
            r, col = to_pixel(d['x'], d['y'], meta, img.shape)
            inside = 0 <= r < img.shape[0] and 0 <= col < img.shape[1]
            if not inside:
                print(f'  {d["name"]:<10}  지도 밖'); continue
            clr = float(c['clearance'][r, col])
            can_stand = bool(c['standable'][r, col])
            can_turn = bool(c['turnable'][r, col])
            far_v = float(c['to_turn'][r, col])
            if can_turn:
                kind = '바로 돈다'
            elif not can_stand:
                kind = '못 섬'
            elif not np.isfinite(far_v):
                kind = '함정'
            elif far_v <= NEAR_M:
                kind = f'{NEAR_M:.0f} m 안'
            else:
                kind = '멀다'
            far = float(c['to_turn'][r, col])
            verdicts.append({'name': d['name'], 'x': d['x'], 'y': d['y'],
                             'clearance': clr, 'standable': can_stand,
                             'turnable': can_turn, 'kind': kind,
                             'to_turnable': far})
            print(f'  {d["name"]:<10}{clr:7.3f}m{"O" if can_stand else "X":>6}'
                  f'{"O" if can_turn else "X":>7}{kind:>14}'
                  f'{(f"{far:.2f} m" if np.isfinite(far) else "못 감"):>20}')
        print()

    out = Path(args.out) if args.out else (WS / 'maps' / f'{args.map}_turnability.png')
    draw(c, meta, dests, out, args.map, inner, outer)
    print(f'  그림: {out}')
    if args.json:
        Path(args.json).write_text(json.dumps({
            'map': args.map, 'inner': inner, 'outer': outer,
            'need_width': 2 * outer,
            'area': {k.strip(): n * cell for k, n in rows},
            'destinations': verdicts}, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'  판정: {args.json}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
