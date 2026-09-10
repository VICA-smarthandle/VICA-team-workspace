# "비카야" 호출 접근 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 대기 중인 로봇이 "비카야" 호출을 들으면 소리 난 쪽으로 제자리 회전해 카메라를 겨누고, 사람이 보이면 기존 접근·안내 경로에 합류한다.

**Architecture:** 방아쇠 하나만 새로 만든다. 음성 쪽은 호출 순간 이미 잠그고 있는 DOA 각도를 토픽(`/vica/wake_doa`)으로 한 번 내보낸다. Mission Manager 는 IDLE 에서만 그것을 받아 `State.SEEKING` 으로 제자리 회전하고, 회전이 끝나면 **IDLE 로 돌아가 탐색 창만 든다** — 접근 관문(`check_approach_gate`)이 IDLE 만 통과시키므로 관문을 건드리지 않고 기존 경로에 합류하기 위해서다. 창 안에 접근 요청이 오면 기존 A5 흐름이 전부 이어받고, 안 오면 조용히 원래 각도로 되돌아간다.

**Tech Stack:** Python 3.10 · ROS 2 Humble · rclpy · Nav2 `BasicNavigator.spin()` · pytest · reSpeaker v3.0(XVF3000) DOA

**Spec:** `docs/superpowers/specs/2026-09-10-voice-call-approach-design.md`

## Global Constraints

- **안전 경로 불변.** 회전은 Nav2 `SpinInPlace`(behavior server) → `/cmd_vel_req` → Safety → `/cmd_vel_safe`. `cmd_vel` 계열 직접 발행 금지.
- **`check_approach_gate` 를 한 줄도 바꾸지 않는다.** 이 계획의 설계 근거다.
- **`/vica/wake` 의 기존 동작 불변.** 안내 중 각성·복귀 브레이크·답대기 접기 전부 현행 유지.
- **새 노드 없음. 새 안내 멘트 없음.** 호출 응답 "네?"가 이미 예고를 겸한다.
- **DSP 쓰기 금지(D7 동결).** DOA 는 읽기 전용이라 저촉되지 않는다.
- `SpinInPlace.yaw_rad` 는 **양수 = 반시계**다 (`mission_logic.py:213`).
- DOA 기준선: **핸들 = 180°, 정면 ≈ 0°** (2026-09-01 실측, 표본 33, 범위 172~180).
- 커밋 메시지는 저장소 기존 문체(평서형 국문)를 따른다. push 는 사용자 요청 시에만.

## 작업 브랜치

두 저장소 모두 **dev 에서 갈라낸 새 브랜치**에서 작업한다. 현재 체크아웃된 브랜치 위에 얹지 않는다.

```bash
# ROS2 (dev = c9bd12b)
cd /home/ji_w/wt-dev && git worktree add /home/ji_w/wt-callseek -b feat/voice-call-approach dev

# 음성 (dev, 이미 체크아웃돼 있고 깨끗함)
cd /home/ji_w/VICA-smarthandle/vica-voice-llm && git checkout -b feat/wake-doa-publish dev
```

실기 때는 **메인 워크스페이스**(`/home/ji_w/VICA-smarthandle/vica_ros2_ws`)에서 `feat/voice-call-approach` 를 체크아웃해 빌드한다 — 워크트리는 소스 편집용이고 build/install 은 메인에 있다.

## File Structure

| 파일 | 책임 | 작업 |
| --- | --- | --- |
| `vica-voice-llm/src/wakeword_monitor.py` | 호출 순간 방향을 잠그고 **밖에 알린다** | 수정 (콜백 1개 + 메서드 1개) |
| `vica-voice-llm/src/ros_wakeword_node.py` | 그 방향을 `/vica/wake_doa` 로 발행 | 수정 (퍼블리셔 1개) |
| `vica-voice-llm/tests/test_wake_doa.py` | 위 두 개의 계약 | **신규** |
| `vica-voice-llm/tools/wake_doa_bearing.py` | DOA 부호 실측 도구 | **신규** |
| `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py` | 각도 변환 + `SEEKING` 상태기계 (순수 로직) | 수정 |
| `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_manager_node.py` | 구독·파라미터·`is_moving` 배선 | 수정 |
| `vica_ros2_ws/src/vica_mission_manager/test/test_mission_logic.py` | `SEEKING` 전이 시험 | 수정 (클래스 추가) |

`mission_logic.py` 는 1930 줄로 이미 크지만 **쪼개지 않는다.** 이 계획이 더하는 것은 상태 하나와 분기 두 개이고, 상태기계를 가르는 일은 이 작업의 범위를 훨씬 넘는다.

## 시험 실행 명령

```bash
# ROS2 순수 로직 (현재 171 통과)
cd /home/ji_w/wt-callseek/src/vica_mission_manager && python3 -m pytest test/test_mission_logic.py -q

# 음성 (현재 28 통과)
cd /home/ji_w/VICA-smarthandle/vica-voice-llm && .venv/bin/python -m pytest tests/ -q
```

ROS 노드 배선(퍼블리셔·구독·파라미터)은 자동 시험하지 않는다 — 음성 저장소 `CLAUDE.md` Testing Rules 의 "실제 ROS2 에 의존하는 테스트는 자동화하지 않는다"를 따른다. 그 부분은 Task 7·8 의 손 확인이 담당한다.

---

### Task 1: DOA 부호 실측 (선행 · 사용자 동석 필요)

스펙 §5 가 **구현 전 선행**으로 못박은 작업이다. 마이크 각도가 반시계로 커지는지 시계로 커지는지 이 장비에서 잰 기록이 없고, 틀리면 로봇이 **정확히 반대로 돈다.**

**Files:**
- Create: `vica-voice-llm/tools/wake_doa_bearing.py`
- Modify: `docs/superpowers/specs/2026-09-10-voice-call-approach-design.md` (§5 에 실측값 기록)

**Interfaces:**
- Consumes: `src.dsp_state.DspState` — `available`, `speech_detected() -> bool`, `doa_angle() -> Optional[int]`, `close()`
- Produces: 실측 상수 `s ∈ {+1, -1}`. Task 4 의 `wake_doa_sign` 기본값이 된다.

- [ ] **Step 1: 측정 도구를 만든다**

`vica-voice-llm/tools/wake_doa_bearing.py`:

```python
"""DOA 부호 실측 — 마이크 각도가 반시계로 커지는가 시계로 커지는가.

호출 접근 설계(루트 저장소 docs/superpowers/specs/2026-09-10-voice-call-approach-design.md)
§5 의 선행 측정이다. SpinInPlace 는 양수 = 반시계다. 마이크가 반시계로
커지면 s=+1, 시계로 커지면 s=-1 이고, 틀리면 로봇이 반대로 돈다.

세 자리에서 각각 "비카야"를 부른다 (로봇은 정지):
    ① 정면      기준선 재확인 (0° 부근이어야 한다)
    ② 왼쪽 90°  약 90° -> s=+1 / 약 270° -> s=-1
    ③ 오른쪽 90° ②의 반대편이 나오는지 확인

사용:
    cd ~/VICA-smarthandle/vica-voice-llm
    .venv/bin/python -u -m tools.wake_doa_bearing
"""
from __future__ import annotations

import math
import sys
import time

sys.path.insert(0, ".")

from src.dsp_state import DspState  # noqa: E402

POLL_HZ = 20
LISTEN_SEC = 6.0
POSITIONS = [
    ("① 로봇 정면", "0° 부근이 나와야 한다 (기준선 재확인)"),
    ("② 로봇 왼쪽 90°", "약 90° 면 s=+1(반시계), 약 270° 면 s=-1(시계)"),
    ("③ 로봇 오른쪽 90°", "②의 반대편이어야 한다"),
]


def circular_mean(angles: list) -> float:
    """0/359 경계를 올바로 다루는 원형 평균(도)."""
    if not angles:
        return float("nan")
    x = sum(math.cos(math.radians(a)) for a in angles) / len(angles)
    y = sum(math.sin(math.radians(a)) for a in angles) / len(angles)
    return math.degrees(math.atan2(y, x)) % 360


def listen_once(dsp: DspState) -> tuple:
    """LISTEN_SEC 동안 발화 판정 프레임의 방향만 모은다."""
    angles: list = []
    t_end = time.time() + LISTEN_SEC
    while time.time() < t_end:
        if dsp.speech_detected():
            a = dsp.doa_angle()
            if a is not None:
                angles.append(float(a))
        time.sleep(1.0 / POLL_HZ)
    return circular_mean(angles), len(angles)


def main() -> None:
    dsp = DspState()
    if not dsp.available:
        raise SystemExit("칩 상태를 읽을 수 없다 (udev/장치 확인)")

    print("로봇을 정지시킨 상태로 진행한다. 각 자리에서 엔터 뒤 계속 말한다.\n")
    results = []
    for label, hint in POSITIONS:
        input(f"{label} 에 서서 엔터를 누르고 {LISTEN_SEC:.0f}초간 '비카야'를 반복하세요 > ")
        mean, n = listen_once(dsp)
        print(f"   -> 평균 {mean:6.1f}°  (발화 표본 {n})   {hint}\n")
        results.append((label, mean, n))
    dsp.close()

    print("===== 결과 =====")
    for label, mean, n in results:
        print(f"  {label:16s} {mean:6.1f}°  (표본 {n})")
    left = results[1][1]
    if results[1][2] < 10:
        print("\n판정 불가 — 왼쪽 표본이 너무 적다. 더 크게/가까이 말해 재시험.")
        return
    ccw = min(abs(left - 90.0), 360 - abs(left - 90.0))
    cw = min(abs(left - 270.0), 360 - abs(left - 270.0))
    if ccw < cw:
        print(f"\n판정: 마이크는 **반시계로 증가** -> wake_doa_sign = +1.0")
    else:
        print(f"\n판정: 마이크는 **시계로 증가** -> wake_doa_sign = -1.0")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 사용자와 함께 측정한다**

Run: `cd /home/ji_w/VICA-smarthandle/vica-voice-llm && .venv/bin/python -u -m tools.wake_doa_bearing`

로봇은 정지 상태여야 한다. 사용자가 세 자리에 서서 "비카야"를 반복한다.

Expected: ①이 0° 부근(또는 ±20° 이내)이고, ②·③이 서로 약 180° 떨어져 나온다. ①이 크게 벗어나면 **마이크가 돌아갔다는 뜻**이므로 여기서 멈추고 사용자에게 보고한다 — 기준선(핸들=180°)이 깨졌으면 barge-in 부채꼴도 함께 틀어져 있다.

- [ ] **Step 3: 결과를 스펙에 기록한다**

스펙 §5 의 `[미검증]` 표시를 걷어내고 실측값을 남긴다. 예(실제 측정값으로 대체):

```markdown
## 5. 각도 변환 — 부호 실측 완료 (2026-09-__)

    yaw_rad = wrap_to_pi( s × radians(θ_doa) )      s = +1.0

실측: 정면 __° · 왼쪽 90° 지점 __° · 오른쪽 90° 지점 __° (표본 __/__/__).
마이크 각도는 **반시계로 증가**한다. `wake_doa_sign` 기본값이 이 값이다.
```

- [ ] **Step 4: 커밋**

```bash
cd /home/ji_w/VICA-smarthandle/vica-voice-llm
git add tools/wake_doa_bearing.py
git commit -m "tools: DOA 부호 실측기 — 마이크 각도가 반시계인지 시계인지 잰다

호출 접근에서 이 부호를 틀리면 로봇이 정확히 반대로 돈다. 세 자리에서
'비카야'를 불러 왼쪽 90도가 90도로 읽히는지 270도로 읽히는지 본다."

cd /home/ji_w/wt-callapproach
git add docs/superpowers/specs/2026-09-10-voice-call-approach-design.md
git commit -m "docs(spec): DOA 부호 실측값 기록 — 미검증 표시를 걷는다"
```

---

### Task 2: 음성 — 호출 방향을 콜백으로 내보낸다

**Files:**
- Modify: `vica-voice-llm/src/wakeword_monitor.py` (`__init__` 콜백 목록, `lock_user_direction` 아래에 메서드 추가, `run()` 의 wake 처리부)
- Test: `vica-voice-llm/tests/test_wake_doa.py` (신규)

**Interfaces:**
- Consumes: 기존 `WakewordMonitor.lock_user_direction(doa, now=None)`
- Produces:
  - `WakewordMonitor(..., on_wake_doa: Optional[Callable[[float], None]] = None)`
  - `WakewordMonitor.note_wake_direction(doa: Optional[float], now: Optional[float] = None) -> None`

**왜 `run()` 에 직접 넣지 않고 메서드로 빼는가:** `run()` 은 오디오 스트림과 칩이 있어야 도는 코드라 시험할 수 없다. 잠금과 통보를 한 메서드로 묶으면 시험이 그 메서드를 직접 부를 수 있다.

**주의 — 순서가 중요하다.** `run()` 에서 `process_frame()` 은 내부적으로 `on_wake` 콜백을 먼저 부르고 `"wake"` 를 반환한다. 방향 잠금은 그 **뒤에** 일어난다. 그래서 노드의 `_on_wake` 안에서 잠긴 방향을 읽으면 **직전 대화의 값**을 읽게 된다. 통보는 반드시 잠금과 같은 자리에서 해야 한다.

- [ ] **Step 1: 실패하는 시험을 쓴다**

`vica-voice-llm/tests/test_wake_doa.py`:

```python
"""호출 방향 통보 — "비카야"가 온 방향을 밖(ROS)으로 내보낸다.

로봇이 소리 쪽으로 고개를 돌리려면 그 각도를 알아야 한다. 잠금(barge-in
부채꼴)은 예전부터 있었지만 monitor 안에만 있었다.

잠금과 통보는 반드시 한 자리에서 일어난다 — run() 에서 on_wake 콜백은
방향 잠금보다 먼저 불리므로, 노드가 나중에 읽으면 직전 대화의 방향을 읽는다.
"""
from __future__ import annotations

import numpy as np

from src.wakeword_monitor import WakewordMonitor


class Fake:
    def predict(self, _frame):
        return {"a": 0.0, "b": 0.0}

    def transcribe(self, _audio):
        return ""


def make(**kwargs):
    fake = Fake()
    return WakewordMonitor(
        on_emergency=lambda e: None,
        on_user_text=lambda t: None,
        predict=fake.predict,
        transcribe=fake.transcribe,
        **kwargs,
    )


def test_wake_direction_is_announced():
    seen: list = []
    m = make(on_wake_doa=seen.append)
    m.note_wake_direction(123.0, now=0.0)
    assert seen == [123.0]


def test_wake_direction_is_float():
    """칩은 정수(0~359)를 준다. 밖으로는 float 로 낸다 — Float32 토픽이다."""
    seen: list = []
    m = make(on_wake_doa=seen.append)
    m.note_wake_direction(200, now=0.0)
    assert seen == [200.0]
    assert isinstance(seen[0], float)


def test_no_direction_announces_nothing():
    """DOA 를 못 읽으면 조용히 아무 일도 없다 — 무음 실패."""
    seen: list = []
    m = make(on_wake_doa=seen.append)
    m.note_wake_direction(None, now=0.0)
    assert seen == []


def test_direction_is_still_locked_for_barge_in():
    """통보를 붙였다고 기존 barge-in 잠금이 사라지면 안 된다."""
    m = make()
    m.note_wake_direction(236.0, now=0.0)
    assert m._locked_doa == 236.0
    assert m._locked_doa_at == 0.0


def test_callback_is_optional():
    """콜백을 안 주면 통보 없이 잠금만 한다 (기존 도구·시험 호환)."""
    m = make()
    m.note_wake_direction(90.0, now=0.0)   # 예외 없이 끝나야 한다
    assert m._locked_doa == 90.0
```

- [ ] **Step 2: 시험이 실패하는지 확인한다**

Run: `cd /home/ji_w/VICA-smarthandle/vica-voice-llm && .venv/bin/python -m pytest tests/test_wake_doa.py -q`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'on_wake_doa'`

- [ ] **Step 3: 콜백을 더한다**

`src/wakeword_monitor.py` 의 `__init__` 시그니처에서 `on_listen_state` 다음 줄에 더한다:

```python
        on_wake_doa: Optional[Callable[[float], None]] = None,
```

같은 `__init__` 본문의 `self._on_listen_state = on_listen_state or (lambda s: None)` 다음 줄에 더한다:

```python
        # 호출이 온 방향(DOA). 로봇이 그쪽으로 고개를 돌리는 데 쓴다
        # (호출 접근 설계). 방향을 못 읽으면 부르지 않는다.
        self._on_wake_doa = on_wake_doa or (lambda doa: None)
```

- [ ] **Step 4: `note_wake_direction` 을 더한다**

`lock_user_direction` 메서드 **바로 아래**에 더한다:

```python
    def note_wake_direction(self, doa: Optional[float],
                            now: Optional[float] = None) -> None:
        """호출 순간의 방향을 잠그고(barge-in) 밖에 알린다(고개 돌리기).

        둘을 한 자리에 묶는 이유: run() 에서 on_wake 콜백은 방향 잠금보다
        먼저 불린다. 노드가 나중에 잠긴 값을 읽으면 직전 대화의 방향을
        읽게 된다.
        """
        self.lock_user_direction(doa, now=now)
        if doa is not None:
            self._on_wake_doa(float(doa))
```

- [ ] **Step 5: `run()` 이 새 메서드를 쓰게 한다**

`src/wakeword_monitor.py` 의 wake 처리부(현재 `self.lock_user_direction(dsp.doa_angle())`)를 바꾼다:

```python
                if r == "wake":
                    # "비카야"가 온 방향을 이번 대화의 사용자 방향으로 잠그고,
                    # 로봇이 그쪽으로 고개를 돌릴 수 있게 밖에도 알린다.
                    self.note_wake_direction(dsp.doa_angle())
```

- [ ] **Step 6: 시험이 통과하는지 확인한다**

Run: `cd /home/ji_w/VICA-smarthandle/vica-voice-llm && .venv/bin/python -m pytest tests/ -q`
Expected: PASS — 신규 5건 포함 전부 통과 (기존 28건 회귀 없음)

- [ ] **Step 7: 커밋**

```bash
cd /home/ji_w/VICA-smarthandle/vica-voice-llm
git add src/wakeword_monitor.py tests/test_wake_doa.py
git commit -m "feat(wakeword): 호출이 온 방향을 밖으로 통보한다

DOA 잠금은 예전부터 있었지만 barge-in 판정용으로 monitor 안에만 있었다.
로봇이 소리 쪽으로 고개를 돌리려면 그 각도가 밖으로 나와야 한다.

잠금과 통보를 note_wake_direction 한 자리에 묶었다. run() 에서 on_wake
콜백은 방향 잠금보다 먼저 불리므로, 노드가 나중에 읽으면 직전 대화의
방향을 읽게 된다."
```

---

### Task 3: 음성 — `/vica/wake_doa` 발행

**Files:**
- Modify: `vica-voice-llm/src/ros_wakeword_node.py` (import, 퍼블리셔, monitor 생성부)

**Interfaces:**
- Consumes: Task 2 의 `on_wake_doa` 콜백
- Produces: 토픽 `/vica/wake_doa` (`std_msgs/Float32`, 0~359°) — Task 6 이 구독한다

- [ ] **Step 1: import 를 더한다**

`src/ros_wakeword_node.py` 의 std_msgs import 줄에 `Float32` 를 더한다. 현재 그 파일은 `String`, `Bool`, `Empty` 를 쓰고 있으므로 같은 import 문에 붙인다.

- [ ] **Step 2: 퍼블리셔를 만든다**

`self._pub_wake = self.create_publisher(String, "/vica/wake", 10)` 바로 다음 줄에 더한다:

```python
        # 호출이 온 방향(0~359°, 마이크 좌표계. 정면 0 / 핸들 180).
        # 미션이 대기 중에만 받아 그쪽으로 고개를 돌린다(호출 접근 설계).
        # /vica/wake 의 payload 를 넓히지 않는 이유는 그 토픽에 안내 중
        # 각성·복귀 브레이크가 이미 걸려 있어서다.
        self._pub_wake_doa = self.create_publisher(Float32, "/vica/wake_doa", 10)
```

- [ ] **Step 3: 발행 핸들러를 더한다**

`_on_wake` 메서드 **바로 아래**에 더한다:

```python
    def _publish_wake_doa(self, doa: float) -> None:
        """호출이 온 방향. 못 읽으면 monitor 가 아예 부르지 않는다."""
        self._pub_wake_doa.publish(Float32(data=float(doa)))
        self.get_logger().info(f"🧭 호출 방향 {doa:.0f}°")
```

- [ ] **Step 4: monitor 에 콜백을 연결한다**

`WakewordMonitor(...)` 를 만드는 자리(현재 `user_doa_center=self._user_doa_center,` 근처)의 인자 목록에 더한다:

```python
            on_wake_doa=self._publish_wake_doa,
```

- [ ] **Step 5: 문법·기존 시험 확인**

Run: `cd /home/ji_w/VICA-smarthandle/vica-voice-llm && .venv/bin/python -m pytest tests/ -q && .venv/bin/python -c "import ast,sys; ast.parse(open('src/ros_wakeword_node.py').read())"`
Expected: PASS — 시험 전부 통과, 문법 오류 없음

노드 자체는 ROS 런타임이 있어야 도므로 여기서는 문법까지만 본다. 실제 발행은 Task 8 에서 `ros2 topic echo /vica/wake_doa` 로 확인한다.

- [ ] **Step 6: 커밋**

```bash
cd /home/ji_w/VICA-smarthandle/vica-voice-llm
git add src/ros_wakeword_node.py
git commit -m "feat(ros): /vica/wake_doa 로 호출 방향을 낸다

Float32 를 쓴 것은 인터페이스 재빌드를 피하려는 선택이다. 시각은 미션이
수신 시각으로 대신한다 — 호출은 살아 있는 사건이다."
```

---

### Task 4: ROS2 — 각도 변환 (순수 함수)

**Files:**
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py`
- Test: `vica_ros2_ws/src/vica_mission_manager/test/test_mission_logic.py`

**Interfaces:**
- Produces:
  - `wrap_to_pi(rad: float) -> float` — Task 5·6 이 누적 복귀각에 쓴다
  - `doa_to_spin_yaw(doa_deg: float, sign: float = 1.0) -> float`
  - 상수 `SEEK_LOOK_SEC = 6.0`, `SEEK_TURN_TIMEOUT_SEC = 15.0`, `SEEK_MIN_YAW_RAD`

- [ ] **Step 1: 실패하는 시험을 쓴다**

`test/test_mission_logic.py` 의 import 블록에 더한다 (알파벳 순 유지):

```python
    SEEK_LOOK_SEC,
    SEEK_MIN_YAW_RAD,
    SEEK_TURN_TIMEOUT_SEC,
    doa_to_spin_yaw,
    wrap_to_pi,
```

파일 끝에 클래스를 더한다:

```python
class TestDoaToSpinYaw:
    """마이크 각도(0~359°, 정면 0) -> SpinInPlace 회전량(rad, 양수=반시계).

    sign 은 마이크 각도가 반시계로 커지면 +1, 시계로 커지면 -1 이다.
    이 부호를 틀리면 로봇이 정확히 반대로 돈다 (설계 §5, 실측으로 정한다).
    """

    def test_front_is_no_turn(self):
        assert doa_to_spin_yaw(0.0, 1.0) == pytest.approx(0.0)

    def test_ccw_mic_left_turns_left(self):
        assert doa_to_spin_yaw(90.0, 1.0) == pytest.approx(math.pi / 2)

    def test_cw_mic_left_turns_right(self):
        """부호가 반대면 같은 각도가 반대쪽 회전이 된다."""
        assert doa_to_spin_yaw(90.0, -1.0) == pytest.approx(-math.pi / 2)

    def test_takes_the_short_way_round(self):
        """270° 는 왼쪽으로 270° 가 아니라 오른쪽으로 90° 다."""
        assert doa_to_spin_yaw(270.0, 1.0) == pytest.approx(-math.pi / 2)

    def test_behind_is_half_turn(self):
        """뒤(핸들 쪽)는 어느 방향으로 돌든 180° 다."""
        assert abs(doa_to_spin_yaw(180.0, 1.0)) == pytest.approx(math.pi)

    def test_just_left_of_front(self):
        assert doa_to_spin_yaw(359.0, 1.0) == pytest.approx(math.radians(-1.0))


class TestWrapToPi:
    def test_leaves_small_angles_alone(self):
        assert wrap_to_pi(1.0) == pytest.approx(1.0)

    def test_wraps_over_half_turn(self):
        assert wrap_to_pi(math.radians(270.0)) == pytest.approx(math.radians(-90.0))

    def test_wraps_negative(self):
        assert wrap_to_pi(math.radians(-270.0)) == pytest.approx(math.radians(90.0))
```

- [ ] **Step 2: 시험이 실패하는지 확인한다**

Run: `cd /home/ji_w/wt-callseek/src/vica_mission_manager && python3 -m pytest test/test_mission_logic.py -q`
Expected: FAIL — `ImportError: cannot import name 'doa_to_spin_yaw'`

- [ ] **Step 3: 상수를 더한다**

`mission_logic.py` 의 `APPROACH_TURN_TIMEOUT_SEC = 15.0` 아래에 더한다:

```python
# 호출 접근(설계 2026-09-10). "비카야"를 듣고 그쪽으로 고개를 돌린 뒤,
# 카메라가 사람을 찾을 때까지 기다리는 시간.
#
# 6.0 인 이유: 회전이 끝나야 탐지가 쓸모 있어지고, detection_gate 는 5 Hz
# 로 stable 1.0 s + still window 3.0 s 를 본다. 그보다 짧으면 사람이 서
# 있는데도 창이 먼저 닫힌다. 실측으로 확정한다 [TARGET].
SEEK_LOOK_SEC = 6.0
# 회전이 시작조차 안 됐을 때(노드 결함 등) 상태에서 빠져나오는 시계.
# 접근 수락 회전과 같은 값을 쓴다 — 같은 Spin 액션이다.
SEEK_TURN_TIMEOUT_SEC = APPROACH_TURN_TIMEOUT_SEC
# 이보다 작은 회전은 하지 않는다. DOA 퍼짐이 ±4~16° 라 10° 미만은 잡음이고,
# 0 에 가까운 spin 은 behavior server 가 거부하거나 즉시 끝나 무의미하다.
SEEK_MIN_YAW_RAD = math.radians(10.0)
```

- [ ] **Step 4: 변환 함수를 더한다**

`yaw_deg_to_quaternion` 함수 **바로 위**에 더한다:

```python
def wrap_to_pi(rad: float) -> float:
    """각도를 -π~π 로 접는다 — 언제나 짧은 쪽으로 돈다."""
    return math.atan2(math.sin(rad), math.cos(rad))


def doa_to_spin_yaw(doa_deg: float, sign: float = 1.0) -> float:
    """마이크 DOA(0~359°, 정면 0 / 핸들 180)를 제자리 회전량(rad)으로.

    SpinInPlace 는 양수 = 반시계다. sign 은 마이크 각도가 반시계로
    커지면 +1, 시계로 커지면 -1 이며 장비마다 실측으로 정한다 — 틀리면
    로봇이 정확히 반대로 돈다.
    """
    return wrap_to_pi(math.radians(float(doa_deg) * float(sign)))
```

- [ ] **Step 5: 시험이 통과하는지 확인한다**

Run: `cd /home/ji_w/wt-callseek/src/vica_mission_manager && python3 -m pytest test/test_mission_logic.py -q`
Expected: PASS — 신규 9건 포함, 기존 171건 회귀 없음

- [ ] **Step 6: 커밋**

```bash
cd /home/ji_w/wt-callseek
git add src/vica_mission_manager/vica_mission_manager/mission_logic.py \
        src/vica_mission_manager/test/test_mission_logic.py
git commit -m "feat(mission): 마이크 방향을 제자리 회전량으로 바꾼다

DOA 는 0~359 도이고 SpinInPlace 는 양수가 반시계다. 270 도를 왼쪽으로
270 도 돌지 않고 오른쪽으로 90 도 돌도록 -파이~파이 로 접는다.

sign 은 마이크 각도 증가 방향이라 장비마다 실측으로 정한다."
```

---

### Task 5: ROS2 — `SEEKING` 진입

**Files:**
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py` (`State`, `_GOAL_ACTIVE_STATES`, `__init__`, `_to_idle`, 새 메서드)
- Test: `vica_ros2_ws/src/vica_mission_manager/test/test_mission_logic.py`

**Interfaces:**
- Consumes: Task 4 의 `doa_to_spin_yaw`, `wrap_to_pi`, `SEEK_MIN_YAW_RAD`, `SEEK_TURN_TIMEOUT_SEC`
- Produces:
  - `State.SEEKING`
  - `MissionLogic(..., wake_doa_sign: float = 1.0, seek_look_sec: float = SEEK_LOOK_SEC)`
  - `MissionLogic.on_wake_doa(doa_deg: float, nav_ready: bool, now: float) -> list`
  - 내부 상태 `_seek_return_yaw: Optional[float]`, `_seek_deadline: Optional[float]`

**복귀각은 누적한다.** 탐색 창 중에 다시 부르면 로봇이 또 돈다. 그때 복귀각을 덮어쓰면 원래 자세로 못 돌아오므로 `-yaw` 를 계속 더한다.

- [ ] **Step 1: 실패하는 시험을 쓴다**

`test/test_mission_logic.py` 끝에 더한다:

```python
class TestSeekEntry:
    """"비카야" 방향으로 고개 돌리기 — 대기 중에만 연다."""

    def test_wake_doa_turns_toward_the_sound(self):
        logic = MissionLogic(wake_doa_sign=1.0)
        actions = logic.on_wake_doa(90.0, True, 1.0)
        assert logic.state == State.SEEKING
        spins = [a for a in actions if isinstance(a, SpinInPlace)]
        assert len(spins) == 1
        assert spins[0].yaw_rad == pytest.approx(math.pi / 2)

    def test_no_new_ment(self):
        """호출 응답 "네?"는 음성이 이미 했다. 미션은 말하지 않는다."""
        logic = MissionLogic()
        actions = logic.on_wake_doa(90.0, True, 1.0)
        assert not any(isinstance(a, Say) for a in actions)

    def test_remembers_how_to_get_back(self):
        logic = MissionLogic(wake_doa_sign=1.0)
        logic.on_wake_doa(90.0, True, 1.0)
        assert logic._seek_return_yaw == pytest.approx(-math.pi / 2)

    def test_sound_from_the_front_does_not_spin(self):
        """이미 그쪽을 보고 있다 — 돌지 않고 찾기만 한다."""
        logic = MissionLogic(wake_doa_sign=1.0)
        actions = logic.on_wake_doa(3.0, True, 1.0)
        assert logic.state == State.IDLE
        assert not any(isinstance(a, SpinInPlace) for a in actions)
        assert logic._seek_deadline == pytest.approx(1.0 + SEEK_LOOK_SEC)

    def test_ignored_while_guiding(self):
        """안내 중 "비카야"는 기존 사용자의 명령이다 — 고개를 돌리면 안 된다."""
        logic = MissionLogic()
        logic.state = State.NAVIGATING
        assert logic.on_wake_doa(90.0, True, 1.0) == []
        assert logic.state == State.NAVIGATING

    def test_ignored_while_estopped(self):
        logic = MissionLogic()
        logic.estop_active = True
        assert logic.on_wake_doa(90.0, True, 1.0) == []
        assert logic.state == State.IDLE

    def test_ignored_when_nav_not_ready(self):
        logic = MissionLogic()
        assert logic.on_wake_doa(90.0, False, 1.0) == []
        assert logic.state == State.IDLE

    def test_seeking_holds_a_live_goal(self):
        """E-stop 이 회전을 취소할 수 있어야 한다."""
        logic = MissionLogic()
        logic.on_wake_doa(90.0, True, 1.0)
        actions = logic.on_estop(True, 2.0)
        assert any(isinstance(a, CancelNav) for a in actions)
```

- [ ] **Step 2: 시험이 실패하는지 확인한다**

Run: `cd /home/ji_w/wt-callseek/src/vica_mission_manager && python3 -m pytest test/test_mission_logic.py::TestSeekEntry -q`
Expected: FAIL — `AttributeError: SEEKING` / `MissionLogic has no attribute 'on_wake_doa'`

- [ ] **Step 3: 상태를 더한다**

`State` enum 의 `RETURNING = "returning"` 다음 줄에 더한다:

```python
    # "비카야"를 듣고 그 방향으로 고개를 돌리는 중(또는 못 찾고 되돌아 도는
    # 중). 안내 받는 사용자가 아직 없는 구간이다 (호출 접근 설계 §4).
    SEEKING = "seeking"
```

`_GOAL_ACTIVE_STATES` 에 더한다 — E-stop·긴급어가 회전을 취소해야 한다:

```python
_GOAL_ACTIVE_STATES = (
    State.NAVIGATING, State.APPROACHING, State.TURNING, State.RETURNING,
    State.SEEKING,
)
```

- [ ] **Step 4: `__init__` 과 `_to_idle` 에 상태를 더한다**

`__init__` 시그니처의 `arrival_dialog: bool = False,` 다음 줄에 더한다:

```python
        wake_doa_sign: float = 1.0,
        seek_look_sec: float = SEEK_LOOK_SEC,
```

`__init__` 본문의 `self.approach_turn_yaw_rad = approach_turn_yaw_rad` 아래에 더한다:

```python
        # 호출 접근. 마이크 각도 증가 방향(+1 반시계 / -1 시계)은 장비 실측값
        # 이고 노드가 파라미터로 넣어 준다.
        self.wake_doa_sign = wake_doa_sign
        self.seek_look_sec = seek_look_sec
        # 원래 자세로 돌아가기 위해 돌아야 할 누적 각도. 탐색 창 중에 다시
        # 부르면 또 돌므로 덮어쓰지 않고 더한다. None 이면 지금이 복귀 회전이다.
        self._seek_return_yaw: Optional[float] = None
        # 회전을 마치고 사람을 찾는 창의 만료 시각. 이 값이 살아 있는 동안
        # 상태는 IDLE 이다 — 접근 관문을 건드리지 않으려는 설계다.
        self._seek_deadline: Optional[float] = None
```

`_to_idle()` 의 `self._turn_deadline = None` 다음 줄에 더한다:

```python
        self._seek_return_yaw = None
        self._seek_deadline = None
```

- [ ] **Step 5: `on_wake_doa` 를 더한다**

`on_wake` 메서드 **바로 아래**에 더한다:

```python
    def on_wake_doa(self, doa_deg: float, nav_ready: bool, now: float) -> list:
        """"비카야"가 온 방향으로 고개를 돌린다 (호출 접근 설계 §4).

        대기 중에만 연다. 다른 상태의 호출은 기존 on_wake 의 몫이다 —
        안내 중 "비카야"는 지금 안내받는 사용자의 명령이지 새 부름이 아니다.

        마이크는 거리를 모르고 각도도 ±4~16° 라, 소리로 목표점을 만들지
        않는다. 돌아서 카메라가 확인한 뒤에야 기존 접근 경로가 이어받는다.
        """
        if self.state != State.IDLE or self.estop_active or not nav_ready:
            return []
        yaw = doa_to_spin_yaw(doa_deg, self.wake_doa_sign)
        # 돌아야 할 만큼 돌았다고 치고 복귀각을 먼저 누적한다 — 창 중에 다시
        # 부르면 또 돌기 때문에 덮어쓰면 원래 자세로 못 돌아온다.
        back = wrap_to_pi((self._seek_return_yaw or 0.0) - yaw)
        if abs(yaw) < SEEK_MIN_YAW_RAD:
            # 이미 그쪽을 보고 있다. 돌지 않고 찾는 창만 연다.
            self._seek_return_yaw = back
            self._seek_deadline = now + self.seek_look_sec
            return []
        self.state = State.SEEKING
        self._seek_return_yaw = back
        self._seek_deadline = None
        self._turn_deadline = now + SEEK_TURN_TIMEOUT_SEC
        return [SpinInPlace(yaw)]
```

`_turn_deadline` 을 함께 쓰는 것은 의도적이다 — `SEEKING` 과 `TURNING` 은 동시에 성립하지 않고, `_to_idle()` 이 이미 그 값을 비운다.

- [ ] **Step 6: 시험이 통과하는지 확인한다**

Run: `cd /home/ji_w/wt-callseek/src/vica_mission_manager && python3 -m pytest test/test_mission_logic.py -q`
Expected: PASS — 전부 통과

- [ ] **Step 7: 커밋**

```bash
cd /home/ji_w/wt-callseek
git add src/vica_mission_manager/vica_mission_manager/mission_logic.py \
        src/vica_mission_manager/test/test_mission_logic.py
git commit -m "feat(mission): 대기 중 호출 방향으로 고개를 돌린다 (SEEKING)

마이크는 거리를 모르고 각도도 오차가 커서 소리로 목표점을 만들지 않는다.
돌아서 카메라가 확인한 뒤에야 기존 접근 경로가 이어받는다.

안내 중 호출은 열지 않는다 — 그것은 지금 안내받는 사용자의 명령이다.
정면(10도 미만)이면 돌지 않고 찾는 창만 연다."
```

---

### Task 6: ROS2 — 탐색 창과 조용한 복귀

**Files:**
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py` (`on_tick`)
- Test: `vica_ros2_ws/src/vica_mission_manager/test/test_mission_logic.py`

**Interfaces:**
- Consumes: Task 5 의 `State.SEEKING`, `_seek_return_yaw`, `_seek_deadline`
- Produces: 없음 (상태기계 내부 완결)

**흐름:** 회전이 끝나면 `_to_idle()` 로 IDLE 에 내려놓고 탐색 창을 다시 건다. `_seek_return_yaw` 가 `None` 이면 그 회전이 복귀 회전이었다는 뜻이므로 창을 걸지 않고 끝낸다.

- [ ] **Step 1: 실패하는 시험을 쓴다**

`test/test_mission_logic.py` 끝에 더한다:

```python
def seek_and_finish_turn(logic, doa=90.0, t0=1.0):
    """호출 -> 회전 -> 회전 완료. 탐색 창이 열린 IDLE 을 만든다."""
    logic.on_wake_doa(doa, True, t0)
    logic.on_tick(t0 + 1.0, NavStatus.SUCCEEDED)
    return logic


class TestSeekLookWindow:
    def test_turn_done_returns_to_idle_with_a_window(self):
        """IDLE 로 내려오는 것이 요점이다 — 접근 관문은 IDLE 만 통과시킨다."""
        logic = MissionLogic()
        seek_and_finish_turn(logic, t0=1.0)
        assert logic.state == State.IDLE
        assert logic._seek_deadline == pytest.approx(2.0 + SEEK_LOOK_SEC)

    def test_person_found_cancels_the_way_back(self):
        """사람에게 갔으면 되돌아가지 않는다."""
        logic = MissionLogic()
        seek_and_finish_turn(logic, t0=1.0)
        actions, reason = logic.on_approach_request(
            make_approach(), BOUNDS, True, 3.0)
        assert reason == GateReason.OK
        assert logic.state == State.APPROACHING
        # 창이 만료될 시각을 지나도 복귀 회전이 없다.
        later = logic.on_tick(30.0, NavStatus.RUNNING)
        assert not any(isinstance(a, SpinInPlace) for a in later)

    def test_nobody_found_turns_back_quietly(self):
        logic = MissionLogic(wake_doa_sign=1.0)
        seek_and_finish_turn(logic, doa=90.0, t0=1.0)
        actions = logic.on_tick(2.0 + SEEK_LOOK_SEC, NavStatus.NONE)
        spins = [a for a in actions if isinstance(a, SpinInPlace)]
        assert len(spins) == 1
        assert spins[0].yaw_rad == pytest.approx(-math.pi / 2)
        assert logic.state == State.SEEKING
        # 조용히. 복도 소음 오인에 로봇이 말을 걸면 주변을 놀래킨다.
        assert not any(isinstance(a, Say) for a in actions)

    def test_back_home_ends_in_idle(self):
        logic = MissionLogic()
        seek_and_finish_turn(logic, t0=1.0)
        logic.on_tick(2.0 + SEEK_LOOK_SEC, NavStatus.NONE)   # 복귀 회전 시작
        logic.on_tick(20.0, NavStatus.SUCCEEDED)             # 복귀 회전 완료
        assert logic.state == State.IDLE
        assert logic._seek_deadline is None
        assert logic._seek_return_yaw is None

    def test_calling_again_accumulates_the_way_back(self):
        """두 번 부르면 두 번 돈다. 복귀각은 덮어쓰지 않고 더한다."""
        logic = MissionLogic(wake_doa_sign=1.0)
        seek_and_finish_turn(logic, doa=90.0, t0=1.0)        # +90도
        logic.on_wake_doa(90.0, True, 3.0)                   # 또 +90도
        assert logic.state == State.SEEKING
        assert logic._seek_return_yaw == pytest.approx(-math.pi)

    def test_a_new_errand_wins(self):
        """탐색 창 중에 할 일이 생기면 제자리 돌기를 시작하지 않는다."""
        logic = MissionLogic()
        seek_and_finish_turn(logic, t0=1.0)
        logic.on_intent(make_intent(), make_dest(), BOUNDS, True, 3.0)
        assert logic.state == State.NAVIGATING
        actions = logic.on_tick(2.0 + SEEK_LOOK_SEC, NavStatus.RUNNING)
        assert not any(isinstance(a, SpinInPlace) for a in actions)

    def test_spin_that_never_started_escapes_by_clock(self):
        logic = MissionLogic()
        logic.on_wake_doa(90.0, True, 1.0)
        logic.on_tick(1.0 + SEEK_TURN_TIMEOUT_SEC, NavStatus.NONE)
        assert logic.state == State.IDLE

    def test_failed_turn_still_looks(self):
        """회전이 거부돼도 찾아는 본다 — 카메라가 이미 사람을 볼 수도 있다."""
        logic = MissionLogic()
        logic.on_wake_doa(90.0, True, 1.0)
        logic.on_tick(2.0, NavStatus.FAILED)
        assert logic.state == State.IDLE
        assert logic._seek_deadline is not None
```

`BOUNDS`(34행) · `make_approach`(658행) · `make_intent` · `make_dest` 는 이 시험 파일에 이미 있는 이름이다. 새로 만들지 않는다.

- [ ] **Step 2: 시험이 실패하는지 확인한다**

Run: `cd /home/ji_w/wt-callseek/src/vica_mission_manager && python3 -m pytest test/test_mission_logic.py::TestSeekLookWindow -q`
Expected: FAIL — 회전 완료 후 창이 안 열린다 (`_seek_deadline is None`)

- [ ] **Step 3: `on_tick` 에 두 분기를 더한다**

`on_tick` 의 `elif self.state == State.TURNING:` 블록 **바로 앞**에 더한다:

```python
        elif self.state == State.SEEKING:
            if nav_status in (NavStatus.SUCCEEDED, NavStatus.FAILED,
                              NavStatus.CANCELED):
                # 복귀각이 남아 있으면 방금 것은 '가는' 회전이다 — IDLE 로
                # 내려놓고 사람을 찾는 창을 연다. IDLE 이어야 접근 관문을
                # 그대로 통과한다. 없으면 방금 것이 복귀 회전이라 끝이다.
                #
                # 회전이 거부돼도(FAILED) 찾아는 본다. 카메라가 이미 사람을
                # 보고 있을 수 있고, 못 봐도 창이 닫히면 조용히 끝난다.
                back = self._seek_return_yaw
                self._to_idle()
                if back is not None:
                    self._seek_return_yaw = back
                    self._seek_deadline = now + self.seek_look_sec
            elif (self._turn_deadline is not None
                  and now >= self._turn_deadline):
                # spin 이 시작조차 안 됐다. 시계로 탈출한다.
                self._to_idle()

        elif self.state == State.IDLE:
            # 찾는 창이 닫혔다. 아무도 못 찾았으니 조용히 원래 자세로.
            # 되돌리지 않으면 오작동 한 번에 카메라가 벽만 보는 자세로 굳는다.
            if self._seek_deadline is not None and now >= self._seek_deadline:
                back = self._seek_return_yaw
                self._seek_deadline = None
                self._seek_return_yaw = None
                if back is not None and abs(back) >= SEEK_MIN_YAW_RAD:
                    self.state = State.SEEKING
                    self._turn_deadline = now + SEEK_TURN_TIMEOUT_SEC
                    actions.append(SpinInPlace(back))
```

IDLE 분기가 `_seek_deadline` 만 보므로, 그 사이 목적지를 받아 상태가 바뀌면 이 분기 자체에 닿지 않는다. 나중에 IDLE 로 내려올 때 `_to_idle()` 이 값을 비운다.

- [ ] **Step 4: 시험이 통과하는지 확인한다**

Run: `cd /home/ji_w/wt-callseek/src/vica_mission_manager && python3 -m pytest test/test_mission_logic.py -q`
Expected: PASS — 전부 통과 (기존 171건 회귀 없음)

- [ ] **Step 5: 커밋**

```bash
cd /home/ji_w/wt-callseek
git add src/vica_mission_manager/vica_mission_manager/mission_logic.py \
        src/vica_mission_manager/test/test_mission_logic.py
git commit -m "feat(mission): 고개를 돌린 뒤 찾는 창을 열고, 없으면 조용히 되돌아간다

회전이 끝나면 IDLE 로 내려놓는다. 접근 관문이 IDLE 만 통과시키므로 관문을
건드리지 않고 기존 접근 경로에 합류할 수 있다.

사람을 못 찾으면 말없이 원래 각도로 돌아간다. 안 되돌리면 오작동 한 번에
카메라가 벽만 보는 자세로 굳는다. 복도 소음 오인에 말을 걸면 주변을
놀래키므로 멘트는 없다."
```

---

### Task 7: ROS2 — 노드 배선

**Files:**
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_manager_node.py`

**Interfaces:**
- Consumes: Task 3 의 토픽 `/vica/wake_doa`, Task 5 의 `logic.on_wake_doa(...)`
- Produces: ROS 파라미터 `wake_doa_sign`(double, 기본 1.0), `seek_look_sec`(double, 기본 6.0)

- [ ] **Step 1: import 를 더한다**

`from std_msgs.msg import Bool, String` 을 바꾼다:

```python
from std_msgs.msg import Bool, Float32, String
```

같은 파일의 `mission_logic` import 목록에 `State` 가 이미 있는지 확인한다 (Step 4 에서 쓴다). 없으면 더한다.

- [ ] **Step 2: 파라미터를 선언한다**

`self.declare_parameter("approach_turn_yaw_deg", 180.0)` 다음 줄에 더한다:

```python
        # 마이크 각도 증가 방향. +1 반시계 / -1 시계 — 장비 실측값이다
        # (호출 접근 설계 §5). 틀리면 로봇이 호출 방향의 정반대로 돈다.
        self.declare_parameter("wake_doa_sign", 1.0)
        # 고개를 돌린 뒤 사람을 찾는 시간(초).
        self.declare_parameter("seek_look_sec", 6.0)
```

- [ ] **Step 3: `MissionLogic` 에 넘긴다**

`approach_turn_yaw_rad=math.radians(...)` 인자 아래에 더한다:

```python
            wake_doa_sign=float(self.get_parameter("wake_doa_sign").value),
            seek_look_sec=float(self.get_parameter("seek_look_sec").value),
```

- [ ] **Step 4: 구독과 핸들러를 더한다**

`/vica/wake` 구독 블록 **바로 아래**에 더한다:

```python
        # 호출이 온 방향. 대기 중에만 받아 그쪽으로 고개를 돌린다
        # (호출 접근 설계). /vica/wake 와 도착 순서는 상관없다 — IDLE 에서
        # /vica/wake 는 아무 일도 하지 않고, 새 흐름은 이 토픽만으로 열린다.
        self.create_subscription(
            Float32, "/vica/wake_doa", self._on_wake_doa, 10,
            callback_group=self._main_group,
        )
```

`_on_wake` 메서드 **바로 아래**에 더한다:

```python
    def _on_wake_doa(self, msg: Float32) -> None:
        """/vica/wake_doa — 호출 방향으로 고개를 돌린다 (IDLE 에서만)."""
        before = self.logic.state
        actions = self.logic.on_wake_doa(
            float(msg.data), self._nav2_ready(), self._now())
        if actions or before != self.logic.state:
            self._run_actions(actions)
            self.get_logger().info(
                f"'비카야' 방향 {msg.data:.0f}°: "
                f"{before.value} -> {self.logic.state.value}")
```

- [ ] **Step 5: 회전 중에는 YOLO 를 멈춘다**

`msg.is_moving = self.logic.state == State.NAVIGATING` 을 바꾼다:

```python
        # SEEKING(제자리 회전) 중 영상은 화면이 통째로 흐른다. detection_gate 의
        # 변위 관문(0.3 m)이 어차피 트랙을 계속 깨뜨리므로, 쓰이지 않을 추론에
        # CPU 를 쓰지 않는다 — 이 로봇의 제1 병목은 CPU 다.
        # APPROACHING 을 넣지 않는 것은 의도된 현행 유지다: 접근 중에는 목표점
        # 갱신에 탐지가 필요하다.
        msg.is_moving = self.logic.state in (State.NAVIGATING, State.SEEKING)
```

- [ ] **Step 6: 빌드하고 기존 시험을 돌린다**

Run:
```bash
cd /home/ji_w/wt-callseek/src/vica_mission_manager && python3 -m pytest test/ -q
python3 -c "import ast; ast.parse(open('/home/ji_w/wt-callseek/src/vica_mission_manager/vica_mission_manager/mission_manager_node.py').read())"
```
Expected: PASS — 시험 전부 통과, 문법 오류 없음

- [ ] **Step 7: 커밋**

```bash
cd /home/ji_w/wt-callseek
git add src/vica_mission_manager/vica_mission_manager/mission_manager_node.py
git commit -m "feat(mission): /vica/wake_doa 를 받아 SEEKING 을 연다

마이크 각도 증가 방향(wake_doa_sign)은 장비 실측값이라 파라미터로 뺐다.
회전 중에는 is_moving 을 세워 YOLO 추론을 멈춘다 — 화면이 통째로 흐르는
동안의 탐지는 변위 관문에 어차피 걸려 버려진다."
```

---

### Task 8: 실기 검증 (사용자 판정)

**Files:** 없음 (관찰과 기록)

**Interfaces:**
- Consumes: Task 1~7 전부

- [ ] **Step 1: 브랜치가 dev 에 뒤처지지 않았는지 본다**

```bash
cd /home/ji_w/wt-callseek && git log --oneline feat/voice-call-approach..dev
cd /home/ji_w/VICA-smarthandle/vica-voice-llm && git log --oneline feat/wake-doa-publish..dev
```
Expected: 둘 다 출력 없음. 있으면 dev 를 머지한 뒤 진행한다 — 뒤처진 브랜치로 달리면 옛 footprint·옛 파라미터로 시험하게 된다.

- [ ] **Step 2: 메인 워크스페이스에서 체크아웃하고 빌드한다**

```bash
cd /home/ji_w/VICA-smarthandle/vica_ros2_ws && git status --porcelain
```
먼저 이 명령으로 **작업 중인 변경이 없는지 확인한다** (현재 이 워크스페이스는 `feat/carto-corridor-window` 에 67개 변경이 있다). 있으면 사용자에게 알리고 어떻게 할지 물은 뒤에 진행한다 — 임의로 stash 하거나 버리지 않는다.

깨끗해진 뒤:
```bash
git checkout feat/voice-call-approach
colcon build --packages-select vica_mission_manager --symlink-install
```

- [ ] **Step 3: 방향이 실제로 나오는지 본다**

노드를 띄운 뒤 별도 칸에서:
```bash
ros2 topic echo /vica/wake_doa
```
"비카야"를 부른다.

Expected: 부를 때마다 값이 한 번 나온다. 값이 서 있는 자리와 대체로 맞아야 한다(정면 0 부근 / 핸들 쪽 180 부근).

- [ ] **Step 4: 네 방향에서 부른다 — 부호 확인이 여기서 끝난다**

로봇을 대기(IDLE) 상태로 두고 **왼쪽 · 오른쪽 · 뒤** 각각에서 "비카야"를 부른다.

Expected: 매번 **부른 쪽으로** 돈다. 반대로 돌면 `wake_doa_sign` 부호가 틀린 것이므로 파라미터를 뒤집고 재시험한다. 바퀴가 떠 있는지 먼저 확인하고, 주행 명령을 내리기 전 knob(가변저항)이 0% 가 아닌지 본다.

- [ ] **Step 5: 종단 한 번**

옆에서 부른 뒤 그대로 서 있는다.

Expected: 회전 → 접근(1.1 m 앞 정지) → "안내를 받으시겠어요?" → "네" → 회전 예고 멘트 → 180° 회전 → 온보딩 질문까지 **끊김 없이** 이어진다.

- [ ] **Step 6: 헛호출과 회귀**

- 아무도 없는 쪽으로 돌게 만든 뒤(복도 소음·먼 곳에서 호출) **조용히** 원래 각도로 돌아오는지 본다. `SEEK_LOOK_SEC` 6초가 너무 짧거나 길면 여기서 드러난다 — 값을 조정하고 스펙의 `[TARGET]` 을 걷는다.
- **안내 중** "비카야"를 불러 종전대로 동작하는지 본다(고개를 돌리면 안 된다).

- [ ] **Step 7: 결과를 devlog 에 남기고 커밋한다**

관찰한 것(부호 실측값, `SEEK_LOOK_SEC` 최종값, 실패 사례)을 `devlog/2026-09-__-호출접근-실기.md` 에 남긴다. 실주행 1회마다 커밋하고, 커밋 메시지에 바꾼 파라미터의 이유와 결과를 적는다.

**dev 머지는 사용자가 판정한다.** 시험 통과가 머지 근거가 아니다.

---

## Self-Review

**스펙 대응:**

| 스펙 절 | 담당 Task |
| --- | --- |
| §2 마이크 사실·한계 | Task 1 (기준선 재확인) |
| §3 `/vica/wake_doa` · `/vica/wake` 불변 | Task 2·3 |
| §4 `SEEKING` · IDLE 탐색 창 · 관문 불변 | Task 5·6 |
| §4 `_GOAL_ACTIVE_STATES` · `is_moving` 확장 | Task 5 (전자) · Task 7 (후자) |
| §4 상수 `SEEK_LOOK_SEC` · `SEEK_TURN_TIMEOUT_SEC` | Task 4 |
| §5 부호 실측 | Task 1 · Task 8 Step 4 |
| §6 건드리지 않는 것 | Global Constraints + 각 Task 커밋 범위 |
| §7 실패·경계 9종 | Task 5·6 시험 (헛호출·재호출·선점·시계탈출·E-stop·회전실패) |
| §8 범위 | Task 1~8 |
| §9 시험 | Task 4·5·6 (단위) · Task 8 (실기) |

**스펙 정정 1건:** §7 의 "탐색 창 중 다시 호출 → 복귀각은 **처음 것을 유지**"는 부정확했다. 두 번 돌면 복귀각도 두 번 분이어야 하므로 **누적**이 맞다. Task 5 는 누적으로 구현하고, 스펙 §7 의 그 줄도 함께 고친다.
