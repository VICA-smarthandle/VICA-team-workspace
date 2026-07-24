# VICA 통합 상태 감시·즉시 피드백·자동 복구 아키텍처 초안

문서 상태: 팀 검토용 초안
작성 기준일: 2026-07-24
기준 작업공간: 이 문서가 포함된 작업공간 루트
대상: VICA ROS 2 전체 시스템, 모터 안전제어, Nav2, 사용자 안내, 음성, 앱
범위: 설계 및 구현 계획 제안
비범위: 소스 코드, launch, 파라미터, 펌웨어 직접 변경

판정 표기는 `vica_architecture.md`·`vica_scenario.md`와 동일하게 사용한다.

- `[CURRENT]`: 코드·설정·launch가 현재 작업공간에 존재한다.
- `[GAP]`: 구성요소나 계약은 있으나 실제 producer/consumer 또는 launch 연결이 끊겨 있다.
- `[TARGET]`: 현재 코드에는 없으며 이 문서가 구현 목표로 제안한다.
- `[미검증]`: 코드는 있으나 실기기 종단 동작이 아직 검증되지 않았다.

---

## 1. 문서 목적

VICA의 모터, 센서, 자율주행, 음성, LED, Smart Handle, 앱 기능을 한 번에 실행할 때
다음 요구사항을 만족하는 최소 변경 구조를 제안한다.

1. 노드 종료, 통신 끊김, 데이터 지연, 센서 이상, 하드웨어 고장을 자동 감지한다.
2. 위험 상태에서는 진단 시스템을 기다리지 않고 모터를 즉시 정지한다.
3. 사용자에게 LED, 햅틱, 음성, 앱으로 현재 상태와 필요한 조치를 알린다.
4. 안전한 범위의 오류만 제한적으로 자동 복구한다.
5. 복구할 수 없는 오류는 안전 상태를 유지하고 사람이 원인을 확인할 수 있게 기록한다.
6. 모든 기능을 한 번에 배포하되, 한 기능의 장애가 전체 프로세스를 종료시키지 않게 한다.
7. 새로운 사용자 정의 노드는 가능한 한 하나만 추가한다.

이 문서는 다음 작업공간 기준 문서와 함께 검토한다.

- [VICA 통합 아키텍처](vica_architecture.md)
- [VICA 제품 시나리오](vica_scenario.md)
- [VICA BT·패키지·폴더 구조](bt와%20visual%20hierarchy%20of%20your%20folders%20and%20files.md)

---

## 2. 결론부터 보기

권장 구조의 핵심은 **안전제어와 시스템 모니터링을 서로 다른 경로로 운영하는 것**이다.

```text
빠른 안전 경로
센서·핸들·CAN 이상
    → safety_supervisor_node
    → /cmd_vel_safe = 0
    → mdrobot_can_keyboard_knob_node [CURRENT]
    → 바퀴 정지

상태 감시·운영 경로
모든 노드의 /diagnostics [TARGET]
    → diagnostic_aggregator
    → robot_health_monitor_node
    → /robot/health, /robot/events
    → 앱·음성·LED·햅틱·로그·제한적 자동 복구
```

최소 변경 기준의 권장안은 다음과 같다.

| 구분 | 권장안 |
|---|---|
| 기존 기능 노드 | 각 노드 내부에 진단 항목만 추가 |
| 표준 진단 수집 | ROS 2 `diagnostic_aggregator` 사용 |
| 신규 사용자 정의 노드 | `robot_health_monitor_node` 하나 |
| 안전 정지 | 기존 `safety_supervisor_node`와 모터 driver가 담당 |
| 사용자 알림 | 기존 앱·TTS·LED·햅틱 출력 경로 재사용 |
| 프로세스 재시작 | launch 및 systemd가 담당 |
| Nav2 복구 | Nav2 Lifecycle Manager 기능 재사용 |
| 장애 기록 | rosbag2 snapshot과 구조화 로그 사용 |

`robot_health_monitor_node`는 Safety Supervisor를 대체하지 않는다. 이 노드는 전체 상태를
요약하고 복구 정책을 선택하지만, 모터의 긴급정지 경로에 필수 구성요소로 들어가면 안 된다.

---

## 3. 반드시 지켜야 할 설계 원칙

### 3.1 모터 정지는 진단 집계 결과를 기다리지 않는다

`/diagnostics`는 상태 설명과 운영 판단에는 적합하지만, 긴급정지 신호 전달 경로로 사용하면
안 된다. 진단 발행 주기, 집계 지연, 노드 부하 때문에 정지 시점이 늦어질 수 있기 때문이다.

따라서 다음 오류는 Safety Supervisor 또는 모터 driver가 직접 감지해야 한다.

- 물리 E-stop 입력
- CAN 응답 timeout
- `/cmd_vel_safe` timeout
- Smart Handle 통신 단절 (아두이노 나노 포트·전송 실패)
- Safety Supervisor heartbeat timeout
- 모터 controller fault bit
- 명령 속도와 encoder 속도의 비정상 불일치

### 3.2 모니터 노드가 고장 나도 안전 기능은 유지한다

`robot_health_monitor_node`가 종료되어도 다음 기능은 계속 동작해야 한다.

- 모터 명령 timeout에 의한 정지
- Safety Supervisor의 정지 명령
- 물리 E-stop
- 모터 controller 또는 MCU의 로컬 watchdog
- 긴급 상태를 직접 구독하는 LED·햅틱 알림

### 3.3 자동 복구와 자동 재개를 구분한다

노드나 통신을 자동으로 복구하는 것은 가능하지만, 이전 주행 임무를 자동으로 다시 시작하는
것은 별도의 안전 승인 없이 수행하지 않는다.

```text
허용 가능
├── 음성 인식 노드 재시작
├── 앱 연결 재시도
├── LiDAR driver 제한적 재시작
└── Nav2 lifecycle 재구성

기본 금지
├── E-stop 자동 해제
├── motor fault latch 자동 해제
├── 사용자가 확인하지 않은 이전 goal 자동 재개
└── 안전 원인을 모르는 상태에서 반복 재시작
```

### 3.4 하나의 노드에 모든 기능을 합치지 않는다

“한 번에 실행”은 “하나의 프로세스”를 뜻하지 않는다. 하나의 bringup 명령과 하나의 systemd
target으로 전체 시스템을 시작하되, 모터·주행·음성·앱은 프로세스를 분리해야 장애 격리가
가능하다.

### 3.5 상태는 문자열이 아니라 코드와 상태 전이로 관리한다

예를 들어 `"라이다 오류"`라는 문자열만 발행하지 않고 다음 정보를 함께 관리한다.

- component: `lidar`
- fault_code: `LIDAR_DATA_TIMEOUT`
- severity: `STOP`
- active: `true`
- latched: `false`
- first_seen / last_seen
- occurrence_count
- suggested_action

한국어 안내 문구는 앱과 TTS에서 fault code를 기준으로 생성한다. 이렇게 해야 로그 분석,
다국어 지원, 중복 알림 억제가 쉬워진다.

---

## 4. 목표 전체 아키텍처

### 4.1 전체 실행 구조

```text
┌──────────────────────────── Hardware Layer ────────────────────────────┐
│ MDROBOT Controller │ LiDAR │ IMU │ Camera │ Smart Handle MCU │ E-stop │
└──────────────┬──────────┬───────┬─────────────┬───────────────────────┘
               │          │       │             │
               ▼          ▼       ▼             ▼
┌──────────────────────── ROS 2 Driver Layer ────────────────────────────┐
│ mdrobot_can_keyboard_knob_node │ sensor drivers │ guidance driver     │
│ ├ hardware state   │ ├ data         │ ├ LED / Servo / Haptic output   │
│ ├ local watchdog   │ └ diagnostics  │ ├ handle input / connected      │
│ └ diagnostics      │                │ └ diagnostics                   │
└──────────────┬──────────┬──────────────────────┬───────────────────────┘
               │          │                      │
               │          ▼                      │
               │  localization / Nav2            │
               │  ├ TF, odom, path, action       │
               │  └ diagnostics                  │
               │                                 │
               ▼                                 ▼
┌────────────────────── Fast Safety Path ────────────────────────────────┐
│ safety_supervisor_node                                                │
│ ├ input: requested velocity, E-stop, obstacle, handle, CAN health     │
│ ├ output: /cmd_vel_safe                                               │
│ └ output: /safety_state [CURRENT]                                     │
└──────────────┬──────────────────────────────────┬───────────────────────┘
               │                                  │
               ▼                                  ▼
       mdrobot_can_keyboard_knob_node     LED / Haptic / App
       └── wheel stop                     └── immediate feedback

모든 기존 노드
    └── /diagnostics
          │
          ▼
┌────────────────────────────────────────────────────────────────────────┐
│ diagnostic_aggregator                                                 │
│ └── /diagnostics_agg: component별 표준 진단 요약                       │
└──────────────────────────────┬─────────────────────────────────────────┘
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│ robot_health_monitor_node                                             │
│ ├ node/topic/TF heartbeat 확인                                        │
│ ├ 전체 준비 상태 계산                                                  │
│ ├ fault 중복 제거·등급 결정                                            │
│ ├ 복구 정책과 재시도 횟수 관리                                         │
│ ├ 장애 snapshot trigger                                               │
│ └── /robot/health, /robot/events                                      │
└──────────┬──────────────────┬───────────────────┬───────────────────────┘
           │                  │                   │
           ▼                  ▼                   ▼
      앱·대시보드         TTS·LED·햅틱       launch/systemd/Nav2
      상태 표시           사용자 알림         제한적 자동 복구
```

### 4.2 Safety Supervisor와 Health Monitor의 차이

| 항목 | `safety_supervisor_node` | `robot_health_monitor_node` |
|---|---|---|
| 주목적 | 모터의 최종 주행 허가와 즉시 정지 | 전체 시스템 상태 요약과 운영 대응 |
| 시간 민감도 | 매우 높음 | 상대적으로 낮음 |
| 출력 | `/cmd_vel_safe`, `/safety_state` `[CURRENT]` | `/robot/health`, `/robot/events` `[TARGET]` |
| 입력 | 직접 안전 입력 | diagnostics, node/topic/TF 상태 |
| 장애 시 결과 | 모터가 안전하게 정지해야 함 | 안전제어는 유지, 통합 상태 표시는 제한 |
| 자동 복구 | 원칙적으로 담당하지 않음 | 정책에 따라 복구 요청 |
| 위치 | `vica_safety` | `vica_system_monitor` |

---

## 5. 권장 워크스페이스 Tree

아래 tree는 현재 세 제품 저장소 경계를 유지하면서 감시 기능을 추가하는 목표 구조다.
`[TARGET]` 항목은 아직 구현되지 않았으며, 현재 파일을 즉시 이동하라는 의미가 아니다.

```text
VICA-smarthandle/                         # 조정 작업공간 [CURRENT]
├── guideline/
│   ├── vica_architecture.md              # 현재 통합 계약 [CURRENT]
│   ├── vica_scenario.md                  # 현재 제품 시나리오 [CURRENT]
│   └── vica_system_health_monitoring_draft.md
│
├── vica_ros2_ws/                         # ROS 2 제품 저장소 [CURRENT]
│   └── src/
│       ├── mdrobot_can_control/           # /cmd_vel_safe → CAN [CURRENT]
│       ├── encoder_feedback/              # CAN C5 → /wheel/odom [CURRENT]
│       ├── vica_safety/                   # E-stop + Safety Supervisor [CURRENT]
│       ├── vica_localization/             # EKF /odom [CURRENT]
│       ├── vica_nav2/                     # Nav2 [CURRENT]
│       ├── vica_mission_manager/          # Goal 권한 [CURRENT]
│       ├── vica_interfaces/
│       │   └── msg/
│       │       ├── SafetyState.msg        # [TARGET]
│       │       ├── RobotHealth.msg        # [TARGET]
│       │       └── RobotEvent.msg         # [TARGET]
│       │
│       ├── vica_user_guidance/            # [TARGET]
│       │   ├── turn_guide_node
│       │   └── user_guidance_driver_node
│       │
│       ├── vica_system_monitor/           # [TARGET] 신규 권장 패키지
│       │   ├── config/
│       │   │   ├── diagnostic_aggregator.yaml
│       │   │   ├── required_components.yaml
│       │   │   └── recovery_policy.yaml
│       │   ├── launch/system_monitor.launch.py
│       │   ├── vica_system_monitor/
│       │   │   ├── robot_health_monitor_node.py
│       │   │   ├── health_logic.py
│       │   │   ├── recovery_policy.py
│       │   │   └── event_deduplicator.py
│       │   └── test/
│       │       ├── test_health_logic.py
│       │       └── test_recovery_policy.py
│       │
│       └── vica_bringup/                  # 통합 bringup 패키지 [TARGET]
│           ├── launch/full_robot.launch.py
│           └── config/deployment_profile.yaml
│
├── vica-voice-llm/                        # Voice/LLM 저장소 [CURRENT]
│   └── src/
│       ├── ros_stt_node.py
│       ├── ros_emergency_node.py
│       ├── ros_node.py
│       └── ros_tts_node.py
│
└── VICA_Supervisor/                       # 앱 저장소 [CURRENT]
    └── ros2/
        └── vica_status_app_node.py
```

### 5.1 새 패키지를 분리하는 이유

`vica_system_monitor`는 특정 하드웨어나 특정 사용자 인터페이스가 아니라 전체 시스템을
관찰한다. 따라서 모터 패키지, Nav2 패키지, 음성 패키지 중 하나에 포함하면 다음 문제가
발생한다.

- 해당 패키지를 사용하지 않는 시험 구성에서 전체 상태 감시도 함께 빠진다.
- 모터 안전제어와 운영 진단 책임이 혼합된다.
- 다른 기능을 추가할수록 패키지 의존성이 순환할 가능성이 커진다.
- 모니터를 재시작하는 과정이 모터 driver 재시작과 묶일 수 있다.

그러므로 Safety Supervisor는 `vica_safety`, 전체 상태 모니터는
`vica_system_monitor`에 두는 구성이 가장 명확하다.

---

## 6. 최소 노드 구성

### 6.1 추가되는 실행 노드

| 노드 | 종류 | 역할 |
|---|---|---|
| `diagnostic_aggregator` | ROS 2 표준 노드 | 여러 `/diagnostics`를 component별로 집계 |
| `robot_health_monitor_node` | VICA 신규 노드 | 준비 상태, fault, 복구 정책, 이벤트 관리 |

기존 노드에 진단을 추가하는 것은 새 프로세스를 만드는 것이 아니다. 각 노드 내부에서
`diagnostic_updater`를 사용해 상태를 발행하므로 node 수가 늘어나지 않는다.

### 6.2 별도 노드로 만들지 않을 기능

다음 기능은 초기 단계에서 `robot_health_monitor_node` 내부 모듈로 구현하는 편이 낫다.

- node 존재 여부 확인
- topic 주기와 데이터 age 확인
- 필수 TF 연결 확인
- fault 중복 제거
- 자동 복구 재시도 횟수 계산
- 장애 snapshot trigger

ROS graph 감시는 `rosgraph_monitor`의 기능이나 라이브러리를 재사용할 수 있다. 규모가 커져
독립 실행과 독립 배포가 필요한 시점에만 별도 노드로 분리한다.

---

## 7. 권장 인터페이스

### 7.1 `SafetyState`

즉시 사용자 피드백과 다른 시스템의 안전 상태 확인에 사용한다.
현재 Safety Supervisor는 `/safety_state`에 `std_msgs/String`으로 상태값을 발행하며, 확정 상태
enum은 `vica_architecture.md` 9.3절과 동일하다(아래 `state` 필드). 아래 `SafetyState` 사용자 정의
메시지는 이 문자열 계약을 즉시 교체한다는 뜻이 아닌 `[TARGET]`이다. 변경 시 앱과 Safety consumer를
함께 전환하고 호환·rollback 계획을 별도로 승인해야 한다.

```text
SafetyState
├── state                          # vica_architecture.md 9.3절 확정 enum
│   ├── IDLE                       # 사용자 미이용, 주행 명령 없음
│   ├── RUNNING                    # 주행 승인·진행 중
│   ├── ESTOP_ACTIVE               # E-stop 래치 활성, 즉시 정지
│   ├── ESTOP_RELEASED_WAIT_RESET  # 원인 해제됨, 명시적 reset 대기
│   ├── READY_TO_GO                # reset 완료, 주행 재승인 가능
│   └── FAULT                      # 반복 복구 실패 또는 원인 불명
├── reason_code
├── stop_latched
├── reset_required
├── speed_limit
└── stamp
```

### 7.2 `RobotHealth`

전체 시스템을 한 번에 이해할 수 있는 `[TARGET]` 요약 상태다.

```text
RobotHealth
├── state
│   ├── STARTING
│   ├── READY
│   ├── DEGRADED
│   ├── STOPPED
│   ├── ESTOPPED
│   └── FAULT
├── motor_ready
├── safety_ready
├── localization_ready
├── navigation_ready
├── guidance_ready
├── voice_ready
├── app_ready
├── active_fault_count
├── highest_severity
├── primary_fault_code
└── stamp
```

`READY`는 단순히 모든 노드가 실행 중이라는 뜻이 아니다.

```text
READY =
    safety state가 IDLE 또는 READY_TO_GO (허용 상태)
AND motor_ready
AND localization_ready
AND navigation_ready
AND 필수 Smart Handle 상태 정상
AND 필수 topic과 TF가 정해진 시간 안에 갱신됨
```

음성이나 원격 앱이 주행 필수 기능이 아니라면 해당 기능 장애는 `DEGRADED`로 처리할 수 있다.
필수 여부는 `required_components.yaml`에 명시한다.

### 7.3 `RobotEvent`

상태 변화, 장애 발생, 복구 시도와 결과를 전달하는 `[TARGET]` 메시지다.

```text
RobotEvent
├── event_id
├── component
├── fault_code
├── severity
├── active
├── latched
├── occurrence_count
├── first_seen
├── last_seen
├── suggested_action
└── stamp
```

### 7.4 권장 Topic

| Topic | 발행자 | 구독자 | 목적 |
|---|---|---|---|
| `/diagnostics` | 모든 진단 대상 노드 | aggregator | 표준 개별 진단 `[TARGET]` |
| `/diagnostics_agg` | aggregator | health monitor, 개발 도구 | 계층형 진단 `[TARGET]` |
| `/safety_state` | Safety Supervisor | 앱, health monitor, guidance | 즉시 안전 상태 `[CURRENT]`, 신규 consumer는 `[TARGET]` |
| `/robot/health` | health monitor | 앱, Mission, 배포 검사 | 전체 준비·운영 상태 `[TARGET]` |
| `/robot/events` | health monitor | 앱, TTS, logger | 상태 변화와 fault 이벤트 `[TARGET]` |
| `/cmd_vel_safe` | Safety Supervisor | motor adapter | 최종 안전 속도 `[CURRENT]` |
| `/smart_handle/state` | guidance driver | Safety Supervisor, health monitor | 연결·접촉·입력 상태 `[TARGET]` |
| `/user_guidance/turn` | turn guide | guidance driver | 좌·우 방향 안내 `[TARGET]` |

---

## 8. Component별 감지 항목

### 8.1 모터 및 CAN

| 감지 항목 | 판단 근거 | 권장 반응 |
|---|---|---|
| CAN interface down | OS interface 상태 | 즉시 정지, latch |
| controller 응답 timeout | 마지막 수신 monotonic age | 즉시 정지, latch |
| 속도 명령 timeout | 마지막 `/cmd_vel_safe` age | driver가 0 rpm 출력 |
| controller fault bit | 상태 frame | 즉시 정지, 수동 확인 |
| encoder 미수신 | encoder frame age | 정지 또는 주행 금지 |
| 명령·실측 속도 불일치 | command와 encoder 비교 | 감속 후 정지, event 기록 |
| 과전류·과온 | controller telemetry | 제한 또는 정지 |
| firmware 불일치 | expected/actual version | 시작 금지 또는 경고 |

모터 driver는 ROS 시간이 아니라 monotonic clock을 기준으로 timeout을 계산해야 시간 동기화나
simulation time 변경에 영향을 덜 받는다.

### 8.2 Safety Supervisor

| 감지 항목 | 설명 |
|---|---|
| 현재 safety state | SAFE, STOP, ESTOP, FAULT 구분 |
| stop latch | 원인이 사라져도 정지를 유지하는지 |
| reset 필요 여부 | 사용자 확인이 필요한지 |
| requested cmd age | upstream 명령 단절 |
| 물리 E-stop age | 입력 장치 연결과 현재 상태 |
| Smart Handle age | handle MCU 또는 사용자 접촉 단절 |
| obstacle 상태 | collision monitor나 직접 안전 센서 |
| CAN health | driver가 보고하는 하드웨어 연결 상태 |
| 적용 speed limit | 현재 감속 제한 |
| reason code | 정지 원인의 기계 판독 코드 |

### 8.3 Smart Handle, LED, 서보, 햅틱

| 감지 항목 | 권장 판정 |
|---|---|
| MCU 통신 상태(`connected`) | 아두이노 나노 포트·전송 실패면 handle disconnected (heartbeat 프로토콜 미사용) |
| 터치센서 접촉(`user_contact`) | 활성 모드에서 미감지 지속 시 유예 후 STOP (아래 참조), 비활성 모드에서는 정지 사유 아님 `[TARGET]` |
| 스마트 핸들 모드 상태 | 활성/비활성 모드와 knob 게이팅 상태 표시 `[TARGET]` |
| 서보 목표·실제 위치 | 오차가 일정 시간 지속되면 servo fault |
| 서보 전류 | stall 또는 기구물 걸림 감지 |
| LED 출력 진단 | driver/MCU fault 확인 |
| 햅틱 출력 진단 | actuator fault 확인 |
| safety state age | 오래되면 driver가 비상 표시 또는 안전한 기본값 적용 |
| turn cue age | 오래된 방향 안내는 즉시 폐기 |

햅틱 고장은 모터 정지 자체를 방해하지 않아야 한다. 다만 VICA의 핵심 사용자가 시각장애인이고
햅틱이 필수 안전 알림으로 분류된다면, 주행 가능 여부 정책은 팀의 위험성 평가 결과에 따라
`DEGRADED`가 아니라 `STOP`으로 올릴 수 있다.

터치센서 미감지 판정은 스마트 핸들 모드에 따라 의미가 다르다(`vica_scenario.md` 2-1절 `[TARGET]`).
활성 모드에서만 “터치 미감지 지속”을 정지 사유로 처리하며, 비활성 모드에서는 정지 사유가 아니다.
활성 모드의 핸들 놓음 처리 순서는 다음과 같다. 유예·정지 지연 시간값과 최종 등급(STOP/ESTOP)은
팀 위험성 평가로 확정한다.

```text
활성 모드에서 터치 미감지 시작
    → 짧은 유예(예: 1~2초)
    → 유예 초과 시 TTS 안내 후
    → N초 경과까지 미감지 지속
    → 감속 후 정지 (STOP 계열, 등급 팀 확정)
```

### 8.4 Localization과 TF

| 감지 항목 | 예시 |
|---|---|
| wheel odom rate | 설정된 최소 Hz 미달 |
| IMU rate | 데이터 주기와 age |
| `/odom` age | 최근 위치 추정 시간 |
| TF age | `map→odom`, `odom→base_footprint` |
| TF 연결성 | 필수 frame chain 존재 여부 |
| covariance | 임계값 초과 |
| pose jump | 짧은 시간 동안 비현실적인 위치 변화 |
| timestamp | 미래 stamp, 역행, 장치 시간 불일치 |

### 8.5 Nav2와 Mission

| 감지 항목 | 권장 반응 |
|---|---|
| lifecycle state | inactive/unconfigured이면 READY 금지 |
| action server | 연결되지 않으면 mission 시작 금지 |
| global path age | 장시간 갱신 없음 |
| controller feedback age | 진행 중인데 feedback 단절 |
| cmd output age | 목표 진행 중인데 속도 출력 없음 |
| progress timeout | 목표 취소, 안전정지 |
| 반복 recovery | 제한 횟수 초과 시 FAULT |
| mission heartbeat | manager 종료 시 goal 취소 또는 정지 |

### 8.6 Voice, LLM, TTS

| 감지 항목 | 권장 반응 |
|---|---|
| microphone open 상태 | 자동 reconnect |
| 입력 audio age | 음성 대기 상태에서 데이터 단절 감지 |
| STT/LLM/TTS model load | 준비되지 않으면 DEGRADED |
| STT latency | 연속 임계 초과 시 경고 |
| LLM latency/timeout | 재시도 제한, 앱에 상태 표시 |
| TTS queue | queue 적체 또는 device error |
| 긴급 음성 감지 node | 필수 정책이면 주행 금지 |
| GPU OOM/temperature | 관련 기능 중지·재시작, 운영 경고 |

음성 기능 장애가 모터 안전 경로를 막으면 안 된다. 단, 음성 기반 긴급정지가 유일한 사용자
정지 수단으로 승인된 구성이라면 필수 component 정책을 별도로 정의해야 한다.

### 8.7 Jetson과 운영체제

다음 항목은 기존 노드에 직접 구현하기보다 `diagnostic_common_diagnostics` 같은 표준 도구의
재사용을 우선 검토한다.

- CPU 사용률과 load
- RAM과 swap
- 디스크 여유 공간
- CPU/GPU 온도
- fan 상태
- GPU memory와 OOM
- 시스템 시간 동기화
- 프로세스 재시작 횟수
- 전원 및 배터리 상태

---

## 9. 상태 등급과 기본 반응

| 등급 | 의미 | 주행 | 사용자 피드백 | 자동 복구 |
|---|---|---|---|---|
| `OK` | 정상 | 허용 | 일반 상태 표시 | 불필요 |
| `WARN` | 성능 저하 가능성 | 조건부 허용 | 앱 표시 | 가능 |
| `DEGRADED` | 일부 비필수 기능 사용 불가 | 정책에 따라 허용 | 앱·음성 알림 | 제한적 |
| `STOP` | 안전 확인 전 주행 불가 | 제어 정지 | LED·햅틱·음성·앱 | 원인별 제한 |
| `ESTOP` | 즉시 정지 필요 | 즉시 정지·latch | 최우선 경보 | 자동 해제 금지 |
| `FAULT` | 반복 복구 실패 또는 원인 불명 | 정지 유지 | 정비 요청 | 추가 자동 시도 중단 |

### 9.1 기본 Fault 처리 표

| 장애 | 등급 | 즉시 동작 | 자동 복구 | 다시 움직이기 위한 조건 |
|---|---|---|---|---|
| 물리 E-stop | ESTOP | brake/stop latch | 없음 | 물리 해제 후 수동 reset |
| motor CAN timeout | ESTOP | driver와 supervisor 정지 | 연결 재시도만 허용 | 통신 정상 + 수동 reset |
| Safety Supervisor 단절 | ESTOP | motor watchdog 정지 | process 재시작 가능 | safety READY + 수동 승인 |
| LiDAR timeout | STOP | goal 취소, 정지 | driver 최대 2회 재시작 | scan 정상 + 새 주행 승인 |
| odom/TF timeout | STOP | goal 취소, 정지 | localization 재구성 | 품질 정상 + 새 주행 승인 |
| Nav2 controller 오류 | STOP | goal 취소 | lifecycle reset 제한 | READY + 새 goal |
| Smart Handle 통신 단절(`connected=false`) | STOP/ESTOP | 정지 | 장치 reconnect | handle 정상 + 사용자 승인 |
| 활성 모드 터치 미감지(핸들 놓음) | STOP `[TARGET]` | 유예 → TTS 안내 → N초 후 감속·정지 | 없음(재접촉 시 정상 주행) | 터치 재감지 또는 새 주행 승인 |
| 서보 고장 | DEGRADED/STOP | 정책에 따른 정지 | 중립 복귀 1회 | 장치 정상 |
| 햅틱 고장 | DEGRADED/STOP | 다른 알림 활성화 | 장치 재연결 | 접근성 위험 평가에 따름 |
| TTS 장애 | DEGRADED | 앱·LED·햅틱 사용 | process 재시작 | TTS 정상 |
| 앱 연결 단절 | WARN/DEGRADED | 로컬 기능 유지 | reconnect | 연결 회복 |
| 디스크 부족 | DEGRADED/FAULT | 녹화 중단, 경고 | 오래된 정책 로그 정리 검토 | 여유 공간 확보 |
| GPU OOM | DEGRADED | 음성/비전 기능 중지 | 해당 process 재시작 | 자원 정상 |

`STOP/ESTOP`처럼 두 등급 가능성이 있는 항목은 하드웨어 구성과 위험성 평가를 통해 하나로
확정해야 한다.

---

## 10. 즉시 피드백 설계

### 10.1 Critical 경로

긴급 상황은 다음처럼 가장 짧은 경로로 전달한다.

```text
safety_supervisor_node
    ├── /cmd_vel_safe = 0 ───────────────▶ mdrobot_can_keyboard_knob_node
    └── /safety_state = ESTOP_ACTIVE
             ├───────────────────────────▶ user_guidance_driver_node
             │                              ├── 긴급 LED
             │                              ├── 강한 햅틱
             │                              └── 서보 중립
             ├───────────────────────────▶ vica_status_app_node
             └───────────────────────────▶ TTS emergency queue
```

`robot_health_monitor_node`는 같은 이벤트를 기록하고 전체 상태를 갱신하지만 이 직접 경로의
중간에 들어가지 않는다.

### 10.2 일반 장애 경로

```text
component diagnostics
    → diagnostic_aggregator
    → robot_health_monitor_node
    → /robot/events
        ├── app: component, 원인, 조치 표시
        ├── TTS: 중요 이벤트만 음성 안내
        ├── LED/Haptic: 우선순위 패턴 출력
        └── logger: 구조화 로그와 snapshot
```

### 10.3 알림 폭주 방지

같은 장애를 매 진단 주기마다 사용자에게 읽어주면 실제 위험 알림이 묻힌다. 다음 정책이
필요하다.

1. 상태가 정상에서 fault로 바뀔 때 한 번 알린다.
2. 같은 fault는 occurrence count만 증가시킨다.
3. 장시간 유지되면 설정된 간격으로만 재알림한다.
4. 복구되면 recovery event를 한 번 발행한다.
5. 더 높은 등급이 발생하면 즉시 기존 알림을 덮어쓴다.
6. E-stop 알림은 rate limit보다 높은 우선순위를 갖는다.

### 10.4 권장 사용자 메시지 예

```text
좋지 않은 예
"에러가 발생했습니다."

권장 예
"라이다 데이터가 0.5초 동안 들어오지 않아 주행을 정지했습니다.
자동 재연결을 1회 시도합니다."

"모터 통신이 끊겨 긴급정지했습니다.
로봇을 확인한 뒤 앱에서 안전 초기화를 실행해 주세요."
```

---

## 11. 자동 복구 정책

### 11.1 책임 분리

| 기능 | 담당 |
|---|---|
| 모터 즉시 정지 | Motor driver + Safety Supervisor |
| Nav2 configure/activate/reset | Nav2 Lifecycle Manager |
| process 종료 감지·재시작 | launch 또는 systemd |
| 재시도 허용 여부·횟수 결정 | Health Monitor |
| 사용자 승인 | 앱/물리 버튼/운영 절차 |
| 이전 mission 재개 | Mission Manager, 기본은 자동 금지 |

### 11.2 예시 정책

```yaml
lidar_timeout:
  severity: STOP
  action: restart_lidar
  max_attempts: 2
  retry_window_sec: 60
  cooldown_sec: 5
  require_manual_resume: true

nav2_controller_error:
  severity: STOP
  action: reset_nav2_lifecycle
  max_attempts: 1
  cooldown_sec: 3
  require_manual_resume: true

tts_device_error:
  severity: DEGRADED
  action: restart_tts
  max_attempts: 3
  retry_window_sec: 120
  cooldown_sec: 5
  require_manual_resume: false

motor_can_timeout:
  severity: ESTOP
  action: none
  max_attempts: 0
  require_manual_reset: true
```

### 11.3 복구 상태 전이

```text
NORMAL
  │ fault detected
  ▼
DETECTED
  ├── critical ─────────────▶ LATCHED_STOP
  │
  └── recoverable
         ▼
      RECOVERING
         ├── success ───────▶ WAITING_FOR_VALIDATION
         │                        ├── valid ─▶ RECOVERED
         │                        └── invalid ─▶ FAULT
         └── retry exceeded ────▶ FAULT
```

`RECOVERED`는 장치가 다시 연결되었다는 뜻이며 이전 주행을 자동 재개해도 된다는 뜻이 아니다.

---

## 12. QoS와 Timeout 원칙

| Interface | 권장 QoS 방향 | 이유 |
|---|---|---|
| `/safety_state` | reliable, transient local, 작은 depth `[TARGET QoS]` | 늦게 연결된 노드도 최신 안전 상태 확인 |
| `/robot/health` | reliable, transient local | 앱과 bringup 검사에서 최신 상태 즉시 확인 |
| `/robot/events` | reliable, volatile | 이벤트 순서 전달, 과거 전체 재전송은 별도 로그 사용 |
| `/smart_handle/state` | reliable + deadline/liveliness 검토 | `connected` 상태와 topic age로 단절 감지 (하드웨어 heartbeat 아님) |
| `/user_guidance/turn` | reliable, depth 1, lifespan 적용 | 오래된 회전 안내 폐기 |
| LiDAR/IMU | sensor data profile | 고주기 데이터 처리 |

DDS QoS의 deadline/liveliness는 단절 감지에 유용하지만, 이것만으로 모터 안전 timeout을
구현하면 안 된다. Safety Supervisor와 motor driver는 application-level monotonic timeout을
함께 가져야 한다.

---

## 13. 전체 Bringup 순서

모든 기능을 한 번에 시작하되 다음 준비 순서를 지킨다.

```text
1. robot description / static TF
2. motor driver + Safety Supervisor
   └── 시작 상태는 반드시 정지 또는 latch
3. system monitor + diagnostic aggregator
4. LiDAR / IMU / Camera / Handle drivers
5. localization
6. Nav2 lifecycle configure → activate
7. mission manager
8. turn guide + user guidance driver
9. voice pipeline
10. app bridge
11. RobotHealth readiness 검사
12. 모든 필수 조건 정상일 때 READY
```

시작 중인 노드가 아직 준비되지 않은 것을 fault로 오판하지 않도록 각 component별 startup
grace period가 필요하다. 다만 motor와 Safety Supervisor의 timeout은 이 유예 때문에
비활성화하면 안 된다.

### 13.1 Mission 시작 Gate

```text
mission_start_allowed =
    RobotHealth.state == READY
AND SafetyState.state in (IDLE, READY_TO_GO)
AND stop_latched == false
AND motor_ready
AND localization_ready
AND navigation_ready
AND guidance_required_components_ready
```

---

## 14. 실제 로봇의 피드백 수집 방식

실제 로봇에서는 하나의 진단 topic만 보지 않고 네 계층의 피드백을 조합한다.

### 14.1 하드웨어 내부 피드백

- 모터 controller heartbeat·watchdog (Smart Handle 아두이노 나노는 heartbeat 미사용, `connected`로 판정)
- hardware watchdog
- motor current, temperature, voltage
- encoder 속도와 위치
- driver fault bit
- E-stop 회로 상태
- BMS 상태

ROS 2 노드가 멈추어도 하드웨어가 마지막 속도로 계속 움직이지 않도록 하는 최후의 방어선이다.

### 14.2 ROS 2 런타임 피드백

- `/diagnostics`
- node 존재 여부
- topic 주기와 마지막 수신 시간
- TF 연결과 timestamp
- Lifecycle state
- Action goal/result/feedback
- 데이터 품질과 상호 일관성

단순히 “node가 존재한다”는 것만 확인하면 callback 정지나 데이터 고착을 찾을 수 없다.
반드시 topic age와 데이터 값의 변화도 함께 확인한다.

### 14.3 현장 사용자 피드백

- LED: 정상, 방향, 경고, E-stop 패턴
- 햅틱: 회전 안내와 긴급정지 패턴 구분
- 서보: 좌·우 방향과 중립
- TTS: 장애 원인과 사용자 조치
- 앱: 전체 상태, active fault, 복구 진행, reset 가능 여부

### 14.4 원격 운영·개발 피드백

- 구조화 로그
- process 재시작 횟수
- rosbag2 장애 전후 snapshot
- 성능 metric
- software/config/firmware version
- 배포 성공과 rollback 기록

원격 서버나 cloud가 끊겨도 로봇의 안전 기능과 현장 알림은 계속 동작해야 한다.

---

## 15. 장애 데이터 기록

### 15.1 rosbag2 Snapshot

평소에는 순환 buffer에 최근 데이터만 유지하고 `ERROR`, `STOP`, `ESTOP` 발생 시 장애 전후
구간을 저장하는 방식을 권장한다.

기본 저장 대상:

```text
/diagnostics
/diagnostics_agg
/robot/health
/robot/events
/safety_state
/cmd_vel_req
/cmd_vel_safe
/wheel/odom
/odom
/tf
/tf_static
/scan
/plan
/mission/state
/smart_handle/state
```

카메라 영상은 저장 용량과 개인정보 영향을 검토한 뒤 별도 profile로 선택한다.

### 15.2 반드시 함께 기록할 버전

- software release version
- Git commit SHA
- ROS parameter/config hash
- map ID와 map version
- MDROBOT firmware version
- Smart Handle MCU firmware version
- STT/LLM/TTS model version
- Nav2 parameter version
- 배포 시간과 장치 ID

이 정보가 없으면 동일한 장애를 개발 환경에서 재현하기 어렵다.

---

## 16. 실제 배포 구조

### 16.1 하나의 target, 여러 service

권장 예:

```text
vica.target
├── vica-core.service
│   └── motor + safety + system monitor
├── vica-navigation.service
│   └── sensors + localization + Nav2 + mission
├── vica-guidance.service
│   └── turn guide + LED/servo/haptic driver
├── vica-voice.service
│   └── STT + LLM + TTS
├── vica-app.service
│   └── app bridge
└── vica-isaac.service
    └── GPU 기반 perception이 있을 때만 사용
```

운영자는 `vica.target` 하나만 시작한다. 내부적으로 service를 나누면 음성 process의 OOM이나
앱 오류가 motor/safety process를 같이 종료시키는 것을 방지할 수 있다.

`vica-core.service`가 재시작될 때 motor driver의 시작 출력은 항상 0이어야 하며,
Safety Supervisor가 READY가 되기 전에는 주행 명령을 허용하면 안 된다.

### 16.2 권장 설치 위치

```text
/opt/vica/releases/<version>/    # 버전별 read-only artifact
/opt/vica/current                # 현재 release를 가리키는 링크
/etc/vica/                       # 장치별 설정
/var/lib/vica/                   # map, model, 운영 데이터
/var/log/vica/                   # 로그와 장애 snapshot
```

### 16.3 배포 흐름

```text
CI build/test
    → ARM64 release artifact 생성
    → bench test
    → HIL 또는 실제 controller 연동 시험
    → 로봇 controlled stop 확인
    → 새 release 배포
    → vica.target 시작
    → /robot/health READY 검사
        ├── 성공: 배포 확정
        └── 실패: 이전 release rollback
```

배포 health check는 process PID만 확인하지 않고 다음을 확인해야 한다.

- `/robot/health` 수신
- motor/safety readiness
- 필수 sensor topic rate
- localization TF
- Nav2 lifecycle active
- Smart Handle `connected` 정상
- active STOP/ESTOP/FAULT 없음

---

## 17. 최소 변경 구현 순서

### 1단계: 기존 노드가 자신의 상태를 설명하게 한다

새 감시 노드부터 만들기 전에 motor, safety, handle, localization, Nav2 adapter, voice, app
노드가 `/diagnostics`에 필요한 데이터를 발행하도록 설계한다.

완료 기준:

- 각 component의 마지막 데이터 age 확인 가능
- hardware/communication/state/error 구분 가능
- 사람이 읽는 message와 기계가 읽는 key-value 모두 존재

### 2단계: 표준 진단 집계기를 추가한다

`diagnostic_aggregator` 설정만 추가해 component별 tree를 만든다.

```text
VICA
├── Hardware
│   ├── Motor
│   ├── LiDAR
│   ├── IMU
│   └── Smart Handle
├── Safety
├── Localization
├── Navigation
├── User Guidance
├── Voice
├── App
└── Computer
```

### 3단계: Health Monitor 한 개를 추가한다

초기 역할은 다음으로 제한한다.

- 필수 component readiness 계산
- node/topic/TF timeout 확인
- fault severity와 code 결정
- `/robot/health`, `/robot/events` 발행
- 중복 알림 억제

### 4단계: 기존 출력 경로를 연결한다

새로운 알림 노드를 추가하지 않고 기존 구성요소를 재사용한다.

- `vica_status_app_node`: `/robot/health`, `/robot/events`
- TTS: 중요 event만 수신
- `user_guidance_driver_node`: `/safety_state` 직접 수신, 일반 event 선택 수신

### 5단계: 제한적 자동 복구를 추가한다

먼저 TTS, 앱, 센서 reconnect 같은 비안전 영역부터 적용한다. motor fault, E-stop, mission
재개는 자동화하지 않는다.

### 6단계: 배포와 장애 snapshot을 연결한다

systemd service, release versioning, `/robot/health` 기반 배포 검사, rollback, rosbag2 snapshot을
추가한다.

---

## 18. 시험 계획과 승인 기준

### 18.1 Fault Injection 시험

| 시험 | 예상 결과 |
|---|---|
| Safety Supervisor 강제 종료 | motor watchdog으로 정지, ESTOP 또는 FAULT 표시 |
| motor CAN cable 분리 | 즉시 정지, CAN fault latch, 수동 reset 요구 |
| LiDAR topic 중단 | Nav2 goal 취소, STOP, 제한적 driver 복구 |
| `/odom` 중단 | 주행 정지, localization fault |
| TF 제거 또는 오래된 stamp | READY 해제, 주행 금지 |
| Smart Handle 전원 차단 | timeout 내 정지, 햅틱 불가 상태 앱/TTS 표시 |
| guidance node 종료 | 모터 안전 유지, 앱에 guidance fault |
| TTS 강제 종료 | 주행 정책에 따라 DEGRADED, 앱/LED/햅틱 유지 |
| app network 차단 | 로컬 주행 안전과 현장 알림 유지 |
| GPU OOM 유도 | 관련 process만 복구, core safety 유지 |
| Health Monitor 종료 | motor/safety 직접 경로 유지 |
| diagnostic aggregator 종료 | safety 유지, monitoring degraded 표시 |

### 18.2 안전 승인 기준

다음 항목은 구현 완료 조건으로 사용한다.

1. Safety Supervisor 또는 Health Monitor가 종료되어도 모터가 안전 시간 안에 정지한다.
2. 오래된 `/cmd_vel_safe`가 재사용되지 않는다.
3. E-stop은 원인이 사라져도 명시적 reset 전까지 latch된다.
4. 자동 복구 후 이전 mission이 자동 재개되지 않는다.
5. 장애 원인, 최초 시점, 지속 시간, 복구 시도가 기록된다.
6. 동시에 여러 fault가 발생해도 가장 높은 severity가 먼저 안내된다.
7. 앱·음성·네트워크가 모두 끊겨도 로컬 LED/햅틱 및 모터 안전이 유지된다.
8. 새로운 release가 READY에 도달하지 못하면 이전 release로 되돌릴 수 있다.

### 18.3 성능 측정 항목

팀에서 하드웨어 실측 후 수치를 확정해야 한다.

- E-stop 입력부터 wheel stop 명령까지의 최대 지연
- CAN timeout부터 0 rpm/brake 명령까지의 최대 지연
- fault 발생부터 LED/햅틱 시작까지의 최대 지연
- fault 발생부터 앱/TTS 알림까지의 최대 지연
- node/topic/TF 단절 판정 시간
- 자동 복구 성공 시간과 최대 재시도 시간
- 장애 snapshot의 전·후 보존 길이

---

## 19. 팀에서 확정해야 할 항목

다음은 코드 구현 전에 안전·하드웨어·앱 담당자가 함께 결정해야 한다.

1. Smart Handle 접촉 단절을 `STOP`과 `ESTOP` 중 어느 등급으로 볼 것인가?
1-1. 활성 모드 터치 미감지의 유예 시간, TTS 안내 후 정지 지연(N초), 최종 등급은 얼마/무엇인가?
1-2. 터치센서 모드 전환 판정과 knob 게이팅을 어느 노드가 담당하는가? (`vica_scenario.md` 2-1절 `[TARGET]`)
2. 햅틱 또는 서보 고장 시 주행을 허용할 수 있는가?
3. voice emergency monitor는 주행 필수 component인가?
4. LiDAR와 localization의 timeout 및 startup grace period는 얼마인가?
5. motor fault 중 자동 통신 재연결만 허용할 항목은 무엇인가?
6. 수동 reset은 물리 버튼, 앱, 둘의 조합 중 무엇으로 할 것인가?
7. 복구 후 새 mission 승인 절차는 무엇인가?
8. rosbag에 camera/audio를 포함할 것인가?
9. 장애 로그와 bag의 보존 기간 및 개인정보 정책은 무엇인가?
10. systemd service를 Jetson 한 대에 둘지, 일부 기능을 별도 컴퓨터에 둘지?

---

## 20. 최종 권고안

가장 적은 구조 변경으로 현재 기능을 유지하면서 상태 감지와 즉시 피드백을 추가하려면 다음
구성을 권장한다.

```text
기존 노드
└── diagnostic_updater로 자신의 상태 발행

표준 diagnostic_aggregator
└── 전체 상태를 component tree로 집계

신규 vica_system_monitor 패키지
└── robot_health_monitor_node 1개
    ├── 준비 상태 계산
    ├── node/topic/TF 감시
    ├── fault code·severity 결정
    ├── 중복 알림 억제
    ├── 제한적 복구 정책
    └── 장애 snapshot trigger

기존 safety 경로
└── safety_supervisor_node → /cmd_vel_safe → motor driver
    └── 모니터와 무관하게 즉시 정지

기존 사용자 피드백 경로
├── /safety_state → LED·햅틱·앱·TTS
└── /robot/events → 앱·TTS·일반 경고
```

새 custom node를 여러 개 만드는 대신 표준 ROS 2 진단과 lifecycle 기능을 재사용하고,
`robot_health_monitor_node` 하나에 VICA 고유 정책만 둔다. 동시에 모터 안전 경로는 이
모니터에서 분리한다. 이것이 노드 수, 장애 격리, 실시간성, 팀의 유지보수성을 함께 고려한
권장 균형점이다.

---

## 21. 참고 자료

아래 자료는 상세 구현 시 확인할 ROS 2 공식 문서다.

- [ROS 2 diagnostic_updater](https://docs.ros.org/en/ros2_packages/humble/api/diagnostic_updater/index.html)
- [ROS 2 diagnostic_aggregator](https://docs.ros.org/en/ros2_packages/humble/api/diagnostic_aggregator/)
- [ROS 2 Humble QoS 설정](https://docs.ros.org/en/humble/Concepts/Intermediate/About-Quality-of-Service-Settings.html)
- [ROS 2 Managed Node Lifecycle 설계](https://design.ros2.org/articles/node_lifecycle.html)
- [Nav2 Lifecycle Manager](https://docs.nav2.org/configuration/packages/configuring-lifecycle.html)
- [ROS 2 Launch](https://docs.ros.org/en/humble/Tutorials/Intermediate/Launch/Launch-Main.html)
- [rosgraph_monitor](https://docs.ros.org/en/ros2_packages/humble/api/rosgraph_monitor/)
- [diagnostic_common_diagnostics](https://docs.ros.org/en/ros2_packages/humble/api/diagnostic_common_diagnostics/diagnostic_common_diagnostics.html)
- [ROS 2 Topics, Services, Actions](https://docs.ros.org/en/humble/Concepts/Basic/Interfaces-Topics-Services-Actions.html)
- [ROS 2 Humble rosbag2 snapshot 관련 릴리스 문서](https://docs.ros.org/en/humble/Releases/Release-Humble-Hawksbill.html)

---

## 22. 문서 변경 전 체크

이 초안이 승인되기 전에는 다음 작업을 하지 않는다.

- 기존 패키지 이동 또는 이름 변경
- 기존 node 분리·통합
- topic 이름 변경
- Safety Supervisor 로직 변경
- motor timeout 및 안전 제한값 변경
- systemd service 설치
- 자동 복구 활성화

먼저 팀 검토를 통해 필수 component, fault severity, timeout, 수동 reset 방식과 시험 승인
기준을 확정한 후 구현 작업을 별도 계획으로 진행한다.
