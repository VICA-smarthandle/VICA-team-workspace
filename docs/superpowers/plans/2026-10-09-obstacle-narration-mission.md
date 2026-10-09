# 주행 중 장애물 안내 2단계 — 미션 안에 넣기 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 1단계 점검 도구의 장애물 판정을 미션 패키지로 옮겨, 안내 주행 중 앞에 진짜 물체가 있어 크게 비키거나 줄일 때 미션이 TTS 로 한 번 말하게 한다.

**Architecture:** 판정(`obstacle_judge.py`)은 음성 저장소 1단계 코드를 글자 그대로 옮긴다. 미션 노드는 장애물 입력을 새 콜백 그룹으로만 받고(라이다·깊이는 최근 1장), 판정이 "말할 후보"를 큐에 넣으면 대화 줄의 `_tick` 이 `MissionLogic.obstacle_cue` 로 대화와 겹치는지 보고 `ambient` 등급으로 TTS 에 보낸다. 장애물 부분의 예외는 `Guard` 가 받아 안내만 끈다.

**Tech Stack:** ROS 2 Humble rclpy(MultiThreadedExecutor·콜백 그룹·QoS), tf2_ros, numpy, scipy(`ndimage.distance_transform_edt`), pytest. 음성 쪽은 vica-voice-llm `.venv`.

**Spec:** 루트 `docs/superpowers/specs/2026-10-08-obstacle-narration-design.md` — 3절(판정), 5절 2단계(2026-10-09 결정), 6절(소리).

## Global Constraints

- 판정 숫자·규칙은 바꾸지 않는다: `obstacle_judge.py` 의 14번째 줄부터 끝까지는 음성 저장소 `scripts/obstacle_judge.py` 와 글자까지 같아야 한다(머리 13줄만 다르다).
- 문장은 사용자가 고른 두 개뿐이다: "앞에 장애물이 있어 피해 갈게요." / "앞에 장애물이 있어 천천히 갈게요." (10-08 사용자 선택 A1·S1). 새 멘트를 더하지 않는다.
- 새 노드를 만들지 않는다. tf 리스너도 `spin_thread` 없이 미션 노드 안에서 쓴다.
- 장애물 입력 구독은 `_main_group`·`_emergency_group` 에 넣지 않는다.
- 장애물 안내 TTS 등급은 `ambient` 다(다른 말 중이면 버리고, 다른 말이 오면 비킨다).
- 대화가 먼저다: 귀가 듣는 중(`_ear_holds`)·취소 확인 대기(`cancel_confirm_pending`)·안내 주행 아님이면 말하지 않는다. 행동 시작에서 2.5초가 지난 후보는 버린다.
- 빌드는 `colcon build --packages-select vica_mission_manager` 만 한다. 전체 빌드 금지.
- 두 저장소 모두 브랜치 `after_feedback_waiting`. 내 파일만 `git add` 한다(ROS 저장소에 다른 세션의 maps·urdf.rviz 변경이 있다). 푸시하지 않는다.
- 주행 중(`ros2 bag record` 실행 중)에는 시험 묶음·빌드를 돌리지 않는다. 확인: `ps -eo args | grep -c "[b]ag record"` 가 0. 시험은 `nice -n 19`.
- 미션 시험 명령: `.superpowers/sdd/2026-10-08-mission-request-reactions/run_mission.sh` 와 같은 방식(원래 실패 3개 `test_progress_narration` 은 뺀다).
- 실기 시점은 사용자가 정한다. 실기 전 dev 머지 금지.

## Review Focus

1. 지도 파일이 없거나 깨졌을 때 — 미션은 평소대로 뜨고 장애물 안내만 꺼진 채 경고 한 줄을 남겨야 한다 → Task 2 `test_load_grid_*`.
2. 주행 중 이상한 메시지로 판정이 예외를 낼 때 — 미션은 계속 돌고 안내만 꺼진다, 예외가 밖으로 나가지 않는다 → Task 2 `TestGuard`.
3. 깊이 띠가 다른 좌표틀로 올 때 — 그 점은 쓰지 않는다(엉뚱한 자리에 물체가 생기지 않게) → Task 2 `test_depth_frame_*`.
4. 사용자가 말한 직후(귀 closed 뒤 유예 6초) 비키기가 일어날 때 — 말하지 않는다 → Task 3 `test_silent_during_the_grace_after_the_user_spoke`.
5. 대화 줄이 바빠 후보가 늦게 처리될 때 — 2.5초가 지났으면 버린다 → Task 3 `test_late_cue_is_dropped`.

---

## 파일 구조

| 파일 | 할 일 |
| --- | --- |
| `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/obstacle_judge.py` (새) | 판정. 음성 저장소 1단계 코드 그대로 |
| `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/obstacle_inputs.py` (새) | ROS 없이 시험되는 입력 바꾸기(라이다 점·자세·깊이 틀)·지도 읽기·로그 한 줄·`Guard` |
| `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py` | 두 문장 상수·`OBSTACLE_STALE_SEC`·`MissionLogic.obstacle_cue` |
| `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_manager_node.py` | 파라미터·구독(새 그룹)·tf·후보 큐·`_tick` 에서 말하기 |
| `vica_ros2_ws/src/vica_mission_manager/launch/mission_manager.launch.py` | `obstacle_narration` 인자 |
| `vica_ros2_ws/src/vica_mission_manager/package.xml` | 의존성 |
| `vica_ros2_ws/src/vica_mission_manager/test/test_obstacle_judge.py` (새) | 판정 시험 40개(음성 저장소에서 옮김) |
| `vica_ros2_ws/src/vica_mission_manager/test/test_obstacle_inputs.py` (새) | 입력·지도·로그·Guard 시험 |
| `vica_ros2_ws/src/vica_mission_manager/test/test_obstacle_cue.py` (새) | 말할지 판단 시험 |
| `vica_ros2_ws/src/vica_mission_manager/test/test_obstacle_wiring.py` (새) | 노드·launch·package 배선 계약(소스 글자) |
| `vica-voice-llm/src/mission_phrases.py` | 두 문장 사본 + 녹음 목록 |
| `vica-voice-llm/tests/test_mission_phrases.py` | 사본이 미션과 같은지 |
| `vica-voice-llm/src/tts_queue.py` | `ambient` 설명에 장애물 안내 추가(주석만) |

---

### Task 1: 판정 코드를 미션 패키지로 옮기기

**Files:**
- Create: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/obstacle_judge.py`
- Create: `vica_ros2_ws/src/vica_mission_manager/test/test_obstacle_judge.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/package.xml` (`python3-yaml` 줄 아래)

**Interfaces:**
- Consumes: 없음
- Produces: `obstacle_judge.ObstacleJudge(grid)` 와 메서드 `on_dialog(t, state)`, `on_goal(t, event, x, y, loc)`, `on_rail(t, xy)`, `on_pose(t, X, Y, A)`, `on_points(sensor, t, x, y)`, `on_vcc(t, st)`, `on_bt(t, node, status)`, `on_cm(t, what)`, `tick(now) -> list[dict]`; `MapGrid.from_yaml(path)`, `MapGrid.wall_dist(X, Y)`; 함수 `parse_state(text) -> dict|None`, `cm_what(msg) -> str|None`, `goal_event(text) -> dict|None`; 상수 `PHRASES = {"avoid": ..., "slow": ...}`. 결정 dict 의 키: `t, kind, decision, phrase, why, n, n_scan, n_depth, n_wall, near, lat, mode, goal_dist, detail, decided_at`.

- [ ] **Step 1: 시험을 먼저 옮긴다**

```bash
cd /home/ji_w/VICA-smarthandle/vica_ros2_ws/src/vica_mission_manager
SRC=/home/ji_w/VICA-smarthandle/vica-voice-llm/tests/test_obstacle_judge.py
{ cat <<'EOF'
"""obstacle_judge — 주행 중 장애물 안내 판정 시험 (음성 저장소 tests/test_obstacle_judge.py 를 2026-10-09 옮김).

설계서: 루트 docs/superpowers/specs/2026-10-08-obstacle-narration-design.md 3절.
로봇은 원점에서 +x 를 보고, 레일은 x 축(왼쪽 +y)이다. 지도는 비어 있다(벽 시험만 칸을 채운다).
"""
import json
import math

import numpy as np
import pytest

from vica_mission_manager import obstacle_judge as oj
EOF
tail -n +18 "$SRC"; } > test/test_obstacle_judge.py
head -16 test/test_obstacle_judge.py
```

Expected: 위 머리 다음에 빈 줄 둘과 `# ------------------------------------------------------------------ 도우미` 가 보인다.

- [ ] **Step 2: 실패를 확인한다**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest test/test_obstacle_judge.py -q -p no:cacheprovider 2>&1 | tail -3`
Expected: `ImportError`(cannot import name 'obstacle_judge') 로 수집 오류 1개.

- [ ] **Step 3: 판정 코드를 옮긴다 (머리 13줄만 새로)**

```bash
SRC=/home/ji_w/VICA-smarthandle/vica-voice-llm/scripts/obstacle_judge.py
{ cat <<'EOF'
#!/usr/bin/env python3
"""주행 중 장애물 안내 판정 — 순수 코드(ROS·스피커 없음).

설계서: 루트 docs/superpowers/specs/2026-10-08-obstacle-narration-design.md 3절(판정)·5절 2단계(미션에 넣기).

로봇의 행동(차선 옮김·경로 우회·급감속·장애물 정지·충돌감시)이 시작되면, 그 순간부터 0.5초 동안
가던 길 위에 '지도에 없는' 점이 3개 이상 있는지 본다. 있으면 한 번 말하고, 같은 장애물에는 다시
말하지 않는다. 숫자는 녹화본 10개(run60~69)로 맞췄고 시운전 run81(10-09)에서 16번 모두 실물이었다.

음성 저장소 scripts/obstacle_judge.py(1단계 점검 도구)를 2026-10-09 그대로 옮겼다 — 이제 이 파일이 정본이다.
미션 노드가 실시간으로 쓰고, 녹화본 재현은 1단계 도구(avoid_cue.py --bag)로 한다.
입력 시각은 모두 '받은 시각'(초)이다.
"""
EOF
tail -n +14 "$SRC"; } > vica_mission_manager/obstacle_judge.py
diff <(tail -n +14 "$SRC") <(tail -n +14 vica_mission_manager/obstacle_judge.py) && echo "판정 본문 같음"
```

Expected: `판정 본문 같음`.

- [ ] **Step 4: 의존성을 적는다**

`package.xml` 의 `<exec_depend>python3-yaml</exec_depend>` 바로 아래에 두 줄을 넣는다.

```xml
  <exec_depend>python3-numpy</exec_depend>
  <exec_depend>python3-scipy</exec_depend>
```

- [ ] **Step 5: 통과를 확인한다**

Run: `PYTHONDONTWRITEBYTECODE=1 nice -n 19 python3 -m pytest test/test_obstacle_judge.py -q -p no:cacheprovider 2>&1 | tail -2`
Expected: `40 passed`.

- [ ] **Step 6: 커밋**

```bash
git add vica_mission_manager/obstacle_judge.py test/test_obstacle_judge.py package.xml
git commit -m "feat(mission): 장애물 안내 판정을 미션 패키지로 옮긴다 — 1단계 판정 그대로(run81 16번 모두 실물)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019d3r5Lo3xoGRrEm7mcZ2QE"
```

---

### Task 2: 입력 바꾸기·지도 읽기·로그·보호막 (`obstacle_inputs.py`)

**Files:**
- Create: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/obstacle_inputs.py`
- Create: `vica_ros2_ws/src/vica_mission_manager/test/test_obstacle_inputs.py`

**Interfaces:**
- Consumes: Task 1 `obstacle_judge.MapGrid`, `obstacle_judge.PHRASES`
- Produces: `LASER_DEFAULT: tuple`, `BASE_FRAME: str`, `scan_points(msg, offset=(0.0, 0.0)) -> (ndarray, ndarray)`, `yaw_of(q) -> float`, `depth_frame_ok(frame_id: str) -> bool`, `load_grid(map_yaml: str) -> tuple[MapGrid | None, str]`, `format_decision(d: dict) -> str`, `class Guard(on_error)` 와 `Guard.enabled: bool`, `Guard.wrap(fn) -> fn`

- [ ] **Step 1: 시험을 쓴다**

`test/test_obstacle_inputs.py`:

```python
"""장애물 안내의 입력 바꾸기·지도 읽기·로그·보호막 (2026-10-09 2단계, 설계서 5절).

라이다 점 시험 셋은 음성 저장소 tests/test_avoid_cue.py 의 TestScanPoints 를 옮겼다.
"""
import math
from types import SimpleNamespace

import pytest

from vica_mission_manager.obstacle_inputs import (
    Guard, depth_frame_ok, format_decision, load_grid, scan_points, yaw_of,
)


def scan(ranges, angle_min=-math.pi / 2, inc=math.pi / 2, rmin=0.15, rmax=12.0):
    return SimpleNamespace(ranges=ranges, angle_min=angle_min, angle_increment=inc, range_min=rmin, range_max=rmax)


class TestScanPoints:
    def test_points_in_robot_frame_with_laser_offset(self):
        # 오른쪽(-90°) 1 m, 앞(0°) 2 m, 왼쪽(+90°) 1 m — 라이다는 차체 기준 x +0.031
        x, y = scan_points(scan([1.0, 2.0, 1.0]), offset=(0.031, 0.0))
        assert x == pytest.approx([0.031, 2.031, 0.031], abs=1e-9)
        assert y == pytest.approx([-1.0, 0.0, 1.0], abs=1e-9)

    def test_drops_invalid_and_far_points(self):
        x, y = scan_points(scan([float("inf"), 0.1, 5.0], angle_min=0.0, inc=0.1))
        assert len(x) == 0   # inf·최소 거리 미만·앞 4 m 밖

    def test_keeps_only_box_around_robot(self):
        x, y = scan_points(scan([2.0, 2.0], angle_min=math.pi / 2, inc=math.pi / 2))
        assert len(x) == 0   # 옆 2 m(상자 ±1.5 m 밖)와 뒤 2 m(상자 -0.3 m 밖)


def test_yaw_of_quarter_turn():
    q = SimpleNamespace(x=0.0, y=0.0, z=math.sin(math.pi / 4), w=math.cos(math.pi / 4))
    assert yaw_of(q) == pytest.approx(math.pi / 2)


def test_depth_frame_ok_only_for_the_robot_frame():
    assert depth_frame_ok("") and depth_frame_ok("base_footprint")
    assert not depth_frame_ok("camera_link")


def _write_map(tmp_path, rows):
    """rows: 위쪽 줄부터, '#' = 벽. 칸 0.1 m, 원점 (0, 0)."""
    h, w = len(rows), len(rows[0])
    pix = bytes(0 if c == "#" else 254 for row in rows for c in row)
    (tmp_path / "m.pgm").write_bytes(f"P5\n{w} {h}\n255\n".encode() + pix)
    (tmp_path / "m.yaml").write_text(
        "image: m.pgm\nresolution: 0.1\norigin: [0.0, 0.0, 0.0]\nnegate: 0\n"
        "occupied_thresh: 0.65\nfree_thresh: 0.196\n", encoding="utf-8")
    return tmp_path / "m.yaml"


def test_load_grid_reads_the_map(tmp_path):
    grid, why = load_grid(str(_write_map(tmp_path, ["#...", "....", "...."])))
    assert why == "" and grid is not None
    assert grid.wall_dist([0.05], [0.25])[0] == pytest.approx(0.0)              # 맨 윗줄 왼쪽 칸 = 벽
    assert grid.wall_dist([0.35], [0.05])[0] == pytest.approx(0.36, abs=0.01)   # 대각선 3·2칸


def test_load_grid_without_a_path_turns_narration_off():
    grid, why = load_grid("")
    assert grid is None and "map_yaml" in why


def test_load_grid_with_a_broken_path_turns_narration_off(tmp_path):
    grid, why = load_grid(str(tmp_path / "없는지도.yaml"))
    assert grid is None and "없는지도.yaml" in why


def _decision(**kw):
    d = {"t": 1.0, "kind": "LAT", "decision": "announce", "phrase": "avoid", "why": [], "n": 5, "n_scan": 2,
         "n_depth": 3, "n_wall": 0, "near": 1.2, "lat": 0.1, "mode": "rail", "goal_dist": 4.5, "detail": {}}
    d.update(kw)
    return d


def test_format_decision_announce():
    assert format_decision(_decision()) == (
        "차선 옮김 → 말함 '앞에 장애물이 있어 피해 갈게요.' · 점 5(라이다 2·깊이 3·벽 0) "
        "앞 1.20 m 옆 +0.10 m · 목적지 4.5 m")


def test_format_decision_excluded_shows_the_reasons():
    d = _decision(kind="CM", decision="excluded", phrase=None, why=["near_goal", "cm_not_driving"],
                  n=0, n_scan=0, n_depth=0, near=None, lat=None, goal_dist=0.8)
    assert format_decision(d) == (
        "충돌감시 → 뺌 (목적지 1 m 안·회전·정지 중 충돌감시) · 점 0(라이다 0·깊이 0·벽 0) · 목적지 0.8 m")


class TestGuard:
    def test_error_turns_it_off_once_and_never_raises(self):
        errors, calls = [], []

        def boom(x):
            calls.append(x)
            raise ValueError("bad scan")

        f = Guard(errors.append)
        wrapped = f.wrap(boom)
        assert wrapped(1) is None
        assert wrapped(2) is None
        assert calls == [1]
        assert f.enabled is False
        assert len(errors) == 1 and isinstance(errors[0], ValueError)

    def test_passes_values_through_while_healthy(self):
        g = Guard(lambda e: None)
        assert g.wrap(lambda a, b: a + b)(2, 3) == 5
        assert g.enabled
```

- [ ] **Step 2: 실패를 확인한다**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest test/test_obstacle_inputs.py -q -p no:cacheprovider 2>&1 | tail -3`
Expected: `ModuleNotFoundError: No module named 'vica_mission_manager.obstacle_inputs'` 수집 오류.

- [ ] **Step 3: 구현한다**

`vica_mission_manager/obstacle_inputs.py`:

```python
"""장애물 안내의 ROS 입력 바꾸기·지도 읽기·로그·보호막 — ROS 없이 시험되는 부분 (2026-10-09 2단계).

판정은 obstacle_judge.py, 말할지 마지막 판단은 MissionLogic.obstacle_cue, ROS 배선은 mission_manager_node 가
한다(설계서 2026-10-08-obstacle-narration-design.md 5절). 라이다 점 바꾸기·라벨은 음성 저장소
scripts/avoid_cue.py(1단계 점검 도구)의 것을 그대로 옮겼다.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from .obstacle_judge import PHRASES, MapGrid

LASER_DEFAULT = (0.031, 0.0)   # base_footprint → laser_frame (tf_static 실측)
BASE_FRAME = "base_footprint"

KIND_KO = {"LAT": "차선 옮김", "DET": "경로 우회", "DEC": "급감속", "HOLD": "장애물 정지", "CM": "충돌감시"}
DECISION_KO = {"announce": "말함", "merged": "묶음(같은 장애물)", "excluded": "뺌", "no_cause": "원인 없음",
               "no_map": "지도 없음"}
WHY_KO = {"not_guided": "안내 주행 아님", "resync": "유턴 뒤 자리 맞추기", "after_turn": "유턴 직후",
          "near_goal": "목적지 1 m 안", "cm_not_driving": "회전·정지 중 충돌감시", "dec_from_lane_shift": "차선 옮김 감속"}


def scan_points(msg, offset=(0.0, 0.0)):
    """LaserScan → base_footprint 기준 (x, y). 앞 -0.3~4.0 m, 옆 ±1.5 m 만."""
    r = np.asarray(msg.ranges, dtype=float)
    a = msg.angle_min + np.arange(len(r)) * msg.angle_increment
    ok = np.isfinite(r) & (r >= msg.range_min) & (r <= msg.range_max)
    x = offset[0] + r[ok] * np.cos(a[ok])
    y = offset[1] + r[ok] * np.sin(a[ok])
    keep = (x >= -0.3) & (x <= 4.0) & (np.abs(y) <= 1.5)
    return x[keep], y[keep]


def yaw_of(q) -> float:
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def depth_frame_ok(frame_id: str) -> bool:
    """depth_band_to_scan 은 base_footprint 로 낸다(10-08 확인). 다른 틀이면 쓰지 않는다."""
    return frame_id in ("", BASE_FRAME)


def load_grid(map_yaml: str) -> tuple[Optional[MapGrid], str]:
    """정지 지도를 읽는다 → (지도, "") 또는 (None, 이유). 못 읽으면 노드는 장애물 안내만 끈다."""
    if not map_yaml:
        return None, "map_yaml 이 비어 있습니다"
    path = Path(map_yaml).expanduser()
    try:
        return MapGrid.from_yaml(path), ""
    except Exception as exc:  # noqa: BLE001 — 어떤 이유든 안내만 끄고 미션은 뜬다
        return None, f"{path}: {exc!r}"


def format_decision(d: dict) -> str:
    """판정 한 건을 미션 로그 한 줄로(1단계 기록 CSV 와 같은 칸)."""
    kind = KIND_KO.get(d["kind"], d["kind"])
    dec = DECISION_KO.get(d["decision"], d["decision"])
    why = "·".join(WHY_KO.get(w, w) for w in d.get("why", []))
    say = f" '{PHRASES[d['phrase']]}'" if d.get("phrase") else ""
    tail = f" ({why})" if why else ""
    where = "" if d.get("near") is None else f" 앞 {d['near']:.2f} m 옆 {d['lat']:+.2f} m"
    return (f"{kind} → {dec}{say}{tail} · 점 {d['n']}(라이다 {d['n_scan']}·깊이 {d['n_depth']}·벽 {d['n_wall']})"
            f"{where} · 목적지 {d['goal_dist']} m")


class Guard:
    """장애물 안내 콜백 보호막 — 예외가 한 번이라도 나면 안내를 끄고 미션은 계속 돈다
    (2026-10-09 사용자 요구: 오류가 나면 장애물 안내만 꺼지고 안내 주행은 계속)."""

    def __init__(self, on_error: Callable[[BaseException], None]):
        self.enabled = True
        self._on_error = on_error

    def wrap(self, fn: Callable) -> Callable:
        def run(*args, **kwargs):
            if not self.enabled:
                return None
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                self.enabled = False
                self._on_error(exc)
                return None
        return run
```

- [ ] **Step 4: 통과를 확인한다**

Run: `PYTHONDONTWRITEBYTECODE=1 nice -n 19 python3 -m pytest test/test_obstacle_inputs.py -q -p no:cacheprovider 2>&1 | tail -2`
Expected: `12 passed`.

- [ ] **Step 5: 커밋**

```bash
git add vica_mission_manager/obstacle_inputs.py test/test_obstacle_inputs.py
git commit -m "feat(mission): 장애물 안내 입력·지도·로그·보호막 — 오류가 나면 안내만 끄고 미션은 계속

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019d3r5Lo3xoGRrEm7mcZ2QE"
```

---

### Task 3: 미션이 말할지 정한다 (`MissionLogic.obstacle_cue`)

**Files:**
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py` — 상수는 `MSG_WAIT_EXPIRED` 정의(약 452줄) 바로 아래, 메서드는 `_home_beacon_tick` 바로 위, `Say.priority` 주석(약 213줄)
- Create: `vica_ros2_ws/src/vica_mission_manager/test/test_obstacle_cue.py`

**Interfaces:**
- Consumes: Task 1 `obstacle_judge.PHRASES`(시험에서 글자 대조만)
- Produces: `MSG_OBSTACLE_AVOID: str`, `MSG_OBSTACLE_SLOW: str`, `OBSTACLE_STALE_SEC: float = 2.5`, `MissionLogic.obstacle_cue(phrase: str, onset: float, now: float) -> tuple[list, str]` — 말하면 `([Say(text, priority="ambient")], "")`, 아니면 `([], 이유)`. 이유: `"unknown_phrase" | "not_navigating" | "question_pending" | "ear_busy" | "stale"`

- [ ] **Step 1: 시험을 쓴다**

`test/test_obstacle_cue.py`:

```python
"""장애물 안내 — 미션이 말할지 마지막으로 정한다 (2026-10-09 2단계, 설계서 5절 '대화와 겹칠 때').

대화가 먼저다: 귀가 듣는 중이거나 취소 확인의 답을 기다리면 말하지 않는다. 다른 말 중이면 TTS 가
버리도록 ambient 로 보낸다. 늦은 후보(행동 시작 2.5초 뒤)는 버린다.
"""
import pytest

from vica_mission_manager import obstacle_judge as oj
from vica_mission_manager.mission_logic import (
    EAR_GRACE_SEC, MSG_OBSTACLE_AVOID, MSG_OBSTACLE_SLOW, OBSTACLE_STALE_SEC, MissionLogic, Say, State,
)


def _driving():
    logic = MissionLogic()
    logic.state = State.NAVIGATING
    return logic


def _said(actions):
    return [(a.text, a.priority) for a in actions if isinstance(a, Say)]


def test_phrases_match_the_judge():
    assert oj.PHRASES == {"avoid": MSG_OBSTACLE_AVOID, "slow": MSG_OBSTACLE_SLOW}


@pytest.mark.parametrize("phrase,text", [("avoid", MSG_OBSTACLE_AVOID), ("slow", MSG_OBSTACLE_SLOW)])
def test_speaks_while_guiding_as_ambient(phrase, text):
    actions, why = _driving().obstacle_cue(phrase, 100.0, 100.4)
    assert why == ""
    assert _said(actions) == [(text, "ambient")]


@pytest.mark.parametrize("state", [State.IDLE, State.PAUSED, State.CONFIRMING, State.RETURNING, State.WAITING])
def test_silent_when_not_guiding(state):
    logic = MissionLogic()
    logic.state = state
    actions, why = logic.obstacle_cue("avoid", 100.0, 100.4)
    assert actions == [] and why == "not_navigating"


def test_silent_while_the_ear_is_listening():
    logic = _driving()
    logic.on_listen_state("open", 100.0)
    actions, why = logic.obstacle_cue("avoid", 100.2, 100.5)
    assert actions == [] and why == "ear_busy"


def test_silent_during_the_grace_after_the_user_spoke():
    logic = _driving()
    logic.on_listen_state("open", 100.0)
    logic.on_listen_state("closed", 101.0)          # 말이 LLM 으로 가는 중 — 대답이 곧 온다
    actions, why = logic.obstacle_cue("slow", 102.0, 102.3)
    assert actions == [] and why == "ear_busy"
    later = 101.0 + EAR_GRACE_SEC + 0.5
    actions, why = logic.obstacle_cue("slow", later, later + 0.3)
    assert why == "" and _said(actions) == [(MSG_OBSTACLE_SLOW, "ambient")]


def test_empty_listen_window_frees_the_ear_at_once():
    logic = _driving()
    logic.on_listen_state("open", 100.0)
    logic.on_listen_state("empty:ghost", 101.0)
    actions, why = logic.obstacle_cue("avoid", 101.2, 101.4)
    assert why == "" and actions


def test_silent_while_the_cancel_question_waits():
    logic = _driving()
    logic.cancel_confirm_pending = True              # "안내를 취소할까요?" 답 대기
    actions, why = logic.obstacle_cue("avoid", 100.0, 100.3)
    assert actions == [] and why == "question_pending"


def test_late_cue_is_dropped():
    actions, why = _driving().obstacle_cue("avoid", 100.0, 100.0 + OBSTACLE_STALE_SEC + 0.1)
    assert actions == [] and why == "stale"


def test_unknown_phrase_is_dropped():
    actions, why = _driving().obstacle_cue("boom", 100.0, 100.1)
    assert actions == [] and why == "unknown_phrase"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest test/test_obstacle_cue.py -q -p no:cacheprovider 2>&1 | tail -3`
Expected: `ImportError: cannot import name 'MSG_OBSTACLE_AVOID'` 수집 오류.

- [ ] **Step 3: 상수를 넣는다**

`mission_logic.py` 의 `MSG_WAIT_EXPIRED = "대기 시간이 종료되어 제자리로 돌아갑니다."` 줄 바로 아래:

```python
# 주행 중 장애물 안내(2026-10-08 사용자 선택 A1·S1, 10-09 미션에 넣음). 안내 주행 중 앞에 지도에 없는 물체가
# 있어 크게 비키거나(avoid) 줄이거나 설 때(slow) 한 번. 판정은 obstacle_judge.py(설계서 3절), 말할지는
# MissionLogic.obstacle_cue(설계서 5절 2단계). 음성 mission_phrases 에 같은 글자의 녹음이 있다.
MSG_OBSTACLE_AVOID = "앞에 장애물이 있어 피해 갈게요."
MSG_OBSTACLE_SLOW = "앞에 장애물이 있어 천천히 갈게요."
# 행동이 시작되고 이만큼 지난 후보는 버린다 — 늦은 장애물 안내는 지나간 물체 이야기다(1단계 도구와 같은 값).
OBSTACLE_STALE_SEC = 2.5
```

`Say` 의 priority 주석에서 `# ambient(2026-10-07)는 대기 중 10초 알림(M3) 전용이다 — 다른 말이 나가거나 줄 서` 를
`# ambient(2026-10-07)는 배경 알림 — 대기 중·홈 알림(M3)과 주행 중 장애물 안내(2026-10-09). 다른 말이 나가거나 줄 서`
로 바꾼다.

- [ ] **Step 4: 메서드를 넣는다**

`mission_logic.py` 의 `    def _home_beacon_tick(self, now: float) -> list:` 바로 위:

```python
    def obstacle_cue(self, phrase: str, onset: float, now: float) -> tuple[list, str]:
        """장애물 안내 후보를 말할지 정한다 → (actions, 뺀 이유). 말하면 이유는 "".

        판정(obstacle_judge)이 '앞에 진짜 물체가 있어 비켰다·줄였다'고 넘긴 후보다. 대화가 먼저다
        (2026-10-09 사용자 확인): 귀가 듣는 중이거나 취소 확인의 답을 기다리면 말하지 않는다 — 로봇 말이
        시작되면 귀가 열린 재청취 창을 접어 사용자 대답이 잘린다. 로봇이 다른 말을 하는 중이면 TTS 가
        버리도록 ambient 로 보낸다. 늦은 후보도 버린다. 버린 안내는 다시 하지 않는다.
        """
        text = {"avoid": MSG_OBSTACLE_AVOID, "slow": MSG_OBSTACLE_SLOW}.get(phrase)
        if text is None:
            return [], "unknown_phrase"
        if self.dialog_state != State.NAVIGATING.value:
            return [], "not_navigating"
        if self.cancel_confirm_pending:
            return [], "question_pending"
        if self._ear_holds(now):
            return [], "ear_busy"
        if now - onset > OBSTACLE_STALE_SEC:
            return [], "stale"
        return [Say(text, priority="ambient")], ""

```

- [ ] **Step 5: 통과를 확인한다**

Run: `PYTHONDONTWRITEBYTECODE=1 nice -n 19 python3 -m pytest test/test_obstacle_cue.py -q -p no:cacheprovider 2>&1 | tail -2`
Expected: `14 passed`.

- [ ] **Step 6: 미션 전체 시험**

Run: `nice -n 19 bash /home/ji_w/VICA-smarthandle/.superpowers/sdd/2026-10-08-mission-request-reactions/run_mission.sh 2>&1 | tail -2`
Expected: `1056 passed, 1 skipped, 3 deselected` 이고 failed 없음(이전 990 + Task 1~3 의 40·12·14).

- [ ] **Step 7: 커밋**

```bash
git add vica_mission_manager/mission_logic.py test/test_obstacle_cue.py
git commit -m "feat(mission): 장애물 안내를 말할지 미션이 정한다 — 안내 주행 중만, 듣는 중·취소 확인 대기·2.5초 지남이면 안 함, ambient

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019d3r5Lo3xoGRrEm7mcZ2QE"
```

---

### Task 4: 노드 배선 — 새 줄로 받고, 대화 줄에서 말한다

**Files:**
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_manager_node.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/launch/mission_manager.launch.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/package.xml`
- Create: `vica_ros2_ws/src/vica_mission_manager/test/test_obstacle_wiring.py`

**Interfaces:**
- Consumes: Task 1 `ObstacleJudge`, `parse_state`, `cm_what`, `goal_event`; Task 2 `Guard`, `scan_points`, `yaw_of`, `depth_frame_ok`, `load_grid`, `format_decision`, `LASER_DEFAULT`, `BASE_FRAME`; Task 3 `MissionLogic.obstacle_cue`
- Produces: 노드 파라미터 `obstacle_narration`(bool, 기본 true), launch 인자 `obstacle_narration`(기본 "true"), 미션 로그 줄 `장애물: …`·`장애물 안내 뺌: …`·`장애물 안내: 켜짐/꺼짐/오류로 끕니다`

- [ ] **Step 1: 배선 계약 시험을 쓴다**

`test/test_obstacle_wiring.py`:

```python
"""장애물 안내 노드 배선 계약 (2026-10-09 2단계, 설계서 5절) — rclpy 없이 소스 글자로 본다(test_handle_mode 방식)."""
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
NODE = (PKG / "vica_mission_manager" / "mission_manager_node.py").read_text(encoding="utf-8")
LAUNCH = (PKG / "launch" / "mission_manager.launch.py").read_text(encoding="utf-8")
XML = (PKG / "package.xml").read_text(encoding="utf-8")


def _setup_block() -> str:
    return NODE[NODE.index("    def _setup_obstacle_narration"):NODE.index("    def _on_obstacle_error")]


def test_switch_is_declared_and_exposed():
    assert 'self.declare_parameter("obstacle_narration", True)' in NODE
    assert 'DeclareLaunchArgument("obstacle_narration", default_value="true")' in LAUNCH
    assert '"obstacle_narration": ParameterValue(' in LAUNCH


def test_inputs_use_their_own_group_not_the_dialog_group():
    block = _setup_block()
    assert "group = MutuallyExclusiveCallbackGroup()" in block
    assert "_main_group" not in block and "_emergency_group" not in block
    assert block.count("callback_group=group") == 8          # 구독 7 + 판정 타이머 1


def test_sensor_inputs_keep_only_the_latest():
    block = _setup_block()
    assert "QoSProfile(depth=1, history=HistoryPolicy.KEEP_LAST," in block
    assert '"/scan", wrap(self._obs_scan), latest' in block
    assert '"/camera/depth_scan", wrap(self._obs_depth), latest' in block


def test_tf_listener_lives_in_this_node_without_a_new_node():
    block = _setup_block()
    assert "tf2_ros.TransformListener(self._tf_buffer, self)" in block
    assert "spin_thread" not in block and "create_node" not in block


def test_every_obstacle_callback_is_guarded():
    assert _setup_block().count("wrap(self._obs_") == 8


def test_speaking_is_decided_in_the_dialog_tick():
    tick = NODE[NODE.index("    def _tick(self)"):NODE.index("    def _publish_robot_state")]
    assert "self._drain_obstacle_cues()" in tick
    assert "self.logic.obstacle_cue(phrase, onset, self._now())" in NODE


def test_missing_map_turns_only_the_narration_off():
    block = _setup_block()
    assert "grid, why = load_grid(map_yaml)" in block
    assert "return" in block.split("if grid is None:")[1].split("self._obstacle = ObstacleJudge")[0]


def test_package_declares_the_new_dependencies():
    for dep in ("<depend>sensor_msgs</depend>", "<depend>nav_msgs</depend>", "<depend>rcl_interfaces</depend>",
                "<depend>tf2_ros</depend>", "<exec_depend>python3-numpy</exec_depend>",
                "<exec_depend>python3-scipy</exec_depend>"):
        assert dep in XML, dep
```

- [ ] **Step 2: 실패를 확인한다**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest test/test_obstacle_wiring.py -q -p no:cacheprovider 2>&1 | tail -3`
Expected: `8 failed`(대부분 `ValueError: substring not found` 또는 assert).

- [ ] **Step 3: import 를 고친다**

`mission_manager_node.py` 머리에서:

- `from datetime import datetime` 바로 위에 `from collections import deque` 를 넣는다.
- `import rclpy` 아래에 `import tf2_ros` 를 넣는다.
- `from nav2_msgs.msg import SpeedLimit` 를 `from nav2_msgs.msg import BehaviorTreeLog, SpeedLimit` 로 바꾸고, 그 위에 `from nav_msgs.msg import Path as PathMsg` 를 넣는다(이 파일은 이미 `pathlib.Path` 를 쓴다 — 이름이 겹치지 않게 `PathMsg`).
- `from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy` 를 `from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy` 로 바꾼다.
- `from rcl_interfaces.msg import Log` 와 `from sensor_msgs.msg import LaserScan` 를 `from rclpy.qos …` 아래·`from std_msgs.msg …` 위에 넣는다.
- `from .mission_logic import (` 묶음이 끝나는 `)` 바로 아래에:

```python
from .obstacle_inputs import (
    BASE_FRAME,
    LASER_DEFAULT,
    Guard,
    depth_frame_ok,
    format_decision,
    load_grid,
    scan_points,
    yaw_of,
)
from .obstacle_judge import ObstacleJudge, cm_what, goal_event, parse_state
```

- [ ] **Step 4: 파라미터를 선언한다**

`self.declare_parameter("home_beacon_interval_sec", HOME_BEACON_INTERVAL_SEC)` 바로 아래:

```python
        # 주행 중 장애물 안내(2026-10-09, 설계서 2026-10-08-obstacle-narration-design.md 5절 2단계).
        # false 면 장애물 입력을 아예 구독하지 않는다.
        self.declare_parameter("obstacle_narration", True)
```

- [ ] **Step 5: 설치 블록을 넣는다**

`__init__` 안, `/amcl_pose` 구독 블록이 끝난 바로 뒤(`tick_hz = float(self.get_parameter("tick_hz").value)` 위):

```python
        # ---- 주행 중 장애물 안내 (2026-10-09) — 입력은 전용 줄, 말할지는 _tick 이 정한다 ----------
        self._obstacle: Optional[ObstacleJudge] = None
        self._obstacle_guard = Guard(self._on_obstacle_error)
        self._obstacle_cues: deque = deque(maxlen=8)
        if bool(self.get_parameter("obstacle_narration").value):
            self._setup_obstacle_narration(map_yaml)
        else:
            self.get_logger().info("장애물 안내: 꺼짐(obstacle_narration=false)")

```

`map_yaml` 은 같은 `__init__` 위쪽(`map_yaml = str(self.get_parameter("map_yaml").value)`)에서 이미 정해진 지역 변수다.

- [ ] **Step 6: 메서드를 넣는다**

`_on_amcl_pose` 메서드가 끝난 바로 뒤(다음 `def` 위):

```python
    # -- 주행 중 장애물 안내 (2026-10-09) ------------------------------------------------------
    # 판정은 obstacle_judge(설계서 3절, 시운전 run81 에서 16번 모두 실물). 입력은 전용 콜백 그룹으로만 받아
    # 대화 줄(_main_group)과 서로 기다리지 않는다. 라이다·깊이는 최근 1장만 둔다(밀려도 쌓이지 않게).
    # 판정 줄은 말할 후보만 _obstacle_cues 에 넣고, 말할지는 대화 줄의 _tick 이 logic.obstacle_cue 로 정한다.
    # 장애물 부분의 예외는 Guard 가 받아 안내만 끈다 — 안내 주행은 계속된다.

    def _setup_obstacle_narration(self, map_yaml: str) -> None:
        grid, why = load_grid(map_yaml)
        if grid is None:
            self.get_logger().warn(f"장애물 안내: 지도를 못 읽어 끕니다 — {why}")
            return
        self._obstacle = ObstacleJudge(grid)
        self._laser_offset: Optional[tuple] = None
        # 위치(tf)는 리스너가 스스로 만드는 Reentrant 그룹으로 받는다 — 새 노드·스레드 없이 이 노드의
        # MultiThreadedExecutor 가 처리한다. 리스너의 전용 스레드 옵션은 같은 노드를 executor 두 개에 넣게 돼 못 쓴다.
        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self)
        group = MutuallyExclusiveCallbackGroup()
        latest = QoSProfile(depth=1, history=HistoryPolicy.KEEP_LAST,
                            reliability=ReliabilityPolicy.BEST_EFFORT)
        wrap = self._obstacle_guard.wrap
        self.create_subscription(LaserScan, "/scan", wrap(self._obs_scan), latest, callback_group=group)
        self.create_subscription(LaserScan, "/camera/depth_scan", wrap(self._obs_depth), latest,
                                 callback_group=group)
        self.create_subscription(String, "/vcc/state", wrap(self._obs_vcc), 10, callback_group=group)
        self.create_subscription(BehaviorTreeLog, "/behavior_tree_log", wrap(self._obs_bt), 50,
                                 callback_group=group)
        self.create_subscription(Log, "/rosout", wrap(self._obs_rosout), 50, callback_group=group)
        self.create_subscription(PathMsg, "/rail_plan", wrap(self._obs_rail), 5, callback_group=group)
        self.create_subscription(String, "/vica_goal_event", wrap(self._obs_goal), 10, callback_group=group)
        self.create_timer(0.1, wrap(self._obs_tick), callback_group=group)
        self.get_logger().info(f"장애물 안내: 켜짐 (지도 {map_yaml})")

    def _on_obstacle_error(self, exc: BaseException) -> None:
        self._obstacle = None
        self._obstacle_cues.clear()
        self.get_logger().error(f"장애물 안내: 오류로 끕니다 — 안내 주행은 계속됩니다 ({exc!r})")

    def _obs_pose(self, t: float) -> None:
        try:
            tr = self._tf_buffer.lookup_transform("map", BASE_FRAME, rclpy.time.Time())
        except tf2_ros.TransformException:
            return   # 위치를 아직 모르면 원인 판정만 쉰다
        p, q = tr.transform.translation, tr.transform.rotation
        self._obstacle.on_pose(t, p.x, p.y, yaw_of(q))

    def _obs_laser_offset(self) -> tuple:
        if self._laser_offset is None:
            try:
                tr = self._tf_buffer.lookup_transform(BASE_FRAME, "laser_frame", rclpy.time.Time())
            except tf2_ros.TransformException:
                return LASER_DEFAULT
            self._laser_offset = (tr.transform.translation.x, tr.transform.translation.y)
        return self._laser_offset

    def _obs_scan(self, msg: LaserScan) -> None:
        t = self._now()
        self._obs_pose(t)
        self._obstacle.on_points("scan", t, *scan_points(msg, self._obs_laser_offset()))

    def _obs_depth(self, msg: LaserScan) -> None:
        if depth_frame_ok(msg.header.frame_id):
            self._obstacle.on_points("depth", self._now(), *scan_points(msg))

    def _obs_vcc(self, msg: String) -> None:
        st = parse_state(msg.data)
        if st is not None:
            t = self._now()
            # 안내 주행인지는 미션 자신의 대화 단계로 본다(1단계 도구는 /vica/robot_state 로 받았다).
            self._obstacle.on_dialog(t, self.logic.dialog_state)
            self._obstacle.on_vcc(t, st)

    def _obs_bt(self, msg: BehaviorTreeLog) -> None:
        for e in msg.event_log:
            self._obstacle.on_bt(e.timestamp.sec + e.timestamp.nanosec * 1e-9, e.node_name, e.current_status)

    def _obs_rosout(self, msg: Log) -> None:
        if msg.name == "collision_monitor":
            what = cm_what(msg.msg)
            if what:
                self._obstacle.on_cm(self._now(), what)

    def _obs_rail(self, msg: PathMsg) -> None:
        self._obstacle.on_rail(self._now(), [(p.pose.position.x, p.pose.position.y) for p in msg.poses])

    def _obs_goal(self, msg: String) -> None:
        # 이 노드가 낸 goal 사건을 이 노드가 다시 받는다 — 판정 입력을 1단계 도구와 똑같이 둔다.
        ev = goal_event(msg.data)
        if ev:
            self._obstacle.on_goal(self._now(), ev["event"], ev["x"], ev["y"], ev["loc"])

    def _obs_tick(self) -> None:
        t = self._now()
        self._obs_pose(t)
        for d in self._obstacle.tick(t):
            if d["decision"] == "announce":
                self._obstacle_cues.append((d["phrase"], d["t"]))
            self.get_logger().info("장애물: " + format_decision(d))

    def _drain_obstacle_cues(self) -> None:
        """판정 줄이 넘긴 후보를 대화 줄에서 말할지 정한다(_tick 끝에서 부른다)."""
        while self._obstacle_cues:
            phrase, onset = self._obstacle_cues.popleft()
            actions, why = self.logic.obstacle_cue(phrase, onset, self._now())
            if why:
                self.get_logger().info(f"장애물 안내 뺌: {why}")
            self._run_actions(actions)

```

- [ ] **Step 7: `_tick` 에서 부른다**

`_tick` 안의 `self._run_actions(actions)` 줄 바로 아래:

```python
        self._drain_obstacle_cues()
```

- [ ] **Step 8: launch 인자와 의존성**

`launch/mission_manager.launch.py` 의 `DeclareLaunchArgument("grip_assume_held", default_value="true"),` 바로 아래:

```python
            # obstacle_narration: 주행 중 장애물 안내(2026-10-09, 설계서 5절 2단계). false 면 구독도 안 한다.
            DeclareLaunchArgument("obstacle_narration", default_value="true"),
```

같은 파일 노드 parameters 의 `"grip_assume_held": ParameterValue(…, value_type=bool,),` 항목 바로 아래:

```python
                        "obstacle_narration": ParameterValue(
                            LaunchConfiguration("obstacle_narration"),
                            value_type=bool,
                        ),
```

`package.xml` 의 `<depend>nav2_simple_commander</depend>` 바로 아래:

```xml
  <depend>sensor_msgs</depend>
  <depend>nav_msgs</depend>
  <depend>rcl_interfaces</depend>
  <depend>tf2_ros</depend>
```

- [ ] **Step 9: 통과·문법·import 를 확인한다**

```bash
PYTHONDONTWRITEBYTECODE=1 nice -n 19 python3 -m pytest test/test_obstacle_wiring.py -q -p no:cacheprovider 2>&1 | tail -2
python3 -m py_compile vica_mission_manager/mission_manager_node.py launch/mission_manager.launch.py && echo "문법 OK"
bash -c 'source /opt/ros/humble/setup.bash && source /home/ji_w/VICA-smarthandle/vica_ros2_ws/install/setup.bash && cd /home/ji_w/VICA-smarthandle/vica_ros2_ws/src/vica_mission_manager && python3 -c "import vica_mission_manager.mission_manager_node as m; print(\"import OK\", m.MissionManagerNode.__name__)"'
```

Expected: `8 passed`, `문법 OK`, `import OK MissionManagerNode`.

- [ ] **Step 10: 미션 전체 시험**

Run: `nice -n 19 bash /home/ji_w/VICA-smarthandle/.superpowers/sdd/2026-10-08-mission-request-reactions/run_mission.sh 2>&1 | tail -2`
Expected: `1064 passed, 1 skipped, 3 deselected`, failed 없음(Task 4 의 8 더함).

- [ ] **Step 11: 커밋**

```bash
git add vica_mission_manager/mission_manager_node.py launch/mission_manager.launch.py package.xml test/test_obstacle_wiring.py
git commit -m "feat(mission): 장애물 안내를 미션이 TTS 로 — 입력은 전용 콜백 그룹·라이다 깊이 최신 1장, 말할지는 _tick, 오류면 안내만 끔

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019d3r5Lo3xoGRrEm7mcZ2QE"
```

---

### Task 5: 음성 쪽 — 문장 사본과 녹음 목록

**Files:**
- Modify: `vica-voice-llm/src/mission_phrases.py` — `ESTOP_WAKE` 정의 아래, `baked_mission_ments()` 의 `out = {…}`
- Modify: `vica-voice-llm/tests/test_mission_phrases.py` — `TestSentences.test_wait_spot_constants`
- Modify: `vica-voice-llm/src/tts_queue.py` — 머리 docstring 의 ambient 설명(주석만)

**Interfaces:**
- Consumes: Task 3 `MSG_OBSTACLE_AVOID`, `MSG_OBSTACLE_SLOW`(시험의 `ml` 고정물이 ROS 저장소 mission_logic 을 읽는다)
- Produces: `mission_phrases.OBSTACLE_AVOID`, `mission_phrases.OBSTACLE_SLOW`, 녹음 이름 `mission_msg_obstacle_avoid`, `mission_msg_obstacle_slow`

- [ ] **Step 1: 시험을 쓴다**

`tests/test_mission_phrases.py` 의 `test_wait_spot_constants` 안 `assert mp.ESTOP_WAKE == ml.MSG_ESTOP_WAKE` 바로 아래:

```python
        assert mp.OBSTACLE_AVOID == ml.MSG_OBSTACLE_AVOID   # 주행 중 장애물 안내(2026-10-09)
        assert mp.OBSTACLE_SLOW == ml.MSG_OBSTACLE_SLOW
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd /home/ji_w/VICA-smarthandle/vica-voice-llm && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_mission_phrases.py -q -p no:cacheprovider -k wait_spot_constants 2>&1 | tail -2`
Expected: `AttributeError: module 'src.mission_phrases' has no attribute 'OBSTACLE_AVOID'` 로 1 failed.

- [ ] **Step 3: 구현한다**

`src/mission_phrases.py` 의 `ESTOP_WAKE = "지금은 비상 멈춤 상태입니다."` 줄 아래:

```python
# 주행 중 장애물 안내(2026-10-09 미션에 넣음, 사용자 선택 A1·S1). 미션 MSG_OBSTACLE_* 와 같은 글자.
OBSTACLE_AVOID = "앞에 장애물이 있어 피해 갈게요."
OBSTACLE_SLOW = "앞에 장애물이 있어 천천히 갈게요."
```

`baked_mission_ments()` 의 `"mission_msg_wait_need_ask": WAIT_NEED_ASK,` 줄 아래:

```python
        # 주행 중 장애물 안내(2026-10-09) — ambient 라 바로 나가야 한다. 실시간 합성은 늦다.
        "mission_msg_obstacle_avoid": OBSTACLE_AVOID,
        "mission_msg_obstacle_slow": OBSTACLE_SLOW,
```

`src/tts_queue.py` 머리의 `    ambient    배경 알림(2026-10-07, 대기 중 10초 알림 M3 전용). 다른 말이 나가는` 를
`    ambient    배경 알림(2026-10-07 대기·홈 알림 M3, 2026-10-09 주행 중 장애물 안내). 다른 말이 나가는` 로 바꾼다.

- [ ] **Step 4: 시험을 돌린다**

Run: `PYTHONDONTWRITEBYTECODE=1 nice -n 19 .venv/bin/python -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -3`
Expected: `1 failed` = `TestBaked::test_baked_list_is_in_the_manifest`(두 문장이 아직 manifest 에 없다 — Task 6 에서 굽는다), 나머지 통과.

- [ ] **Step 5: 커밋**

```bash
git add src/mission_phrases.py tests/test_mission_phrases.py src/tts_queue.py
git commit -m "feat(voice): 장애물 안내 두 문장 사본·녹음 목록 — 미션이 ambient 로 보낸다(굽기 전 TestBaked 1 실패)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019d3r5Lo3xoGRrEm7mcZ2QE"
```

---

### Task 6: 두 문장 굽기와 고르기 (사용자와 함께)

로봇 스택(특히 ⑫)을 내린 상태에서만 한다 — CosyVoice 가 RAM 약 3 GB 를 쓴다. 주행·녹화 중이면 하지 않는다.

**Files:**
- Create: `vica-voice-llm/assets/baked/mission_msg_obstacle_avoid.wav`, `mission_msg_obstacle_slow.wav`
- Modify: `vica-voice-llm/assets/baked/manifest.json`

- [ ] **Step 1: 굽는다**

```bash
cd /home/ji_w/VICA-smarthandle/vica-voice-llm
ps -eo args | grep -c "[b]ag record"      # 0 이어야 한다
PYTHONPATH=~/CosyVoice:~/CosyVoice/third_party/Matcha-TTS nice -n 10 ~/venvs/cosyvoice/bin/python scripts/bake_one_cv.py --mission 2>&1 | grep -E "구움|건너"
```

Expected: `구움: mission_msg_obstacle_avoid.wav`, `구움: mission_msg_obstacle_slow.wav`(이미 있는 문장은 건너뜀).

- [ ] **Step 2: 사용자가 듣고 고른다**

새 녹음(CosyVoice, 다른 미션 멘트와 같은 목소리)과 1단계 녹음(Supertonic 1.2배)을 차례로 들려준다.

```bash
aplay assets/baked/mission_msg_obstacle_avoid.wav; aplay assets/obstacle_narration/avoid.wav
aplay assets/baked/mission_msg_obstacle_slow.wav;  aplay assets/obstacle_narration/slow.wav
```

1단계 녹음을 고르면 같은 이름으로 덮는다(글자는 같아 manifest 는 그대로 둔다):

```bash
cp assets/obstacle_narration/avoid.wav assets/baked/mission_msg_obstacle_avoid.wav
cp assets/obstacle_narration/slow.wav assets/baked/mission_msg_obstacle_slow.wav
```

- [ ] **Step 3: 시험을 돌린다**

Run: `PYTHONDONTWRITEBYTECODE=1 nice -n 19 .venv/bin/python -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -2`
Expected: failed 없음.

- [ ] **Step 4: 녹음을 커밋한다**

`manifest.json` 에는 10-09 오전에 구운 반응표 7문장(미커밋, 사용자 청취 확인 대기)도 들어 있다. 사용자에게 7문장도 괜찮은지 묻고, 괜찮으면 같이 넣는다.

```bash
git add -f assets/baked/manifest.json assets/baked/mission_msg_obstacle_avoid.wav assets/baked/mission_msg_obstacle_slow.wav
# 7문장도 확인됐으면:
git add -f assets/baked/mission_msg_wait_need_ask.wav 'assets/baked/mission_msg_wait_front_'*.wav
git commit -m "feat(voice): 장애물 안내 두 문장 녹음(사용자 선택: <CosyVoice 또는 1단계>)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019d3r5Lo3xoGRrEm7mcZ2QE"
```

---

### Task 7: 빌드와 실기 (사용자가 정한 때)

- [ ] **Step 1: 빌드 — 미션 패키지만**

```bash
ps -eo args | grep -c "[b]ag record"      # 0
cd /home/ji_w/VICA-smarthandle/vica_ros2_ws && source /opt/ros/humble/setup.bash && source install/setup.bash
nice -n 10 colcon build --packages-select vica_mission_manager 2>&1 | tail -3
diff -q src/vica_mission_manager/vica_mission_manager/mission_manager_node.py \
  install/vica_mission_manager/lib/python3.10/site-packages/vica_mission_manager/mission_manager_node.py && echo "설치본 = 소스"
```

Expected: `1 package finished`, `설치본 = 소스`.

- [ ] **Step 2: 사용자가 ⑩ mission 과 ⑫ llm+tts 를 다시 켠다** (⑩ 먼저. ⑫ 는 새 녹음 목록을 읽으려면 다시 켜야 한다)

확인(가벼운 읽기만):

```bash
ps -eo pid,lstart,args | grep -E "[m]ission_manager/mission_manager|[s]rc\.ros_tts_node" | cut -c1-110
L=$(ls -t ~/.ros/log/python3_*.log | xargs grep -l "vica_mission_manager 시작" | head -1); grep -m3 "장애물 안내" "$L"
```

Expected: 두 프로세스 시작 시각이 빌드 뒤, 미션 로그에 `장애물 안내: 켜짐 (지도 …map_1002_150946.yaml)`.

- [ ] **Step 3: 녹화를 걸고 실제로 쓰이는지 확인한다** (메모리 규칙)

`bash ~/vica_data/record_obstacle_test.sh run<NN>` 을 백그라운드로 걸고, 1~2분 뒤 bag 폴더 크기가 늘어나는지 본다. 확인 전에는 "걸었다"고 말하지 않는다.

- [ ] **Step 4: 시나리오 (사람 기준 판정)**

| # | 상황 | 통과 기준 |
| --- | --- | --- |
| 1 | 안내 주행, 레일 위에 상자 | 물체 앞에서 두 문장 중 하나가 한 번 |
| 2 | 같은 길, 물체 치움 | 조용 |
| 3 | 물체 앞을 지나며 "비카야" → 말하기 | 대답이 잘리지 않음. 듣는 동안 장애물 안내 없음(미션 로그 `장애물 안내 뺌: ear_busy`) |
| 4 | "다 됐어" → "안내를 취소할까요?" 대기 중 물체 | 장애물 안내 없음(`question_pending`), "아니요"가 잘 먹힘 |
| 5 | 미션이 다른 말을 하는 순간 물체 | 두 말이 겹쳐 나오지 않음(TTS 로그 `발화 무시` 또는 `배경 알림 중단`) |
| 6 | 홈 복귀·대기 장소 이동 중 물체 | 조용(안내 주행 아님) |

- [ ] **Step 5: 연산량을 잰다** (1분, `/proc` 읽기만 — 녹화 중에도 가볍다)

10-09 실측과 같은 방법으로 미션 프로세스의 CPU % 를 잰다(코어 하나 = 100 %). 기준: 통합 전 미션 약 6 %, 판정만 따로 주행 중 추정 10 % 안팎.

- [ ] **Step 6: 기록과 커밋**

녹화를 멈춘 뒤(주행 끝) 미션 로그의 `장애물:` 줄을 세어 말함·뺌 이유를 정리하고, 필요하면 `avoid_cue.py --bag` 으로 같은 녹화본을 돌려 판정이 같은지 본다. 결과를 `devlog/2026-10-XX.md` 에 적고, 바꾼 것이 있으면 회차 커밋을 한다(실주행 1회마다 커밋). 실기 전 dev 머지는 하지 않는다.

**주의:** 미션이 장애물 안내를 하는 동안 1단계 도구(`avoid_cue.py`)를 실시간으로 함께 켜지 않는다(같은 말을 두 번 하게 된다). 녹화본 모드(`--bag`)는 괜찮다.

---

## Self-Review

- **설계 대조.** 5절 2단계 표: 판정 그대로 → Task 1(본문 diff). 받는 줄 → Task 4 Step 6·`test_inputs_use_their_own_group_not_the_dialog_group`. 최신 것만 → Task 4·`test_sensor_inputs_keep_only_the_latest`. 위치 tf → Task 4·`test_tf_listener_lives_in_this_node_without_a_new_node`. 말할지 _tick → Task 3·Task 4 Step 7. 오류 → Task 2 `Guard`·Task 4 `wrap`. 스위치 → Task 4 Step 4·8. 대화와 겹칠 때: ambient → Task 3 `test_speaks_while_guiding_as_ambient`, 듣는 중 → `test_silent_while_the_ear_is_listening`·`..._grace_...`, 취소 확인 → `test_silent_while_the_cancel_question_waits`, 2.5초 → `test_late_cue_is_dropped`, 비카야·멈춰 우선 → 기존 TTS·귀 동작 그대로(Task 7 #3). 녹음 → Task 5·6. 연산량 재측정 → Task 7 Step 5.
- **빈칸 검사.** "TBD"·"적절히"·"나중에" 없음. Task 6 커밋 메시지의 `<CosyVoice 또는 1단계>` 는 사용자 선택을 그대로 적는 자리다.
- **이름 일관성.** `obstacle_cue(phrase, onset, now) -> (actions, why)`, `_obstacle_cues`(deque of `(phrase, t)`), `_drain_obstacle_cues`, `Guard.wrap`, `load_grid`, `format_decision`, `depth_frame_ok`, `BASE_FRAME`, `LASER_DEFAULT`, `MSG_OBSTACLE_AVOID/SLOW`, `OBSTACLE_STALE_SEC` — 모든 작업에서 같은 이름.
- **Review Focus.** 다섯 줄 모두 소유 작업의 시험으로 들어 있다(Task 2·3).
- **남은 위험.** ① 노드 배선은 ROS 없이 소스 글자로만 시험한다 — 실제 구독·QoS 일치는 Task 7 Step 2·4 에서 본다. ② 판정 줄이 `logic.dialog_state` 를 다른 스레드에서 읽는다 — 문자열 읽기라 깨지지는 않지만 순간 낡을 수 있다(최대 VCC 한 주기 0.2초). 말할지 마지막 판단은 대화 줄에서 다시 하므로 잘못 말하지는 않는다. ③ 시연(≈10-27) 2주 반 전 변경이다 — `obstacle_narration:=false` 로 바로 끌 수 있다.
