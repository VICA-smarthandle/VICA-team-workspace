# Motor CAN health 보고와 중앙 걸쇠 통합 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 주행 중 CAN 장애가 발생해도 `mdrobot_can_keyboard_knob_node`가 종료되지 않고, CAN 링크 상태를 보고하며, `emergency_stop_node`가 이를 중앙 걸쇠 원인으로 흡수해 관리자 앱 reset 경로 하나로만 해제되게 한다.

**Architecture:** motor node는 CAN 예외를 격리해 프로세스를 유지하고 `/motor/can_ok`(`std_msgs/Bool`)로 링크 상태를 발행한다. `emergency_stop_node`는 이 토픽을 `motor_can` 원인으로 구독하되, **미수신도 고장으로 판정**해 motor node 프로세스 사망까지 커버한다. 걸쇠는 safety 계층이 단독 소유하고, motor node는 자체 걸쇠를 갖지 않는다.

**Tech Stack:** ROS 2 Humble (rclpy), python-can, `diagnostic_updater`, pytest, colcon

**설계 문서:** `docs/superpowers/specs/2026-07-27-motor-can-health-design.md`

## Global Constraints

- 모든 경과시간 판단은 단일 `ClockType.STEADY_TIME` clock과 **정수 나노초**를 쓴다. 판정 함수는 시각을 스스로 조회하지 않고 인자로 주입받는다.
- 미수신 sentinel은 `0.0`이 아니라 `None`이다. 음수 age(시간 역전)는 stale로 처리한다.
- 순수 판정 로직은 ROS 의존 없는 별도 모듈에 두고 단위 테스트한다 (`freshness.py`, `motor_watchdog.py` 패턴).
- `/diagnostics`는 **보고 전용**이다. 정지 경로로 쓰지 않는다.
- motor node는 E-stop 걸쇠를 소유하지 않는다. reset은 관리자 앱 경로 하나뿐이다.
- 기존 timeout 파라미터 값, 토픽 이름, QoS, Safety 정책은 바꾸지 않는다.
- 신규 파일은 flake8/pydocstyle을 통과해야 한다. 기존 `mdrobot_can_control`의 `test_flake8`/`test_pep257` 실패는 이번 변경 이전부터 있던 것이며, **위반 수를 늘리지 않는 것**이 기준이다.
- 작업 브랜치: `feat/motor-can-health` (dev에서 분기)
- 테스트 실행은 `source /opt/ros/humble/setup.bash` 이후에 한다.

---

### Task 1: `CanLink` 순수 모델

**Files:**
- Create: `vica_ros2_ws/src/mdrobot_can_control/mdrobot_can_control/can_link.py`
- Test: `vica_ros2_ws/src/mdrobot_can_control/test/test_can_link.py`

**Interfaces:**
- Consumes: `mdrobot_can_control.freshness.sec_to_ns` (기존)
- Produces:
  - `class CanLink`
  - `CanLink(retry_interval_ns: int)` — 생성 직후 상태는 정상(`is_ok() is True`)
  - `record_success() -> None`
  - `record_error(exc: BaseException, now_ns: int) -> None`
  - `is_ok() -> bool`
  - `should_retry(now_ns: int) -> bool`
  - `mark_retry_attempted(now_ns: int) -> None`
  - `last_error: Optional[str]` (속성)

- [ ] **Step 1: Write the failing test**

`vica_ros2_ws/src/mdrobot_can_control/test/test_can_link.py`:

```python
"""CAN 링크 상태 모델 단위 테스트.

주행 중 CAN 장애에서 프로세스를 유지하되 출력을 0으로 막기 위한 판정이다.
시각은 모두 정수 나노초(STEADY_TIME)이며 모델이 스스로 조회하지 않는다.
"""

from mdrobot_can_control.can_link import CanLink
from mdrobot_can_control.freshness import sec_to_ns


T0 = 1_000_000_000
RETRY_NS = sec_to_ns(1.0)


def test_new_link_is_ok():
    """bus 개방 성공 뒤에만 생성하므로 초기 상태는 정상이다."""
    link = CanLink(retry_interval_ns=RETRY_NS)

    assert link.is_ok() is True
    assert link.last_error is None


def test_error_marks_link_failed():
    """CAN 예외를 기록하면 즉시 비정상으로 전환한다."""
    link = CanLink(retry_interval_ns=RETRY_NS)

    link.record_error(OSError("Network is down"), T0)

    assert link.is_ok() is False
    assert "Network is down" in link.last_error


def test_success_restores_link():
    """재연결 성공 뒤에는 정상으로 복귀한다."""
    link = CanLink(retry_interval_ns=RETRY_NS)
    link.record_error(OSError("boom"), T0)

    link.record_success()

    assert link.is_ok() is True


def test_healthy_link_never_retries():
    """정상 상태에서는 재연결을 시도하지 않는다."""
    link = CanLink(retry_interval_ns=RETRY_NS)

    assert link.should_retry(T0) is False


def test_retry_waits_for_interval():
    """실패 직후에는 재시도하지 않고 간격이 지나야 시도한다."""
    link = CanLink(retry_interval_ns=RETRY_NS)
    link.record_error(OSError("boom"), T0)

    assert link.should_retry(T0 + RETRY_NS - 1) is False
    assert link.should_retry(T0 + RETRY_NS) is True


def test_retry_attempt_restarts_interval():
    """시도했으면 다음 간격까지 다시 기다린다."""
    link = CanLink(retry_interval_ns=RETRY_NS)
    link.record_error(OSError("boom"), T0)
    link.mark_retry_attempted(T0 + RETRY_NS)

    assert link.should_retry(T0 + RETRY_NS + 1) is False
    assert link.should_retry(T0 + RETRY_NS * 2) is True


def test_time_reversal_allows_retry():
    """시간이 뒤로 가도 재연결이 영구히 막히면 안 된다(fail-safe 방향)."""
    link = CanLink(retry_interval_ns=RETRY_NS)
    link.record_error(OSError("boom"), T0)

    assert link.should_retry(T0 - sec_to_ns(3600)) is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source /opt/ros/humble/setup.bash
cd vica_ros2_ws/src/mdrobot_can_control && python3 -m pytest test/test_can_link.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'mdrobot_can_control.can_link'`

- [ ] **Step 3: Write minimal implementation**

`vica_ros2_ws/src/mdrobot_can_control/mdrobot_can_control/can_link.py`:

```python
"""CAN 링크 상태 모델.

주행 중 CAN 인터페이스가 사라지면 python-can이 예외를 던진다. 이를 잡지 않으면
최종 구동단 노드가 종료되어 정지 상태를 유지하거나 보고할 주체가 사라진다.
이 모델은 예외를 상태로 바꾸고, 재연결 시도 시점을 결정한다.

시각은 모두 정수 나노초(STEADY_TIME)이며 호출자가 주입한다. 이 모델은 걸쇠가
아니다. 걸쇠는 vica_safety의 중앙 래치가 소유한다.
"""

from typing import Optional


class CanLink:
    """Track CAN bus health and pace reconnect attempts."""

    def __init__(self, retry_interval_ns: int):
        """Start in the healthy state; created only after the bus opened."""
        self.retry_interval_ns = retry_interval_ns
        self._ok = True
        self.last_error: Optional[str] = None
        self._last_attempt_ns: Optional[int] = None

    def record_success(self) -> None:
        """Return to the healthy state after a successful CAN operation."""
        self._ok = True
        self._last_attempt_ns = None

    def record_error(self, exc: BaseException, now_ns: int) -> None:
        """Move to the failed state and remember the reason."""
        self._ok = False
        self.last_error = str(exc)
        self._last_attempt_ns = now_ns

    def is_ok(self) -> bool:
        """Return True only while CAN traffic is believed to work."""
        return self._ok

    def should_retry(self, now_ns: int) -> bool:
        """Return True when a reconnect attempt is due.

        시간 역전(음수 경과)에서도 True를 돌려준다. 재연결이 영구히 막히면
        `/motor/can_ok`가 복구되지 않아 관리자 reset이 불가능해진다.
        """
        if self._ok:
            return False
        if self._last_attempt_ns is None:
            return True
        elapsed = now_ns - self._last_attempt_ns
        if elapsed < 0:
            return True
        return elapsed >= self.retry_interval_ns

    def mark_retry_attempted(self, now_ns: int) -> None:
        """Record a reconnect attempt so the next one waits one interval."""
        self._last_attempt_ns = now_ns
```

- [ ] **Step 4: Run test to verify it passes**

```bash
source /opt/ros/humble/setup.bash
cd vica_ros2_ws/src/mdrobot_can_control && python3 -m pytest test/test_can_link.py -q
```

Expected: `7 passed`

- [ ] **Step 5: Check style**

```bash
source /opt/ros/humble/setup.bash
cd vica_ros2_ws/src/mdrobot_can_control
python3 -m flake8 mdrobot_can_control/can_link.py test/test_can_link.py
python3 -m pydocstyle mdrobot_can_control/can_link.py test/test_can_link.py
```

Expected: 출력 없음 (위반 0건)

- [ ] **Step 6: Commit**

```bash
cd vica_ros2_ws
git add src/mdrobot_can_control/mdrobot_can_control/can_link.py \
        src/mdrobot_can_control/test/test_can_link.py
git commit -m "feat(motor): CAN 링크 상태 모델 추가

주행 중 CAN 예외를 상태로 바꾸고 재연결 시점을 결정하는 순수 모델.
시간 역전에서도 재연결을 막지 않아 복구 경로가 닫히지 않게 한다."
```

---

### Task 2: motor node가 CAN 예외에 죽지 않고 출력을 0으로 막는다

**Files:**
- Modify: `vica_ros2_ws/src/mdrobot_can_control/mdrobot_can_control/mdrobot_can_keyboard_knob_node.py`
- Modify: `vica_ros2_ws/src/mdrobot_can_control/package.xml`

**Interfaces:**
- Consumes: `CanLink` (Task 1), `motor_speed_ratio` (기존)
- Produces: 토픽 `/motor/can_ok` (`std_msgs/msg/Bool`), 노드 속성 `self.can_link`

**배경:** 현재 `drain_can_rx`의 `self.bus.recv()`와 `send_vel_cmd`의 `self.bus.send()`가 예외를 흘려보내 프로세스가 종료된다. 2026-07-27 실기에서 `can.exceptions.CanOperationError: Error receiving: Network is down`으로 재현했다.

- [ ] **Step 1: 새 파라미터와 상태 선언**

`mdrobot_can_keyboard_knob_node.py`의 `declare_parameter("min_rpm_when_moving", 0)` 바로 뒤에 추가:

```python
        # CAN 실패 후 재연결을 시도하는 최소 간격(초)
        self.declare_parameter("can_reconnect_interval_sec", 1.0)
```

파라미터 로딩부(`self.min_rpm_when_moving = ...` 뒤)에 추가:

```python
        self.can_reconnect_interval_sec = float(
            self.get_parameter("can_reconnect_interval_sec").value
        )
```

`self.resend_interval_ns = sec_to_ns(self.resend_interval_sec)` 뒤에 추가:

```python
        self.can_reconnect_interval_ns = sec_to_ns(
            self.can_reconnect_interval_sec
        )
```

`self.last_send_ns = None` 선언 뒤에 로그 throttle 상태를 추가:

```python
        self.last_can_error_log_ns = None
```

- [ ] **Step 2: import와 CanLink 생성**

파일 상단 import에 추가:

```python
from std_msgs.msg import Bool

from .can_link import CanLink
```

`self.bus = can.interface.Bus(...)` 블록 **뒤**에 추가:

```python
        self.can_link = CanLink(
            retry_interval_ns=self.can_reconnect_interval_ns
        )
```

`self.sub_cmd_vel = self.create_subscription(...)` 뒤에 발행자 추가:

```python
        self.pub_can_ok = self.create_publisher(Bool, "/motor/can_ok", 10)
```

- [ ] **Step 3: CAN 송수신을 예외 격리로 감싼다**

`send_pnt_io_monitor_on`은 **수정하지 않는다.** 생성자에서 호출될 때는 기동
실패를 fail-fast로 드러내야 하고, Step 4에서 추가할 `try_reconnect_can`이
호출할 때는 그쪽 `try/except`가 예외를 받는다.

`send_vel_cmd`의 마지막 줄 `self.bus.send(msg)`를 교체:

```python
        try:
            self.bus.send(msg)
        except can.CanError as exc:
            self.can_link.record_error(exc, self.now_ns())
            self.log_can_error_throttled("send", exc)
```

`drain_can_rx`의 `for` 루프 전체를 `try`로 감싼다:

```python
        try:
            # 버스 혼잡을 줄이기 위해 사이클당 읽는 CAN 프레임 수를 제한합니다.
            for _ in range(50):
                msg = self.bus.recv(timeout=0.0)
                if msg is None:
                    break

                d = msg.data
                if len(d) == 8 and d[0] == PID_PNT_IO_MONITOR:
                    if d[1] == 0:
                        self.knob1 = clamp(int(d[6]), 0, 100)
                        self.knob2 = clamp(int(d[7]), 0, 100)
                        self.last_knob_ns = now_ns
        except can.CanError as exc:
            self.can_link.record_error(exc, now_ns)
            self.log_can_error_throttled("recv", exc)
```

- [ ] **Step 4: 재연결과 로그 throttle 메서드 추가**

`now_ns` 메서드 바로 뒤에 추가:

```python
    def log_can_error_throttled(self, phase: str, exc: BaseException) -> None:
        """Report a CAN failure at most once per reconnect interval."""
        now = self.now_ns()
        due = (
            self.last_can_error_log_ns is None or
            (now - self.last_can_error_log_ns) >= self.can_reconnect_interval_ns
        )
        if due:
            self.get_logger().error(
                f"[CAN FAULT] phase={phase} iface={self.can_iface} "
                f"error={exc}; 출력을 0으로 유지합니다"
            )
            self.last_can_error_log_ns = now

    def try_reconnect_can(self, now_ns: int) -> None:
        """Reopen the CAN bus while the link is failed.

        걸쇠는 vica_safety가 소유하므로 재연결에 성공해도 주행이 스스로
        재개되지 않는다. 재연결이 없으면 `/motor/can_ok`가 복구되지 않아
        관리자 reset이 영원히 거부된다.
        """
        if not self.can_link.should_retry(now_ns):
            return
        self.can_link.mark_retry_attempted(now_ns)
        try:
            if self.bus is not None:
                self.bus.shutdown()
        except Exception:  # noqa: BLE001 - 종료 실패는 재개방을 막지 않는다
            pass
        try:
            self.bus = can.interface.Bus(
                channel=self.can_iface,
                interface="socketcan"
            )
            self.send_pnt_io_monitor_on()
            self.can_link.record_success()
            self.get_logger().info(
                f"[CAN RECOVERED] iface={self.can_iface}; "
                "주행 재개는 관리자 reset 이후에만 가능합니다"
            )
        except (can.CanError, OSError) as exc:
            self.can_link.record_error(exc, now_ns)
```

- [ ] **Step 5: control_loop에 CAN 게이트와 발행 추가**

`control_loop`에서 `self.drain_can_rx(now)` **뒤**, `speed_ratio = motor_speed_ratio(` **앞**에 추가:

```python
        if not self.can_link.is_ok():
            self.try_reconnect_can(now)

        can_ok_msg = Bool()
        can_ok_msg.data = self.can_link.is_ok()
        self.pub_can_ok.publish(can_ok_msg)
```

`speed_ratio = motor_speed_ratio(...)` 호출 **뒤**에 CAN 게이트를 추가:

```python
        # CAN 링크가 비정상이면 cmd·knob 판정과 무관하게 0으로 막는다.
        # 정지는 여기서 즉시 이루어지며 /diagnostics를 기다리지 않는다.
        if not self.can_link.is_ok():
            speed_ratio = 0.0
```

- [ ] **Step 6: package.xml 의존 추가**

`<depend>geometry_msgs</depend>` 뒤에 추가:

```xml
  <depend>std_msgs</depend>
```

- [ ] **Step 7: 빌드하고 기존 테스트가 깨지지 않는지 확인**

```bash
cd vica_ros2_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select mdrobot_can_control
colcon test --packages-select mdrobot_can_control
colcon test-result --verbose 2>&1 | tail -20
```

Expected: 기능 테스트 전부 통과. 실패는 기존 `test_flake8`/`test_pep257` 2건뿐.

- [ ] **Step 8: 스타일 위반 수가 늘지 않았는지 확인**

```bash
source /opt/ros/humble/setup.bash
cd vica_ros2_ws
python3 -m flake8 src/mdrobot_can_control/mdrobot_can_control/mdrobot_can_keyboard_knob_node.py | wc -l
```

Expected: 78 이하 (변경 전 값이 78이다. 초과하면 새 위반을 추가한 것이므로 고칠 것)

- [ ] **Step 9: Commit**

```bash
cd vica_ros2_ws
git add src/mdrobot_can_control/mdrobot_can_control/mdrobot_can_keyboard_knob_node.py \
        src/mdrobot_can_control/package.xml
git commit -m "fix(motor): CAN 장애에서 노드를 유지하고 /motor/can_ok를 발행

주행 중 can1이 사라지면 bus.recv/send가 예외를 던져 프로세스가 종료됐다.
예외를 CanLink 상태로 격리해 노드를 유지하고, 링크가 비정상이면 cmd·knob
판정과 무관하게 출력을 0으로 막는다. 링크 상태는 /motor/can_ok로 발행해
safety 계층이 걸쇠 판단에 쓴다. 재연결은 간격 제한을 두고 시도하되, 걸쇠는
소유하지 않으므로 주행 재개는 관리자 reset을 거친다."
```

---

### Task 3: 중앙 걸쇠에 `motor_can` 원인 추가

**Files:**
- Modify: `vica_ros2_ws/src/vica_safety/vica_safety/emergency_latch.py`
- Modify: `vica_ros2_ws/src/vica_safety/test/test_emergency_latch.py`

**Interfaces:**
- Consumes: `vica_safety.freshness.is_fresh_ns` (기존)
- Produces:
  - `EmergencyLatch(f1_timeout_ns: int, motor_can_timeout_ns: int, initially_latched: bool = True)`
  - `mark_motor_can_seen(ok: bool, now: int) -> None`
  - `evaluate()`가 돌려주는 `active_sources`에 `"motor_can"` / `"motor_can_stale"` 포함

**주의:** 생성자에 인자를 추가하므로 기존 테스트 9곳의 `EmergencyLatch(...)` 호출을 모두 갱신해야 한다. 기본값을 주지 않는 이유는 안전 파라미터를 암묵적으로 상속시키지 않기 위해서다.

- [ ] **Step 1: Write the failing tests**

`test_emergency_latch.py` 상단 상수 아래에 추가:

```python
MOTOR_CAN_TIMEOUT_NS = sec_to_ns(0.5)
```

파일 끝에 추가:

```python
def test_motor_can_failure_latches():
    """motor node가 CAN 장애를 보고하면 중앙 걸쇠가 걸린다."""
    latch = EmergencyLatch(
        f1_timeout_ns=TIMEOUT_NS,
        motor_can_timeout_ns=MOTOR_CAN_TIMEOUT_NS,
    )
    latch.mark_physical_seen(False, T0)

    latch.mark_motor_can_seen(False, T0)

    snapshot = latch.evaluate(T0)
    assert snapshot.latched is True
    assert "motor_can" in snapshot.active_sources


def test_missing_motor_can_report_is_stale():
    """motor node가 죽어 보고가 끊기면 stale로 걸쇠가 걸린다."""
    latch = EmergencyLatch(
        f1_timeout_ns=TIMEOUT_NS,
        motor_can_timeout_ns=MOTOR_CAN_TIMEOUT_NS,
    )
    latch.mark_physical_seen(False, T0)
    latch.mark_motor_can_seen(True, T0)

    now = T0 + MOTOR_CAN_TIMEOUT_NS + 1
    latch.mark_physical_seen(False, now)

    snapshot = latch.evaluate(now)
    assert snapshot.latched is True
    assert "motor_can_stale" in snapshot.active_sources


def test_motor_can_boundary_is_fresh():
    """경계값 age == timeout은 fresh다."""
    latch = EmergencyLatch(
        f1_timeout_ns=TIMEOUT_NS,
        motor_can_timeout_ns=MOTOR_CAN_TIMEOUT_NS,
    )
    now = T0 + MOTOR_CAN_TIMEOUT_NS
    latch.mark_physical_seen(False, now)
    latch.mark_motor_can_seen(True, T0)

    snapshot = latch.evaluate(now)
    assert "motor_can_stale" not in snapshot.active_sources


def test_never_reported_motor_can_is_stale():
    """한 번도 보고받지 못한 상태는 fail-closed로 stale이다."""
    latch = EmergencyLatch(
        f1_timeout_ns=TIMEOUT_NS,
        motor_can_timeout_ns=MOTOR_CAN_TIMEOUT_NS,
    )
    latch.mark_physical_seen(False, T0)

    snapshot = latch.evaluate(T0)
    assert "motor_can_stale" in snapshot.active_sources


def test_reset_rejected_while_motor_can_failed():
    """CAN이 비정상인 동안에는 관리자 reset도 거부된다."""
    latch = EmergencyLatch(
        f1_timeout_ns=TIMEOUT_NS,
        motor_can_timeout_ns=MOTOR_CAN_TIMEOUT_NS,
    )
    latch.mark_physical_seen(False, T0)
    latch.mark_motor_can_seen(False, T0)

    accepted, message = latch.try_reset(T0)

    assert accepted is False
    assert "motor_can" in message


def test_reset_allowed_after_can_recovers():
    """CAN 복구 후에는 관리자 reset으로 해제된다."""
    latch = EmergencyLatch(
        f1_timeout_ns=TIMEOUT_NS,
        motor_can_timeout_ns=MOTOR_CAN_TIMEOUT_NS,
    )
    latch.mark_physical_seen(False, T0)
    latch.mark_motor_can_seen(False, T0)

    now = T0 + sec_to_ns(0.1)
    latch.mark_physical_seen(False, now)
    latch.mark_motor_can_seen(True, now)

    accepted, _ = latch.try_reset(now)
    assert accepted is True
    assert latch.evaluate(now).latched is False
```

기존 9곳의 `EmergencyLatch(f1_timeout_ns=TIMEOUT_NS)` 호출을 모두 아래로 바꾸고, 각 테스트에서 `mark_motor_can_seen(True, <해당 now>)`를 호출해 stale 원인이 섞이지 않게 한다:

```python
    latch = EmergencyLatch(
        f1_timeout_ns=TIMEOUT_NS,
        motor_can_timeout_ns=MOTOR_CAN_TIMEOUT_NS,
    )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source /opt/ros/humble/setup.bash
cd vica_ros2_ws/src/vica_safety && python3 -m pytest test/test_emergency_latch.py -q
```

Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'motor_can_timeout_ns'`

- [ ] **Step 3: Write minimal implementation**

`emergency_latch.py`의 `__init__`을 교체:

```python
    def __init__(
        self,
        f1_timeout_ns: int,
        motor_can_timeout_ns: int,
        initially_latched: bool = True,
    ):
        self.f1_timeout_ns = f1_timeout_ns
        self.motor_can_timeout_ns = motor_can_timeout_ns
        self.latched = initially_latched
        self.sources = {
            "physical_f1": False,
            "app": False,
            "voice": False,
            "motor_can": False,
        }
        # None = 물리 F1을 한 번도 수신하지 않음 (0.0 sentinel 금지).
        self.last_physical_ns: Optional[int] = None
        # None = motor node의 CAN 상태를 한 번도 수신하지 않음.
        self.last_motor_can_ns: Optional[int] = None
```

`mark_physical_seen` 뒤에 추가:

```python
    def mark_motor_can_seen(self, ok: bool, now: int) -> None:
        """Record the motor node CAN link report.

        `ok=False`는 CAN 장애이므로 즉시 latch한다. 보고가 끊기는 경우는
        `evaluate`가 stale로 처리한다(motor node 프로세스 사망 포함).
        """
        self.sources["motor_can"] = not ok
        self.last_motor_can_ns = now
        if not ok:
            self.latched = True
```

`evaluate`를 교체:

```python
    def evaluate(self, now: int) -> LatchSnapshot:
        physical_fresh = is_fresh_ns(
            self.last_physical_ns,
            now_ns=now,
            timeout_ns=self.f1_timeout_ns,
        )
        motor_can_fresh = is_fresh_ns(
            self.last_motor_can_ns,
            now_ns=now,
            timeout_ns=self.motor_can_timeout_ns,
        )
        active_sources = [
            name for name, active in self.sources.items() if active
        ]
        if not physical_fresh:
            active_sources.append("physical_stale")
        if not motor_can_fresh:
            active_sources.append("motor_can_stale")
        if active_sources:
            self.latched = True
        return LatchSnapshot(
            latched=self.latched,
            active_sources=tuple(sorted(active_sources)),
            physical_fresh=physical_fresh,
            reset_allowed=self.latched and not active_sources,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source /opt/ros/humble/setup.bash
cd vica_ros2_ws/src/vica_safety && python3 -m pytest test/test_emergency_latch.py -q
```

Expected: 기존 테스트 + 신규 6건 전부 PASS

- [ ] **Step 5: Commit**

```bash
cd vica_ros2_ws
git add src/vica_safety/vica_safety/emergency_latch.py \
        src/vica_safety/test/test_emergency_latch.py
git commit -m "feat(safety): 중앙 걸쇠에 motor_can 원인 추가

motor node의 CAN 링크 보고를 걸쇠 원인으로 흡수한다. false 수신은 물론
미수신(motor_can_stale)도 원인으로 처리해 motor node 프로세스 사망까지
fail-closed로 덮는다. 해제는 기존 관리자 reset 경로 하나를 그대로 쓴다."
```

---

### Task 4: `emergency_stop_node`가 `/motor/can_ok`를 구독한다

**Files:**
- Modify: `vica_ros2_ws/src/vica_safety/vica_safety/emergency_stop_node.py`

**Interfaces:**
- Consumes: `EmergencyLatch.mark_motor_can_seen` (Task 3), 토픽 `/motor/can_ok` (Task 2)
- Produces: 파라미터 `motor_can_timeout_sec` (기본 0.5)

- [ ] **Step 1: 파라미터 선언과 로딩**

`self.declare_parameter("log_f1_frames", True)` 뒤에 추가:

```python
        self.declare_parameter("motor_can_timeout_sec", 0.5)
```

`self.log_f1_frames = bool(...)` 뒤에 추가:

```python
        self.motor_can_timeout_sec = float(
            self.get_parameter("motor_can_timeout_sec").value
        )
```

`self.f1_timeout_ns = sec_to_ns(self.f1_timeout_sec)` 뒤에 추가:

```python
        self.motor_can_timeout_ns = sec_to_ns(self.motor_can_timeout_sec)
```

- [ ] **Step 2: 걸쇠 생성에 인자 전달**

`self.latch = EmergencyLatch(...)`를 교체:

```python
        self.latch = EmergencyLatch(
            f1_timeout_ns=self.f1_timeout_ns,
            motor_can_timeout_ns=self.motor_can_timeout_ns,
            initially_latched=True,
        )
```

- [ ] **Step 3: 구독과 콜백 추가**

`self.create_subscription(Bool, "/emergency_stop_input", ...)` 블록 뒤에 추가:

```python
        self.create_subscription(
            Bool,
            "/motor/can_ok",
            self.motor_can_callback,
            10,
        )
```

`test_input_callback` 뒤에 추가:

```python
    def motor_can_callback(self, msg: Bool) -> None:
        """Feed the motor CAN link report into the central latch."""
        self.latch.mark_motor_can_seen(bool(msg.data), self.now_ns())
```

- [ ] **Step 4: 기동 로그에 새 입력 명시**

`self.get_logger().info("Publishing central latch: ...")` 앞에 추가:

```python
        self.get_logger().info(
            "Subscribed: /app_emergency_stop, /voice_emergency_stop, "
            "/motor/can_ok"
        )
```

- [ ] **Step 5: 빌드와 테스트**

```bash
cd vica_ros2_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select vica_safety mdrobot_can_control
colcon test --packages-select vica_safety mdrobot_can_control
colcon test-result --verbose 2>&1 | tail -20
```

Expected: `vica_safety` 실패 0건. `mdrobot_can_control` 실패는 기존 스타일 2건뿐.

- [ ] **Step 6: Commit**

```bash
cd vica_ros2_ws
git add src/vica_safety/vica_safety/emergency_stop_node.py
git commit -m "feat(safety): /motor/can_ok를 중앙 걸쇠 입력으로 구독

motor_can_timeout_sec(기본 0.5)로 신선도를 판정한다. f1_timeout_sec와 같은
값으로 시작하며, 실기에서 실제 발행 주기를 측정해 확인한다."
```

---

### Task 5: `/diagnostics` 보고 추가

**Files:**
- Modify: `vica_ros2_ws/src/mdrobot_can_control/mdrobot_can_control/mdrobot_can_keyboard_knob_node.py`
- Modify: `vica_ros2_ws/src/mdrobot_can_control/package.xml`

**Interfaces:**
- Consumes: `CanLink` (Task 1), `diagnostic_updater`
- Produces: 토픽 `/diagnostics`의 `mdrobot_can_control: CAN link` 항목

**배경:** 초안 6.1이 지정한 방식이다 — *"각 노드 내부에서 `diagnostic_updater`를 사용해 상태를 발행하므로 node 수가 늘어나지 않는다."* 초안 3.1에 따라 **보고 전용**이며 정지 경로가 아니다.

- [ ] **Step 1: import와 updater 생성**

파일 상단 import에 추가:

```python
from diagnostic_msgs.msg import DiagnosticStatus
from diagnostic_updater import DiagnosticStatusWrapper, Updater
```

`self.pub_can_ok = self.create_publisher(...)` 뒤에 추가:

```python
        self.diag_updater = Updater(self)
        self.diag_updater.setHardwareID(self.can_iface)
        self.diag_updater.add("CAN link", self.diagnose_can_link)
```

- [ ] **Step 2: 진단 콜백 추가**

`log_can_error_throttled` 뒤에 추가:

```python
    def diagnose_can_link(
        self,
        stat: DiagnosticStatusWrapper,
    ) -> DiagnosticStatusWrapper:
        """Report CAN link health for operators.

        초안 3.1에 따라 보고 전용이다. 정지는 control_loop이 즉시 수행하며
        이 진단이 늦거나 실패해도 정지에는 영향이 없다.
        """
        now = self.now_ns()
        if self.can_link.is_ok():
            stat.summary(DiagnosticStatus.OK, "CAN link OK")
        else:
            stat.summary(
                DiagnosticStatus.ERROR,
                "CAN link FAILED; motor output forced to 0",
            )
        stat.add("iface", self.can_iface)
        stat.add("last_error", str(self.can_link.last_error))
        stat.add("knob_age_sec", self.age_text(self.last_knob_ns, now))
        stat.add("cmd_age_sec", self.age_text(self.last_cmd_ns, now))
        return stat

    @staticmethod
    def age_text(last_ns, now_ns: int) -> str:
        """Render an age in seconds, or 'never' when nothing arrived yet."""
        if last_ns is None:
            return "never"
        return f"{(now_ns - last_ns) / 1e9:.3f}"
```

- [ ] **Step 3: package.xml 의존 추가**

`<depend>std_msgs</depend>` 뒤에 추가:

```xml
  <depend>diagnostic_msgs</depend>
  <depend>diagnostic_updater</depend>
```

- [ ] **Step 4: 빌드하고 실제 발행을 확인**

```bash
cd vica_ros2_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select mdrobot_can_control
source install/setup.bash
```

can1을 올린 상태에서 노드를 띄우고 확인한다:

```bash
ros2 run mdrobot_can_control keyboard_knob --ros-args -p can_iface:=can1 &
sleep 5
ros2 topic echo /diagnostics --once
```

Expected: `name: "mdrobot_can_keyboard_knob_node: CAN link"`, `level: 0`, `message: "CAN link OK"`

- [ ] **Step 5: 스타일 확인**

```bash
source /opt/ros/humble/setup.bash
cd vica_ros2_ws
python3 -m flake8 src/mdrobot_can_control/mdrobot_can_control/mdrobot_can_keyboard_knob_node.py | wc -l
```

Expected: 78 이하

- [ ] **Step 6: Commit**

```bash
cd vica_ros2_ws
git add src/mdrobot_can_control/mdrobot_can_control/mdrobot_can_keyboard_knob_node.py \
        src/mdrobot_can_control/package.xml
git commit -m "feat(motor): diagnostic_updater로 CAN 링크 상태 보고

초안 6.1이 지정한 방식으로 /diagnostics에 CAN 링크 상태, 마지막 오류,
cmd/knob age를 싣는다. 초안 3.1에 따라 보고 전용이며 정지 경로가 아니다."
```

---

### Task 6: 실기 검증

**Files:**
- Modify: `vica_ros2_ws/src/vica_safety/docs/safety_steady_clock_test_checklist.md` (검증 기록 추가)

**전제:** Jetson 실기, **바퀴를 바닥에서 띄운 무부하 상태**, `can1` UP, 드라이버 전원 정상.

**주의:** `emergency_stop_node`를 수정했으므로 기존 물리 E-stop·reset 경로를 반드시 재검증한다.

- [ ] **Step 1: 기동과 정상 주행 확인**

```bash
cd vica_ros2_ws
source /opt/ros/humble/setup.bash && source install/setup.bash
ros2 launch vica_safety safety_bringup.launch.py &
ros2 launch mdrobot_can_control motor_bringup.launch.py &
```

`/motor/can_ok` 발행 주기를 측정한다:

```bash
ros2 topic hz /motor/can_ok
```

Expected: 약 30 Hz. **최대 간격이 `motor_can_timeout_sec`(0.5초)보다 충분히 작아야 한다.** 그렇지 않으면 상시 걸쇠가 걸리므로 파라미터를 조정한다.

관리자 앱에서 reset한 뒤 주행 명령을 넣어 바퀴가 도는 것을 확인한다.

- [ ] **Step 2: 물리 E-stop 회귀 검증**

주행 중 물리 버튼을 누른다.

Expected: 즉시 0 rpm, `/safety_state`가 `ESTOP_ACTIVE`. 버튼을 풀어도 `ESTOP_RELEASED_WAIT_RESET` 유지. 관리자 앱 reset 후에만 `READY_TO_GO`.

- [ ] **Step 3: CAN interface down 검증**

주행 중 실행한다:

```bash
sudo ip link set can1 down
```

Expected:
- motor node 프로세스가 **살아있다** (`ps -eo args | grep -c '[k]eyboard_knob'` → 1)
- 로그에 `[CAN FAULT] phase=recv ... 출력을 0으로 유지합니다`
- `/safety_state`가 `ESTOP_ACTIVE`
- 바퀴 정지

- [ ] **Step 4: 복구와 reset 검증**

```bash
sudo ip link set can1 up
```

드라이버 전원을 재투입한다(이 장비는 CAN이 한 번 끊기면 드라이버 동력이 차단된다).

Expected: 로그에 `[CAN RECOVERED]`, `/motor/can_ok`가 `true`로 복귀. 관리자 앱 reset이 **수락**되어 `READY_TO_GO`로 전이. reset 전에는 주행 불가.

- [ ] **Step 5: motor node 사망 검증**

주행 중 프로세스를 강제 종료한다:

```bash
pkill -9 -f 'mdrobot_can_control/keyboard_knob'
```

Expected: `/safety_state`가 `ESTOP_ACTIVE`, `emergency_stop_node` 로그의 원인에 `motor_can_stale` 포함. 노드를 다시 띄우고 관리자 reset 후에만 주행 재개.

- [ ] **Step 6: 결과를 체크리스트 문서에 기록하고 커밋**

`safety_steady_clock_test_checklist.md` 5절에 하위 절을 추가해 위 5개 단계의 실측값(정지까지 걸린 시간, `/motor/can_ok` 실측 주기, 관측된 `active_sources`)을 기록한다.

```bash
cd vica_ros2_ws
git add src/vica_safety/docs/safety_steady_clock_test_checklist.md
git commit -m "docs(safety): motor CAN health 실기 검증 결과 기록"
```

---

## 완료 조건

- `vica_safety` 단위 테스트 실패 0건
- `mdrobot_can_control` 기능 테스트 실패 0건 (스타일 2건은 기존 위반)
- 실기 6단계 전부 통과, 특히 **물리 E-stop 회귀 없음**
- `dev` 머지 전 팀 리뷰(PR) 권장 — 안전 크리티컬 노드를 수정했다
