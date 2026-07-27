# Motor CAN health 보고와 중앙 걸쇠 통합 설계

작성일: 2026-07-27
대상 저장소: `vica_ros2_ws`
관련 계약: `guideline/vica_system_health_monitoring_draft.md` (3.1, 3.2, 4.2, 8.1, 9.1),
`CLAUDE.md` (중앙 E-stop 래치, 관리자 앱 단일 reset)

## 1. 문제

주행 중 `sudo ip link set can1 down`을 실행하면
`mdrobot_can_keyboard_knob_node`가 예외를 처리하지 않아 종료된다.

```
can.exceptions.CanOperationError: Error receiving: Network is down [Error Code 100]
  drain_can_rx -> self.bus.recv(timeout=0.0)
process has died [exit code 1]
```

2026-07-27 Jetson 실기에서 재현했다. 이 동작에는 세 가지 문제가 있다.

- **상태를 알 수 없다.** 죽은 노드는 무엇이 잘못됐는지 보고하지 못한다. 앞으로
  만들 `robot_health_monitor_node`가 읽을 대상 자체가 사라진다.
- **정지 상태를 유지할 주체가 없다.** 초안 8.1은 CAN interface down에 대해
  "즉시 정지, latch"를 요구하지만, 프로세스가 없으면 latch를 유지할 수 없다.
- **safety 계층이 모른다.** `emergency_stop_node`는 CAN 상태를 입력으로 받지
  않으므로, 최종 구동단이 사라진 사실을 인지하지 못한다.

폭주 위험은 낮다. 드라이버가 `PID_COM_WATCH_DELAY = 5`(0.5초)로 설정되어 있어
통신이 끊기면 스스로 정지한다(2026-07-27 드라이버에서 직접 read하여 확인).
그러나 이는 하드웨어의 보조 계층이며, 소프트웨어가 이를 전제로 방어를 생략하면
드라이버 설정이 바뀌는 순간 위험해진다.

## 2. 목표

주행 중 CAN 장애가 발생해도:

1. `mdrobot_can_keyboard_knob_node`가 종료되지 않는다.
2. 모터 출력이 0으로 유지된다.
3. safety 계층이 이를 인지하고 중앙 걸쇠를 건다.
4. 해제는 기존 관리자 앱 reset 경로 하나로만 이루어진다.
5. **motor node 프로세스가 죽는 경우에도** 3, 4가 성립한다.

## 3. 설계 원칙과 근거

| 결정 | 근거 |
|---|---|
| 걸쇠는 `emergency_stop_node`가 소유 | `CLAUDE.md` 중앙 래치·관리자 앱 단일 reset |
| 정지는 노드가 즉시 직접 수행 | 초안 3.1 (`/diagnostics`를 정지 경로로 쓰지 않는다) |
| `/diagnostics`는 보고 전용 | 초안 3.1, 6.1 (`diagnostic_updater` 사용) |
| 미수신을 고장으로 간주 | fail-closed. 기존 `physical_stale` 패턴과 동일 |
| motor node는 자체 걸쇠를 갖지 않음 | 초안 9.1 "통신 정상 + 수동 reset". 현재 상태만 보고해야 복구 후 reset이 가능하다 |
| 자동 재연결 허용 | 초안 9.1 "연결 재시도만 허용". 중앙 걸쇠가 자동 재개를 막으므로 안전하다 |

### 3.1 한계 (명시)

이 설계는 전부 소프트웨어 계층이다. `emergency_stop_node`가 스스로 경고하듯
*"This software latch does not replace hardware torque removal."* 실제 토크 차단은
물리 E-stop 회로와 드라이버의 `COM_WATCH_DELAY`가 담당한다. `/motor/can_ok`는
안전 등급 통신 채널이 아닌 일반 DDS 토픽이며, 전달 보장이 없다. 다만 미수신을
고장으로 처리하므로 실패 방향은 안전 측이다.

## 4. 구조

```
mdrobot_can_keyboard_knob_node          emergency_stop_node
├ CAN 예외 격리 (프로세스 유지)           ├ 기존 원인: physical_f1 / app / voice
├ CAN 비정상 시 출력 0 강제               └ 추가 원인: motor_can
├ 주기적 CAN 재연결 시도                       ├ false 수신 → 걸쇠
├ /motor/can_ok 발행 ─────────────────────────┤
└ /diagnostics 상세 보고 (보고 전용)           └ 미수신(stale) → 걸쇠
                                              해제: 관리자 앱 reset 경로 하나
```

### 4.1 `/motor/can_ok` 계약

| 항목 | 값 |
|---|---|
| 타입 | `std_msgs/msg/Bool` |
| 발행자 | `mdrobot_can_keyboard_knob_node` |
| 구독자 | `emergency_stop_node` |
| 발행 주기 | `send_hz`(기본 30 Hz)와 동일한 control loop |
| QoS | depth 10, 기본 신뢰성 (기존 토픽과 동일) |
| 의미 | `true` = CAN 송수신 정상, `false` = CAN 장애 |

`emergency_stop_node`의 판정 시각은 기존과 같이 단일 STEADY_TIME clock과 정수
나노초를 쓰고, `is_fresh_ns`로 신선도를 판정한다. 신규 파라미터
`motor_can_timeout_sec`(기본 0.5)를 둔다. 기존 `f1_timeout_sec`와 같은 값으로
시작한다.

### 4.2 CAN 링크 상태

motor node 내부 상태는 두 가지로 충분하다.

| 상태 | 진입 조건 | 출력 | `/motor/can_ok` | `/diagnostics` |
|---|---|---|---|---|
| `OK` | 송수신 성공 | 기존 watchdog 판정대로 | `true` | `OK` |
| `FAILED` | `can.CanError` 발생 | **0 강제** | `false` | `ERROR` |

`FAILED`에서는 매 `can_reconnect_interval_sec`(기본 1.0)마다 bus 재개방을 시도하고,
성공하면 `OK`로 돌아간다. 걸쇠는 여전히 걸려 있으므로 주행은 재개되지 않는다.

중간 등급(`DEGRADED`)은 두지 않는다. 일시적 실패와 영구 실패를 구분할 판단
근거가 현재 없고, 구분해도 반응이 같기 때문이다(둘 다 출력 0).

### 4.3 걸쇠 통합

`EmergencyLatch.sources`에 `"motor_can"` 항목을 추가한다. 기존 `physical_f1`이
`physical_stale`을 다루는 방식과 동일하게, 미수신은 `motor_can_stale`로 표시한다.

```
active_sources 판정
├── motor_can        : /motor/can_ok == false 수신
└── motor_can_stale  : 마지막 수신 age > motor_can_timeout_ns 또는 미수신
```

두 경우 모두 `latched = True`가 되고, 원인이 사라진 뒤 관리자 reset으로만
해제된다. `reset_allowed`는 기존 로직대로 모든 원인이 해소되어야 참이 된다.

초기값은 미수신(`None`)이므로 기동 시 fail-closed가 유지된다. 이는 기존
`initially_latched=True`와 일관된다.

## 5. 컴포넌트별 변경

### 5.1 `mdrobot_can_control`

**신규** `can_link.py` — 순수 모델. ROS 의존 없음.

```
CanLinkState        : OK | FAILED (enum 또는 문자열 상수)
class CanLink       : record_success() / record_error(exc) / should_retry(now_ns)
                      is_ok() -> bool
```

기존 `freshness.py`, `motor_watchdog.py`와 같은 패턴을 따른다. 시각은 정수
나노초를 인자로 주입받고 스스로 조회하지 않는다.

**수정** `mdrobot_can_keyboard_knob_node.py`

- `drain_can_rx`, `send_vel_cmd`, `send_pnt_io_monitor_on`의 `bus.recv`/`bus.send`를
  `try/except can.CanError`로 감싸고 `CanLink`에 결과를 기록한다.
- `control_loop`에서 `CanLink.is_ok()`가 거짓이면 `speed_ratio`와 무관하게 출력 0.
- `FAILED` 상태에서 재연결을 시도한다.
- `/motor/can_ok`를 매 control loop 발행한다.
- `diagnostic_updater`로 `/diagnostics`에 CAN 링크 상태, 마지막 오류 메시지,
  cmd/knob age를 보고한다.
- `package.xml`에 `diagnostic_updater`, `std_msgs` 의존을 추가한다.

기동 시 `require_can_interface_up` 동작은 **바꾸지 않는다.** 기동 실패는 launch
로그에 남고 로봇이 움직이지 않는 상태이므로 fail-fast가 적절하다. 이번 변경이
다루는 것은 주행 중 장애다.

### 5.2 `vica_safety`

**수정** `emergency_latch.py`

- `sources`에 `"motor_can"` 추가.
- `mark_motor_can_seen(ok: bool, now: int)` 추가 (`mark_physical_seen`과 대칭).
- `evaluate()`에서 `motor_can` 신선도를 판정하고 `motor_can_stale`을 원인에 넣는다.
- 생성자에 `motor_can_timeout_ns` 인자를 추가한다.

**수정** `emergency_stop_node.py`

- `motor_can_timeout_sec` 파라미터(기본 0.5) 선언.
- `/motor/can_ok` 구독 추가, 콜백에서 `mark_motor_can_seen` 호출.
- 상태 전이 로그에 새 원인이 드러나도록 기존 `describe_latch_transition` 경로를
  그대로 사용한다.

## 6. 테스트

### 6.1 단위 테스트 (개발용 컴퓨터)

`mdrobot_can_control/test/test_can_link.py`

- 생성 직후 상태는 `OK`다. `CanLink`는 bus 개방에 성공한 뒤에만 만들어지므로
  "미수신" 초기 상태가 존재하지 않는다(미수신 판정은 구독 측인
  `emergency_stop_node`가 담당한다).
- `record_error` 후 `is_ok()`는 거짓.
- `record_success` 후 `is_ok()`는 참.
- `should_retry`는 재시도 간격 이전에는 거짓, 이후 참.
- 시간 역전(음수 경과)에서도 재시도를 막지 않는다(fail-safe 방향).

`vica_safety/test/test_emergency_latch.py` (기존 파일에 추가)

- `motor_can=false` 수신 시 latch.
- `motor_can` 미수신 시 `motor_can_stale`이 원인에 포함되고 latch.
- 경계값: age == timeout은 fresh, timeout + 1은 stale.
- 모든 원인 해소 후에만 `try_reset` 성공.
- `motor_can`이 false인 동안 reset 거부.

### 6.2 실기 검증 (Jetson, 바퀴 무부하)

기존 §2.1 항목을 재실행하고 아래 두 가지를 추가한다.

| 시험 | 방법 | 통과 기준 |
|---|---|---|
| CAN interface down | 주행 중 `sudo ip link set can1 down` | 노드 **생존**, 출력 0, `/safety_state` ESTOP, 관리자 reset 전 재기동 불가 |
| motor node 사망 | 주행 중 프로세스 강제 종료 | `motor_can_stale`로 중앙 걸쇠, 관리자 reset 전 재기동 불가 |
| 복구 후 reset | CAN 복구 + 노드 재기동 후 관리자 reset | `READY_TO_GO` 전이 성공 |

물리 E-stop과 reset 경로는 safety 노드를 수정하므로 **반드시 재검증한다.**

주의: 이 장비는 CAN이 한 번 끊기면 드라이버 동력이 차단되어 전원 재투입이
필요하다. CAN만 격리해 시험하려면 `tc` ingress drop 또는 문서화된
`CMD_PNT_IO_MONITOR_OFF(86)` 명령을 쓴다.

## 7. 이번 범위에 포함하지 않는 것

- `robot_health_monitor_node`, `diagnostic_aggregator` 도입 (초안 6.1의 별도 작업)
- `RobotHealth`/`RobotEvent` 메시지 정의 (초안 7.2, 7.3의 `[TARGET]`)
- DDS liveliness QoS 기반 노드 생존 감시 (현재 heartbeat 방식과 병행 가능하나
  지금 필요하지 않다)
- `reason_code` 체계 (초안 7.1의 `[TARGET]`). 지금은 `/diagnostics` 문자열로 충분하다
- 기동 시 CAN 부재 상황의 동작 변경

## 8. 위험과 완화

| 위험 | 완화 |
|---|---|
| safety 노드 수정으로 기존 E-stop 경로 회귀 | 단위 테스트 확장 + 실기 §2.1 전 항목 재검증 |
| 새 걸쇠 원인이 상시 참이 되어 주행 불가 | `motor_can_timeout_sec`를 `f1_timeout_sec`와 같은 0.5초로 시작하고, 실기에서 `/motor/can_ok` 실제 주기를 측정해 확인 |
| 재연결 시도가 control loop를 지연 | 재연결은 간격 제한(기본 1.0초)을 두고, bus 개방 실패는 예외로 잡아 loop를 막지 않는다 |
| `/diagnostics` 발행이 loop 부하 증가 | `diagnostic_updater` 기본 1 Hz로 두고 control loop와 분리 |
