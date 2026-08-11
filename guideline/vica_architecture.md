# VICA 통합 아키텍처

검토 기준일: 2026-07-26
기준 작업공간: 이 문서가 포함된 작업공간 루트

## 1. 문서 목적과 판정 기준

이 문서는 최신 작업공간에서 확인한 VICA의 저장소, 노드, 토픽, 데이터, TF와 안전 경계를 정리한다.

문서 안에서는 다음 세 범위를 구분한다.

- **현재 구조**: 코드·설정·launch가 현재 작업공간에 존재한다.
- **통합 gap**: 구성요소는 있지만 실제 producer/consumer 또는 launch 연결이 끊겨 있다.
- **목표 구조**: Smart Handle 서보·LED 또는 안전 통합을 위해 앞으로 구현할 구조다.

설계 문서나 코드 주석에만 있는 기능을 구현 완료로 간주하지 않는다.

## 2. 작업공간 구성

VICA는 하나의 monorepo가 아니라 세 개의 Git 저장소와 공용 참고자료 폴더로 구성된다.

| 경로 | 현재 브랜치 | 역할 |
| --- | --- | --- |
| `vica_ros2_ws/` | `dev` | ROS2 제어, Nav2, SLAM, TF, 안전, 모터, Mission, 인터페이스 |
| `vica-voice-llm/` | `dev` | STT, TTS, 긴급어 감지, LLM 목적지 해석 |
| `VICA_Supervisor/` | `dev` | Flutter 운영 앱, rosbridge, 상태·지도·장소 관리 |
| `GOVERNANCE.md` | 조정 저장소 | 팀·AI 협업, 변경 승인, 배포 기준 |
| `guideline/` | 조정 저장소 | 통합 문서(시나리오·아키텍처·BT), 공식 URL 목록 |
| `source_file/` | 로컬 전용(Git 제외) | 하드웨어·공식 문서 원본(PDF, drawio) |
| `devlog/` | 조정 저장소 | 날짜별 개발 로그(`YYYY-MM-DD.md`, 팀 공유) |

작업공간 루트는 기준 문서와 `workspace.repos`를 관리하는 조정 Git 저장소다. 세 제품
저장소는 루트 Git에서 제외하고 manifest로 구성한다. `source_file/` 원본은 로컬에
유지하고 Git에서 제외하며, 팀은 권한이 확인된 별도 공유 위치 또는 공식 URL로 받는다.

LLM과 앱은 dependency·빌드·배포 주기가 다르므로 별도 저장소를 유지한다. 세 제품
저장소를 하나로 합치지 않고 `GOVERNANCE.md`, guideline과 향후 배포 manifest에서
공용 계약과 정확한 버전을 중앙 관리한다.

`vica_ros2_ws/src`의 VICA ROS 패키지는 현재 12개다.

| 패키지 | 역할 |
| --- | --- |
| `encoder_feedback` | MDROBOT C5 위치 피드백을 wheel odometry로 변환 |
| `mdrobot_can_control` | `/cmd_vel_safe`를 CAN motor 명령으로 변환하는 actuator adapter |
| `vica_cartographer` | Cartographer 2D 설정과 SLAM launch |
| `vica_description` | URDF/Xacro, mesh, robot_state_publisher launch |
| `vica_destination_manager` | 지도별 목적지 YAML 저장·조회·삭제와 Mission reload |
| `vica_interfaces` | `VicaIntent`, `RobotState`, `EmergencyEvent` 메시지 |
| `vica_localization` | wheel odometry와 IMU를 `robot_localization` EKF로 융합하고 표준 `/odom` 제공 |
| `vica_mission_manager` | 목적지 gate, Mission 상태, Nav2 goal, 음성 E-stop bridge |
| `vica_nav2` | 저장 지도 기반 Nav2 bringup과 parameter |
| `vica_nvblox_bringup` | Isaac ROS Docker의 D455·nvblox launch와 VICA override |
| `vica_sensor_adapters` | IMU frame 변환, VSLAM covariance adapter |
| `vica_safety` | 물리·앱·음성 E-stop 중앙 래치, Safety Supervisor, reset 오케스트레이터 |

현재 `vica_user_guidance`, `vica_exploration` 패키지는 존재하지 않는다.

`vica_system_monitor`(외부 대상 진단 어댑터와 전체 상태 모니터)는 **미머지 브랜치에만**
있다. 13절이 그 계약을 정리하지만 `dev`의 패키지 수는 아직 12개다.

## 3. 전체 현재 구조

```text
┌──────────────────── Voice / LLM ────────────────────┐
│ 마이크 → STT → /vica/user_text → LLM → /vica/intent │
│ 마이크 → 긴급어 감지 → /vica/emergency              │
└────────────────────────┬─────────────────────────────┘
                         │
                         ▼
┌────────────────── Mission Manager ──────────────────┐
│ VicaIntent 검증                                      │
│ destination/pose/Nav2/E-stop gate                    │
│ NavigateToPose 발행                                  │
│ /vica/robot_state, /vica/tts_request 발행            │
└────────────────────────┬─────────────────────────────┘
                         │ NavigateToPose
                         ▼
┌──────────────────────── Nav2 ────────────────────────┐
│ map_server + AMCL + planner + controller + BT        │
│ local costmap: /scan voxel + nvblox 3D slice         │
│ 최종 속도 출력: /cmd_vel_req                          │
└────────────────────────┬─────────────────────────────┘
                         ▼
                    /cmd_vel_req
                         │
                         ▼
                 Safety Supervisor
                         │ /cmd_vel_safe [CURRENT]
                         ▼
                   MDROBOT motor
                         │
                         ▼
                    CAN → MDROBOT
```

앱은 rosbridge를 통해 상태 topic과 관리 service를 사용한다. 앱과 시험 도구
`vica_goto_goal.py`는 Nav2 action을 직접 처리하지 않고 Mission Manager의 공개 목적지
요청 service를 호출한다.

## 4. 인터페이스 계약

### 4.1 공용 ROS 메시지

#### `VicaIntent`

```text
string intent
string destination_candidate
string matched_destination_id
float32 confidence
bool need_confirm
string reply
string safety_flag
```

- `destination_candidate`: LLM 제안
- `matched_destination_id`: 코드가 검증한 목적지 ID
- `VicaIntent`는 이동 명령이 아니다.

#### `RobotState`

```text
int32 current_floor
string current_building
bool is_moving
```

현재 Mission Manager가 1Hz로 발행한다. 앱의 `/robot_status` JSON과는 별도 계약이다.

#### `EmergencyEvent`

```text
string keyword
string source_text
float64 detected_at
```

긴급어를 LLM보다 먼저 전달한다.

#### `RobotFault`

```text
string component
string fault_code
uint8 severity          # OK=0, WARN=1, DEGRADED=2, STOP=3, FAULT=4
bool active
bool latched
uint32 occurrence_count
builtin_interfaces/Time first_seen
builtin_interfaces/Time last_seen
string detail
string suggested_action
```

결함 하나를 표현한다. Header가 없는 순수 데이터라 `RobotHealth`와 `RobotEvent`가 그대로
재사용한다.

`detail`·`suggested_action`의 한국어 문구 **정본은 로봇 쪽 `fault_catalog.py`**다. 앱은
받은 문구를 표시만 한다. 문구를 앱에 두면 로봇이 새 fault를 추가할 때마다 앱을 다시
배포해야 하고 정본이 두 저장소로 갈라진다.

`first_seen`·`last_seen`은 사람에게 보여줄 시각이므로 SYSTEM_TIME이다. 만료·신선도
판정에는 쓰지 않는다. 그 판정은 STEADY_TIME 계약을 따른다(9.4절).

**등급 축에 비상정지가 없다.** E-stop은 STOP보다 한 단계 심각한 것이 아니라 종류가
다르다 — 래치가 걸리고, 관리자 reset이 있어야 풀리고, `emergency_stop_node`가 소유한다.
그 사실은 `latched`와 `RobotHealth.state == ESTOPPED`가 나타낸다.

| 축 | 답하는 질문 | 표현 |
| --- | --- | --- |
| `severity` | 얼마나 나쁜가 | OK … STOP, FAULT |
| `latched` | 관리자 reset이 필요한가 | bool |
| `RobotHealth.state` | 어떤 모드인가 | … STOPPED, **ESTOPPED** … |

등급에 섞으면 진단 결함 하나가 "비상 정지"로 표시되어 관리자가 있지도 않은 버튼을
찾는다. 폭주 억제 해제 조건도 등급이 아니라 `latched`를 본다 — 등급으로 판정했을 때
모터 진단 미수신이 초당 한 건씩 알림을 냈다.

이 분리로 "E-stop을 걸어야 할 만큼 심각"과 "주행만 막으면 됨"의 구분은 사라졌다.
그 구분이 필요해지는 시점은 자동 복구(초안 11절 `[TARGET]`)이며, 그때는 **복구 정책
필드**로 표현한다. 표시용 등급에 다시 싣지 않는다.

#### `RobotHealth`

```text
std_msgs/Header header
uint8 state             # STARTING=0, READY=1, DEGRADED=2, STOPPED=3, ESTOPPED=4, FAULT=5
uint8 motor_readiness           # UNKNOWN=0, NOT_READY=1, READY=2
uint8 safety_readiness
uint8 localization_readiness
uint8 navigation_readiness
uint8 lidar_readiness
uint8 perception_readiness
uint8 guidance_readiness
uint8 voice_readiness
uint8 app_readiness
uint16 active_fault_count
uint8 highest_severity
string primary_fault_code
RobotFault[] active_faults
```

readiness는 bool이 아니라 **3상태**다. `UNKNOWN`은 "정상"이 아니라 **관측 수단이 없다**는
뜻이다. Smart Handle은 아두이노에서 젯슨으로 올라오는 상향 경로가 없어 서보·LED·햅틱이
실제로 동작했는지 확인할 방법이 없다(12절). 이것을 `READY`로 보고하면 관리자에게 잘못된
안심을 준다. `SmartHandleState.msg`가 경고하는 실패 모드와 같다.

`active_faults` 배열은 앱 재접속 복원용이다. 앱은 이 배열 하나로 현재 결함 전체를 복원한다.

#### `RobotEvent`

```text
std_msgs/Header header
RobotFault fault
uint8 transition        # RAISED=0, ESCALATED=1, REMINDER=2, CLEARED=3
```

결함의 상태 전이만 발행한다. `event_id`는 두지 않는다 — 중복 판정 키는
`component`+`fault_code`로 충분하고 목록 표시용 고유 id는 앱이 만든다.

### 4.2 핵심 topic·service·action

| 인터페이스 | 타입 | 현재 producer | 현재 consumer | 상태 |
| --- | --- | --- | --- | --- |
| `/vica/user_text` | `std_msgs/String` | STT | LLM node | 연결됨 |
| `/vica/intent` | `VicaIntent` | LLM node | Mission Manager | 이동 요청 후보, 연결됨 |
| `/vica/emergency` | `EmergencyEvent` | 긴급어 감시 | Mission Manager, E-stop bridge | LLM 우회 경로, 연결됨 |
| `/vica/robot_state` | `RobotState` | Mission Manager | LLM node | 1 Hz 상태 입력, 연결됨 |
| `/vica/tts_request` | `std_msgs/String` | STT, LLM, Mission Manager | TTS | 우선순위 큐 연결, 실제 음성 출력 `[미검증]` |
| `/vica/tts_state` | `std_msgs/Bool` | TTS | 긴급어 감시 | 재생 중 자가 E-stop 오탐 억제 |
| `/voice_emergency_stop` | `std_msgs/Bool` | emergency bridge | emergency_stop_node | 연결 가능 |
| `/app_emergency_stop` | `std_msgs/Bool` | app_emergency_node | emergency_stop_node | 연결 가능 |
| `/emergency_stop` | `std_msgs/Bool` | vica_safety/emergency_stop_node | Safety, Mission, app_emergency_node | 중앙 래치 코드·launch 구현, 실기 `[미검증]` |
| `/estop_state` | `std_msgs/Bool` | vica_safety/emergency_stop_node | 호환·진단 consumer | 중앙 래치 호환 출력, motor 소유 아님 |
| `/safety_state` | `std_msgs/String` | Safety Supervisor | app_emergency_node | 코드상 연결, runtime `[미검증]` |
| `/cmd_vel` | `Twist` | test tool | 안전 운영 consumer 없음 | 운영 Nav2 출력으로 사용하지 않음 |
| `/speed_limit` | `nav2_msgs/msg/SpeedLimit` | Mission Manager | Nav2 controller server | Goal 잔여거리 3 m에서 70% 제한, 실제 주행 `[미검증]` |
| `/cmd_vel_req` | `Twist` | Nav2 velocity smoother | Safety Supervisor | launch remap 구현, 실기 종단 `[미검증]` |
| `/cmd_vel_safe` | `Twist` | Safety Supervisor | motor | 코드상 연결, launch/runtime 검증 필요 |
| `/wheel/odom` | `nav_msgs/Odometry` | encoder_feedback | `robot_localization` EKF | 코드·설정·launch 연결 및 로컬 기동 검증 완료, 실기 검증 필요 |
| `/imu/base_link` | `sensor_msgs/Imu` | IMU frame adapter | `robot_localization` EKF | D455 실행 환경의 실제 입력 연결 검증 필요 |
| `/odom` | `nav_msgs/Odometry` | `robot_localization` EKF | Cartographer, Nav2, 앱 상태 | 표준 출력 계약 및 launch 연결 완료, 실기 검증 필요 |
| `/navigate_to_pose` | Nav2 action | Mission Manager | Nav2 | 운영 Goal 단일 권한 |
| `/vica/mission/request_destination` | `RequestDestination` | Flutter, CLI | Mission Manager | UUID·지도·Mission gate를 거치는 공개 요청 |
| `/vica/mission/reload_destinations` | `Trigger` | destination manager | Mission Manager | YAML 변경 후 catalog 교체 |
| `/vica/mission/cancel_destination` | `MissionCommand` | Flutter | Mission Manager | 진행 중 안내 취소, 실기 `[미검증]` |
| `/vica/mission/pause_navigation` | `MissionCommand` | Flutter | Mission Manager | 목적지 보관 후 일시정지, 실기 `[미검증]` |
| `/vica/mission/resume_navigation` | `MissionCommand` | Flutter | Mission Manager | 보관 목적지로 재출발, 실기 `[미검증]` |
| `/vica_goal_event` | JSON `String` | Mission Manager | status app node, vica_goto_goal | goal 생명주기 이벤트, `goal_paused` 포함 |
| `/app_estop_activate` | `Trigger` | Flutter client | app_emergency_node | vica_safety launch 포함, runtime `[미검증]` |
| `/app_estop_reset` | `Trigger` | Flutter client | app_emergency_node | 전체 reset 오케스트레이션 진입점 |
| `/safety_reset` | `Trigger` | 유지보수 CLI | app_emergency_node | 앱과 같은 절차, 호출자 인증 `[GAP]` |
| `/vica_safety/internal/estop_reset` | `Trigger` | app_emergency_node | emergency_stop_node | 모든 source 해제·F1 fresh 조건 |
| `/vica_safety/internal/supervisor_reset` | `Trigger` | app_emergency_node | Safety Supervisor | E-stop fresh/false·요청 명령 0 조건 |
| `/robot_status` | JSON `String` | status app node | Flutter | 연결 가능 |
| `/app_estop_state` | JSON `String` | app emergency node | Flutter | 중앙 E-stop·Safety 통합 상태, 앱 호환 `active` 유지 |
| `/diagnostics` | `diagnostic_msgs/DiagnosticArray` | motor node, `external_diagnostics_node`, health monitor | `diagnostic_aggregator` | 표준 개별 진단, 발행자 확대는 13.4절 순서 |
| `/diagnostics_agg` | `diagnostic_msgs/DiagnosticArray` | `diagnostic_aggregator` | health monitor, `rqt_robot_monitor` | 계층형 진단 1 Hz, 실기 `[미검증]` |
| `/robot/health` | `RobotHealth` | `robot_health_monitor_node` | Flutter, status app node | 1 Hz 상시 + 변화 시 즉시, 실기 `[미검증]` |
| `/robot/events` | `RobotEvent` | `robot_health_monitor_node` | Flutter | 전이 시점 발행, 실기 `[미검증]` |

## 5. Voice·LLM 아키텍처

### 5.1 정상 발화

```text
ros_wakeword_node               ← 마이크 앞단. 호출어 "비카야" 감지 후 청취
  └─ /vica/user_text
      └─ ros_node
          ├─ /vica/robot_state 구독
          ├─ LangChain + Ollama Cloud/Local
          ├─ destination_matcher 코드 검증
          └─ /vica/intent
```

호출어를 진입 경로로 두는 이유는 사용자가 버튼을 누를 수 없기 때문이다. 시각장애인
사용자는 push-to-talk 엔터를 칠 수 없고 스마트핸들에 버튼을 더 달 수 없다.
`ros_stt_node`(push-to-talk)는 개발용으로 남으며 launch 에는 들어가지 않는다 —
마이크는 한 프로그램만 쓸 수 있어 동시 실행이 불가능하다.

LLM backend는 환경변수로 선택한다.

- 개발 기본값: Ollama Cloud, `gemma4:cloud`
- Jetson 목표: 로컬 Ollama, `gemma4:e2b`
- STT: faster-whisper
- TTS: Supertonic

LLM 호출 실패 시 `unknown` 의도와 안전한 재시도 문구를 반환한다.

### 5.2 긴급어

```text
마이크 상시 감시 (ros_wakeword_node)
→ openWakeWord 모델 B 관문 → whisper 검증 → 정확 매칭
→ /vica/emergency
├─ Mission Manager: goal 취소 + estopped 상태
└─ emergency_estop_bridge
   → /voice_emergency_stop 펄스
   → emergency_stop_node
   → /emergency_stop
```

**2단 구조를 쓰는 이유**: 모델 관문만으로는 유사어(멈춤·정지야·스톡)가 뚫리고,
whisper 상시 감시만으로는 부하가 크다(RTF 0.59 → 0.12). 두 신호는 오류 원인이
독립적이라 — 임베딩은 유사음에, whisper 는 발음 편차에 약하다 — 함께 쓰면 오탐이
크게 준다. 실측 근거는 `vica-wakeword/docs/stt-gate-findings.md`.

`keyword` 는 whisper 전사에서 정확 매칭으로 뽑으므로 항상 아래 목록 안의 값이다.
브리지·래치 체인은 변경되지 않았다.

hard-stop 키워드는 현재 6개다.

```text
멈춰, 정지, 스탑, 스톱, 안돼, 위험해
```

`잠깐`, `천천히`, `느리게`는 E-stop 감지 목록에서 제외되어 일반 발화로 처리된다.
감속 intent는 아직 `[TARGET]`이다. `잠깐` 계열을 일시정지(`pause`) intent 로
연결하는 것은 `vica_scenario.md` 9.6절이 정한 방향이며 음성 쪽은 아직 `[GAP]`이다.

`ros_emergency_node`(whisper 상시 감시)는 롤백 경로로 남아 있다. launch 에는 없다.

### 5.3 현재 실행 계약

`vica_voice.launch.py`는 LLM node, TTS node, 웨이크워드 node, 청각 안내 node를
실행한다(2026-08-04 갱신). 개발용 RobotState·state-machine stub 과 중복
`vica_interfaces` 사본은 제거됐고, push-to-talk STT 는 launch 에서 빠졌다.

TTS는 STT·LLM·Mission Manager가 발행하는 `/vica/tts_request`를 우선순위 큐로 처리하고
`/vica/tts_state`를 발행한다. 재생은 워커 스레드에서 **문장 단위로 끊어** 돌며, 문장
사이마다 감시가 다시 열린다 — 한 덩어리가 길수록 사용자의 진짜 "멈춰"를 놓치는 구간이
길어지기 때문이다. 웨이크워드 node 는 이 신호로 재생 중 감시를 억제하고, 해제 신호를
놓쳐도 fail-safe 타임아웃으로 자동 재개한다. 코드·단위 테스트 계약은 연결됐고 실제
마이크·스피커 재생은 `[미검증]`이다.

청각 안내 node(`ros_audio_cue_node`)는 `/vica/turn_guide`와 `/vica_goal_event`를 구독해
회전·도착을 소리와 말로 알린다(2026-08-05). 안내음은 TTS 큐를 거치지 않으므로 줄을
서지 않고 `/vica/tts_state`도 켜지 않는다. 회전 문구는 축약하지 않고 매번 같은 문장을
쓴다 — 방향 안내는 안전과 직결되어 매번 같은 판단이 가능해야 한다.

음성 저장소 내부 토픽(팀 계약 아님): `/vica/wake`(호출 앵커, 계측용),
`/vica/sim/event`·`/vica/sim/reset`(`[SIM ONLY]`).

## 6. Mission Manager 아키텍처

Mission Manager는 음성 intent에서 Nav2 goal로 넘어가는 검증 관문이다.

### 6.1 gate

```text
intent navigate
AND matched id 존재
AND 사용자 확인 완료
AND safety flag normal
AND E-stop 비활성
AND 현재 주행 중 아님
AND 목적지 존재
AND 접근 가능
AND pose 유효
AND Nav2 준비
```

pose 검증은 다음을 포함한다.

- `frame_id == map`
- `(x, y) != (0, 0)`
- `calibrated != false`
- map bounds 안의 좌표

### 6.2 상태

```text
idle / confirming / navigating / arrived / failed / estopped
```

Mission Manager는 `vica_safety/emergency_stop_node`가 발행하는 `/emergency_stop` 중앙
래치만을 E-stop 상태 계약으로 사용한다. motor 소유 `/estop_state` 의존은 제거했다.
E-stop reset 뒤 이전 goal은 자동 재개하지 않는다.

### 6.3 현재 제약

- Mission Manager가 공개 UUID 요청 service와 음성 intent를 같은 gate로 처리한다.
- `vica_goto_goal.py`는 Mission service만 호출하며 NavigateToPose 권한이 없다.
- Mission Manager가 `/vica_goal_event`를 발행해 앱 상태 bridge와 연결한다.
- 이 경로의 실제 Nav2·Safety·motor 종단 동작은 `[미검증]`이다.

## 7. Nav2 아키텍처

### 7.1 bringup

`vica_nav2/launch/nav2_map_test.launch.py`는 `nav2_bringup/bringup_launch.py`를 다음과 같이 사용한다.

- `slam=False`
- 외부 map YAML 필수
- AMCL localization
- autostart 기본 true
- composition 기본 false

### 7.2 planner·controller·costmap

| 영역 | 현재 설정 |
| --- | --- |
| Global planner | `nav2_smac_planner/SmacPlanner2D` (2026-07-28 NavFn에서 교체) |
| Local controller | `dwb_core::DWBLocalPlanner` |
| DWB obstacle critic | `ObstacleFootprint` (scale 0.15). `BaseObstacle`은 원형 가정이라 부적합 |
| 최대 직선 속도 | 0.26 m/s |
| DWB 최대 회전 속도 | 0.4 rad/s |
| Goal 접근 속도 | 경로 잔여거리 3.0 m부터 직선·회전 최대속도의 70% |
| Goal tolerance | x/y 0.25 m, yaw 0.25 rad |
| Local costmap | `odom`, voxel(`/scan`) + nvblox slice + inflation |
| Global costmap | `map`, static + obstacle + inflation, `/scan` |
| Footprint | 전방 0.305 m, 후방 -0.60 m, 좌우 ±0.227 m, padding 0.05 (2026-07-27 실측) |
| inflation | `inflation_radius` 0.45, `cost_scaling_factor` 3.5 |

footprint는 2026-07-27 전방 좌측 범퍼 실충돌 뒤 `vica_description/meshes/base_link.stl`
실측으로 교정한 값이다. 구값(전방 0.15, 좌우 ±0.1875)은 실제 차체보다 전방 15.5 cm,
좌우 각 4 cm 작아 Nav2가 그만큼을 free 공간으로 오인했다.
`vica_nav2/test/test_footprint_contract.py`가 이 회귀를 감시한다.

여기서 파생되는 구조적 제약이 하나 있다. footprint 내접반경은 0.277 m인데
외접반경은 0.707 m로 **2.6배** 차이가 난다(핸들 때문에 차체가 0.905 m로 길다).
`SmacPlanner2D`는 중심 셀 비용만 보는 **점 로봇 planner**라 내접반경만 보장한다.
그래서 planner가 "통과 가능"으로 그린 자리에서 DWB의 `ObstacleFootprint`가
회전 궤적을 전부 거부해 로봇이 굳는 사례가 실측됐다(2026-07-29, `[GAP]`).

`nvblox_layer`는 local costmap `plugins`에 포함되며
`nvblox::nav2::NvbloxCostmapLayer`를 사용한다. slice 입력은
`/nvblox_node/static_map_slice`, frame은 local costmap과 같은 `odom`이다.
`vica_nvblox_bringup`이 Isaac ROS Docker의 D455·nvblox launch와 높이 override를
소유한다. Host에는 `nvblox_nav2`·`nvblox_msgs`가 로드 가능한 상태여야 하며,
dependency contract가 XML·library·message 존재를 검사한다. 실제 D455→slice→local
costmap→Goal 종단은 `[미검증]`이다.

### 7.3 Behavior Tree

사용자 정의 BT XML은 저장소에 없다. 현재 Nav2 기본 파일을 사용한다.

```text
nav2_bt_navigator/navigate_to_pose_w_replanning_and_recovery.xml
nav2_bt_navigator/navigate_through_poses_w_replanning_and_recovery.xml
```

복구 동작의 속도 명령은 `behavior_server`가 직접 발행한다. Nav2 humble
`navigation_launch.py`는 `controller_server`에만 `('cmd_vel', 'cmd_vel_nav')`를 주고
`behavior_server`에는 remap을 주지 않아, 기본 상태에서는 `/cmd_vel`로 나간다.
VICA에는 그 토픽 구독자가 없어 **복구 동작이 한 번도 로봇을 움직이지 못했다**
(2026-07-29 실측: `/cmd_vel` 발행자 5·구독자 0). `vica_nav2` launch에서 노드 지정
remap `behavior_server:cmd_vel:=/cmd_vel_req`로 Safety 경로에 연결했다.

접두사 없는 전역 `cmd_vel` remap은 쓰면 안 된다. launch_ros가 global remap을
node-level보다 먼저 붙이고 rcl은 첫 일치 규칙을 쓰므로, `controller_server`의
`cmd_vel:=cmd_vel_nav`를 덮어써 velocity_smoother를 건너뛴다.
`test_nav2_launch_contract.py`가 두 규칙을 함께 감시한다.

상세 BT와 Mission decision flow는 `bt와 visual hierarchy of your folders and files.md`에 정리한다.

## 8. Odometry·SLAM·TF

### 8.1 목표 TF ownership

```text
map                         Cartographer 또는 AMCL
└─ odom                     EKF
   └─ base_footprint
      └─ base_link          robot_state_publisher / URDF
         ├─ laser_frame
         └─ camera_link
```

- 저장 지도 주행: AMCL이 `map → odom`
- Cartographer SLAM: Cartographer가 `map → odom`
- EKF: `odom → base_footprint`
- URDF/RSP: `base_footprint → base_link → sensors`
- 동일 transform의 중복 publisher를 허용하지 않는다.

### 8.2 URDF 기준

현재 Xacro의 고정 센서 위치:

| frame | base_link 기준 |
| --- | --- |
| `laser_frame` | x=0.185, y=0, z=0.192 m |
| `camera_link` | x=0.28683, y=0, z=0.130 m |

`base_footprint → base_link` 높이는 0.19 m다.

현재 `/scan`을 발행하는 2D LiDAR는 YDLIDAR G2를 수리 보내 임시로 RPLIDAR를 사용한다
(2026-07-22 기준). 위 `laser_frame` 오프셋은 YDLIDAR G2 장착 기준이므로, RPLIDAR 운용
동안 실제 장착 위치를 실측해 URDF와 대조한다. `/scan` 토픽 계약 자체는 라이다와 무관하게
유지된다. [미검증]

### 8.3 현재 odometry 구현

```text
encoder_feedback
└─ /wheel/odom (raw, TF 미발행)
          │
          ├──────────────┐
          ▼              │
vica_localization        │
└─ robot_localization EKF│
   ├─ odom0: /wheel/odom │
   ├─ imu0: /imu/base_link ◀── D455 IMU frame adapter
   ├─ 출력 remap: /odom
   └─ TF: odom → base_footprint
          │
     ┌────┴─────────┐
     ▼              ▼
Cartographer/Nav2  App status
└─ /odom 입력      └─ /odom 구독
```

`vica_localization/launch/wheel_ekf.launch.py`는 `encoder_feedback`과 EKF를 실행하고
`odometry/filtered`를 `/odom`으로 remap한다. `encoder_feedback`의 TF 발행은 비활성화되어
EKF가 `odom → base_footprint`의 단일 authority가 된다.

Cartographer와 Nav2 launch는 `vica_localization` bringup을 포함하며 표준 `/odom`을 사용하도록
연결되어 있다. Cartographer 하위 launch의 `odom_topic` argument도 실제 remap에 적용된다.

정본 EKF 설정은 `vica_ros2_ws/src/vica_localization/config/ekf.yaml`이다. 기존 활성 설정
형식과 주석 처리된 VSLAM 대안 블록을 유지한 채 `odom0`만 `/wheel/odom`으로 정합화했다.

**호환용 사본은 2026-08-06에 삭제했다**(`b1e88f5`). WS 루트 `ekf_config/ekf.yaml`은 어떤
launch도 읽지 않으면서 `sensor_timeout 0.1`을 품고 있었다. 정본은 `/wheel/odom` 실효 주기가
9.45 Hz(105.8 ms)라 매 주기 timeout을 넘기던 문제를 고쳐 0.2로 올린 값이고,
`print_diagnostics` 항목도 없어 기본 true로 남아 실기에서 앱에 "주행 불가 · 위치추정 오류"로
뜨던 거짓 ERROR도 함께 되살아났다. 누가 `ekf_params_file:=`로 그 경로를 넘기면 조용히 두
버그로 돌아가므로 지웠다. **EKF 설정 정본은 하나뿐이다.** 로컬의 미추적 `src/ekf_config/`
사본은 팀 배포 범위에 포함하지 않는다.

2026-07-22 기준으로 관련 4개 패키지 빌드, EKF 계약 테스트 2건, EKF 노드 기동,
실제 로드 파라미터와 `/odom` 단일 publisher 생성까지 로컬 검증했다. 다만 개발 PC의
시스템 ROS 경로에는 `ros-humble-robot-localization`과 `python3-can`이 설치되어 있지
않다. 임시 추출한 공식 패키지로 수행한 기동 검증과 별도로 팀 환경에 의존성을 설치하고
깨끗한 workspace에서 다시 빌드·테스트해야 한다.

D455 launch는 현재 VICA 저장소 안에 없고 별도 Docker/Isaac ROS 환경이 센서를 실행한다.
`wheel_ekf.launch.py`는 IMU adapter를 시작하지 않으므로 `/imu/base_link`는 외부 실행
전제다. 실제 D455 토픽, adapter, TF와 C5 encoder를 함께 사용한 실기 융합은 아직
완료되지 않았다.

### 8.4 확정 odometry 계약

```text
encoder_feedback /wheel/odom
          │
          ▼
robot_localization EKF
          ├─ /odom
          └─ odom → base_footprint
               │
       ┌───────┴────────┐
       ▼                ▼
Cartographer/Nav2   App status
```

**확정(2026-07-22): raw wheel odometry는 `/wheel/odom`, IMU 입력은
`/imu/base_link`, EKF 최종 출력은 `/odom`으로 통일한다.** Nav2와 앱의 기존 consumer
수정을 최소화하기 위한 결정이며 과거 `/odom/ekf_filtered` 설계안은 폐기한다. EKF 실행과
설정 정본은 `vica_ros2_ws/src/vica_localization` 패키지가 소유한다.

## 9. 주행·안전 아키텍처

### 9.1 현재 구조

```text
Mission Manager
        ├─ NavigateToPose Goal
        └─ /speed_limit (잔여거리 3 m부터 70%)
                 ↓
Nav2 controller
        └─ /cmd_vel_nav
             └─ velocity_smoother
                  └─ /cmd_vel_req

Safety Supervisor
        ├─ /cmd_vel_req 구독
        └─ /cmd_vel_safe 발행
             └─ mdrobot_can_keyboard_knob_node
                  └─ CAN 0xCF → motor
```

`nav2_map_test.launch.py`는 Humble Nav2 velocity smoother의 원래 최종 출력
`cmd_vel_smoothed`만 `/cmd_vel_req`로 scope remap한다. controller의 내부
`/cmd_vel_nav` 연결은 유지되며 Safety Supervisor가 승인한 `/cmd_vel_safe`만 motor에
도달한다. 코드·정적 계약은 연결됐지만 Nav2 Goal부터 CAN motor까지의 실기 종단 동작은
아직 `[미검증]`이다. 시험 도구 `vica_goto_goal.py`의 별도 yaw 정렬과 `/cmd_vel`
발행은 제거했으며, 목적지 pose의 최종 방향 정렬은 Nav2가 담당한다.

Mission Manager는 Nav2 feedback의 양수 `distance_remaining`이 3.0 m 이하가 된 첫
시점에 `/speed_limit`으로 최대 직선·회전속도를 70%로 제한한다. 현재 DWB 설정 기준
0.182 m/s와 0.28 rad/s이며, 재계획으로 잔여거리가 늘어나도 해당 Goal이 끝날 때까지
유지한다. 성공·실패·취소·E-stop과 새 Goal 시작 시 `speed_limit=0.0`으로 제한을
해제한다. 이 경로의 실제 Goal·Safety·motor 종단 동작은 `[미검증]`이다.

motor node는 MDROBOT F1 I/O 모니터의 knob(스마트핸들 가변저항) 값으로 주행 속도를
보정한다(보행 속도 추종, 현재 구현됨). F1이 `knob_timeout_sec` 안에 수신되지 않으면
knob 0으로 처리되어 정지한다.

motor node는 CAN 객체 생성과 모터 명령 송신 전에 `can_iface`의 Linux `IFF_UP` 상태를
읽기 전용으로 검사한다. 인터페이스가 없거나 DOWN이면 `[MOTOR START BLOCKED]` 오류와 함께
시작을 거부하며 CAN을 자동으로 UP하거나 bitrate를 바꾸지 않는다. CAN 설정은 motor,
encoder와 물리 E-stop 입력이 공유하므로 상위 시스템 인프라가 먼저 준비한다.

### 9.2 목표 구조

```text
Nav2 controller / 승인된 teleop
        │
        ▼
velocity smoother / collision monitor
        │ 최종 요청
        ▼
/cmd_vel_req
        │
        ▼
safety_supervisor_node
  - E-stop freshness
  - command timeout
  - 속도 상한
  - 향후 Handle/CAN/sensor health
        │
        ▼
/cmd_vel_safe
        │
        ▼
MDROBOT motor adapter
        │
        ▼
CAN + driver watchdog + physical E-stop
```

Safety Supervisor 뒤에 velocity smoother를 두면 smoother가 새로운 비영(0이 아닌) 값을 만들 가능성이 있다. 최종 Safety 출력 뒤에는 속도를 변형하는 노드를 두지 않는다.

E-stop 입력은 Safety가 각각 직접 구독하지 않고 `emergency_stop_node` 한 곳에서
통합·래치한 `/emergency_stop`만 구독한다. 입력별 우회 경로를 추가하지 않는다.

### 9.3 Safety 상태

현재 Safety Supervisor 상태:

```text
IDLE
RUNNING
ESTOP_ACTIVE
ESTOP_RELEASED_WAIT_RESET
READY_TO_GO
FAULT
```

다음 조건에서 출력은 0이다.

- E-stop active
- `/emergency_stop` stale
- `/cmd_vel_req` timeout
- reset 미완료
- 입력 명령이 0
- FAULT

### 9.4 motor 방어

현재 motor node가 가진 방어는 다음과 같다.

- `/cmd_vel_safe`만 구독
- `/cmd_vel_safe` command timeout 시 0 RPM
- F1 knob timeout 시 속도 비율 0
- knob 비율 기반 속도 제한과 최대 RPM 제한

motor node에는 E-stop 래치, `/estop_state`, `/estop_reset`을 두지 않는 것이 확정된
목표 구조다. E-stop 상태 통합과 래치는 `emergency_stop_node`, 주행 허용 판단은
Safety Supervisor가 소유한다. CAN 0 RPM만으로 인명 안전을 보장하지 않으므로 물리
전원·토크 차단 E-stop은 별도로 필요하다.

### 9.5 reset 권한과 현재 계약

`vica_safety`는 reset을 세 권한으로 분리한다.

| 인터페이스 | 소유자 | 규칙 |
| --- | --- | --- |
| `/app_estop_reset` | `app_emergency_node` | Flutter용 공개 오케스트레이션 진입점 |
| `/safety_reset` | `app_emergency_node` | 영구 유지보수 진입점, 앱과 같은 절차이며 호출자 인증 `[GAP]` |
| `/vica_safety/internal/estop_reset` | `emergency_stop_node` | 모든 원인 해제와 물리 F1 freshness 확인 뒤 중앙 래치만 해제 |
| `/vica_safety/internal/supervisor_reset` | `safety_supervisor_node` | fresh `/emergency_stop=false`와 `/cmd_vel_req=0` 또는 timeout 확인 뒤 재승인 |

`app_emergency_node`는 앱 source를 false로 내리고 Nav2 action status의 마지막 상태값을
확인한다. accepted, executing 또는 canceling Goal이면 전체 취소를 요청하고, 취소 요청
이후의 새 terminal 상태를 확인한다. 마지막 상태가 terminal이면 취소 서비스를 호출하지
않는다. Nav2 status 수신 이력이 없으면 Goal이 한 번도 생성되지 않은 정상 상태로 판정해
Goal 검사를 생략하며, action server도 없으면 Nav2 미실행으로 구분한다. action status는
주기 heartbeat가 아닌 상태 변경 이벤트이므로 메시지 나이는 reset 조건으로 사용하지
않는다. 그 뒤 중앙 래치 reset, fresh
`/emergency_stop=false`, Supervisor 내부 reset,
`/safety_state=READY_TO_GO`를 순서대로 확인한다. 어느 단계든 실패하면 다음 단계로
진행하지 않는다. 앱이나 STT의 `false`는 입력 원인 해제일 뿐 reset이 아니며 이전 Goal은
자동 재개하지 않는다.

관리자 앱 인증은 아직 구현되지 않았다. `/safety_reset`의 `Trigger` 요청에도 호출자
신원이 없으므로 현재는 `[GAP]`이며, 이후 SROS2·로컬 shell 권한·네트워크 ACL을 검토한다.

### 9.6 E-stop 중앙 래치 현재 계약

```text
MDROBOT F1 물리 버튼 상태 ─┐
앱 /app_emergency_stop ─────┼→ emergency_stop_node
STT /voice_emergency_stop ──┘   ├─ source 상태·freshness 관리
                                ├─ 하나라도 true면 중앙 latch
                                ├─ /emergency_stop 주기 발행
                                └─ internal/estop_reset
                                           │
                         ┌─────────────────┴────────────────┐
                         ▼                                  ▼
                 Mission Manager                    Safety Supervisor
                 Goal 취소·재개 금지                /cmd_vel_safe=0
```

| 입력 | 활성 의미 | 비활성 의미 | reset 권한 |
| --- | --- | --- | --- |
| 물리 CAN F1 | 버튼 눌림 또는 입력 상실 fail-safe | 버튼이 실제 해제되고 상태가 fresh함 | 없음 |
| 앱 Bool | 관리자가 E-stop 활성 요청 | 앱 입력 원인 해제 | 없음 |
| STT Bool | 긴급어 감지 펄스 | 펄스 종료 | 없음 |
| 앱·유지보수 reset | 해당 없음 | app_emergency_node의 전체 절차 시작 | 공개 오케스트레이터만 호출 |

`false` 입력은 중앙 래치를 직접 끄지 않는다. `emergency_stop_node`가 reset 요청을
수락하려면 모든 입력이 비활성이고 물리 F1이 fresh해야 한다. Nav2 활성 Goal 확인과
필요한 경우의 전체 취소는 `app_emergency_node`, 요청 속도 0 또는 stale 확인은
`safety_supervisor_node`가 책임진다. 코드·launch·단위 테스트는
구현됐지만 CAN·Nav2·motor를 함께 사용한 실기 종단 동작은 `[미검증]`이다.

## 10. Supervisor 앱 아키텍처

### 10.1 Flutter 역할

- rosbridge WebSocket 연결
- 지도·장소 조회와 좌표 저장
- `/robot_status` 기반 로봇 상태 표시
- `/robot/health`·`/robot/events` 기반 세부 결함 표시(시스템 진단 화면, 대시보드 배너)
- `/app_estop_state` 기반 앱 E-stop 표시
- E-stop activate/reset service 호출
- 진행 중 안내의 취소·일시정지·재개 요청(`MissionCommand` service 3종)
- 연결·오류·E-stop·장소 관리 로그
- 목표: IDLE(사용자 미이용) 한정 원격 목적지 요청 — 앱 장소 선택을 Mission Manager 경유로 전달(`vica_scenario.md` 10.5절). 수동 teleop은 범위 제외.

앱은 안전 계층이나 motor path를 우회하지 않는다. 원격 목적지 요청도 Mission Manager gate와 안전 계층을 거친다.

앱은 요청 가능 여부를 스스로 판정하지 않는다. 앱이 가진 장소 정보는 마지막으로 받아온
사본이라 최신이 아닐 수 있어, 권한·접근성·Safety·Nav2 검증은 `vica_goto_goal`, LLM과
동일하게 Mission Manager가 담당한다. 앱은 요청을 보내고 `accepted`와 `message`만 표시한다.

### 10.2 현재 로그인 상태

Flutter source에는 `AuthGate`, `LoginScreen`, `AuthProvider`와 로컬 관리자 계정 설정이
있다. 앱은 저장된 로그인 상태에 따라 로그인 화면과 `SupervisorShell`을 분기하고
로그아웃 시 상태를 삭제한다. 신규 회원가입과 복잡한 역할 관리는 범위 밖이다.

이 로그인은 앱 진입 제어이며 ROS service에 호출자 신원을 전달하지 않는다. 따라서
`/app_estop_reset`과 `/safety_reset`의 관리자 인증·접근 통제는 여전히 `[GAP]`이다.

### 10.3 상태 bridge

`vica_status_app_node.py`는 다음 정보를 `/robot_status` JSON으로 요약한다.

- TF `map → base_footprint` 기반 x/y/yaw
- `/odom` twist와 fallback pose
- `/diagnostics` 오류
- `/vica_goal_event` 목적지 상태
- map ID와 가까운 저장 장소명

상태 우선순위는 오류 → 위치 미확보 → goal/속도 기반 moving → waiting이다.
일시정지는 `status="waiting"`과 `waiting_reason="일시정지"`로 표현하며, 재개할 목적지를
앱이 보여줄 수 있도록 `current_goal`을 유지한다.

Mission Manager가 `/vica_goal_event`를 발행하도록 연결했으며 앱 표시 runtime은
`[미검증]`이다.

구독 입력은 모두 monotonic 기준 만료를 적용한다. `/diagnostics`는 여러 노드가 함께 쓰는
공용 topic이고 각 메시지가 그 발행자의 상태만 담으므로, 마지막 메시지 하나만 보관하면
ERROR 발행자와 정상 발행자가 번갈아 도착할 때 오류 표시가 깜빡인다. 항목별로 누적하고
확정·해제에 지연을 둔다.

이 깜빡임 결함의 근본 해소는 판정 지점을 하나로 모으는 것이다. `robot_health_monitor_node`
가 항목별 누적과 전이 판정을 전담하고, 앱 브리지는 그 결과를 받는다. 전환은
`error_source` 파라미터로 감싼다.

| `error_source` | 오류 판정 입력 | 상태 |
| --- | --- | --- |
| `diagnostics`(기본) | 기존 `/diagnostics` 직접 파싱 | `[CURRENT]` |
| `health` | `/robot/health`의 `highest_severity >= STOP` | 코드 구현, 실기 `[미검증]` |

기본값이 현재 동작이므로 패키지를 빌드해도 거동이 바뀌지 않는다. 실기에서 파라미터
한 줄로 A/B한 뒤 기본값을 `health`로 바꾸는 것은 **별도 커밋**으로 한다. 롤백 단위가
커밋이 아니라 파라미터다.

`/robot_status` JSON 스키마는 바꾸지 않는다. 세부 결함 표시는 앱이 `/robot/health`·
`/robot/events`를 rosbridge로 **직접** 구독해 담당하며 이 노드를 거치지 않는다.

### 10.3.1 안내 취소·일시정지·재개

E-stop과 성격이 다른 별도 경로다. 안전 사건이 아니라 목표 조작이므로 래치와 reset이 없다.

| 구분 | 취소·일시정지 | E-stop |
| --- | --- | --- |
| 목적 | 목표 철회 | 위험 차단 |
| 정지 방식 | goal 취소 후 `velocity_smoother` 감속 램프 | `/cmd_vel_safe=0` 강제 |
| 래치 | 없음 | 중앙 래치 |
| 해제 | 불필요 | 관리자 reset |
| 이후 상태 | `IDLE` 또는 `PAUSED` | `ESTOPPED` |

Mission Manager는 `cancelTask()`로 `NavigateToPose` goal을 취소할 뿐 감속을 지시하지
않는다. 취소되면 `controller_server`가 `/cmd_vel` 발행을 멈추고, 그 뒤를
`velocity_smoother`가 `max_decel`(현재 `[-1.0, 0.0, -3.2]`) 기울기로 0까지 이어 붙여
감속 램프를 만든다. 이 값은 도착·취소·controller 정지에 전역 적용되며 `[미검증]`
트레이드오프로 남아 있어 실기에서 확정한다.

직선 감속은 2026-08-01에 `-2.5`에서 `-1.0`으로 완화했다. 시각장애인이 핸들을 잡고
걷기 때문에 정지 순간의 충격이 곧 안전이라는 판단이며, 대가로 감속 구간 이동이
1.35 cm에서 3.38 cm로 늘었다. `footprint_padding` 0.05 m가 이를 덮는다
(`vica_nav2/config/nav2_params.yaml`의 `velocity_smoother` 주석).
회전(`-3.2`)은 승차감이 아니라 조향 권한이므로 DWB와 정합시킨 값 그대로 둔다.

`max_velocity`가 `[0.26, 0.0, 1.0]`이므로 이 감속률에서 정지까지 약 0.26초, 0.0338 m다.
즉 감속 램프와 즉시 정지의 물리적 차이가 매우 작다. 사용자에게 "천천히 멈춘다"를 제공해야
하는 상황에서는 감속률이 아니라 정지 전 유예 시간으로 설계한다
(`vica_scenario.md` 2-1.2절).

감속 램프도 명령이므로 Safety Supervisor의 freshness 판정에는 살아 있는 명령으로 보인다.
따라서 `velocity_smoother.velocity_timeout`(0.4 s)은 `safety_supervisor_node`의
`cmd_timeout_sec`(0.5 s)보다 짧게 유지해야 하며,
`vica_nav2/test/test_nav2_params_contract.py`가 이 관계를 강제한다. 비상정지는 이 경로를
타지 않고 Safety가 `/cmd_vel_safe=0`을 직접 강제한다.

일시정지는 Nav2 goal을 취소하되 목적지를 `MissionLogic.paused_destination`에 보관하고,
재개 요청 시 그 목적지로 새 goal을 만든다. E-stop이 활성화되면 보관분을 폐기해
"E-stop 해제 후 이전 Goal을 자동 재개하지 않는다"는 원칙을 유지한다.

요청 주체는 앱(`MissionCommand` service)과 음성(`VicaIntent.intent`의
`cancel`/`pause`/`resume`)이며 둘 다 같은 게이트를 통과한다. 음성 취소는 오인식 시
안내가 끊기므로 Mission Manager가 되물어 확인한 뒤에만 실제로 취소하고, 확인을
기다리는 동안 주행은 계속한다. 앱은 관리자 로그인과 확인 대화상자를 거치므로 재확인이 없다.

### 10.4 앱 E-stop bridge

`app_emergency_node`는 `vica_safety` 패키지의 공개 reset 오케스트레이터다.

```text
Flutter
├─ /app_estop_activate Trigger
├─ /app_estop_reset Trigger
└─ /app_estop_state JSON 구독
          │
          ▼
app_emergency_node
├─ /app_emergency_stop Bool
├─ NavigateToPose 전체 goal 취소
├─ /vica_safety/internal/estop_reset
├─ /vica_safety/internal/supervisor_reset
└─ /app_estop_state 중앙 통합 상태 JSON
```

이 node는 `ros2 launch vica_safety safety_bringup.launch.py`에 포함된다.
`/app_estop_state`의 기존 `active` key는 유지하면서 중앙 `/emergency_stop`을 표시한다.
관리자 인증은 아직 `[GAP]`이며 Flutter의 `/app_estop_reset`과 터미널 `/safety_reset`은
동일한 안전 절차를 호출한다.

### 10.5 저장소 경계 목표

Flutter client는 `VICA_Supervisor/`에 유지한다. `VICA_Supervisor/ros2/`의 상태·지도·장소·
Goal 보조 노드는 로봇에서 실행되는 코드이므로 장기적으로
`vica_ros2_ws/src/vica_supervisor_bridge/` 같은 ROS 패키지로 이동하는 것이 목표다.
현재는 파일 이동이 승인되지 않았으므로 기존 위치를 `[CURRENT]`, 이동안을 `[TARGET]`으로
관리한다.

## 11. 목적지·지도 데이터

| 데이터 | 현재 위치 | 용도 |
| --- | --- | --- |
| 목적지 정본 | `~/vica_data/destinations/<map_id>/destinations.yaml` | UUID, 이름, alias, 권한, 접근성, pose |
| 지도 | `vica_ros2_ws/maps/*.yaml`, 이미지 | Nav2, 앱 표시 |

앱과 ROS Bridge 사이 전송은 JSON을 유지하지만 영구 저장은 지도별 YAML 하나다.
기존 `locations.json`은 이관하지 않는다. Mission Manager는 UUID 존재, 현재 map ID,
`public`, 접근 가능, pose, E-stop과 Nav2 준비 상태를 다시 검사한다.

## 12. Smart Handle·LED 목표 아키텍처

현재 ROS 구현은 없다. 다음 구조를 목표로 한다.
(리코일 기반 보행 속도 추종은 별개로 motor node에 이미 구현되어 있다 — 9.1절.)

```text
[1단계] EKF odometry yaw 변화량   [2단계·추후] Nav2 global path + TF
          │                               │
          └──────────────┬────────────────┘
                         ▼
                turn_guide_node
                  - 1단계: yaw 변화량 기반 LEFT/RIGHT 감지
                  - 2단계: path look-ahead 사전 예고(PREPARE/NOW/COMPLETE)
                  - debounce/hysteresis
                  - sequence/timeout
                         │ TurnGuide
                         ▼
                user_guidance_driver_node
                  ├─ 좌·우 방향 LED (회전 시 해당 방향 황색 점멸)
                  ├─ 기본 상태 LED (직진 시 파란색 점멸)
                  ├─ Smart Handle 서보 (좌·우 촉각 안내)
                  ├─ 비상 햅틱 (Safety 상태 직접 구독)
                  └─ diagnostics
                         │
                         ▼
                아두이노 나노 (서보·LED·햅틱 실제 구동, heartbeat 프로토콜 없음)
```

권장 메시지:

### `TurnGuide`

```text
direction: NONE | LEFT | RIGHT
phase: IDLE | PREPARE | NOW | COMPLETE | CANCELED
distance_m
turn_angle_deg
sequence_id
valid_until
```

### `SmartHandleState`

```text
connected          # Jetson-아두이노 나노 통신 상태 (heartbeat 프로토콜 없이 포트/전송 실패로 판정)
user_contact
servo_ok
left_led_ok
right_led_ok
haptic_ok
fault_code
stamp
```

### 원칙

- 같은 cue로 LED와 서보를 동기화한다.
- 서보는 조향 장치가 아니다.
- 회전 판단은 raw `/cmd_vel.angular.z`를 쓰지 않는다. 1단계는 EKF odometry yaw
  변화량, 2단계는 Nav2 path look-ahead를 사용한다.
- 서보·LED·햅틱은 핸들의 아두이노 나노가 구동하며 heartbeat 프로토콜은 사용하지 않는다.
- 햅틱은 비상상황 알림 전용이며 Safety 상태를 직접 구독한다. 모터 정지 성공 여부를
  대신 보장하지 않는다.
- stale cue는 재실행하지 않는다.
- E-stop, Mission 종료, node timeout 시 LED 기본 상태(파란색 점멸)와 서보 중립을 기본으로 한다.
- 비상 표시(햅틱·LED)는 방향지시 황색 점멸·직진 파란색 점멸과 명확히 구분한다.
- 리코일 기반 보행 속도 추종은 guidance 계층이 아니라 motor node의 knob 속도 보정으로
  이미 구현되어 있다(9.1절).

## 13. 상태 감시 아키텍처

설계 배경과 미확정 항목은 [`vica_system_health_monitoring_draft.md`](vica_system_health_monitoring_draft.md)가
정본이다. 이 절은 확정된 계약과 **관측 범위 경계**만 담는다.

### 13.1 두 경로 분리

```text
[진단성 정보]  motor node · external_diagnostics_node · health monitor 자신
                     └─ /diagnostics ─→ diagnostic_aggregator ─→ /diagnostics_agg ─┐
                                                                                   │
[안전 신호]    /emergency_stop · /safety_state · TF map→base_footprint ────────────┤
               /bt_navigator/get_state 폴링 · /vica/robot_state                     ▼
                                                            robot_health_monitor_node
                                                                       ▼
                                                    /robot/health + /robot/events
                                                                       ▼
                                                          rosbridge ─→ Flutter
```

안전 신호는 aggregator를 거치지 않는다. `diagnostic_aggregator`는 기본 1 Hz로 집계하므로
E-stop 표시가 최대 1초 늦는다. **진단성 정보는 표준 체인, 안전 상태는 직접 입력**이 이
설계의 뼈대다.

`robot_health_monitor_node`는 Safety Supervisor를 대체하지 않으며 모터 정지 경로에 들어가지
않는다. 모니터가 죽어도 `/cmd_vel_req → Safety → /cmd_vel_safe → CAN` 경로는 그대로 동작한다.

### 13.2 어댑터를 두는 이유

`rplidar_ros`, nvblox(Docker), D455는 외부 패키지라 `/diagnostics`를 내지 않고 코드를 고칠
수도 없다. `external_diagnostics_node`가 그 대상을 **대신해** 진단을 발행하므로 외부 대상도
우리 노드와 같은 경로로 흐른다.

부수 효과가 중요하다 — `nvblox_msgs` 같은 외부 타입 의존이 어댑터 프로세스에만 갇힌다.
모니터는 센서 메시지 타입을 전혀 import하지 않고, 어댑터가 죽어도 모니터는 살아 있다.

감시 도구가 스스로 오탐을 만들 수 있다는 점이 이 어댑터의 최대 위험이다. `/scan`을
RELIABLE로 구독하면 rplidar가 sensor_data(BEST_EFFORT)로 발행할 때 QoS 비호환으로 한 건도
받지 못해 `LIDAR_SCAN_STALE`이 영구 오탐된다. 따라서 구독 QoS를 `probes.yaml`에 두고
실기 `ros2 topic info -v`로 확정하며, 어댑터는 "구독자는 붙었는데 메시지가 0건"을 진단
message에 구분해 남긴다.

### 13.3 관측 범위와 사각지대

**"health가 정상이라고 했는데 왜 못 잡았나"를 구조적으로 막기 위해 경계를 문서에 고정한다.**
어댑터가 대신 발행할 수 있는 것은 토픽과 `/proc`으로 이미 나오는 것뿐이다. 노드 내부 상태는
그 노드를 수정하지 않으면 원리적으로 볼 수 없다.

관측하는 것:

| 신호 | 방법 |
| --- | --- |
| 모터 CAN 링크·cmd/knob age | motor node의 기존 `/diagnostics` |
| `/scan` 주기 | 어댑터 topic_rate |
| nvblox slice age·Hz | 어댑터 topic_rate |
| depth·color `camera_info` 주기 | 어댑터 topic_rate |
| `/odom` 실효 Hz (= EKF 실효 주기) | 어댑터 topic_rate |
| `/wheel/odom` 미발행 | 어댑터 topic_rate |
| 노드별 프로세스 CPU % | 어댑터 process_cpu (`/proc`) |
| E-stop 래치·`/safety_state` | 모니터 직접 구독 |
| TF `map→base_footprint` age | 모니터 직접 tf2 |
| Nav2 lifecycle 상태 | 모니터 `GetState` 폴링 |

관측하지 **못하는** 것:

| 신호 | 왜 불가 | 실제 위험 |
| --- | --- | --- |
| 마이크 무입력 | 오디오 콜백 내부 | **긴급어 감시가 조용히 멈춘다** |
| 긴급 감시 실효 hop·창 건너뜀 | 카운터가 아예 없다 | 긴급어 사각지대 확대 |
| STT/TTS CPU 폴백 여부 | 노드 내부 변수, `print`로만 나감 | 폴백 시 지연 3.7배·10배 |
| 목적지 카탈로그 부재 | warn 로그 한 줄. 간접 추정만 | 모든 안내가 `unknown_destination` |
| Smart Handle 서보·LED·햅틱 실동작 | 상향 통신 경로 자체가 없다(12절) | readiness가 `UNKNOWN`으로 남는다 |

카메라는 원본 `image`가 아니라 `camera_info`를 구독한다. 같은 주기지만 수백 바이트다.
30 Hz depth 프레임을 복사하면 감시 노드가 대역폭 소비자가 된다.

### 13.4 임계값과 확장 규율

- **임계값과 기대 토픽 목록을 코드에 두지 않는다.** 전부 YAML이다. `probes.yaml`(수집
  대상·기대 주기·구독 QoS), `diagnostic_aggregator.yaml`(분류·`timeout`·`expected`),
  `required_components.yaml`(필수 여부·severity). timeout은 aggregator yaml만 소유한다 —
  두 곳에 두면 어느 쪽이 이기는지 모호해진다.
- **토픽 부재를 자동으로 fault로 만들지 않는다.** `publish_voxel_map: False`나 `backup`
  behavior 제거처럼 토픽이 사라지는 것이 정상 변경일 수 있다. 부재 판정은 반드시 YAML의
  `required` 플래그를 거친다.
- **계약 테스트가 4파일의 이름 집합 일치를 강제한다.** 오타로 감시가 조용히 빠지는 것을
  막는다. `vica_nav2/test/test_nav2_params_contract.py`와 같은 패턴이다.
- **다른 노드에 진단을 추가할 때 모니터 코드를 고치지 않는다.** aggregator yaml에 항목만
  추가하면 `DIAG_COMPONENT_ERROR`/`WARN`/`STALE` 통로로 앱까지 표시된다. 표준 체인을 먼저
  깔아 두는 가장 큰 이유가 이것이다.
- 진단 발행자 확대 우선순위는 초안 17절 1단계 표를 따른다. 1위가 마이크 무입력이다.
  `safety_supervisor_node`·`emergency_stop_node` 수정은 E-stop 경로 전체 실기 재검증을
  요구하므로 마지막이다.

### 13.5 자동 복구는 범위 밖

이 계층은 **관측과 보고만** 한다. `recovery_policy.yaml`과 자동 재시도는 초안 11절의
`[TARGET]`으로 남는다. nvblox slice가 stale일 때 Mission을 취소하는 방어도 아직 없다 —
감지는 구현했으나 방어는 유령 장애물 진단이 끝난 뒤 결정한다
(`devlog/2026-07-30-nvblox-ghost-obstacle.md` 12절).

## 14. 현재 주요 위험과 우선순위

| 우선순위 | 문제 | 조치 |
| --- | --- | --- |
| P0 | Nav2→Safety 속도 경로 실기 종단 미검증 | `/cmd_vel_req → /cmd_vel_safe → CAN`을 바퀴를 띄운 HIL에서 검증 |
| P0 | E-stop/reset 코드의 실기 종단 검증이 없음 | 바퀴를 띄운 HIL에서 F1·앱·음성·Nav2·motor fail-closed 검증 |
| P0 | localization 런타임 의존성 미설치 | `robot_localization`, `python3-can` 설치 후 깨끗한 환경에서 전체 build/test |
| P0 | wheel+IMU 실기 융합 미검증 | C5, D455 adapter, `/odom`과 TF 단일 authority를 HIL에서 검증 |
| P0 | `vica_safety`의 `can_f1` launch가 실기 미검증 | `can1`·`0x701`·F1 freshness를 읽기 우선으로 검증 |
| P1 | Mission·앱·CLI 경로의 runtime 미검증 | 공개 Mission service와 `/vica_goal_event` 종단 검증 |
| P1 | nvblox local costmap 종단 미검증 | Host plugin·Docker slice·Nav2 Goal을 함께 검증 |
| P1 | 통합 음성 출력 미검증 | `/vica/tts_request` 우선순위와 실제 마이크·스피커 검증 |
| P1 | 앱 Mission 상세 상태 미연결 | 공통 mission status 계약 정의 |
| P1 | 목적지 통합 runtime 미검증 | 지도별 YAML 저장·reload·음성 검색을 함께 검증 |
| P1 | 상태 감시 임계값이 전부 실측 없이 정해져 있음 | Jetson에서 QoS·주기·CPU를 실측해 확정. 확정 전 결함 표시를 판정 근거로 쓰지 않는다(13.4절) |
| P1 | 긴급어 감시의 마이크 무입력이 관측 불가 | 상시 감시 노드(`wakeword_monitor.py`, 롤백 경로는 `emergency_monitor.py`)에 무입력 카운터와 진단 발행 추가(13.3절 표) |
| P2 | Smart Handle 안내 미구현 | 메시지 → mock → bench → HIL 순서 구현 |

## 15. 권장 통합 순서

1. 현재 토픽과 TF를 rosbag/읽기 전용 명령으로 확인한다.
2. localization 의존성을 설치하고 확정된 `/wheel/odom + /imu/base_link → EKF → /odom` 계약을 깨끗한 환경에서 재검증한다.
3. Nav2 `/cmd_vel_req` remap의 일반·composition 모드와 실기 종단 동작을 검증한다.
4. motor가 `/cmd_vel_safe`만 받는 현재 계약을 build/runtime에서 검증한다.
5. `vica_safety`의 중앙 래치와 reset 오케스트레이션을 package build/test한다.
6. 물리·음성·앱 E-stop과 유지보수 `/safety_reset`을 바퀴를 띄운 상태에서 종단 검증한다.
7. Host nvblox plugin과 Docker slice를 local costmap에 연결해 Goal을 검증한다.
8. 통합 음성 launch와 `/vica/tts_request` 실제 재생을 검증한다.
9. 앱 Mission 상태와 목적지 데이터 계약을 runtime에서 검증한다.
10. Turn Guide 순수 로직과 mock driver를 구현한다.
11. 서보·LED MCU bench test를 수행한다.
12. 전체 HIL 뒤 제한 구역 저속 주행을 수행한다.

## 16. 공식 참고자료

전체 공식 URL 목록과 버전 주의사항은 별도 유지 문서인 [`official_reference_urls.md`](official_reference_urls.md)를 기준으로 한다.

적용 원칙:

- ROS2는 Ubuntu 22.04 + Humble 기준
- Nav2 최신 문서의 파라미터를 그대로 복사하지 않고 Humble branch와 비교
- Isaac ROS는 Humble/JetPack 6.x 호환을 위해 release 3.2 문서 우선
- NVIDIA, Nav2, ROS 공식 예제보다 VICA의 안전 권한 경계를 우선
- MDROBOT CAN frame과 E-stop 동작은 `source_file`의 실제 하드웨어 매뉴얼 및 실측 결과로 검증
