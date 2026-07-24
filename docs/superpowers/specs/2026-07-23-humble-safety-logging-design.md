# ROS 2 Humble Safety 상태 로그 안정화 설계

## 목적

`vica_safety`가 상태 전이 로그의 심각도를 `ERROR`, `WARN`, `INFO`로 바꿀 때 ROS 2
Humble의 `RcutilsLogger` 호출 위치별 심각도 고정 규칙을 위반하지 않도록 한다.

## 원인

현재 코드는 한 소스 위치에서 `getattr(logger, severity)(message)`를 호출한다. Humble은
동일한 호출 위치를 재사용하면서 심각도가 바뀌면
`ValueError: Logger severity cannot be changed between calls.`를 발생시킨다. reset 성공
뒤 `WARN/ERROR` 상태에서 `INFO` 상태로 바뀌는 순간 예외가 timer callback 밖으로 전파되어
`emergency_stop_node`와 `safety_supervisor_node`가 종료된다.

## 설계

- 심각도 문자열과 메시지를 받는 작은 공통 함수에서 `error()`, `warning()`, `info()`를
  서로 다른 소스 줄로 명시 호출한다.
- 기존 상태 판정, marker, topic, service, reset 순서는 변경하지 않는다.
- `vica_safety`의 동적 심각도 호출 네 곳을 같은 공통 함수로 교체한다.
- 실제 Humble `RcutilsLogger`로 `ERROR → WARN → INFO`를 연속 호출하는 회귀 테스트를
  추가한다.

## 성공 조건

- 실제 ROS 로거가 연속 심각도 변경에서 `ValueError`를 발생시키지 않는다.
- `vica_safety` 기존 단위 테스트와 package build/test가 통과한다.
- motor, CAN, Nav2 및 실기기 상태는 변경하지 않는다.
