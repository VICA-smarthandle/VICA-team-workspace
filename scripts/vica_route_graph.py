#!/usr/bin/env python3
"""레일(route graph)을 그린다 — nav2_route 가 읽는 GeoJSON 을 만든다.

무엇을 하나
    지도와 등록된 목적지를 읽어, 목적지들을 잇는 레일을 만든다. 레일은
    벽에 붙지 않고 **열린 공간 한가운데**로 지나간다. 결과는 두 개다.

        maps/<지도>_route.geojson   nav2_route 가 읽는 파일
        maps/<지도>_route.png       사람이 보고 고칠 그림

왜 한가운데로 지나가나
    레일은 '이 선 위로 다녀라'는 규칙이다. 선이 벽에 붙어 있으면 규칙을 지킬수록
    벽을 긁는다. 그래서 길을 찾을 때 거리뿐 아니라 **벽에서 떨어진 정도**도
    비용에 넣는다(PREFER_CLEAR).

어떻게 만드나
    0. 자유 공간 한가운데 흩어진 회색 잡티(미지 칸 몇 개짜리 섬)는 자유로 친다(SPECK_MAX_PX).
    1. 지도에서 '로봇이 설 수 있는 곳'(여유 >= 내접반경)을 길로 쓴다.
       회전 가능 구역만 쓰면 안 된다 - 2026-09-16 에 해 봤더니 그 구역이 섬으로
       나뉘어 있어 목적지 두 곳이 2~3 m 씩 밀렸다. 레일은 좁은 복도도 지나간다.
       거기서 돌 필요가 없을 뿐이다.
    2. 목적지마다 가장 가까운 '설 수 있는' 지점을 레일 진입점으로 삼는다.
       그 지점에서 돌 수 있는지는 따로 표시해 준다.
    3. 진입점을 잇는다. 두 가지 모양이 있다.
         고리(기본)  진입점을 방 중심 기준 각도 순으로 정렬해 고리로 잇는다.
                     방이 둥글게 늘어선 0630 같은 지도용.
         나무(--tree) 서로 가장 먼 두 진입점 사이를 등뼈로 깔고, 나머지는 레일까지
                     곁가지를 낸다. 일자 복도인 0903_d 같은 지도용. 고리로 닫으면
                     갔던 복도를 되돌아와 레일이 두 가닥으로 겹친다(2026-09-17).
    4. 두 점 사이는 설 수 있는 구역 안에서만 길을 찾는다(다익스트라).
    5. 그 길을 꺾이는 점만 남겨 단순화한다(Douglas-Peucker).
    6. 가까운 점끼리 합친다.
    7. 15~120° 코너를 반지름 ≤1.0 m 호로 둥글린다(FILLET_*, 안 들어가면 0.75·0.5 로 줄여 본다). 나무의 곁가지 접점은
       등뼈 양쪽으로 호를 두 개 놓아 Y 자로 만든다.
    8. 엣지를 MAX_EDGE_M(1 m) 이하로 쪼갠다 — 직선 복도에 중간역을 박는다.
    9. 양방향 엣지로 GeoJSON 을 쓴다.

형식
    /opt/ros/humble/share/nav2_route/graphs/*.geojson 의 실제 파일에서 확인했다.
        노드  {"type":"Feature","properties":{"id":N,"frame":"map"},
               "geometry":{"type":"Point","coordinates":[x,y]}}
        엣지  {"type":"Feature","properties":{"id":N,"startid":A,"endid":B},
               "geometry":{"type":"MultiLineString","coordinates":[[[x1,y1],[x2,y2]]]}}
    엣지는 **방향이 있다.** 양쪽으로 다니려면 두 개를 만들어야 한다.

쓰는 법
    python3 scripts/vica_route_graph.py vica_map_0630
    python3 scripts/vica_route_graph.py vica_map_0903_d --tree     일자 복도
    python3 scripts/vica_route_graph.py vica_map_0630 --loop-only   목적지 진입점만 잇는다
"""
from __future__ import annotations

import argparse
import heapq
import json
import math
import sys
from pathlib import Path

import numpy as np
import yaml
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vica_corridor_measure import robot_radii  # noqa: E402

WS = Path(__file__).resolve().parent.parent / 'vica_ros2_ws'

# Douglas-Peucker 가 재귀라, 경로가 길면 기본 한계(1000)에 걸린다.
sys.setrecursionlimit(50000)

# 벽에서 이만큼 떨어져 다니고 싶다. 그보다 가까우면 비용이 붙는다.
WANT_CLEAR = 1.00
PREFER_CLEAR = 6.0     # 여유 부족에 붙는 비용 배수. 크면 더 한가운데로 돈다
SIMPLIFY_M = 0.25      # 이보다 작게 꺾이는 점은 지운다
MERGE_M = 0.60         # 이보다 가까운 노드는 하나로 합친다
# 엣지(역과 역 사이) 상한. 2026-09-16 2판.
#   1판은 꺾이는 점만 남겨 직선 복도가 6.71 m 짜리 엣지 하나가 됐다. route_server
#   는 로봇이 첫 노드를 지나치면 그 노드를 잘라내는데(goal_intent_extractor.cpp),
#   엣지가 하나뿐이면 잘라낸 뒤 엣지 0개 -> 경로가 점 1개 -> controller 가
#   "zero length" 로 선다. 엣지를 짧게 두면 로봇이 어디 있든 앞에 엣지가 남는다.
#   1.0 m = 로봇 한 대 길이. 더 촘촘히 해도 마지막 엣지에서는 같은 일이 나므로
#   (그건 BT 의 IsRoutePathUsable 이 막는다) 그 이하로 줄일 이유가 없다.
MAX_EDGE_M = 1.00
# 코너 둥글리기 (fillet). 2026-09-16 run8.
#   nav2_route 의 smooth_corners 는 일직선 위 중간역(각 0°)을 둥글리다 NaN 을 넣어
#   껐다. 대신 여기서 코너를 호(arc)로 바꿔 GeoJSON 에 굽는다. 뾰족한 채 두면 DWB 가
#   코너를 지나쳤다 되돌아와 손잡이가 흔들린다(run8 방2→화장실 w ±0.29 왕복 2 s).
#   반지름은 코너 양쪽 엣지 길이에 맞춰 줄이고, 호 위의 점이 설 수 없는 칸이면 그
#   코너는 그대로 둔다(둥글리다 벽에 붙는 것보다 뾰족한 편이 낫다).
#   2026-09-17 run20: 상한 0.5→1.0. 접점 호 R 0.48 은 0.5 m/s 에서 w 1.04 rad/s 가 필요한데 상한이 0.5
#   라 로봇이 호 안쪽으로 0.3~0.4 m 잘라 들어가며 w 가 상한에 붙었다. R ≥ v/w = 1.0 이어야 상한 안에서
#   돈다. 좁은 곳(0630)은 1.0 이 안 들어가면 0.75·0.5 로 줄여 본다 — 뾰족한 채 두는 것보다 낫다.
FILLET_R = 1.00        # 호 반지름 상한(m). v 0.5 / w 0.5 = 1.0
FILLET_R_FALLBACK = (0.75, 0.50)   # 상한이 안 들어가는 코너에서 차례로 시도
FILLET_MIN_DEG = 15    # 이보다 덜 꺾이면 둥글릴 필요 없다
FILLET_MAX_DEG = 120   # 이보다 더 꺾이면 되돌아가는 스퍼(목적지 끝)라 호가 안 된다
FILLET_STEP_DEG = 20   # 호를 이 각도마다 점으로 찍는다
# 잡티. 2026-09-17 0903_d.
#   지도에는 자유 공간 한가운데 회색(미지, 205) 한두 칸짜리 점이 흩어져 있다(0903_d 128개,
#   0630 42개). 검은 칸(벽) 없이 회색만 있는 작은 섬은 '한 번도 못 본 칸'이지 물체가 아니다.
#   Nav2 도 이 칸을 부풀리지 않고(inflate_unknown 기본 false) planner 는 통과를 허용한다
#   (allow_unknown true). 그런데 이 생성기는 회색을 벽으로 세어 1 m 벌점 거품을 씌웠다 —
#   테스트2 옆 회색 점 한 줄이 등뼈를 0.7 m 남쪽으로 밀어 곁가지를 만들었고, 테스트_끝은
#   0.46 m 옆 점 하나 때문에 "못 돈다"가 됐다. 그래서 회색만으로 된 SPECK_MAX_PX 이하
#   섬은 자유로 친다. 검은 칸이 하나라도 섞인 섬은 그대로 벽이다(Nav2 가 부풀린다).
SPECK_MAX_PX = 40      # 0.1 m2. 이보다 큰 회색 덩어리는 '못 본 구역'일 수 있어 그대로 둔다
# 나무형(--tree) 곁가지 하한. 2026-09-17.
#   진입점이 레일에서 이보다 가까우면 곁가지를 내지 않는다. BT 는 목적지 이 거리 안에서
#   레일을 버리고 자유주행으로 넘기므로(IsRoutePathUsable handoff_dist_to_goal) 그 토막은
#   어차피 안 탄다. 등뼈는 복도 한가운데를 지키고 마지막 접근만 planner 가 그린다.
#   BT 의 handoff_dist_to_goal 을 바꾸면 여기도 맞출 것.
STUB_M = 2.00


def load_map(name):
    base = WS / 'maps' / name
    meta = yaml.safe_load(base.with_suffix('.yaml').read_text(encoding='utf-8'))
    return np.array(Image.open(str(base) + '.pgm')), meta


def free_mask(img):
    """자유 칸. 회색만으로 된 작은 섬(잡티)은 자유로 친다. (mask, 지운 섬 수)"""
    free = img > 250
    lab, n = ndimage.label(~free)
    if n == 0:
        return free, 0
    idx = range(1, n + 1)
    sizes = ndimage.sum(np.ones(img.shape, dtype=np.int32), lab, idx)
    blacks = ndimage.sum(img < 200, lab, idx)          # 섬 안의 벽 칸 수
    specks = [k + 1 for k in range(n) if sizes[k] <= SPECK_MAX_PX and blacks[k] == 0]
    if specks:
        free = free | np.isin(lab, specks)
    return free, len(specks)


def to_px(x, y, meta, shape):
    ox, oy = float(meta['origin'][0]), float(meta['origin'][1])
    res = float(meta['resolution'])
    return int(round(shape[0] - 1 - (y - oy) / res)), int(round((x - ox) / res))


def to_world(r, c, meta, shape):
    ox, oy = float(meta['origin'][0]), float(meta['origin'][1])
    res = float(meta['resolution'])
    return ox + c * res, oy + (shape[0] - 1 - r) * res


def dijkstra(mask, clearance, start, goal, res):
    """mask 안에서 start -> goal 최단경로. 벽에 가까울수록 비용이 붙는다.

    goal 은 셀 하나이거나 bool 배열(그중 비용이 가장 싼 셀까지)이다.
    """
    h, w = mask.shape
    INF = math.inf
    dist = np.full((h, w), INF)
    prev = {}
    dist[start] = 0.0
    pq = [(0.0, start)]
    nb = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
          (-1, -1, 1.4142), (-1, 1, 1.4142), (1, -1, 1.4142), (1, 1, 1.4142)]
    hit = (lambda rc: rc == goal) if isinstance(goal, tuple) else (lambda rc: bool(goal[rc]))
    found = None
    while pq:
        d, (r, c) = heapq.heappop(pq)
        if d > dist[r, c]:
            continue
        if hit((r, c)):
            found = (r, c)
            break
        for dr, dc, step in nb:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < h and 0 <= nc < w) or not mask[nr, nc]:
                continue
            short = max(0.0, WANT_CLEAR - clearance[nr, nc])
            nd = d + step * res * (1.0 + PREFER_CLEAR * short)
            if nd < dist[nr, nc]:
                dist[nr, nc] = nd
                prev[(nr, nc)] = (r, c)
                heapq.heappush(pq, (nd, (nr, nc)))
    if found is None:
        return None
    path, cur = [found], found
    while cur != start:
        cur = prev[cur]
        path.append(cur)
    return path[::-1]


def simplify(points, tol):
    """Douglas-Peucker. 꺾이는 점만 남긴다."""
    if len(points) < 3:
        return list(points)
    a, b = np.array(points[0], float), np.array(points[-1], float)
    ab = b - a
    n = np.hypot(*ab)
    if n < 1e-9:
        d = [np.hypot(*(np.array(p, float) - a)) for p in points]
    else:
        d = [abs(np.cross(ab, np.array(p, float) - a)) / n for p in points]
    i = int(np.argmax(d))
    if d[i] <= tol:
        return [points[0], points[-1]]
    return simplify(points[:i + 1], tol)[:-1] + simplify(points[i:], tol)


def nearest_true(mask, r, c):
    """(r,c) 에서 가장 가까운 mask=True 셀."""
    if mask[r, c]:
        return (r, c)
    idx = ndimage.distance_transform_edt(~mask, return_distances=False,
                                         return_indices=True)
    return int(idx[0][r, c]), int(idx[1][r, c])


def _fill_between(nd, nb, drivable, meta, shape):
    """두 노드 사이를 MAX_EDGE_M 이하로 쪼갤 사이 점들.

    사이 점은 두 노드를 잇는 직선 위에 고르게 놓는다. 그 자리가 '설 수 없는' 칸이면
    가장 가까운 설 수 있는 칸으로 옮긴다(꺾임 단순화 허용치가 0.25 m 라 직선이
    벽에 붙는 일은 드물지만, 붙으면 레일이 벽을 긁게 되므로 반드시 옮긴다).
    """
    out = []
    seg = math.dist(nd['xy'], nb['xy'])
    k = int(math.ceil(seg / MAX_EDGE_M)) - 1      # 끼워 넣을 점 개수
    for j in range(1, k + 1):
        t = j / (k + 1)
        wx = nd['xy'][0] + t * (nb['xy'][0] - nd['xy'][0])
        wy = nd['xy'][1] + t * (nb['xy'][1] - nd['xy'][1])
        r, c = to_px(wx, wy, meta, shape)
        r = min(max(r, 0), shape[0] - 1)
        c = min(max(c, 0), shape[1] - 1)
        rr, cc = nearest_true(drivable, r, c)
        if (rr, cc) != (r, c):
            wx, wy = to_world(rr, cc, meta, shape)
        out.append({'xy': (wx, wy), 'px': (rr, cc), 'filler': True})
    return out


def split_long_edges(nodes, drivable, meta, shape):
    """고리의 모든 엣지를 MAX_EDGE_M 이하로 쪼갠다."""
    out = []
    n = len(nodes)
    for i, nd in enumerate(nodes):
        out.append(nd)
        out.extend(_fill_between(nd, nodes[(i + 1) % n], drivable, meta, shape))
    return out


def split_chain_long(nodes, drivable, meta, shape):
    """열린 사슬의 엣지를 MAX_EDGE_M 이하로 쪼갠다. 끝점은 그대로."""
    out = []
    for i in range(len(nodes) - 1):
        out.append(nodes[i])
        out.extend(_fill_between(nodes[i], nodes[i + 1], drivable, meta, shape))
    out.append(nodes[-1])
    return out


def fillet_arc(a, b, c, drivable, meta, shape, t=None, r_max=None):
    """코너 b(a→b→c)를 호(arc) 위의 점들로 바꾼다. 못 바꾸면 None.

    양쪽 엣지 위에 접점 P1·P2 를 잡고 그 사이를 반지름 R 의 호로 잇는다. R 은
    FILLET_R 을 상한으로, 접점이 엣지의 45 % 를 넘지 않게 줄인다(다음 코너와 겹치지
    않도록). t 를 주면 접점 거리를 그 값으로 못 박는다(Y 접점의 두 호가 같은 점에서
    만나야 할 때).
    """
    va = (a[0] - b[0], a[1] - b[1]); vc = (c[0] - b[0], c[1] - b[1])
    la, lc = math.hypot(*va), math.hypot(*vc)
    if la < 1e-6 or lc < 1e-6:
        return None
    cosphi = max(-1.0, min(1.0, (va[0]*vc[0] + va[1]*vc[1]) / (la * lc)))
    phi = math.acos(cosphi)                # b 에서 본 내각
    theta = math.pi - phi                  # 진행 방향이 꺾이는 각
    if not (math.radians(FILLET_MIN_DEG) <= theta <= math.radians(FILLET_MAX_DEG)):
        return None
    # 접점 거리 t = R / tan(phi/2). 엣지의 45 % 안에 들도록 R 을 줄인다.
    tan_half = math.tan(phi / 2.0)
    if t is None:
        R = min(r_max or FILLET_R, 0.45 * min(la, lc) * tan_half)
    else:
        R = t * tan_half
    if R < 0.15:
        return None
    t = R / tan_half
    ua = (va[0] / la, va[1] / la); uc = (vc[0] / lc, vc[1] / lc)
    p1 = (b[0] + ua[0] * t, b[1] + ua[1] * t)
    p2 = (b[0] + uc[0] * t, b[1] + uc[1] * t)
    bis = (ua[0] + uc[0], ua[1] + uc[1]); lb = math.hypot(*bis)
    if lb < 1e-6:
        return None
    d_center = R / math.sin(phi / 2.0)
    o = (b[0] + bis[0] / lb * d_center, b[1] + bis[1] / lb * d_center)
    a1 = math.atan2(p1[1] - o[1], p1[0] - o[0]); a2 = math.atan2(p2[1] - o[1], p2[0] - o[0])
    sweep = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi    # 짧은 쪽으로
    steps = max(2, int(math.ceil(abs(sweep) / math.radians(FILLET_STEP_DEG))))
    pts = []
    for k in range(steps + 1):
        ang = a1 + sweep * k / steps
        x, y = o[0] + R * math.cos(ang), o[1] + R * math.sin(ang)
        r, col = to_px(x, y, meta, shape)
        if not (0 <= r < shape[0] and 0 <= col < shape[1]) or not drivable[r, col]:
            return None
        pts.append({'xy': (x, y), 'px': (r, col), 'fillet': True})
    return pts


def fillet_try(a, b, c, drivable, meta, shape):
    """상한 반지름부터 시도해 들어가는 첫 호를 돌려준다. 다 안 들어가면 None(뾰족한 채)."""
    for r in (FILLET_R,) + tuple(FILLET_R_FALLBACK):
        pts = fillet_arc(a, b, c, drivable, meta, shape, r_max=r)
        if pts:
            return pts
    return None


def fillet_corners(nodes, drivable, meta, shape):
    """고리의 꺾이는 노드를 호 위의 점 여러 개로 바꾼다."""
    n = len(nodes)
    out = []
    for i, nd in enumerate(nodes):
        pts = fillet_try(nodes[i - 1]['xy'], nd['xy'], nodes[(i + 1) % n]['xy'],
                         drivable, meta, shape)
        out.extend(pts if pts else [nd])
    return out


def fillet_chain(nodes, drivable, meta, shape):
    """열린 사슬의 안쪽 코너만 둥글린다. 끝점(접점·진입점)과 이미 호인 점은 그대로."""
    if len(nodes) < 3:
        return nodes
    out = [nodes[0]]
    for i in range(1, len(nodes) - 1):
        nd = nodes[i]
        pts = None if nd.get('fillet') else fillet_try(
            nodes[i - 1]['xy'], nd['xy'], nodes[i + 1]['xy'], drivable, meta, shape)
        out.extend(pts if pts else [nd])
    out.append(nodes[-1])
    return out


def _tangent_limit(a, b, c, r_max=None):
    """코너 b 에서 fillet_arc 가 기본으로 잡는 접점 거리(엣지 45 %·R 상한)."""
    va = (a[0] - b[0], a[1] - b[1]); vc = (c[0] - b[0], c[1] - b[1])
    la, lc = math.hypot(*va), math.hypot(*vc)
    if la < 1e-6 or lc < 1e-6:
        return None
    cosphi = max(-1.0, min(1.0, (va[0]*vc[0] + va[1]*vc[1]) / (la * lc)))
    phi = math.acos(cosphi)
    tan_half = math.tan(phi / 2.0)
    if tan_half < 1e-6:
        return None
    return min(r_max or FILLET_R, 0.45 * min(la, lc) * tan_half) / tan_half


def fillet_junction(chains, j_px, spur_i, drivable, meta, shape):
    """곁가지 접점을 Y 자로 만든다. 등뼈 양쪽에서 곁가지로 드는 호 두 개를 놓고,
    곁가지는 접점 J 대신 두 호가 만나는 점 S' 에서 시작한다.

        등뼈  … W1 ── W' ── J ── E' ── E1 …
                       ╲          ╱
                        호       호
                         ╲      ╱
                           S'
                           │  곁가지
                           S1 …

    T 자(등뼈 사슬이 J 로 하나 들어오고 하나 나감)가 아니거나 호를 놓을 자리가
    없으면 False 를 돌려주고 뾰족한 채 둔다.
    """
    spur = chains[spur_i]
    ins = [k for k, ch in enumerate(chains) if k != spur_i and ch[-1]['px'] == j_px]
    outs = [k for k, ch in enumerate(chains) if k != spur_i and ch[0]['px'] == j_px]
    if len(ins) != 1 or len(outs) != 1 or len(spur) < 2:
        return False
    W, E = chains[ins[0]], chains[outs[0]]
    if len(W) < 2 or len(E) < 2:
        return False
    J, w1, e1, s1 = spur[0]['xy'], W[-2]['xy'], E[1]['xy'], spur[1]['xy']
    arc_w = arc_e = None
    for r in (FILLET_R,) + tuple(FILLET_R_FALLBACK):      # 상한부터, 안 들어가면 줄여 본다
        tw, te = _tangent_limit(w1, J, s1, r), _tangent_limit(e1, J, s1, r)
        if tw is None or te is None:
            return False
        t = min(tw, te)
        arc_w = fillet_arc(w1, J, s1, drivable, meta, shape, t=t)
        arc_e = fillet_arc(e1, J, s1, drivable, meta, shape, t=t)
        if arc_w is not None and arc_e is not None:
            break
    if arc_w is None or arc_e is None:
        return False
    s_new = arc_w[-1]                       # S'. 같은 t 라 arc_e[-1] 과 같은 점
    arc_e[-1] = s_new
    W.insert(len(W) - 1, arc_w[0])          # W'
    E.insert(1, arc_e[0])                   # E'
    spur[0] = s_new
    chains.append(arc_w)
    chains.append(arc_e)
    return True


def merge_chain(pts_rc, meta, shape):
    """가까운 점 합치기. 사슬 끝점(접점·진입점)은 반드시 남긴다."""
    nodes = []
    last_i = len(pts_rc) - 1
    for k, rc in enumerate(pts_rc):
        wx, wy = to_world(rc[0], rc[1], meta, shape)
        if nodes and math.dist((wx, wy), nodes[-1]['xy']) < MERGE_M:
            if k != last_i:
                continue
            if len(nodes) > 1:
                nodes.pop()
        nodes.append({'xy': (wx, wy), 'px': rc})
    return nodes


def split_chain_at(chains, cell):
    """cell 을 품은 사슬을 그 자리에서 둘로 쪼갠다(셀을 둘이 공유). 끝점이면 그대로."""
    for k, ch in enumerate(chains):
        if cell in ch:
            i = ch.index(cell)
            if i == 0 or i == len(ch) - 1:
                return
            chains[k:k + 1] = [ch[:i + 1], ch[i:]]
            return
    raise RuntimeError(f'접점 {cell} 이 어느 사슬에도 없다')


def load_destinations(name):
    """미션 매니저가 **실제로 쓰는** 목적지를 읽는다.

    2026-09-16 사고. 저장소의 location/<지도>/locations.json 을 읽어 레일을
    깔았는데, 미션 매니저는 ~/vica_data/destinations/<지도>/destinations.yaml 을
    쓴다. 두 파일의 좌표가 달랐고(안내소는 1.03 m), 이름도 달랐다
    (locations.json 의 방1·출구는 없고, destinations.yaml 에는 407호·작업실이 있다).
    그 결과 레일이 목적지를 빗나가 실주행에서 안내소가 1 m 어긋나고 화장실은
    아예 못 갔다. **정본은 destinations.yaml 이다.**

    home.yaml 도 함께 읽는다. 안내가 끝나면 로봇이 그리로 돌아가므로 레일 위에
    있어야 한다.
    """
    out = []
    root = Path.home() / 'vica_data' / 'destinations' / name
    doc = root / 'destinations.yaml'
    if doc.exists():
        data = yaml.safe_load(doc.read_text(encoding='utf-8')) or {}
        for d in data.get('destinations', []):
            po = d.get('pose') or {}
            if po.get('x') is None:
                continue
            out.append({'name': d.get('name', '?'), 'x': float(po['x']),
                        'y': float(po['y']), 'yaw': float(po.get('yaw', 0.0)),
                        'src': 'destinations.yaml'})
        home = root / 'home.yaml'
        if home.exists():
            h = (yaml.safe_load(home.read_text(encoding='utf-8')) or {}).get('pose') or {}
            if h.get('x') is not None:
                out.append({'name': '홈', 'x': float(h['x']), 'y': float(h['y']),
                            'yaw': float(h.get('yaw', 0.0)), 'src': 'home.yaml'})
        print(f'  목적지 출처: {doc}')
        return out

    # 예비: 저장소 사본. 미션 매니저가 안 쓰는 파일이므로 경고한다.
    alt = WS / 'location' / name / 'locations.json'
    if alt.exists():
        print(f'  [!] {doc} 가 없다. 저장소 사본을 쓴다: {alt}')
        print('      미션 매니저가 쓰는 파일이 아니라 좌표가 다를 수 있다.')
        return [{'name': d['name'], 'x': d['x'], 'y': d['y'],
                 'yaw': float(d.get('yaw', 0.0)), 'src': 'locations.json'}
                for d in json.loads(alt.read_text(encoding='utf-8'))]
    print('  목적지 파일을 못 찾았다.')
    return []


def _path_len_m(path, res):
    return sum(math.dist(path[i], path[i + 1]) for i in range(len(path) - 1)) * res


def build_loop(entries, drivable, clearance, meta, shape, res, loop_only):
    """고리: 진입점을 방 중심 기준 각도 순으로 이어 닫는다. (노드 목록, 엣지 목록)"""
    cx = float(np.mean([e['world'][0] for e in entries]))
    cy = float(np.mean([e['world'][1] for e in entries]))
    entries.sort(key=lambda e: math.atan2(e['world'][1] - cy, e['world'][0] - cx))

    # 이웃끼리 길을 찾아 이어 붙인다.
    polyline = []
    m = len(entries)
    for i in range(m if not loop_only else m):
        a, b = entries[i], entries[(i + 1) % m]
        path = dijkstra(drivable, clearance, a['px'], b['px'], res)
        if path is None:
            print(f'    [X] {a["name"]} -> {b["name"]} 길 없음')
            continue
        pts = simplify(path, SIMPLIFY_M / res)
        if polyline and pts and polyline[-1] == pts[0]:
            pts = pts[1:]
        polyline.extend(pts)

    # 가까운 점 합치기
    nodes = []
    for rc in polyline:
        wx, wy = to_world(rc[0], rc[1], meta, shape)
        if nodes and math.dist((wx, wy), nodes[-1]['xy']) < MERGE_M:
            continue
        nodes.append({'xy': (wx, wy), 'px': rc})
    # 고리이므로 첫 점과 마지막 점이 겹치면 지운다.
    if len(nodes) > 2 and math.dist(nodes[0]['xy'], nodes[-1]['xy']) < MERGE_M:
        nodes.pop()

    # 코너를 호로 바꾼다(생성기 자체 둥글리기 — nav2 smooth_corners 는 끈다).
    nodes = fillet_corners(nodes, drivable, meta, shape)
    # 긴 엣지를 MAX_EDGE_M 이하로 쪼갠다. 꺾이는 점(위)은 그대로 두고 사이만 채운다.
    nodes = split_long_edges(nodes, drivable, meta, shape)

    for i, nd in enumerate(nodes):
        nd['id'] = i + 1
    edges = [(nodes[i], nodes[(i + 1) % len(nodes)]) for i in range(len(nodes))]
    return nodes, edges


def build_tree(entries, drivable, clearance, meta, shape, res):
    """나무: 등뼈(가장 먼 두 진입점) + 곁가지. (노드 목록, 엣지 목록) 또는 None"""
    a, b = max(((p, q) for p in entries for q in entries),
               key=lambda pq: math.dist(pq[0]['world'], pq[1]['world']))
    spine = dijkstra(drivable, clearance, a['px'], b['px'], res)
    if spine is None:
        print(f'    [X] 등뼈 {a["name"]} -> {b["name"]} 길 없음')
        return None
    print(f'  등뼈 {a["name"]} -> {b["name"]}  {_path_len_m(spine, res):.1f} m')
    chains = [list(spine)]                  # 원본 셀 경로(사슬). 접점에서 쪼개 셀을 공유한다
    rail = np.zeros_like(drivable)
    rail[tuple(np.array(spine).T)] = True
    a['kind'] = b['kind'] = '등뼈 끝'
    spurs = []                              # (접점 셀, 곁가지 사슬 번호)
    for e in entries:
        if e is a or e is b:
            continue
        path = dijkstra(drivable, clearance, e['px'], rail, res)
        if path is None:
            print(f'    [X] {e["name"]} -> 레일 길 없음')
            e['kind'] = '연결 실패'
            continue
        L = _path_len_m(path, res)
        if L < STUB_M:
            e['kind'] = f'등뼈 옆 {L:.2f} m — 곁가지 없음(BT 인계 거리 {STUB_M:.1f} m 안)'
            continue
        junction = path[-1]
        split_chain_at(chains, junction)
        spur = path[::-1]                   # 접점 -> 진입점
        chains.append(spur)
        rail[tuple(np.array(spur).T)] = True
        spurs.append((junction, len(chains) - 1))
        e['kind'] = f'곁가지 {L:.2f} m'

    # 사슬마다: 단순화 -> 합치기
    node_chains = []
    for ch in chains:
        pts = simplify(ch, SIMPLIFY_M / res)
        node_chains.append(merge_chain(pts, meta, shape))
    # 접점을 Y 자로 (등뼈 양쪽 호). 사슬 번호는 위 순서 그대로다.
    sharp = 0
    for j_px, spur_i in spurs:
        if not fillet_junction(node_chains, j_px, spur_i, drivable, meta, shape):
            sharp += 1
    if sharp:
        print(f'  [!] 호를 놓지 못한 접점 {sharp}개 — 뾰족한 채 둔다')
    # 사슬 안쪽 코너 둥글리기 -> 1 m 쪼개기
    node_chains = [split_chain_long(fillet_chain(ch, drivable, meta, shape), drivable, meta, shape)
                   for ch in node_chains]

    # id: 같은 셀 = 같은 노드(접점 공유)
    nodes, by_px = [], {}
    for ch in node_chains:
        for k, nd in enumerate(ch):
            if nd['px'] in by_px:
                ch[k] = by_px[nd['px']]
                continue
            nd['id'] = len(nodes) + 1
            by_px[nd['px']] = nd
            nodes.append(nd)
    edges = [(ch[i], ch[i + 1]) for ch in node_chains for i in range(len(ch) - 1)
             if ch[i] is not ch[i + 1]]
    return nodes, edges


def build(name, loop_only, tree=False):
    inner, outer, pad = robot_radii(WS)
    img, meta = load_map(name)
    res = float(meta['resolution'])
    free, specks = free_mask(img)
    clearance = ndimage.distance_transform_edt(free) * res
    turnable = free & (clearance >= outer)      # 여기선 돌 수 있다(표시용)
    drivable = free & (clearance >= inner)      # 여기로 다닐 수 있다(길)
    if not drivable.any():
        print('로봇이 설 수 있는 곳이 없다. 지도나 footprint 를 확인하라.')
        return None

    # 가장 큰 덩어리만 쓴다. 떨어진 섬끼리는 레일로 못 잇는다.
    lab, n = ndimage.label(drivable)
    if n > 1:
        big = 1 + int(np.argmax(np.bincount(lab.ravel())[1:]))
        drivable = lab == big
        turnable = turnable & drivable

    dests = load_destinations(name)
    if len(dests) < 2:
        print('목적지가 2개 미만이라 고리를 못 만든다.')
        return None

    # 목적지마다 레일 진입점 (가장 가까운 설 수 있는 셀)
    entries = []
    for d in dests:
        r, c = to_px(d['x'], d['y'], meta, img.shape)
        r = min(max(r, 0), img.shape[0] - 1)
        c = min(max(c, 0), img.shape[1] - 1)
        rr, cc = nearest_true(drivable, r, c)
        entries.append({'name': d['name'], 'px': (rr, cc),
                        'world': to_world(rr, cc, meta, img.shape),
                        'dest': (d['x'], d['y']), 'yaw': d.get('yaw', 0.0),
                        'can_turn': bool(turnable[rr, cc]), 'kind': ''})

    print(f'  다닐 수 있는 구역 {drivable.sum()*res*res:.1f} m2 '
          f'(그중 회전 가능 {turnable.sum()*res*res:.1f} m2) · 목적지 {len(entries)}개 '
          f'· 자유로 친 회색 잡티 섬 {specks}개')

    if tree:
        built = build_tree(entries, drivable, clearance, meta, img.shape, res)
        if built is None:
            return None
    else:
        built = build_loop(entries, drivable, clearance, meta, img.shape, res, loop_only)
    nodes, edges = built

    print('  레일 진입점')
    for e in entries:
        off = math.dist(e['world'], e['dest'])
        print(f'    {e["name"]:<8} ({e["world"][0]:6.2f}, {e["world"][1]:6.2f})  '
              f'목적지에서 {off:.2f} m  yaw {e.get("yaw", 0):4.0f}도  '
              f'{"여기서 돈다" if e["can_turn"] else "여기선 못 돈다"}'
              + (f'  · {e["kind"]}' if e['kind'] else ''))

    for nd in nodes:
        nd['can_turn'] = bool(turnable[nd['px'][0], nd['px'][1]])
    return {'nodes': nodes, 'edges': edges, 'entries': entries, 'turnable': turnable,
            'drivable': drivable,
            'free': free, 'clearance': clearance, 'meta': meta,
            'img': img, 'inner': inner, 'outer': outer, 'res': res, 'tree': tree}


def write_geojson(g, out):
    feats = []
    for nd in g['nodes']:
        feats.append({'type': 'Feature',
                      'properties': {'id': nd['id'], 'frame': 'map'},
                      'geometry': {'type': 'Point',
                                   'coordinates': [round(nd['xy'][0], 4),
                                                   round(nd['xy'][1], 4)]}})
    eid = 1000
    for nd, nb in g['edges']:
        for a, b in ((nd, nb), (nb, nd)):   # 양방향
            eid += 1
            feats.append({'type': 'Feature',
                          'properties': {'id': eid, 'startid': a['id'], 'endid': b['id']},
                          'geometry': {'type': 'MultiLineString',
                                       'coordinates': [[[round(a['xy'][0], 4), round(a['xy'][1], 4)],
                                                        [round(b['xy'][0], 4), round(b['xy'][1], 4)]]]}})
    doc = {'type': 'FeatureCollection', 'name': 'vica_route_graph',
           'crs': {'type': 'name', 'properties': {'name': 'urn:ogc:def:crs:EPSG::3857'}},
           'features': feats}
    Path(out).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding='utf-8')
    return len(g['nodes']), eid - 1000


def draw(g, out, name):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    for cand in ('NanumGothic', 'NanumBarunGothic', 'Noto Sans CJK JP'):
        try:
            matplotlib.font_manager.findfont(cand, fallback_to_default=False)
            matplotlib.rcParams['font.family'] = cand
            break
        except Exception:
            continue
    matplotlib.rcParams['axes.unicode_minus'] = False

    h, w = g['free'].shape
    rgb = np.zeros((h, w, 3))
    rgb[:] = (0.20, 0.20, 0.22)
    rgb[(g['img'] > 100) & (g['img'] <= 250)] = (0.55, 0.55, 0.57)
    rgb[g['free']] = (0.90, 0.90, 0.92)
    rgb[g['turnable']] = (0.80, 0.90, 0.85)

    fig, ax = plt.subplots(figsize=(max(8.0, w / 90), max(8.0, w / 90) * h / w + 1.0), dpi=150)
    ax.imshow(rgb, interpolation='nearest')
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)

    nodes = g['nodes']
    for nd, nb in g['edges']:
        ax.plot([nd['px'][1], nb['px'][1]], [nd['px'][0], nb['px'][0]],
                '-', color='#1F6F8B', lw=2.4, zorder=3)
    for nd in nodes:
        ax.plot(nd['px'][1], nd['px'][0], 'o', ms=6.5 if nd['can_turn'] else 4.5,
                mfc=('#2E7D5B' if nd['can_turn'] else '#B5721E'),
                mec='white', mew=1.2, zorder=4)
    for e in g['entries']:
        ax.plot(e['px'][1], e['px'][0], 'o', ms=10, mfc='white',
                mec='#A2337E', mew=2.4, zorder=5)
        ax.annotate(e['name'], (e['px'][1], e['px'][0]), textcoords='offset points',
                    xytext=(9, 6), fontsize=9, zorder=6,
                    bbox=dict(boxstyle='round,pad=0.22', fc='white', ec='none', alpha=0.85))

    turn_n = sum(1 for nd in nodes if nd['can_turn'])
    shape = '나무형 레일' if g.get('tree') else '레일'
    ax.set_title(f'{name} — {shape} (노드 {len(nodes)}개, 그중 회전 가능 {turn_n}개)   '
                 f'연한 초록 바닥 = 제자리 회전 가능 구역\n'
                 f'초록 점 = 여기서 돌 수 있다 · 주황 점 = 지나가기만',
                 fontsize=10, pad=10)
    fig.tight_layout()
    fig.savefig(out, bbox_inches='tight', facecolor='white')
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description='nav2_route 용 레일 GeoJSON 을 만든다')
    ap.add_argument('map')
    ap.add_argument('--loop-only', action='store_true')
    ap.add_argument('--tree', action='store_true',
                    help='고리 대신 등뼈+곁가지(일자 복도용)')
    ap.add_argument('--out-dir', default=str(WS / 'maps'))
    args = ap.parse_args()

    print(f'=== {args.map} 레일 만들기 ({"나무형" if args.tree else "고리"}) ===')
    g = build(args.map, args.loop_only, tree=args.tree)
    if g is None:
        return 1
    od = Path(args.out_dir)
    gj = od / f'{args.map}_route.geojson'
    png = od / f'{args.map}_route.png'
    n, e = write_geojson(g, gj)
    draw(g, png, args.map)
    lens = [math.dist(a['xy'], b['xy']) for a, b in g['edges']]
    print()
    print(f'  노드 {n}개 · 엣지 {e}개(양방향) · 레일 총 길이 {sum(lens):.1f} m')
    print(f'  가장 긴 엣지 {max(lens):.2f} m (상한 {MAX_EDGE_M:.2f} m)')
    # 꺾임: 이웃이 정확히 둘인 노드에서만 잰다(고리는 전부, 나무는 끝점·접점 제외).
    adj = {}
    for a, b in g['edges']:
        adj.setdefault(a['id'], []).append(b)
        adj.setdefault(b['id'], []).append(a)
    turns = []
    for nd in g['nodes']:
        nbs = adj.get(nd['id'], [])
        if len(nbs) != 2:
            continue
        a, b, c = nbs[0]['xy'], nd['xy'], nbs[1]['xy']
        v1 = (b[0] - a[0], b[1] - a[1]); v2 = (c[0] - b[0], c[1] - b[1])
        turns.append(abs(math.degrees(math.atan2(v1[0]*v2[1] - v1[1]*v2[0], v1[0]*v2[0] + v1[1]*v2[1]))))
    mid = [t for t in turns if 30 <= t <= FILLET_MAX_DEG]
    print(f'  30~{FILLET_MAX_DEG}° 꺾임 남은 노드 {len(mid)}개 (둥글리기 목표 0) · 되돌림(>{FILLET_MAX_DEG}°) {sum(1 for t in turns if t > FILLET_MAX_DEG)}개')
    if g.get('tree'):
        junctions = sum(1 for v in adj.values() if len(v) >= 3)
        print(f'  접점(엣지 3개 이상) {junctions}개 · 고리 수 {len(g["edges"]) - n + 1}개(Y 접점마다 1개가 정상)')
    print(f'  {gj}')
    print(f'  {png}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
