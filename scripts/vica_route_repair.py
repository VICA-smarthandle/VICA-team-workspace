#!/usr/bin/env python3
"""레일(route geojson)이 벽에 너무 가까운 곳을 밀어낸다.

    python3 scripts/vica_route_repair.py vica_map_0903_d [--apply] [--min-clear 0.70]

**왜 필요한가** (2026-09-21)
생성기는 Dijkstra 비용에 여유 선호(PREFER_CLEAR)를 넣지만 **하드 제약이 아니고**,
코너 호(fillet)와 엣지 쪼개기는 그 뒤에 **직선 현(chord)** 으로 만든다. 굽은 복도를
1 m 직선으로 이으면 그 직선이 벽에 가까워질 수 있다.

실측: **0903_d 는 멀쩡하다**(간선 최소 0.92 m). **0630 은 74개 중 10개가 외접반경
0.62 m 보다 가깝고 최소 0.50 m** 다 — 그 위를 로봇이 따라가면 몸통이 닿는다.
0630 에서 코너를 못 빠져나온 실주행(run29)과 맞는다.

**[측정 함정] 벽은 `img == 0` 이다.** `img > 250`(자유공간의 여집합)으로 잡으면
회색(미탐색)까지 벽으로 세어 여유가 터무니없이 작게 나온다. 같은 날 이 실수로
멀쩡한 0903_d 레일을 "벽 0.05 m 를 지난다"고 오진했다.

**무엇을 하나**
위상(노드 id·연결)은 **그대로 두고** 문제 노드만 자유공간 쪽으로 민다. 목적지 등록·
계약 시험·회차 비교가 깨지지 않게 하기 위함이다. 노드 위치만 바뀐다.

**판정 기준**: 노드 자신과 그 노드가 낀 **모든 간선을 5 cm 간격으로 훑어** 최소 여유가
`--min-clear` 이상이어야 한다. 기본 0.70 m = 외접반경 0.620 + 여유 0.08.
"""
import argparse, json, math, shutil, sys
from pathlib import Path
import numpy as np
import yaml
from PIL import Image
from scipy import ndimage

WS = Path(__file__).resolve().parent.parent / 'vica_ros2_ws'
MAX_MOVE = 0.50     # 노드를 이보다 멀리 옮기지 않는다(레일 모양이 달라진다)
STEP = 0.05         # 간선을 훑는 간격(m)
SEARCH = 0.05       # 후보 격자 간격(m)


def load(map_name):
    img = np.array(Image.open(WS / 'maps' / f'{map_name}.pgm'))
    meta = yaml.safe_load((WS / 'maps' / f'{map_name}.yaml').read_text())
    res = meta['resolution']
    ox, oy = meta['origin'][0], meta['origin'][1]
    # **벽의 정의는 img == 0 (점유)이다.** img > 250 로 잡으면 회색(미탐색)까지
    # 벽으로 세어 여유가 터무니없이 작게 나온다 — 2026-09-21 에 이 실수로 멀쩡한
    # 레일을 "벽 0.05 m 를 지난다"고 오진했다. 실제 최소는 0.90 m 였다.
    # 미탐색은 global_costmap 만 track_unknown_space: true 이고 planner 는
    # allow_unknown: true 다. local(컨트롤러)은 미탐색을 자유공간으로 본다.
    dist = ndimage.distance_transform_edt(~(img == 0)) * res
    H, W = img.shape

    def clear(x, y):
        c = int((x - ox) / res)
        r = H - 1 - int((y - oy) / res)
        if 0 <= r < H and 0 <= c < W:
            return float(dist[r, c])
        return float('nan')
    return clear


def edge_clear(clear, A, B):
    """두 점을 잇는 직선의 최소 여유."""
    L = math.hypot(B[0] - A[0], B[1] - A[1])
    n = max(int(L / STEP), 2)
    vals = []
    for t in np.linspace(0, 1, n):
        c = clear(A[0] + (B[0] - A[0]) * t, A[1] + (B[1] - A[1]) * t)
        if np.isfinite(c):
            vals.append(c)
    return min(vals) if vals else float('nan')


def node_score(clear, nid, pos, nbrs, N):
    """그 노드가 낀 모든 간선 + 자기 자신의 최소 여유."""
    vals = [clear(*pos)]
    for m in nbrs[nid]:
        vals.append(edge_clear(clear, pos, N[m]))
    vals = [v for v in vals if np.isfinite(v)]
    return min(vals) if vals else float('nan')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('map')
    ap.add_argument('--min-clear', type=float, default=0.70)
    ap.add_argument('--apply', action='store_true', help='실제로 파일을 고친다(기본은 점검만)')
    A = ap.parse_args()

    gpath = WS / 'maps' / f'{A.map}_route.geojson'
    gj = json.loads(gpath.read_text())
    N = {f['properties']['id']: list(f['geometry']['coordinates'])
         for f in gj['features'] if f['geometry']['type'] == 'Point'}
    E = sorted({tuple(sorted((f['properties']['startid'], f['properties']['endid'])))
                for f in gj['features'] if f['geometry']['type'] != 'Point'})
    nbrs = {k: [] for k in N}
    for a, b in E:
        nbrs[a].append(b)
        nbrs[b].append(a)
    clear = load(A.map)

    def report(tag):
        worst = sorted((edge_clear(clear, N[a], N[b]), a, b) for a, b in E)
        bad = [w for w in worst if w[0] < A.min_clear]
        print(f'  [{tag}] 간선 최소 {worst[0][0]:.2f} m · '
              f'{A.min_clear} m 미만 {len(bad)}/{len(E)}개')
        return worst, bad

    print(f'== {A.map} : 노드 {len(N)} · 간선 {len(E)} · 기준 {A.min_clear} m ==')
    worst0, bad0 = report('수리 전')
    for mn, a, b in worst0[:8]:
        if mn < A.min_clear:
            print(f'      {mn:.2f} m   {a} - {b}')

    if not bad0:
        print('  고칠 것이 없다.')
        return 0

    # 문제 간선에 닿은 노드만 대상으로 반복해서 민다
    moved = {}
    for _ in range(6):
        targets = set()
        for mn, a, b in ((edge_clear(clear, N[a], N[b]), a, b) for a, b in E):
            if mn < A.min_clear:
                targets.add(a)
                targets.add(b)
        if not targets:
            break
        改 = False
        for nid in sorted(targets):
            x0, y0 = N[nid]
            base = node_score(clear, nid, [x0, y0], nbrs, N)
            best, bp = base, None
            rng = np.arange(-MAX_MOVE, MAX_MOVE + 1e-9, SEARCH)
            for dx in rng:
                for dy in rng:
                    if math.hypot(dx, dy) > MAX_MOVE:
                        continue
                    p = [x0 + dx, y0 + dy]
                    # 원래 자리에서 얼마나 멀어졌는지도 함께 본다(동점이면 덜 움직인 쪽)
                    s = node_score(clear, nid, p, nbrs, N)
                    if not np.isfinite(s):
                        continue
                    if s > best + 1e-4:
                        best, bp = s, p
            if bp is not None:
                N[nid] = bp
                moved[nid] = (math.hypot(bp[0] - x0, bp[1] - y0), base, best)
                改 = True
        if not 改:
            break

    worst1, bad1 = report('수리 후')
    print(f'  옮긴 노드 {len(moved)}개')
    for nid, (d, b0, b1) in sorted(moved.items(), key=lambda kv: -kv[1][0])[:10]:
        print(f'      {nid:>3}  {d*100:5.1f} cm 이동   여유 {b0:.2f} -> {b1:.2f} m')
    if bad1:
        print('  ※ 아직 기준 미달인 간선:')
        for mn, a, b in bad1:
            print(f'      {mn:.2f} m   {a} - {b}')

    # 목적지가 레일에서 떨어지지 않았는지 (계약 시험 DEST_TO_NODE_M = 0.60)
    dfile = Path.home() / 'vica_data' / 'destinations' / A.map / 'destinations.yaml'
    if dfile.is_file():
        far = []
        for d in (yaml.safe_load(dfile.read_text()) or {}).get('destinations', []):
            po = d.get('pose') or {}
            if po.get('x') is None:
                continue
            dd = min(math.dist((po['x'], po['y']), tuple(v)) for v in N.values())
            if dd > 0.60:
                far.append((d.get('name'), round(dd, 2)))
        print(f'  목적지 검사: {"통과" if not far else f"※ 레일에서 먼 목적지 {far}"}')

    if not A.apply:
        print('\n  점검만 했다. 실제로 고치려면 --apply 를 붙인다.')
        return 0

    shutil.copy2(gpath, gpath.with_suffix('.geojson.bak'))
    for f in gj['features']:
        if f['geometry']['type'] == 'Point':
            f['geometry']['coordinates'] = N[f['properties']['id']]
    gpath.write_text(json.dumps(gj, ensure_ascii=False, indent=1))
    print(f'\n  고쳤다. 원본은 {gpath.name}.bak')
    return 0


if __name__ == '__main__':
    sys.exit(main())
