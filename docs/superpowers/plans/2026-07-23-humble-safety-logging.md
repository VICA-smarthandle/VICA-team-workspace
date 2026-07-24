# ROS 2 Humble Safety Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** reset 성공 뒤 상태 로그 심각도가 INFO로 바뀌어도 Safety 노드가 종료되지 않게 한다.

**Architecture:** `vica_safety` 내부에 심각도별 ROS logger 메서드를 서로 다른 소스
위치에서 호출하는 공통 함수를 둔다. 상태 판정과 reset 계약은 그대로 두고 기존의 동적
`getattr()` 호출만 공통 함수로 대체한다.

**Tech Stack:** Python 3.10, ROS 2 Humble `rclpy`, pytest, colcon

## Global Constraints

- 공개 topic, service, action 및 Safety 권한은 변경하지 않는다.
- motor/CAN/Nav2를 실행하거나 장치 상태를 변경하지 않는다.
- 기존 사용자 변경을 reset, stash, 삭제 또는 commit하지 않는다.

---

### Task 1: Humble 로거 심각도 전환 회귀 테스트와 최소 수정

**Files:**
- Create: `vica_ros2_ws/src/vica_safety/vica_safety/logging_utils.py`
- Create: `vica_ros2_ws/src/vica_safety/test/test_logging_utils.py`
- Modify: `vica_ros2_ws/src/vica_safety/vica_safety/emergency_stop_node.py`
- Modify: `vica_ros2_ws/src/vica_safety/vica_safety/safety_supervisor_node.py`
- Modify: `vica_ros2_ws/src/vica_safety/vica_safety/app_emergency_node.py`
- Modify: `devlog/2026-07-23.md`

**Interfaces:**
- Consumes: ROS logger의 `error(str)`, `warning(str)`, `info(str)` 메서드
- Produces: `log_with_severity(logger, severity: str, message: str) -> None`

- [ ] **Step 1: 실제 Humble 로거로 실패하는 회귀 테스트 작성**

```python
from rclpy.impl.rcutils_logger import RcutilsLogger

from vica_safety.logging_utils import log_with_severity


def test_logger_accepts_severity_transitions_from_same_helper():
    logger = RcutilsLogger(name="vica_safety_logging_test")
    log_with_severity(logger, "error", "error state")
    log_with_severity(logger, "warn", "warning state")
    log_with_severity(logger, "info", "ready state")
```

- [ ] **Step 2: 테스트를 실행해 구현 부재로 실패하는지 확인**

Run: `pytest -q src/vica_safety/test/test_logging_utils.py`

Expected: FAIL with `ModuleNotFoundError: No module named 'vica_safety.logging_utils'`

- [ ] **Step 3: 심각도별 호출 위치를 분리한 최소 함수 구현**

```python
def log_with_severity(logger, severity: str, message: str) -> None:
    if severity == "error":
        logger.error(message)
    elif severity == "warn":
        logger.warning(message)
    elif severity == "info":
        logger.info(message)
    else:
        raise ValueError(f"unsupported log severity: {severity}")
```

- [ ] **Step 4: 네 동적 호출 지점을 공통 함수로 교체**

각 모듈에서 `log_with_severity`를 import하고
`getattr(self.get_logger(), severity)(message)`를
`log_with_severity(self.get_logger(), severity, message)`로 교체한다.

- [ ] **Step 5: 회귀 테스트와 전체 패키지 검증**

Run: `pytest -q src/vica_safety/test`

Expected: all tests pass

Run: `colcon build --packages-select vica_safety`

Expected: package build succeeds

Run: `colcon test --packages-select vica_safety --event-handlers console_direct+`

Expected: package tests pass

- [ ] **Step 6: 장애 원인과 실기 미검증 범위 기록**

`devlog/2026-07-23.md`에 Humble 로거의 동일 호출 위치 심각도 변경 제한, 수정 범위,
단위 검증 결과와 실제 E-stop/reset 재시험이 `[미검증]`임을 기록한다.

- [ ] **Step 7: 최종 diff 검증**

Run: `git -C vica_ros2_ws diff --check`

Expected: no output

사용자가 요청하지 않았으므로 commit은 수행하지 않는다.
