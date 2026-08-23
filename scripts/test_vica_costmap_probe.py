#!/usr/bin/env python3
"""vica_costmap_probe.py 의 계산부를 ROS 2 없이 검증한다.

    python3 -m pytest scripts/test_vica_costmap_probe.py -q

왜 필요한가
    이 스크립트의 숫자로 nvblox 를 plugins 에서 뺄지 말지를 정한다. 세는 법이 틀리면
    잘못된 근거로 주행 설정을 바꾸게 되고, 그 뒤로는 아무도 그 숫자를 의심하지 않는다.
    특히 **99 를 INSCRIBED 로 보는 환산**(costmap_2d 내부값 253)이 틀리면 판정이
    통째로 뒤집힌다 — 2026-08-15 오전을 통째로 쓴 혼동이 그것이다.

    스냅샷을 뜨는 부분만 rclpy 를 쓰고, 세고 비교하는 부분은 순수 함수다. 그래서
    로봇도 카메라도 없는 노트북에서 여기까지는 확인할 수 있다.
"""

import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    'vica_costmap_probe', Path(__file__).resolve().with_name('vica_costmap_probe.py'))
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)


# ---------------------------------------------------------------------------
# 시험용 격자 만들기
# ---------------------------------------------------------------------------
def grid(name, fill=0, w=40, h=40, res=0.05, origin=(-1.0, -1.0), robot=(0.0, 0.0),
         slice_publishers=1):
    """2 x 2 m 짜리 local costmap 을 흉내 낸다. 로봇은 가운데 있다."""
    return probe.make_snapshot(
        name=name, width=w, height=h, resolution=res, origin=origin,
        data=[fill] * (w * h),
        robot={'frame': 'base_footprint', 'x': robot[0], 'y': robot[1], 'yaw': 0.0},
        slice_publishers=slice_publishers)


def put(snap, ix, iy, value):
    snap['data'][iy * snap['width'] + ix] = value


def band(snap, iy0, iy1, value):
    """가로 띠 하나를 채운다. 벽과 그 inflation 을 흉내 낸다."""
    for iy in range(iy0, iy1):
        for ix in range(snap['width']):
            put(snap, ix, iy, value)


# ---------------------------------------------------------------------------
# 값 범위 — 0~100 인가 0~255 인가
# ---------------------------------------------------------------------------
def test_내부값과_occupancy_grid_환산표가_맞다():
    assert probe.raw_to_og(0) == 0
    assert probe.raw_to_og(1) == 1
    assert probe.raw_to_og(128) == 50
    assert probe.raw_to_og(252) == 98
    assert probe.raw_to_og(253) == 99      # INSCRIBED
    assert probe.raw_to_og(254) == 100     # LETHAL
    assert probe.raw_to_og(255) == -1      # 미탐색


def test_98은_inscribed가_아니다():
    """99 와 98 사이가 planner 의 거부·통과 경계다. 한 칸 밀리면 판정이 뒤집힌다."""
    assert probe.count_cells([98] * 10)['inscribed'] == 0
    assert probe.count_cells([99] * 10)['inscribed'] == 10
    assert probe.count_cells([100] * 10)['inscribed'] == 10
    assert probe.count_cells([100] * 10)['lethal'] == 10
    assert probe.count_cells([99] * 10)['lethal'] == 0


def test_미탐색은_free와_섞이지_않는다():
    c = probe.count_cells([-1, -1, 0, 0, 30])
    assert c['unknown'] == 2
    assert c['positive'] == 1
    assert c['max'] == 30           # -1 이 최댓값 자리를 차지하지 않는다


# ---------------------------------------------------------------------------
# 로봇 주변 반경
# ---------------------------------------------------------------------------
def test_로봇_반경_밖의_벽은_안_센다():
    """2026-08-15 조사가 쓴 지표다. 반경이 새면 '자기 자리를 막는다'가 거짓이 된다."""
    g = grid('near')
    band(g, 30, 40, 100)                       # y >= +0.5 m 는 벽이다
    assert probe.summarize(g, 0.3)['near']['max'] == 0
    assert probe.summarize(g, 0.3)['near']['inscribed'] == 0
    assert probe.summarize(g, 0.7)['near']['max'] == 100


def test_로봇이_선_자리가_inscribed면_잡아낸다():
    g = grid('stuck')
    for iy in range(18, 22):
        for ix in range(18, 22):
            put(g, ix, iy, 99)                 # 로봇 발밑 ±0.1 m
    near = probe.summarize(g, 0.3)['near']
    assert near['max'] == 99
    assert near['inscribed'] == 16


def test_로봇_위치를_모르면_주변지표만_빈다():
    g = grid('no_tf')
    g['robot'] = None
    s = probe.summarize(g)
    assert s['near'] is None
    assert s['total'] == 1600          # 나머지는 그대로 나온다


# ---------------------------------------------------------------------------
# 스냅샷 파일
# ---------------------------------------------------------------------------
def test_저장했다_읽으면_같다(tmp_path):
    g = grid('roundtrip')
    band(g, 35, 40, 99)
    path = probe.save_snapshot(g, str(tmp_path / 'roundtrip.json'))
    back = probe.load_snapshot(path)
    assert back == g
    assert probe.summarize(back)['inscribed'] == 200


def test_형식이_다른_파일은_거부한다(tmp_path):
    p = tmp_path / 'bad.json'
    p.write_text(json.dumps({'format': 'something/else'}), encoding='utf-8')
    with pytest.raises(ValueError):
        probe.load_snapshot(str(p))


def test_칸수가_안_맞으면_거부한다(tmp_path):
    g = grid('short')
    g['data'] = g['data'][:-1]
    p = tmp_path / 'short.json'
    p.write_text(json.dumps(g), encoding='utf-8')
    with pytest.raises(ValueError):
        probe.load_snapshot(str(p))


# ---------------------------------------------------------------------------
# 비교 — 겹치기
# ---------------------------------------------------------------------------
def test_원점이_옮겨가도_같은_자리끼리_뺀다():
    """rolling window 라 로봇이 조금 움직이면 원점이 따라 움직인다.

    같은 월드 좌표에 같은 벽이 있으면 차이는 0 이어야 한다. 칸 번호로 그냥 빼면
    벽이 통째로 옮겨간 것처럼 보인다.
    """
    a = grid('a')
    b = grid('b', origin=(-1.0 + 0.10, -1.0), robot=(0.10, 0.0))   # 두 칸 이동
    for ix in range(a['width']):
        for iy in range(30, 40):
            put(a, ix, iy, 100)
    for ix in range(b['width']):
        for iy in range(30, 40):
            put(b, ix, iy, 100)

    dx, dy, residual, box = probe.align(a, b)
    assert (dx, dy) == (2, 0)
    assert residual < 1e-9
    c = probe.compare(a, b)
    assert c['rose'] == 0 and c['fell'] == 0
    assert c['overlap_cells'] == 38 * 40           # 겹치는 만큼만 본다


def test_칸이_반칸_어긋나면_잔차로_알려준다():
    a = grid('a')
    b = grid('b', origin=(-1.0 + 0.025, -1.0))
    _, _, residual, _ = probe.align(a, b)
    assert residual == pytest.approx(0.025)


def test_해상도가_다르면_비교하지_않는다():
    a = grid('a')
    b = grid('b', res=0.10)
    with pytest.raises(ValueError):
        probe.align(a, b)


def test_겹치는_영역이_없으면_비교하지_않는다():
    a = grid('a')
    b = grid('b', origin=(9.0, 9.0))
    with pytest.raises(ValueError):
        probe.align(a, b)


# ---------------------------------------------------------------------------
# 비교 — 판정
# ---------------------------------------------------------------------------
def nvblox_on_off():
    """nvblox 가 벽 앞에 한 겹을 더 얹고 있던 상황.

        A(켠 상태)   벽 100 + nvblox 가 얹은 99 한 겹
        B(끈 상태)   벽 100 만 남는다
    """
    a = grid('nvblox_on', slice_publishers=1)
    b = grid('nvblox_off', slice_publishers=0)
    band(a, 35, 40, 100)
    band(b, 35, 40, 100)
    band(a, 32, 35, 99)          # nvblox 기여분 3줄 = 120 칸
    band(b, 32, 35, 30)          # 껐더니 inflation 만 남았다
    return a, b


def test_기여가_있으면_줄었다고_판정한다():
    a, b = nvblox_on_off()
    c = probe.compare(a, b)
    assert c['overlap_a']['inscribed'] == 200 + 120
    assert c['overlap_b']['inscribed'] == 200
    assert c['inscribed_lost'] == 120
    assert c['inscribed_gained'] == 0
    assert c['fell'] == 120 and c['rose'] == 0
    assert c['max_fall'] == 69
    code, line = probe.verdict(c)
    assert code == 'decreased'
    assert '320' in line and '200' in line


def test_껐는데_그대로면_같다고_판정한다():
    """무해와 잔상이 같은 숫자로 나온다. 스크립트는 갈라내지 못하고, 갈라내는 척도 안 한다."""
    a, b = nvblox_on_off()
    b['data'] = list(a['data'])            # 껐는데 costmap 이 하나도 안 바뀌었다
    c = probe.compare(a, b)
    assert c['fell'] == 0 and c['rose'] == 0
    code, _ = probe.verdict(c)
    assert code == 'same'


def test_라이다_흔들림_정도는_같다로_본다():
    a, b = nvblox_on_off()
    b['data'] = list(a['data'])
    for ix in range(10):                   # 10 칸만 INSCRIBED 가 풀렸다
        put(b, ix, 34, 30)
    c = probe.compare(a, b)
    assert c['inscribed_lost'] == 10
    assert probe.verdict(c)[0] == 'same'


def test_늘어나면_판정_대상이_아니라고_말한다():
    a, b = nvblox_on_off()
    b['data'] = list(a['data'])
    band(b, 25, 32, 100)                   # 사람이 앞을 지나갔다
    c = probe.compare(a, b)
    assert c['inscribed_gained'] == 280
    assert probe.verdict(c)[0] == 'increased'


def test_미탐색이_생기고_사라진_것도_센다():
    a, b = nvblox_on_off()
    b['data'] = list(a['data'])
    put(a, 5, 5, -1)
    put(b, 6, 6, -1)
    c = probe.compare(a, b)
    assert c['unknown_only_a'] == 1        # A 만 모르던 칸
    assert c['unknown_only_b'] == 1        # B 에서 새로 모르게 된 칸
    # 미탐색이 섞인 칸은 오르내림에 넣지 않는다. -1 을 0 보다 작은 값으로 빼면 안 된다
    assert c['rose'] == 0 and c['fell'] == 0


# ---------------------------------------------------------------------------
# 글자 그림
# ---------------------------------------------------------------------------
def test_글자그림이_경계값을_제대로_찍는다():
    assert probe.to_char(0) == ' '
    assert probe.to_char(49) == '.'
    assert probe.to_char(98) == '+'
    assert probe.to_char(99) == '#'
    assert probe.to_char(100) == '@'
    assert probe.to_char(-1) == '?'


def test_차이그림이_inscribed_풀린_자리를_표시한다():
    a, b = nvblox_on_off()
    rows = probe.render_diff(a, b, 0.0, 0.0, 1.0, 20)
    assert len(rows) == 20 and len(rows[0]) == 20
    assert any('v' in r for r in rows)     # nvblox 가 얹었던 줄이 풀렸다
    assert not any('^' in r for r in rows)


def test_격자_밖은_None이다():
    g = grid('edge')
    assert probe.value_at_world(g, 0.0, 0.0) == 0
    assert probe.value_at_world(g, 5.0, 0.0) is None


def test_칸_중심은_반칸_안쪽이다():
    g = grid('center')
    assert probe.cell_center(g, 0, 0) == pytest.approx((-0.975, -0.975))


# ---------------------------------------------------------------------------
# 스크립트가 스스로 하는 검사
# ---------------------------------------------------------------------------
def test_자체검사가_통과한다():
    probe.selftest()


# ---------------------------------------------------------------------------
# 판정 문턱 — 0점 측정
# ---------------------------------------------------------------------------
def test_흔들림_폭을_직접_주면_그것을_쓴다():
    """벽 가까이 세우면 INSCRIBED 총량은 벽이 차지한다. 총량에 비례한 기본 문턱은
    정작 재려는 변화를 덮는다. 그래서 0점 측정값을 넣을 수 있어야 한다."""
    a, b = nvblox_on_off()
    c = probe.compare(a, b)               # 120 칸이 줄어든 상황
    assert probe.verdict(c, noise=300)[0] == 'same'        # 흔들림이 크다고 알려 주면
    assert probe.verdict(c, noise=50)[0] == 'decreased'    # 작다고 알려 주면
    assert '0점 측정으로 준 값' in probe.verdict(c, noise=50)[1]
    assert '0점 측정을 안 했다' in probe.verdict(c)[1]


def test_block_max는_칸_최댓값과_미탐색을_함께_준다():
    g = grid('blk', w=4, h=4, res=0.5, origin=(0.0, 0.0))
    put(g, 0, 0, 40)
    put(g, 1, 0, 70)
    put(g, 1, 1, -1)
    best, unknown = probe.block_max(g, 0.0, 0.0, 1.0, 1.0)   # 왼쪽 아래 4칸
    assert best == 70 and unknown is True
    best, unknown = probe.block_max(g, 0.0, 0.0, 0.5, 0.5)   # 칸 하나
    assert best == 40 and unknown is False
    assert probe.block_max(g, 9.0, 9.0, 9.5, 9.5) == (None, False)   # 격자 밖


def test_두_지도와_차이지도가_같은_표본을_쓴다():
    """한쪽은 칸 최댓값, 다른 쪽은 한 점만 보면 눈으로 대조가 안 된다."""
    a, b = nvblox_on_off()
    ma = probe.render(a, 0.0, 0.0, 1.0, 20)
    mb = probe.render(b, 0.0, 0.0, 1.0, 20)
    md = probe.render_diff(a, b, 0.0, 0.0, 1.0, 20)
    for r in range(20):
        for c in range(20):
            if ma[r][c] == '#' and mb[r][c] not in ('#', '@'):
                assert md[r][c] == 'v', (r, c, ma[r][c], mb[r][c], md[r][c])
