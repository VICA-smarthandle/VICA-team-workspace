# VICA 통합 아키텍처

작성 기준일: 2026-07-22
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
| `vica-voice-llm/` | `main` | STT, TTS, 긴급어 감지, LLM 목적지 해석 |
| `VICA_Supervisor/` | `main` | Flutter 운영 앱, rosbridge, 상태·지도·장소 관리 |
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

`vica_ros2_ws/src`에서 `colcon list`로 확인되는 ROS 패키지는 현재 9개다.

| 패키지 | 역할 |
| --- | --- |
| `encoder_feedback` | MDROBOT C5 위치 피드백을 wheel odometry로 변환 |
| `mdrobot_can_control` | CAN motor, E-stop, Safety Supervisor, 앱 E-stop bridge |
| `vica_cartographer` | Cartographer 2D 설정과 SLAM launch |
| `vica_description` | URDF/Xacro, mesh, robot_state_publisher launch |
| `vica_interfaces` | `VicaIntent`, `RobotState`, `EmergencyEvent` 메시지 |
| `vica_localization` | wheel odometry와 IMU를 `robot_localization` EKF로 융합하고 표준 `/odom` 제공 |
| `vica_mission_manager` | 목적지 gate, Mission 상태, Nav2 goal, 음성 E-stop bridge |
| `vica_nav2` | 저장 지도 기반 Nav2 bringup과 parameter |
| `vica_sensor_adapters` | IMU frame 변환, VSLAM covariance adapter |

현재 `vica_user_guidance`, `vica_exploration`, 별도 `vica_safety` 패키지는 존재하지 않는다.

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
│ 현재 기본 속도 출력: /cmd_vel                        │
└────────────────────────┬─────────────────────────────┘
                         │ remap 없음 [GAP]
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

앱은 rosbridge를 통해 상태 topic과 관리 topic을 사용한다. 앱의 일반 UI는 Nav2 action과 `/tf`를 직접 처리하지 않지만, 별도 시험 도구인 `vica_goto_goal.py`는 NavigateToPose를 직접 발행한다.

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

### 4.2 핵심 topic·service·action

| 인터페이스 | 타입 | 현재 producer | 현재 consumer | 상태 |
| --- | --- | --- | --- | --- |
| `/vica/user_text` | `std_msgs/String` | STT | LLM node | 연결됨 |
| `/vica/intent` | `VicaIntent` | LLM node | TTS, Mission Manager, 개발 stub | 운영 stub 중복 주의 |
| `/vica/emergency` | `EmergencyEvent` | 긴급어 감시 | Mission Manager, E-stop bridge, 개발 stub | 연결됨 |
| `/vica/robot_state` | `RobotState` | Mission Manager, 개발 stub | LLM node | 운영 stub 중복 주의 |
| `/vica/tts_request` | `std_msgs/String` | Mission Manager | 없음 | 통합 gap |
| `/voice_emergency_stop` | `std_msgs/Bool` | emergency bridge | emergency_stop_node | 연결 가능 |
| `/app_emergency_stop` | `std_msgs/Bool` | app_emergency_node | emergency_stop_node | 연결 가능 |
| `/emergency_stop` | `std_msgs/Bool` | emergency_stop_node | Safety, Mission | 전달 구현, 중앙 래치 미구현 |
| `/estop_state` | `std_msgs/Bool` | producer 없음 | Mission | 이전 motor 래치 계약 잔재 `[GAP]` |
| `/safety_state` | `std_msgs/String` | Safety Supervisor | 운영 UI consumer 없음 | 부분 연결 |
| `/cmd_vel` | `Twist` | Nav2 / test tool | 안전 운영 consumer 없음 | `/cmd_vel_req` remap 필요 |
| `/cmd_vel_req` | `Twist` | 연결된 producer 없음 | Safety Supervisor | 통합 gap |
| `/cmd_vel_safe` | `Twist` | Safety Supervisor | motor | 코드상 연결, launch/runtime 검증 필요 |
| `/wheel/odom` | `nav_msgs/Odometry` | encoder_feedback | `robot_localization` EKF | 코드·설정·launch 연결 및 로컬 기동 검증 완료, 실기 검증 필요 |
| `/imu/base_link` | `sensor_msgs/Imu` | IMU frame adapter | `robot_localization` EKF | D455 실행 환경의 실제 입력 연결 검증 필요 |
| `/odom` | `nav_msgs/Odometry` | `robot_localization` EKF | Cartographer, Nav2, 앱 상태 | 표준 출력 계약 및 launch 연결 완료, 실기 검증 필요 |
| `/navigate_to_pose` | Nav2 action | Mission Manager, `vica_goto_goal.py` | Nav2 | 권한 중복 |
| `/app_estop_activate` | `Trigger` | Flutter client | app_emergency_node | 별도 node 실행 필요 |
| `/app_estop_reset` | `Trigger` | Flutter client | app_emergency_node | 존재하나 호출 대상 계약이 오래됨 |
| `/estop_reset` | `Trigger` | app_emergency_node client | server 없음 | emergency_stop_node 중앙 reset으로 구현 목표 |
| `/safety_reset` | `Trigger` | 통합 client 없음 | Safety Supervisor | 통합 gap |
| `/robot_status` | JSON `String` | status app node | Flutter | 연결 가능 |
| `/app_estop_state` | JSON `String` | app emergency node | Flutter | 앱 E-stop 상태 전용 |

## 5. Voice·LLM 아키텍처

### 5.1 정상 발화

```text
ros_stt_node
  └─ /vica/user_text
      └─ ros_node
          ├─ /vica/robot_state 구독
          ├─ LangChain + Ollama Cloud/Local
          ├─ destination_matcher 코드 검증
          └─ /vica/intent
```

LLM backend는 환경변수로 선택한다.

- 개발 기본값: Ollama Cloud, `gemma4:cloud`
- Jetson 목표: 로컬 Ollama, `gemma4:e2b`
- STT: faster-whisper
- TTS: Supertonic

LLM 호출 실패 시 `unknown` 의도와 안전한 재시도 문구를 반환한다.

### 5.2 긴급어

```text
마이크 상시 감시
→ EmergencyMonitor
→ /vica/emergency
├─ Mission Manager: goal 취소 + estopped 상태
└─ emergency_estop_bridge
   → /voice_emergency_stop 펄스
   → emergency_stop_node
   → /emergency_stop
```

hard-stop 키워드는 현재 6개다.

```text
멈춰, 정지, 스탑, 스톱, 안돼, 위험해
```

`잠깐`, `천천히`, `느리게`는 감지되지만 hard-stop bridge에서 무시된다.

### 5.3 현재 운영 gap

`vica_voice.launch.py`는 다음 노드를 함께 실행한다.

- LLM node
- TTS node
- emergency monitor
- `ros_robot_state_stub`
- `ros_state_machine_stub`

Mission Manager와 함께 운영할 때 두 stub은 중복 producer/consumer가 되므로 제거하거나 `use_stubs` launch argument로 선택 실행해야 한다.

Mission Manager가 발행하는 `/vica/tts_request`를 TTS가 구독하지 않는다. TTS는 현재 `/vica/intent.reply`만 재생한다.

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

현재 Mission Manager는 `/emergency_stop OR /estop_state`로 판정하지만 `/estop_state`
producer가 없다. 중앙 래치 구조에서는 `/emergency_stop`을 유일한 E-stop 상태 계약으로
사용하고 오래된 `/estop_state` 구독을 제거하는 것이 목표다. E-stop reset 뒤 이전 goal은
자동 재개하지 않는다.

### 6.3 현재 제약

- `mission_manager.launch.py`의 기본 목적지와 지도 경로가 다른 개발자의 개인 홈 경로로 하드코딩되어 있다.
- 앱 시험 도구 `vica_goto_goal.py`도 NavigateToPose를 직접 발행한다.
- 앱 상태 node는 주로 `vica_goto_goal.py`의 `/vica_goal_event`를 사용하므로 Mission 상세 상태가 앱과 자동 동기화되지 않는다.

목표 구조에서는 일반 서비스 goal 발행자를 Mission Manager 하나로 제한한다. `vica_goto_goal.py`는 좌표 시험 전용 도구로 명확히 분리한다.

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
| Global planner | `nav2_navfn_planner/NavfnPlanner` |
| Local controller | `dwb_core::DWBLocalPlanner` |
| 최대 직선 속도 | 0.26 m/s |
| DWB 최대 회전 속도 | 0.4 rad/s |
| Goal tolerance | x/y 0.25 m, yaw 0.25 rad |
| Local costmap | `odom`, voxel + inflation, `/scan` |
| Global costmap | `map`, static + obstacle + inflation, `/scan` |
| Footprint | 전방 0.15 m, 후방 -0.60 m, 좌우 ±0.1875 m |

`nvblox_layer` 설정 블록은 남아 있지만 local costmap `plugins` 목록에는 포함되지 않아 현재 활성 plugin이 아니다.

### 7.3 Behavior Tree

사용자 정의 BT XML은 저장소에 없다. 현재 Nav2 기본 파일을 사용한다.

```text
nav2_bt_navigator/navigate_to_pose_w_replanning_and_recovery.xml
nav2_bt_navigator/navigate_through_poses_w_replanning_and_recovery.xml
```

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
WS 루트 `ekf_config/`는 호환 목적으로 남아 있지만 정본이 아니므로 새 변경은
`vica_localization` 설정을 기준으로 한다. 로컬의 미추적 `src/ekf_config/` 사본은 팀
배포 범위에 포함하지 않는다.

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
Nav2 / vica_goto_goal
        └─ /cmd_vel
             └─ /cmd_vel_req remap 없음 [GAP]

Safety Supervisor
        ├─ /cmd_vel_req 구독
        └─ /cmd_vel_safe 발행
             └─ mdrobot_can_keyboard_knob_node
                  └─ CAN 0xCF → motor
```

Safety Supervisor와 motor 사이의 코드 토픽은 연결됐다. 그러나 Nav2의 `/cmd_vel`을
`/cmd_vel_req`로 보내는 remap/중계가 없어 정상 Nav2 명령이 Safety 입력까지 도달하지
않는다. `vica_goto_goal.py`의 yaw 정렬 기본 출력도 `/cmd_vel`이어서 운영 경로에 쓰면
Safety를 우회한다.

motor node는 MDROBOT F1 I/O 모니터의 knob(스마트핸들 가변저항) 값으로 주행 속도를
보정한다(보행 속도 추종, 현재 구현됨). F1이 `knob_timeout_sec` 안에 수신되지 않으면
knob 0으로 처리되어 정지한다.

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

### 9.5 reset gap

현재 `emergency_stop_node`는 물리 CAN F1·앱·음성·시험 입력을 OR하여 주기 발행하지만
중앙 래치와 reset service는 구현하지 않았다. `app_emergency_node`는 `/estop_reset`을
호출하지만 해당 service server는 현재 motor node에 없으므로 reset 경로가 끊겨 있다.

목표 reset 계약은 다음과 같다.

| 인터페이스 | 소유자 | 규칙 |
| --- | --- | --- |
| `/estop_reset` | `emergency_stop_node` | 모든 원인 해제·물리 입력 freshness·Goal 취소·정지 명령 확인 뒤 중앙 래치 해제 |
| `/safety_reset` | Safety Supervisor | `/emergency_stop=false`와 `/cmd_vel_req=0` 확인 뒤 재허용 |

외부 사용자는 로그인한 관리자 앱 하나뿐이다. 앱은 확인 팝업 또는 명시적 알림 뒤 단일
reset 요청을 보내고, reset orchestration은 중앙 래치 해제와 Safety reset 결과를 모두
확인해야 한다. 앱이나 STT의 `false`는 입력 원인 해제일 뿐 래치 reset이 아니며,
LLM/STT에는 reset 권한을 주지 않는다. 이전 Goal은 자동 재개하지 않는다.

### 9.6 E-stop 중앙 래치 목표 계약

```text
MDROBOT F1 물리 버튼 상태 ─┐
앱 /app_emergency_stop ─────┼→ emergency_stop_node
STT /voice_emergency_stop ──┘   ├─ source 상태·freshness 관리
                                ├─ 하나라도 true면 중앙 latch
                                ├─ /emergency_stop 주기 발행
                                └─ 관리자 앱 /estop_reset
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
| 관리자 앱 reset | 해당 없음 | 모든 원인 해제 뒤 중앙 래치 해제 요청 | 유일한 외부 권한 |

`false` 입력은 중앙 래치를 직접 끄지 않는다. `emergency_stop_node`가 reset 요청을
수락하려면 모든 입력이 비활성·fresh하고 Goal이 취소됐으며 요청 속도가 0인지 확인해야
한다. 앱 인증은 Flutter 계층에서 확인하되 로봇 측 reset 서비스도 요청 출처와 상태를
검증해야 한다. 이 전체 계약은 현재 코드에 완성되지 않은 `[TARGET]`이다.

## 10. Supervisor 앱 아키텍처

### 10.1 Flutter 역할

- rosbridge WebSocket 연결
- 지도·장소 조회와 좌표 저장
- `/robot_status` 기반 로봇 상태 표시
- `/app_estop_state` 기반 앱 E-stop 표시
- E-stop activate/reset service 호출
- 연결·오류·E-stop·장소 관리 로그
- 목표: IDLE(사용자 미이용) 한정 원격 목적지 요청 — 앱 장소 선택을 Mission Manager 경유로 전달(`vica_scenario.md` 10.5절). 수동 teleop은 범위 제외.

앱은 안전 계층이나 motor path를 우회하지 않는다. 원격 목적지 요청도 Mission Manager gate와 안전 계층을 거친다.

### 10.2 현재 로그인 상태

로그인 화면과 기존 사용자 로그인은 확정된 요구사항이지만, 현재 Flutter source에는 로그인 screen, auth provider, 로그인 route가 없으므로 구현 목표로 분류한다. 설정 화면에는 읽기 전용 `admin` 계정 정보만 있다.

후속 통합 시 로그인 기능을 삭제하지 말고 실제 구현 source를 확인해 앱 시작 route 앞에 연결한다. 신규 회원가입과 복잡한 권한 관리는 범위 밖이다.

### 10.3 상태 bridge

`vica_status_app_node.py`는 다음 정보를 `/robot_status` JSON으로 요약한다.

- TF `map → base_footprint` 기반 x/y/yaw
- `/odom` twist와 fallback pose
- `/diagnostics` 오류
- `/vica_goal_event` 목적지 상태
- map ID와 가까운 저장 장소명

상태 우선순위는 오류 → 위치 미확보 → goal/속도 기반 moving → waiting이다.

Mission Manager 상세 상태는 `/vica_goal_event`에 연결되어 있지 않아 앱에 완전히 반영되지 않는다.

### 10.4 앱 E-stop bridge

`app_emergency_node`는 현재 `mdrobot_can_control` 패키지 안에 있다.

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
└─ /estop_reset client                 # 현재 server 없음 [GAP]
```

이 node는 `safety_bringup.launch.py`와 `motor_safety_bringup.launch.py`에 포함되어 있지 않다.
현재 `/app_estop_state`는 앱 입력 상태만 나타내므로 중앙 E-stop 래치의 실제 상태와 다를
수 있다. 목표 구조에서는 앱이 중앙 `/emergency_stop` 또는 동등한 통합 상태를 표시하고,
관리자 확인 팝업 뒤 `emergency_stop_node`의 단일 reset만 호출한다.

### 10.5 저장소 경계 목표

Flutter client는 `VICA_Supervisor/`에 유지한다. `VICA_Supervisor/ros2/`의 상태·지도·장소·
Goal 보조 노드는 로봇에서 실행되는 코드이므로 장기적으로
`vica_ros2_ws/src/vica_supervisor_bridge/` 같은 ROS 패키지로 이동하는 것이 목표다.
현재는 파일 이동이 승인되지 않았으므로 기존 위치를 `[CURRENT]`, 이동안을 `[TARGET]`으로
관리한다.

## 11. 목적지·지도 데이터

| 데이터 | 현재 위치 | 용도 |
| --- | --- | --- |
| 언어 목적지 | `vica-voice-llm/config/destinations.yaml` | 이름, alias, 접근성, 확인/도착 문구, pose |
| 앱 장소 | `vica_ros2_ws/location/<map_id>/locations.json` | 지도별 앱 좌표와 메모 |
| 지도 | `vica_ros2_ws/maps/*.yaml`, 이미지 | Nav2, 앱 표시 |

현재 YAML과 JSON은 자동 동기화되지 않는다. ID, map ID, frame, x/y/yaw, calibrated, 접근 가능 여부를 하나의 검증 계층에서 연결해야 한다.

Mission launch 기본 경로는 현재 특정 사용자 경로로 하드코딩되어 있어 이 작업공간 경로와 맞지 않는다. 배포 설정 또는 launch argument로 명시해야 한다.

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

## 13. 현재 주요 위험과 우선순위

| 우선순위 | 문제 | 조치 |
| --- | --- | --- |
| P0 | Nav2 명령이 Safety 입력에 도달하지 않음 | Nav2 `/cmd_vel`을 `/cmd_vel_req`로 remap |
| P0 | E-stop 중앙 래치가 구현되지 않음 | `emergency_stop_node`에 통합 latch와 관리자 앱 단일 reset 구현 |
| P0 | localization 런타임 의존성 미설치 | `robot_localization`, `python3-can` 설치 후 깨끗한 환경에서 전체 build/test |
| P0 | wheel+IMU 실기 융합 미검증 | C5, D455 adapter, `/odom`과 TF 단일 authority를 HIL에서 검증 |
| P0 | 기본 motor launch가 물리 CAN F1을 사용하지 않음 | 실제 운용 launch에서 검증된 `can_f1` 입력 활성화 |
| P1 | Mission과 앱 시험 도구의 goal 권한 중복 | 운영 goal 권한을 Mission Manager로 제한 |
| P1 | voice launch의 stub 중복 | 운영 launch에서 제외 |
| P1 | Mission TTS 미연결 | `/vica/tts_request` subscriber와 priority queue |
| P1 | 앱 Mission 상세 상태 미연결 | 공통 mission status 계약 정의 |
| P1 | 목적지 YAML/JSON 이중화 | 데이터 동기화 또는 단일 기준 schema |
| P2 | Smart Handle 안내 미구현 | 메시지 → mock → bench → HIL 순서 구현 |

## 14. 권장 통합 순서

1. 현재 토픽과 TF를 rosbag/읽기 전용 명령으로 확인한다.
2. localization 의존성을 설치하고 확정된 `/wheel/odom + /imu/base_link → EKF → /odom` 계약을 깨끗한 환경에서 재검증한다.
3. Nav2 명령을 `/cmd_vel_req`로 연결한다.
4. motor가 `/cmd_vel_safe`만 받는 현재 계약을 build/runtime에서 검증한다.
5. `emergency_stop_node` 중앙 래치와 관리자 앱 단일 reset을 구현한다.
6. 물리·음성·앱 E-stop을 바퀴를 띄운 상태에서 종단 검증한다.
7. voice 운영 stub과 TTS 계약을 정리한다.
8. 앱 Mission 상태와 목적지 데이터 계약을 통합한다.
9. Turn Guide 순수 로직과 mock driver를 구현한다.
10. 서보·LED MCU bench test를 수행한다.
11. 전체 HIL 뒤 제한 구역 저속 주행을 수행한다.

## 15. 공식 참고자료

전체 공식 URL 목록과 버전 주의사항은 별도 유지 문서인 [`official_reference_urls.md`](official_reference_urls.md)를 기준으로 한다.

적용 원칙:

- ROS2는 Ubuntu 22.04 + Humble 기준
- Nav2 최신 문서의 파라미터를 그대로 복사하지 않고 Humble branch와 비교
- Isaac ROS는 Humble/JetPack 6.x 호환을 위해 release 3.2 문서 우선
- NVIDIA, Nav2, ROS 공식 예제보다 VICA의 안전 권한 경계를 우선
- MDROBOT CAN frame과 E-stop 동작은 `source_file`의 실제 하드웨어 매뉴얼 및 실측 결과로 검증
