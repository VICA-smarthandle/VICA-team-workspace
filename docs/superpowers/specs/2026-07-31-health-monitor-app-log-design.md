# 상태 감시 계층과 앱 세부 오류 표시 설계

작성일: 2026-07-31
대상 저장소: `vica_ros2_ws`, `VICA_Supervisor`
관련 계약: `guideline/vica_architecture.md` (4.1, 4.2, 10.3, 13),
`guideline/vica_system_health_monitoring_draft.md` (2, 3.1, 3.2, 5, 6, 7, 17),
`CLAUDE.md` (안전 계층 우회 금지)

## 1. 문제

로봇 어디서 문제가 나든 관리자 앱이 그것을 거의 전달하지 못한다.

- `/diagnostics` 발행자가 `mdrobot_can_keyboard_knob_node`의 CAN link 항목 **하나뿐**이다.
  LiDAR가 꺼져도, nvblox slice가 멈춰도 앱은 모른다.
- 앱 오류 표시는 `vica_status_app_node.py`의 `_diagnostic_reason(min_level=2)`가 ERROR 첫
  메시지 **문자열 하나**를 뽑는 게 전부다. 어느 부품인지, 얼마나 심각한지, 언제부터인지,
  무엇을 해야 하는지가 전부 없다.
- `vica_architecture.md`가 이미 결함을 기록했다 — 마지막 `/diagnostics` 메시지 하나만
  보관하므로 ERROR 발행자와 정상 발행자가 번갈아 도착하면 **표시가 깜빡인다.**

두 번째 문제는 계측이다. 워크스페이스 최적화(imu adapter CPU 38.6 %, EKF 30 Hz 미달)의
**before를 지금 기록하지 않으면 영영 잃는다.** 최적화 후에는 재현할 수 없다.

세 번째는 감지 사각지대다. `/nvblox_node/static_map_slice`는 `nav2_params.yaml`의
`nvblox_layer` 유일 입력인데 `expected_update_rate`가 없다. GPU 경합으로 느려지거나 멈춰도
costmap이 감지하지 못하고 오래된 3D 장애물로 주행한다. `vica_safety`는 slice를 구독하지
않으므로 **E-stop으로도 걸리지 않고 회피 실패로만 발현한다.**

## 2. 목표

1. 관리자가 앱에서 "무엇이 / 어느 부품에서 / 얼마나 심각하게 / 언제부터 / 몇 번 /
   무엇을 해야 하는지"를 본다.
2. 오류 판정 지점을 하나로 모아 깜빡임을 없앤다.
3. 외부 패키지(LiDAR·nvblox·D455)도 코드 수정 없이 같은 경로로 감시한다.
4. 최적화의 before baseline을 상시 측정할 수단을 만든다.
5. **감시 계층이 죽어도 주행·안전 경로가 그대로 동작한다.**
6. 기존 노드(safety·motor·guidance·encoder)를 한 줄도 수정하지 않는다.

## 3. 설계 원칙과 근거

| 결정 | 근거 |
| --- | --- |
| 진단성 정보는 `diagnostic_aggregator` 표준 체인 | 나중에 다른 노드에 진단을 붙일 때 aggregator yaml에 항목만 추가하면 모니터 코드를 고치지 않는다. 발행자가 하나뿐인 지금 표준 체인을 까는 유일한 이유 |
| **안전 신호는 체인을 타지 않고 직접 구독** | aggregator는 기본 1 Hz 집계라 ESTOP 표시가 최대 1초 늦는다. 초안 3.1이 `/diagnostics`를 안전 신호 전달 경로로 쓰지 말라고 한다 |
| 모니터는 모터 정지 경로에 들어가지 않는다 | 초안 3.2. 모니터가 죽어도 `/cmd_vel_req → Safety → /cmd_vel_safe → CAN`이 유지되어야 한다 |
| 외부 대상은 어댑터가 대신 진단 발행 | `rplidar_ros`·nvblox(Docker)·D455는 fork하면 계속 유지보수해야 한다. 어댑터를 두면 외부 타입 의존(`nvblox_msgs`)이 어댑터 프로세스에만 갇힌다 |
| readiness는 bool이 아니라 3상태 | 4장 |
| 임계값을 코드에 두지 않는다 | 5장 |
| 한국어 문구 정본은 로봇 쪽 | 앱에 두면 fault 추가마다 앱을 다시 배포하고 정본이 두 저장소로 갈라진다 |
| 앱 복원을 `transient_local`에 의존하지 않는다 | Humble rosbridge의 `subscribe` op는 durability를 지정하지 않아 volatile로 붙고 latched 샘플을 못 받을 수 있다. 1 Hz 상시 발행 + `active_faults` 스냅샷으로 복원 |

## 4. 구조

```
[진단성 정보]
motor node (기존) ─┐
external_diagnostics_node ─┤ /diagnostics → diagnostic_aggregator → /diagnostics_agg ─┐
robot_health_monitor_node ─┘                                                          │
                                                                                      │
[안전 신호 직접 구독]                                                                  │
/emergency_stop · /safety_state · TF map→base_footprint                               │
/bt_navigator/get_state 폴링 · /vica/robot_state ──────────────────────────────────────┤
                                                                                      ▼
                                                            robot_health_monitor_node
                                                                      ▼
                                                    /robot/health (1 Hz) + /robot/events
                                                                      ▼
                                                          rosbridge → Flutter
```

### 4.1 메시지 3종 (`vica_interfaces`)

| 메시지 | 역할 |
| --- | --- |
| `RobotFault` | 결함 하나. Header 없는 순수 데이터라 아래 둘이 재사용 |
| `RobotHealth` | Header + state + readiness 9종 + `RobotFault[] active_faults` |
| `RobotEvent` | Header + `RobotFault` + `transition`(RAISED/ESCALATED/REMINDER/CLEARED) |

필드 정본은 `guideline/vica_architecture.md` 4.1절이다.

### 4.2 노드 2개 (`vica_system_monitor`)

초안은 신규 노드를 하나로 제한했지만 2개가 되었다.

- **`external_diagnostics_node`** — 외부 대상을 대신해 진단 발행.
  `topic_rate` 프로브(`diagnostic_updater`의 `HeaderlessTopicDiagnostic` +
  `FrequencyStatusParam`)와 `process_cpu` 프로브(`/proc/<pid>/stat`).
  `nvblox_msgs`는 `try/except ImportError`로 감싸 그 프로브만 건너뛴다.
- **`robot_health_monitor_node`** — ROS I/O만. 판정은 순수 모듈이 한다.

분리 이유는 의존성 격리다. 어댑터를 모니터에 합치면 `nvblox_msgs` symlink 하나가 빠져도
감시 전체가 기동 실패한다. 감시 기능이 감시 대상 때문에 죽는 결합은 잘못됐다.

### 4.3 설정 파일 3개의 책임 분리

| 계층 | 파일 | 소유 |
| --- | --- | --- |
| 수집 | `probes.yaml` | 감시 대상 토픽·프로세스, 기대 주기, **구독 QoS** |
| 수집 | `diagnostic_aggregator.yaml` | 계층 분류, 항목별 `timeout`, `expected` |
| 정책 | `required_components.yaml` | 컴포넌트별 `required` 여부, `severity` |
| 문구 | `fault_catalog.py` | fault_code → 한국어 `detail`·`suggested_action` |

**timeout은 aggregator yaml만 소유한다.** 두 곳에 두면 어느 쪽이 이기는지 모호해진다.
예외는 aggregator를 거치지 않는 안전 신호(`/emergency_stop`, `/safety_state`, TF)뿐이며
그 timeout만 `required_components.yaml`이 갖는다.

### 4.4 앱

`vica_status_app_node.py`는 `error_source` 파라미터로 감싼다(7장). Flutter는
`/robot/health`·`/robot/events`를 rosbridge로 **직접** 구독하고 이 노드를 거치지 않는다.
`ros/ros_bridge_client.dart`는 수정하지 않는다 — `msg['data']`가 String이 아니면 raw map을
handler에 넘기는 기존 경로로 타입 메시지를 그대로 받는다.

## 5. readiness를 3상태로 만든 이유

초기 설계에는 `bool guidance_ready`가 있었다. 이것이 이 작업에서 고친 가장 큰 결함이다.

Smart Handle은 아두이노에서 젯슨으로 올라오는 **상향 경로가 없다.** 서보가 실제로 돌았는지,
LED가 켜졌는지, 햅틱이 울렸는지 확인할 방법이 원리적으로 없다.

- `false` → 정상인데 고장으로 보인다
- `true` → **관측하지 못한 것을 정상이라고 보고한다**

두 번째가 위험하다. 시각장애인 안내 로봇에서 "핸들 정상" 초록불은 그 자체가 안전 주장이다.
`SmartHandleState.msg`가 경고하는 실패 모드와 같다.

`UNKNOWN`(0) / `NOT_READY`(1) / `READY`(2)로 두고, 앱은 `UNKNOWN`을 **"관측 불가"**로 표시하며
*"고장이 아니라 상태를 확인할 수단이 없다는 뜻입니다. 정상이라고 볼 수 없습니다."*를 함께
보여준다. 위젯 테스트가 이 문구를 고정한다.

## 6. 임계값 정책 — 하드코딩 금지

현재 동작을 정상으로 가정해 임계값을 박으면 최적화 이후 오탐이 난다.

| 예정된 변경 | 하드코딩하면 |
| --- | --- |
| `/imu/base_link` 400 → 60 Hz | 400 Hz 기준이면 FAULT 오탐 |
| `voxel_layer.publish_voxel_map: False` | 토픽 소멸 → "발행자 없음" 오탐 |
| `behavior_plugins`에서 `backup` 제거 | `/backup` action 소멸 → 동일 |
| `/vica/tts_state` edge → 10 Hz heartbeat | **토픽 의미 자체가 바뀜** |
| imu adapter CPU 38.6 % → 10 % 미만 | 임계 40 %면 개선 후에도 통과해 **회귀를 못 잡음** |

방어책 3가지:

1. 임계값과 기대 토픽 목록을 전부 YAML로 뺀다.
2. `test_config_contract.py`가 4파일의 컴포넌트·프로브 이름 집합 일치를 강제한다.
   `vica_nav2/test/test_nav2_params_contract.py`와 같은 패턴이다.
3. 1차에서 임계값을 확정하지 않는다. 전부 `[미검증]`으로 두고 Jetson 실측 후 확정한다.

**토픽 부재를 자동으로 fault로 만들지 않는다.** 토픽이 사라지는 것이 정상 변경일 수 있으므로
부재 판정은 반드시 YAML의 `required` 플래그를 거친다.

### 6.1 감시 도구가 스스로 만드는 오탐

가장 조용한 실패 모드다. `/scan`을 RELIABLE로 구독하면 rplidar가 sensor_data(BEST_EFFORT)로
발행할 때 QoS 비호환으로 **한 건도 받지 못하고** `LIDAR_SCAN_STALE`이 영구히 뜬다.

방어: 구독 QoS를 프로브별로 `probes.yaml`에 두고, 어댑터가 "구독자는 붙었는데 메시지 0건"을
진단 message에 구분해 남긴다(`classify_zero_message()` → `ZERO_NO_PUBLISHER` /
`ZERO_QOS_SUSPECTED`). 실제 값은 Jetson `ros2 topic info -v`로 확정한다.

## 7. 회귀 방지

이 작업에서 **의미를 바꾸는 변경은 하나**다 — 앱 브리지의 오류 판정 원천.

```python
self.declare_parameter('error_source', 'diagnostics')   # 'diagnostics' | 'health'
```

- `diagnostics`(기본): 기존 `_diagnostic_reason` 경로. **동작 불변**
- `health`: `/robot/health`의 `highest_severity >= SEVERITY_STOP`일 때만 `error_reason`을 채움

임계를 STOP으로 잡은 이유는 `_status()`가 `error_reason`이 있으면 `"error"`를 반환하기
때문이다. 임계를 낮추면 경고 하나로 앱 상태가 뒤집힌다.

Jetson에서 파라미터 한 줄로 A/B하고, 검증 후 기본값을 `health`로 바꾸는 것은 **별도
커밋**으로 한다. 롤백 단위가 커밋이 아니라 파라미터가 된다.
`/robot_status` JSON 스키마는 바꾸지 않아 기존 앱 화면과 하위 호환이 유지된다.

## 8. 관측 범위와 사각지대

**"health가 정상이라고 했는데 왜 못 잡았나"를 구조적으로 막기 위해 경계를 문서에 고정한다.**
어댑터가 대신 발행할 수 있는 것은 토픽과 `/proc`으로 이미 나오는 것뿐이다.

관측하지 **못하는** 것:

| 신호 | 왜 불가 | 실제 위험 |
| --- | --- | --- |
| 마이크 무입력 | 오디오 콜백 내부 | **긴급어 감시가 조용히 멈춘다** |
| 긴급 감시 실효 hop·창 건너뜀 | 카운터가 아예 없다 | 긴급어 사각지대 확대 |
| STT/TTS CPU 폴백 | 노드 내부 변수, `print`로만 나감 | 지연 3.7배·10배 |
| 목적지 카탈로그 부재 | warn 로그 한 줄 | 모든 안내가 `unknown_destination` |
| Smart Handle 서보·LED·햅틱 실동작 | 상향 통신 경로 자체가 없다 | readiness가 `UNKNOWN`으로 남는다 |

**"나중에 못 고친다"가 아니라 "1차 범위에 안 들어간다"이다.** 해당 노드를 수정할 때 진단
발행을 함께 넣고 aggregator yaml에 항목만 추가하면 모니터 코드는 고치지 않는다.
전체 표는 `guideline/vica_architecture.md` 13.3절이 정본이다.

## 9. 테스트

### 9.1 노트북 (ROS 없이 검증 가능한 것)

`vica_system_monitor` 패키지 테스트 162건. 순수 모듈이라 ROS 없이 `pytest`로 돈다.

필수 항목:

- `is_fresh_ns` 경계: `age == timeout` fresh, `timeout+1` stale, **음수 age stale**,
  **`None` stale**
- startup grace 안에서 미수신은 fault가 아니고 `STARTING`
- grace 이후 미수신은 fail-closed로 fault
- 같은 fault 재관측은 이벤트를 추가 발행하지 않고 `occurrence_count`만 올림
- severity 상승 시 `ESCALATED` 즉시, 해소 시 `CLEARED` 정확히 1회
- **ESTOP은 reminder 간격을 무시**
- ERROR 항목과 정상 항목이 번갈아 와도 활성 결함이 깜빡이지 않음
- `agg_parser`가 계층 name(`/VICA/Hardware/Motor`)과 평면 name(`mdrobot: CAN link`)을 모두 매핑
- **`required_components.yaml`의 severity 값만 바꾸면 등급이 바뀜** (nvblox DEGRADED↔STOP)
- **미구성 컴포넌트는 fault도 readiness 실패도 아님** (`nvblox_msgs` import 실패 모의)
- `process_cpu`: utime/stime 델타, 첫 표본은 값 없음, pid 소멸 시 예외 없이 미구성
- **모든 fault detail에 `{`·`?` 자리표시자가 남지 않음** (실행 중 `?초`가 사용자 문구로 샌
  사고의 회귀 테스트)
- `test_config_contract`: 4파일 이름 집합 일치

앱: `dart format --set-exit-if-changed` exit 0, `flutter analyze` 무결함, `flutter test` 58건.
위젯 테스트가 "관측 불가"가 정상으로 보이지 않는지를 고정한다.

**노트북에서 할 수 없는 것**: CAN, 실제 센서, TF, Nav2 lifecycle, GPU, `tegrastats`.
종단 동작을 검증할 수 없다. **성공으로 쓰지 않는다.**

### 9.2 Jetson 1차 — 측정만. 바퀴 안 굴림

착수 전 **노트북·Jetson 둘 다** `sudo apt install -y ros-humble-diagnostic-aggregator`.

| 측정 | 방법 | 산출 |
| --- | --- | --- |
| 발행 QoS | `ros2 topic info -v` × 6토픽 | `probes.yaml` QoS 확정 |
| 실제 주기 | `ros2 topic hz` × 6토픽 | 기대 주기 확정. slice 정상 ~9 Hz |
| 노드별 CPU | 어댑터 `process_cpu` | **imu adapter 38.6 % baseline** |
| `/odom` 실효 Hz | 어댑터 출력 | **EKF 30 Hz 미달 baseline** |
| Docker `/proc` 가시성 | nvblox·D455 프로브 | 안 보이면 미구성 처리 확정 |
| aggregator 트리 | `rqt_robot_monitor` | `/VICA/Hardware/*` 표시 |

**이 시점의 측정값이 최적화 작업의 유일한 before다.** devlog에 기록한다.

### 9.3 Jetson 2차 — fault injection. 바퀴 무부하, 물리 E-stop 확보, 별도 승인

| 시험 | 통과 기준 |
| --- | --- |
| 모터 CAN 단절 | `MOTOR_CAN_TIMEOUT` 카드 + 조치 문구 |
| safety 노드 종료 | `SAFETY_STATE_STALE`. **모터는 기존 경로로 정지** |
| TF 제거 | `LOCALIZATION_TF_STALE` STOP |
| LiDAR 종료·USB 분리 | `LIDAR_SCAN_STALE` STOP |
| nvblox slice 강제 지연·중단 | `NVBLOX_SLICE_STALE`. LiDAR 주행 유지 |
| 카메라 종료 | `CAMERA_DEPTH_STALE`. slice stale과 동시 표시되며 폭주하지 않음 |
| 어댑터 종료 | aggregator가 `expected` 미충족 Stale. 모니터는 계속 동작 |
| aggregator 종료 | 모니터가 `/diagnostics_agg` stale 표시. **모터·safety 정상 유지** |
| **모니터 종료** | **모터·safety 경로 정상 유지.** 앱은 health 만료 표시 |
| 앱 재접속 | 1초 안에 활성 결함 목록 복원 |
| 알림 폭주 | 결함 60초 유지 시 reminder 간격만큼만 추가 |
| `error_source` A/B | `diagnostics`↔`health` 전환에서 앱 표시가 기대대로 |

CAN 격리는 `2026-07-27-motor-can-health-design.md` 6.2절을 따른다 — 이 장비는 CAN이 끊기면
드라이버 동력이 차단되어 전원 재투입이 필요하므로 `tc` ingress drop 또는
`CMD_PNT_IO_MONITOR_OFF(86)`를 쓴다.

## 10. 이번 범위에 포함하지 않는 것

- **자동 복구**(초안 11절). 관측·보고만 한다
- **nvblox slice stale의 실제 방어(Mission 취소)**. 감지는 포함되지만 방어는 아니다.
  지금 넣으면 "유령 때문에 못 감"과 "slice stale이라 멈춤"이 섞여 원인 분리가 어려워진다.
  유령 장애물 진단이 끝난 뒤 결정한다 (`devlog/2026-07-30-nvblox-ghost-obstacle.md` 12절)
- **다른 노드에 `diagnostic_updater` 추가**(초안 17절 1단계). 우선순위 1위는 마이크 무입력
  (`vica-voice-llm/src/emergency_monitor.py`). `safety_supervisor_node` 수정은 E-stop 경로
  전체 실기 재검증을 요구하므로 마지막
- GPU·온도·CPU 전체·디스크(초안 8.7의 `diagnostic_common_diagnostics`, 미설치)
- rosbag2 snapshot, TTS·LED·햅틱 연결, Mission start gate, systemd
- 워크스페이스 최적화 자체. **이 작업은 그 baseline을 만드는 계측 장비다**

## 11. 위험과 완화

| 위험 | 완화 |
| --- | --- |
| **어댑터 QoS 비호환으로 감시가 영구 오탐** | 구독 QoS를 `probes.yaml`로 빼고 실기 `ros2 topic info -v`로 확정. "구독자 붙음 + 0건"을 진단에 구분 표기 |
| **임계값 하드코딩으로 최적화 후 오탐·회귀 미검출** | 전부 YAML + 계약 테스트 + 1차 `[미검증]` 유지 |
| 앱 브리지 변경이 기존 동작을 바꿈 | `error_source` 기본값 = 현재 동작. 전환은 별도 커밋 |
| 토픽 소멸이 정상 변경인데 fault로 뜸 | 부재 판정은 반드시 YAML `required` 경유 |
| 모니터 오탐으로 앱이 계속 error 표시 | startup grace + `error_reason` 임계 STOP 이상 |
| 감시 노드가 대역폭 소비자가 됨 | 카메라는 `image`가 아니라 `camera_info` 구독 |
| `nvblox_msgs` symlink 부재로 감시 기동 실패 | optional import를 **어댑터에만**. 모니터는 센서 타입 미참조 |
| Docker 프로세스가 host `/proc`에 안 보임 | 실기 확인 후 미구성 처리. 등급은 WARN 상한이라 주행을 막지 않음 |
| aggregator가 죽어 진단 전체 끊김 | 모니터가 stale을 fault로 표시. 안전 신호는 직접 구독이라 영향 없음 |
| apt 설치가 한쪽 장비에만 되어 launch가 갈라짐 | 노트북·Jetson 둘 다를 착수 사전 조건으로. bringup 매뉴얼 4.9절 |
| 설정 파일 4개로 감시가 조용히 빠짐 | `test_config_contract.py`가 이름 집합 일치 강제 |
| nvblox 등급을 임의 확정해 안전 판단 왜곡 | 초안 19절 11번 팀 확정 항목으로 유지. 값은 config 한 줄 |
| **Safety 경로 회귀** | safety·motor·guidance·encoder를 **한 줄도 수정하지 않는다.** 기존 테스트 전부 통과를 조건으로 건다 |
