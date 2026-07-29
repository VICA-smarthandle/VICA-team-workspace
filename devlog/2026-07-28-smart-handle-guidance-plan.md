# Smart Handle 시각·촉각 안내 구현 설계안 및 계획서

작성일: 2026-07-28
대상: `vica_ros2_ws/` — 구현 브랜치 `feat/user-guidance`
      (실주행 검증 완료 후 `dev`로 머지. 10.2절)
상태: **Phase 1~4 구현 완료 / 실기 검증 `[미검증]`** — 진행 상태는 10절

> 이 문서는 설계 초안으로 시작해 구현·bench 실측 결과를 함께 기록한다. 앞부분의
> 설계 근거와 뒷부분의 실측 결과가 충돌하면 **실측이 우선**이다.

참고 자료: `/home/msk/led_servoMotor.txt` (아두이노 나노 펌웨어 초안, 166줄)
근거 문서: `guideline/vica_architecture.md` 12장, `guideline/vica_scenario.md` 7장,
`guideline/bt와 visual hierarchy of your folders and files.md` 4.3·10장

---

## 0. 요약

EKF 융합 odometry(`/odom`)의 yaw 변화량으로 좌·우 회전을 감지해, Smart Handle의
서보(촉각)와 좌·우 LED(시각)로 사용자에게 방향 전환을 안내한다. 추후 햅틱을 추가해
비상정지는 긴 진동, 목적지 도착은 짧은 진동 3회로 피드백한다.

핵심 설계 판단 4가지:

| 판단 | 내용 | 근거 |
| --- | --- | --- |
| 2노드 분리 | `turn_guide_node`(판단) + `user_guidance_driver_node`(구동) | 아키텍처 12장 목표 구조. 판단 로직을 하드웨어 없이 단위 테스트 가능 |
| 안전 경로 불간섭 | guidance는 `/cmd_vel*`·Nav2 goal을 **발행하지 않음** | 시나리오 7.1, AGENTS.md 4장 |
| 우선순위 고정 | E-stop > 도착 > 회전 cue | 시나리오 7.5 "E-stop은 모든 일반 회전 cue보다 우선" |
| 시간 판정 단일화 | STEADY_TIME + 정수 ns + 미수신 `None` | `vica_safety/freshness.py` 기존 계약 재사용 |

---

## 1. 현재 사실 확인 (구현 전 기준선)

실제 파일을 확인한 결과다.

### 1.1 존재하는 것

| 항목 | 경로/토픽 | 사실 |
| --- | --- | --- |
| EKF 출력 | `/odom` (`nav_msgs/Odometry`) | `vica_localization/config/ekf.yaml`, `two_d_mode: true`, `world_frame: odom`, yaw 융합 활성(odom0/imu0 config의 12번째 = `true`) |
| E-stop 래치 | `/estop_state`, `/emergency_stop` (`std_msgs/Bool`) | `vica_safety/emergency_stop_node.py:123-124` |
| Safety 상태 | `/safety_state` (`std_msgs/String`) | `vica_safety/safety_supervisor_node.py:97` |
| 도착 이벤트 | `/vica_goal_event` (`std_msgs/String`, JSON) | `mission_manager_node.py:159`, 도착 시 `goal_succeeded` (`:414`) |
| 시간 판정 유틸 | `vica_safety/freshness.py` | `sec_to_ns()`, `is_fresh_ns()` |
| 인터페이스 정본 | `vica_interfaces/` | 현재 msg 3종 + srv 1종, `CMakeLists.txt`에 명시 등록 방식 |
| knob 속도 추종 | motor node | 가변저항 → CAN F1 → 속도 보정. **이미 구현됨. 이번 범위 아님** |

### 1.2 없는 것 `[GAP]`

- `vica_user_guidance` 패키지 자체가 없다.
- `TurnGuide.msg`, `SmartHandleState.msg`가 없다.
- 아두이노와의 시리얼 연결 ROS 노드가 없다.
- 햅틱 장치는 **물리적으로 미장착**(사용자 진술: 추후 부착).

### 1.3 참고 펌웨어 분석 (`led_servoMotor.txt`)

그대로 쓸 수 없는 부분과 살릴 부분을 구분한다.

**살릴 설계**
- 1바이트 상태코드 프로토콜 (`0=NORMAL, 1=LEFT, 2=RIGHT, 3=ESTOP`) — 단순하고 견고
- `applyState()`의 상태 변화 시에만 처리 → 같은 상태 재수신 무시 (LED 애니메이션 리셋 방지)
- 서보 슬로우 이동 (`SERVO_STEP_MS 14`, 1도씩) — 급격한 손목 충격 방지
- 워치독 1500ms → 통신 두절 시 경고 상태 전환

**LED 색상 동작 (아두이노 IDE 실측 확인, 2026-07-28)**

색상은 두 갈래 경로로 나뉜다. 코드만 읽으면 `applyState()`의 `setA/setB(SKY)`가
방향 표시 색으로 보이지만, 실제 사용자가 보는 방향 신호는 `drawLine()`이 만든다.

```text
applyState()  → setA/setB(SKY 또는 OFF)   상태 전환 시 1회, "정지된 배경"
loop()        → drawLine()의 ORANGE       30ms마다 반복, "움직이는 방향 신호"
```

`STATE_LEFT` 수신 시 `setB(OFF)`로 B줄을 잠깐 끄지만, 곧바로 `currentMode = WAVE_B`가
되어 `drawLine(ledB, ...)`이 초당 약 33회 B줄을 `ORANGE`로 덮어쓴다(66행 하드코딩).
따라서 실제 표시는 다음과 같다.

| 상태 | A줄 (D8) | B줄 (D9) |
| --- | --- | --- |
| `NORMAL` (0) | `SKY` 상시 점등 | `SKY` 상시 점등 |
| `LEFT` (1) | `SKY` 상시 점등 | **`ORANGE` 물결** |
| `RIGHT` (2) | **`ORANGE` 물결** | `SKY` 상시 점등 |
| `ESTOP` (3) | `ORANGE` 점멸 | `ORANGE` 점멸 |

**이 동작을 현재 설정 그대로 유지한다** (2026-07-28 사용자 결정). 시나리오 7.1의
"황색 점멸" 요구는 물결 애니메이션으로 충족된 것으로 본다.

**수정 필요**

| 문제 | 현재 펌웨어 | 조치 |
| --- | --- | --- |
| **서보 방향 반전** | `STATE_LEFT` → `SERVO_RIGHT(0)`, `STATE_RIGHT` → `SERVO_LEFT(180)` (89·96행) | 좌회전인데 서보가 오른쪽으로 감. 실기 검증 후 매핑 확정. 코드 상수명과 동작이 어긋나 있어 **[미검증] 표시 필수** |
| **LED 좌우 매핑 [미검증]** | `WAVE_B`=D9=좌측 주석 (91행). `STATE_LEFT`가 B줄을 물결로 씀 → 주석대로면 정합 | A/B 스트립의 물리적 좌·우 위치를 실측으로 확인만 하면 된다 |
| **`drawLine()` 색 하드코딩** | 66행 `ORANGE` 고정 | 방향별 물결 색을 바꿀 수 없다. 코드 4·5는 물결이 아니라 `setA/setB()`로 처리하므로 **이번 범위에서는 인자화하지 않는다** |
| **ESTOP과 통신두절 동일** | 워치독 트립 시 `applyState(STATE_ESTOP)` (138행) | 원인 구분 불가. 별도 코드 `4=LINK_LOST` 추가 |
| **부팅 직후 워치독 오탐** | `setup()`에서 `lastRxMillis = millis()` (119행) 후 바로 감시 시작 | 젯슨 부팅·ROS 기동 전 1.5초가 지나면 통신두절로 판정. `everConnected` 플래그로 **첫 수신 전까지 워치독 보류** |
| **직진 점멸 아님** | `NORMAL`에서 `SKY` 상시 점등 | 시나리오 7.1은 "파란색 점멸". **현재 상시 점등을 유지**하고 문서를 실동작에 맞춘다 |
| **햅틱 없음** | 미구현 | 상태코드 확장 필요 |
| **보드레이트 9600** | `Serial.begin(9600)` | 115200으로 상향 권장 |

> 주의: 펌웨어의 `WATCHDOG_TIMEOUT_MS 1500`은 "신호 없으면 경고"인데, ROS 측 발행
> 주기를 이보다 충분히 짧게(예: 10Hz = 100ms) 유지해야 오탐이 없다.

---

## 2. 목표 아키텍처

```text
   /odom (EKF, nav_msgs/Odometry)        [기존]
        │  yaw 변화량
        ▼
┌────────────────────────┐
│   turn_guide_node      │  1단계: yaw 변화량 → LEFT/RIGHT
│   - 슬라이딩 윈도우     │  debounce + hysteresis + 최소 지속시간
│   - sequence_id 관리    │  2단계(추후): Nav2 path look-ahead
└────────────────────────┘
        │ /vica/turn_guide  (TurnGuide.msg)
        ▼
┌──────────────────────────────────────────┐
│      user_guidance_driver_node           │
│  우선순위 병합:                            │
│    1) /estop_state (Bool)      ─ 최우선    │  [기존]
│    2) /vica_goal_event (String) ─ 도착     │  [기존]
│    3) /vica/turn_guide          ─ 회전     │
│  → 1바이트 상태코드 시리얼 송신 (10Hz)      │
└──────────────────────────────────────────┘
        │ /vica/smart_handle_state (SmartHandleState.msg)  ← 진단 발행
        │ USB Serial (pyserial, 115200)
        ▼
   아두이노 나노 — 서보 / LED A·B / 햅틱(추후)
```

**핵심**: guidance 계층은 어떤 구동 명령도 발행하지 않는다. `/cmd_vel_req`,
`/cmd_vel_safe`, Nav2 goal에 일절 관여하지 않는 순수 출력 계층이다.

---

## 3. 인터페이스 설계

### 3.1 `vica_interfaces/msg/TurnGuide.msg` `[TARGET]`

```
# Smart Handle 회전 안내 cue. 구동 명령이 아니라 사용자 안내 신호다.
std_msgs/Header header

uint8 DIRECTION_NONE=0
uint8 DIRECTION_LEFT=1
uint8 DIRECTION_RIGHT=2
uint8 direction

uint8 PHASE_IDLE=0
uint8 PHASE_PREPARE=1      # 2단계(path look-ahead)에서만 사용
uint8 PHASE_NOW=2
uint8 PHASE_COMPLETE=3
uint8 PHASE_CANCELED=4
uint8 phase

float32 distance_m         # 2단계 전용. 1단계는 NaN
float32 turn_angle_deg     # 누적 yaw 변화량(부호: CCW +)
uint32 sequence_id         # 경로 재계획 시 증가. 이전 sequence cue는 폐기
builtin_interfaces/Time valid_until
```

### 3.2 `vica_interfaces/msg/SmartHandleState.msg` `[TARGET]`

```
# Smart Handle 장치 상태 진단. heartbeat 프로토콜은 사용하지 않는다.
std_msgs/Header header

bool connected             # 시리얼 포트 open + 최근 전송 성공 여부로 판정
bool user_contact          # 터치센서 미장착 시 false 고정 [미검증]
bool servo_ok
bool left_led_ok
bool right_led_ok
bool haptic_ok             # 장치 미장착 시 false

uint8 FAULT_NONE=0
uint8 FAULT_PORT_OPEN=1
uint8 FAULT_WRITE_FAIL=2
uint8 FAULT_NOT_CONFIGURED=3
uint8 fault_code

uint8 last_state_code      # 아두이노로 마지막 전송한 상태코드
```

> `vica_interfaces/CMakeLists.txt`의 `rosidl_generate_interfaces`에 두 msg를 추가하고,
> `std_msgs`·`builtin_interfaces` 의존을 `package.xml`에 확인·추가한다.

### 3.3 시리얼 프로토콜 `[TARGET]`

참고 펌웨어의 1바이트 방식과 **현재 색상 동작을 그대로 유지**하고, 코드 4·5만 새로
추가한다. 0~3은 펌웨어 변경 없이 쓴다.

| 코드 | 이름 | LED (실동작) | 서보 | 햅틱 | 상태 |
| --- | --- | --- | --- | --- | --- |
| 0 | `NORMAL` | 양쪽 `SKY` 상시 점등 | 중립 90° | - | 구현됨 |
| 1 | `LEFT` | B줄 `ORANGE` 물결 / A줄 `SKY` | 좌 안내 위치 | - | 구현됨 |
| 2 | `RIGHT` | A줄 `ORANGE` 물결 / B줄 `SKY` | 우 안내 위치 | - | 구현됨 |
| 3 | `ESTOP` | 양쪽 `ORANGE` 점멸 (300ms) | **중립 복귀** | **긴 진동 1회** | LED·서보 구현됨 / 햅틱 `[TARGET]` |
| 4 | `LINK_LOST` | 양쪽 **`RED` 상시 점등** | 중립 복귀 | - | 구현됨 |
| 5 | `ARRIVED` | 양쪽 **`SKY` 3회 점멸(500ms) 후 자동 복귀** | 중립 | **짧은 진동 3회** | LED 구현됨 / 햅틱 `[TARGET]` |
| 6 | `CHARGING` | 양쪽 `GREEN` 점멸 | 중립 | - | `[TARGET]` |
| 7 | `CHARGED` | 양쪽 `GREEN` 상시 점등 | 중립 | - | `[TARGET]` |

색 구분 — 색 4종을 쓰고, 같은 색 안에서는 **움직임으로 구분**한다.

| 색 | 상시 점등 | 점멸 | 물결 |
| --- | --- | --- | --- |
| 스카이블루 | `NORMAL` (직진) | `ARRIVED` (도착) | — |
| 주황 | — | `ESTOP` (비상) | `LEFT`/`RIGHT` (회전) |
| 빨강 | `LINK_LOST` (단절) | — | — |
| 초록 | `CHARGED` `[TARGET]` | `CHARGING` `[TARGET]` | — |

색 상수:

```c
const uint32_t SKY    = Adafruit_NeoPixel::Color(0,   200, 255);  // 기존
const uint32_t ORANGE = Adafruit_NeoPixel::Color(255, 80,  0  );  // 기존
const uint32_t RED    = Adafruit_NeoPixel::Color(255, 0,   0  );
const uint32_t GREEN  = Adafruit_NeoPixel::Color(0,   255, 0  );  // 충전용 예약
```

> **도착 색 결정 경위 (bench 실측, 2026-07-28).** 녹색 `(0,255,80)` → `SKY`와 구분
> 안 됨(둘 다 R=0, G 높음). 순수 녹색 → 충전 상태에 배정하기로 하여 제외. 무지개 →
> 팀 검토에서 "조잡함"으로 제외. 보라 `(180,0,255)`·순수 파랑 `(0,0,255)` → 사용자
> 선택에서 제외. 최종적으로 **`SKY` 단일 색**으로 통일하고 구분을 점멸 여부에 맡긴다.

> **도착과 직진은 같은 색이다.** 점멸을 놓치면 LED만으로는 도착을 알 수 없다. 실제
> 운영에서 TTS 음성과 햅틱 3회가 함께 나가고 주 사용자가 시각장애인이므로 LED는
> 보조 수단이라는 판단이다. 시각 안내 비중이 커지면 재검토 대상이다.

**코드 5는 펌웨어가 정확히 3회만 재생하고 스스로 기본 표시로 복귀한다.** 도착은
일회성 이벤트이므로 계속 점멸하면 진행 중 상태로 오인된다. ROS가 `arrival_hold_sec`
동안 코드 5를 반복 전송해도 표시는 3회로 고정된다.

**재생 시간은 3.0초가 아니라 3.5초다.** 프레임을 전개하면 ON/OFF 각 3회 + 마지막
소등 유지 1프레임 = 7프레임이므로 `500ms × 7 = 3500ms`다.

```text
 500ms ON(1)  1000 OFF  1500 ON(2)  2000 OFF  2500 ON(3)  3000 OFF  3500 → SKY 복귀
```

> **[결함] `arrival_hold_sec: 3.0`이면 도착 표시가 잘린다.** ROS가 t=3.0s에 코드 0을
> 보내면 `applyState(NORMAL)`이 즉시 실행되어 마지막 소등 프레임이 통째로 날아간다.
> 9.4절 버그 ④와 같은 증상이 ROS 쪽 원인으로 재발한다. 2026-07-28 bench에서는
> 코드 5를 5~8초간 보내서 드러나지 않았다.
>
> **`arrival_hold_sec: 4.0`으로 한다**(3.5초 + 마진 0.5초). 마진 근거는 10Hz 전송
> 양자화와 아두이노 `millis()` 대 Jetson steady clock의 드리프트다. 이 값은 펌웨어
> 상수에 종속되므로 `ARRIVE_BLINK_MS`/`COUNT`를 바꾸면 함께 바꾼다 —
> `test_protocol.py`가 config를 파싱해 이 관계를 고정한다.

**코드 4는 상시 점등이므로 `BLINK_BOTH` 애니메이션을 쓰지 않는다.** `applyState()`에서
`setBoth(RED)`를 1회 실행하고 `currentMode = NORMAL`로 둔다.

**서보는 회전 중(코드 1·2)에만 중립을 벗어난다.** 나머지 전 상태(시작·직진·비상·
단절·도착)에서 중앙 90도다. E-stop은 원본 초안의 "마지막 방향 유지"에서 **중립 복귀로
변경**했다 — 로봇이 정지한 상태에서 손잡이가 방향을 계속 가리키면 잘못된 안내가 되고,
아키텍처 12장의 "E-stop 시 서보 중립" 원칙과도 어긋나기 때문이다.

- 송신 주기 **10Hz 고정**(펌웨어 워치독 1500ms 대비 충분한 여유).
- 상태가 바뀌지 않아도 계속 전송한다 → 펌웨어가 워치독을 갱신하고, `applyState()`가
  동일 상태를 무시하므로 애니메이션은 끊기지 않는다.
- 아두이노 → Jetson 상향 통신은 1단계에서 **사용하지 않는다**(heartbeat 미사용 원칙).
  `connected`는 포트 open 성공과 write 예외 유무로만 판정한다.

### 3.4 단절 감지 책임 분담 `[TARGET]`

단절은 두 종류이며 **감지 주체가 다르다**. 한쪽이 다른 쪽을 대신하지 않는다.

| 상황 | 감지 주체 | 핸들 LED | 상위 표시 |
| --- | --- | --- | --- |
| 부팅 중 (아직 첫 수신 전) | 없음 (감시 보류) | `SKY` 유지 | — |
| **처음부터 미연결** | **젯슨** — 포트 open 실패 | `SKY` 유지 (변화 없음) | `FAULT_PORT_OPEN`, `connected=false` |
| **수신 중 단절** | **아두이노** — 워치독 | **`RED` 상시 점등** | `FAULT_WRITE_FAIL`, `connected=false` |

#### 펌웨어: `everConnected` 플래그

첫 정상 수신 전까지 워치독을 돌리지 않는다. 시간 상수를 조율할 필요가 없다.

```c
bool everConnected = false;   // 한 번이라도 정상 수신했는가

// 수신부 (기존 128~132행 확장)
if (b >= STATE_NORMAL && b <= STATE_ARRIVED) {   // 범위 0~5로 확장
  lastRxMillis    = now;
  watchdogTripped = false;
  everConnected   = true;                        // 최초 1회만 의미 있음
  applyState((uint8_t)b);
}

// 워치독 (기존 136~139행 대체)
if (everConnected && !watchdogTripped &&
    now - lastRxMillis > WATCHDOG_TIMEOUT_MS) {
  watchdogTripped = true;
  applyState(STATE_LINK_LOST);                   // ESTOP 아님
}
```

**초기 타임아웃을 길게 잡는 방식은 채택하지 않는다.** 젯슨 부팅·ROS 기동 시간이
환경마다 달라 유예값의 근거를 세울 수 없고, 짧으면 여전히 오탐이 나고 길면 실제
미연결을 늦게 잡는다. `everConnected`는 조율할 숫자가 없어 틀릴 여지도 없다.

**의미도 정확하다.** `LINK_LOST`는 "연결이 끊겼다"는 뜻이며, 한 번도 연결된 적 없는
상태는 끊긴 것이 아니라 아직 시작되지 않은 것이다.

#### 부팅 중 표시는 `setup()`의 `SKY`를 그대로 쓴다

`setup()`이 이미 `setA(SKY); setB(SKY)`를 실행한다(117행). 별도 대기 표시를 만들지
않는다. 사용자 눈에는 "켜짐 → 안내 시작"으로 자연스럽게 이어진다.

> 처음부터 USB가 미연결이면 핸들은 계속 `SKY`이므로 핸들만 봐서는 알 수 없다. 이는
> **의도된 설계**다. 젯슨의 포트 open 실패가 `SmartHandleState.fault_code =`
> `FAULT_PORT_OPEN`으로 발행되어 관리자 앱에서 확인되므로, 핸들 LED까지 이중으로
> 표시하지 않는다. 핸들 LED는 사용자용, `SmartHandleState`는 운영자용이다.

---

## 4. `turn_guide_node` 상세 설계

### 4.1 회전 판단 알고리즘 (1단계)

raw `/cmd_vel.angular.z`를 쓰지 않는다. `/odom`의 quaternion → yaw로 판단한다.

```
1) /odom 수신 → quaternion을 yaw로 변환
2) (stamp_ns, yaw)를 deque에 저장, window_sec(기본 1.5s) 밖은 폐기
3) 누적 변화량 = unwrap된 (yaw_now - yaw_window_start)   ← ±π 경계 처리 필수
4) |누적| >= enter_threshold_deg(기본 25°)  AND
   같은 부호가 min_duration_sec(기본 0.6s) 이상 지속  → 회전 진입
5) 진입 후 |누적| <= exit_threshold_deg(기본 10°)      → 회전 종료(hysteresis)
6) 진입 시 sequence_id++ , phase=NOW 발행
   종료 시 phase=COMPLETE 발행 후 IDLE
```

**yaw unwrap 처리**가 이 알고리즘의 최대 함정이다. `atan2` 결과는 ±π에서
점프하므로, 연속 샘플 간 차이를 `atan2(sin(d), cos(d))`로 정규화한 뒤 누적해야 한다.
단순 뺄셈은 180° 부근에서 반대 방향 회전으로 오판한다.

**부호 규약**: ROS REP-103에 따라 CCW(반시계) = 양수 = **좌회전(LEFT)**.

### 4.2 파라미터 (`config/user_guidance.yaml`)

```yaml
turn_guide_node:
  ros__parameters:
    odom_topic: /odom
    window_sec: 1.5
    enter_threshold_deg: 25.0    # 시험으로 확정 [미검증]
    exit_threshold_deg: 10.0
    min_duration_sec: 0.6
    odom_timeout_sec: 0.5        # 미수신 시 IDLE + NONE 강제
    publish_rate_hz: 20.0
    cue_valid_sec: 2.0
```

> 문서의 "기존 45도 아이디어"는 실내 90° 코너 기준으로는 반응이 늦다. 25°를 초기값으로
> 두고 사용자 시험으로 확정한다 — 시나리오 7.2가 요구하는 방식이다.

### 4.3 fail-safe

- `/odom` stale(0.5s 초과) → `direction=NONE, phase=IDLE` 발행. 정지 판단은 하지 않는다.
- 노드 종료 시 마지막으로 `NONE/IDLE` 1회 발행 시도.

---

## 5. `user_guidance_driver_node` 상세 설계

### 5.1 우선순위 병합 (배타적, 위에서부터)

```
if estop_latched:            state = ESTOP        # 최우선, 회전 cue 무시
elif arrival_active:         state = ARRIVED      # 도착 후 arrival_hold_sec 동안
elif turn_cue_fresh:         state = LEFT / RIGHT
else:                        state = NORMAL
```

`/estop_state`는 **중앙 래치의 결과**이므로 driver는 이를 구독만 하고 어떤 reset도
수행하지 않는다. 앱·STT의 `false`는 입력 해제일 뿐이라는 CLAUDE.md 원칙이 여기서도
그대로 적용된다 — driver는 래치 상태의 소비자일 뿐이다.

### 5.2 도착 감지

`/vica_goal_event`의 JSON payload에서 `event == "goal_succeeded"`일 때만 도착으로
판정한다(`mission_manager_node.py:414` 확인). `goal_canceled`·`goal_failed`는 도착이
아니므로 햅틱을 울리지 않는다.

### 5.3 시리얼 계층

- `pyserial`, 115200 8N1, `write_timeout` 설정 필수(블로킹 방지).
- 포트 경로는 `/dev/ttyUSB*` 대신 **udev 고정 심볼릭 링크**(`/dev/vica_smart_handle`)를
  파라미터 기본값으로 둔다. USB 재열거 시 번호가 바뀌기 때문이다.
- write 실패 → `fault_code=FAULT_WRITE_FAIL`, `connected=false`, 재연결 backoff 시도.
- **포트가 없어도 노드는 죽지 않는다.** `SmartHandleState`에 fault를 발행하며 계속 동작한다
  (`FAULT_NOT_CONFIGURED`). 개발 PC에서 하드웨어 없이 로직 테스트가 가능해야 한다.

### 5.4 파라미터

```yaml
user_guidance_driver_node:
  ros__parameters:
    serial_port: /dev/vica_smart_handle
    baudrate: 115200
    send_rate_hz: 10.0
    cue_timeout_sec: 1.0        # TurnGuide stale 판정
    estop_timeout_sec: 1.0
    arrival_hold_sec: 3.0       # 짧은 진동 3회 재생 시간
    enable_serial: true         # false면 로그만 (mock 모드)
```

---

## 6. 햅틱 확장 설계 (추후, 장치 부착 후)

사용자 요구사항: **비상제동 = 긴 진동 / 도착 = 짧은 진동 3회**.

### 6.1 원칙 (아키텍처 12장 준수)

> 햅틱은 비상상황 알림 전용이며 Safety 상태를 직접 구독한다.
> **모터 정지 성공 여부를 대신 보장하지 않는다.**

즉 햅틱이 울렸다는 사실은 "사용자에게 알렸다"는 의미일 뿐, "로봇이 멈췄다"는 보증이
아니다. 이 구분을 코드 주석과 문서에 명시한다.

### 6.2 구동 방식

패턴 생성은 **아두이노 펌웨어가 담당**한다. ROS는 상태코드만 보낸다.

| 이벤트 | 상태코드 | 펌웨어 패턴 | 트리거 |
| --- | --- | --- | --- |
| 비상제동 | 3 (`ESTOP`) | ON 800ms 1회 (긴 진동) | `estop_state` false→**true** edge |
| 도착 | 5 (`ARRIVED`) | ON 150ms / OFF 150ms × 3회 | `goal_succeeded` 수신 |

**edge 트리거가 핵심**: `ESTOP` 상태는 10Hz로 계속 전송되지만, 진동은 상태 **진입 시
1회만** 울려야 한다. 참고 펌웨어의 `applyState()`가 이미 "상태 변화 시에만 처리" 구조라
이 요구를 그대로 만족한다 — 진동 트리거를 `applyState()` 안에 두면 된다.

E-stop이 래치된 상태로 지속되는 동안 계속 진동하면 사용자가 상황을 파악하기 어렵고
전력 소모도 크므로, 반복 진동은 하지 않는다.

### 6.3 하드웨어 준비 상태 — **준비 완료** (2026-07-28 사용자 확인)

구동 회로는 이미 준비되어 있다. Phase 6 착수 시 **선행 조건이 아니다**.

| 항목 | 상태 |
| --- | --- |
| MOSFET/트랜지스터 드라이버 | 준비 완료 |
| 역기전력 방지 플라이백 다이오드 | 준비 완료 |
| 별도 5V 전원 (서보 + NeoPixel 60개) | 준비 완료 |

> 회로 구성을 기록으로 남기는 이유: 진동이 약하거나 아두이노가 재부팅되는 문제가
> 생겼을 때 **어떤 회로를 전제로 설계했는지** 알아야 원인을 좁힐 수 있다. 진동 모터는
> 나노 GPIO로 직접 구동할 수 없어(전류 초과) 드라이버가 필수이며, NeoPixel 60개는
> 최대 밝기에서 상당한 전류를 요구해 별도 5V 전원이 필요하다.

**Phase 6에 남은 작업은 두 가지뿐이다.**

1. 진동 모터 물리적 부착
2. 펌웨어 진동 패턴 구현 (6.2절)

---

## 7. 구현 단계 계획

문서가 지정한 순서(`메시지 → mock → bench → HIL`)를 따른다.

### Phase 1 — 인터페이스 정의 (하드웨어 불필요)

| 작업 | 파일 |
| --- | --- |
| `TurnGuide.msg` 추가 | `vica_interfaces/msg/TurnGuide.msg` |
| `SmartHandleState.msg` 추가 | `vica_interfaces/msg/SmartHandleState.msg` |
| CMakeLists 등록 | `vica_interfaces/CMakeLists.txt` |
| 의존 확인 | `vica_interfaces/package.xml` |

검증: `colcon build --packages-select vica_interfaces`

### Phase 2 — 판단 로직 (하드웨어 불필요, TDD)

순수 함수를 노드에서 분리해 rclpy 없이 테스트한다. `vica_safety`가 `safety_gate.py`,
`freshness.py`를 노드에서 분리한 것과 같은 패턴이다.

| 작업 | 파일 |
| --- | --- |
| 패키지 골격 | `vica_user_guidance/{package.xml,setup.py,resource/}` |
| yaw 누적·판정 순수 로직 | `vica_user_guidance/turn_detector.py` |
| 우선순위 병합 순수 로직 | `vica_user_guidance/guidance_priority.py` |
| 단위 테스트 | `test/test_turn_detector.py`, `test/test_guidance_priority.py` |

**필수 테스트 케이스**
- ±π 경계를 넘는 회전에서 방향 오판이 없을 것
- 임계값 미만의 자세 보정으로 cue가 발생하지 않을 것 (hysteresis)
- `min_duration` 미만의 순간 회전이 무시될 것
- odom stale → `NONE/IDLE`
- E-stop이 회전 cue를 무조건 덮어쓸 것
- 도착 이벤트가 `goal_succeeded`에만 반응하고 `goal_failed`에는 반응하지 않을 것

검증: `colcon test --packages-select vica_user_guidance`

### Phase 3 — 노드·mock 구동 (하드웨어 불필요)

| 작업 | 파일 |
| --- | --- |
| 판단 노드 | `vica_user_guidance/turn_guide_node.py` |
| 구동 노드 | `vica_user_guidance/user_guidance_driver_node.py` |
| 파라미터 | `config/user_guidance.yaml` |
| launch | `launch/user_guidance.launch.py` |

`enable_serial: false`로 rosbag 재생 또는 수동 `/odom` 발행 → 상태코드 로그만 확인.

### Phase 4 — 펌웨어 정비 (bench, 바퀴 미동작)

**상태: 코드 작성 + 컴파일 + bench 실기 검증 완료 (2026-07-28)**
7/8 항목 PASS, 8번(단절)만 미확인 — 9.3절 참조.

경로는 모두 `vica_ros2_ws` 저장소 기준이다(이 문서는 별도 저장소에 있다).

| 항목 | 경로 |
| --- | --- |
| 확장 펌웨어 | `src/vica_user_guidance/firmware/smart_handle_firmware/smart_handle_firmware.ino` |
| bench 시험 도구 | `src/vica_user_guidance/firmware/bench_test.py` |
| 원본 초안 | 작업공간 외부(`led_servoMotor.txt`). 저장소에 포함하지 않음 |

> 아두이노 IDE는 스케치 폴더명과 `.ino` 파일명이 같아야 하므로 `smart_handle_firmware/`
> 하위 디렉터리를 유지한다.

> **[해결됨 2026-07-28]** 처음에는 작업공간 루트의 `source_file/`에 두었으나, 루트
> `.gitignore`가 `/source_file/`을 제외해 **bench로 검증한 펌웨어가 어느 저장소에도
> 커밋되지 않는 상태**였다. `vica_user_guidance` 패키지 안으로 옮겨 해결했다.
>
> 같은 패키지에 두는 이유는 형상관리뿐이 아니다. 펌웨어와 ROS 드라이버가 **1바이트
> 상태코드 프로토콜을 공유**하므로, 같은 위치에 있어야 한쪽만 바뀌는 일을 막을 수
> 있다. `test_protocol.py`가 `.ino`를 직접 읽어 상수 일치를 검사하며, 파일이 없으면
> skip이 아니라 실패한다.
>
> `source_file/`은 원래 목적인 매뉴얼·데이터시트 보관용으로 남긴다.

#### 빌드 환경 (2026-07-28 실행 확인)

```bash
# arduino-cli 1.5.1 — ~/bin 설치, sudo 불필요
curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh \
  | BINDIR=~/bin sh
export PATH="$HOME/bin:$PATH"

arduino-cli config init
arduino-cli core update-index
arduino-cli core install arduino:avr           # 1.8.8
arduino-cli lib install "Adafruit NeoPixel"    # 1.15.5
arduino-cli lib install "Servo"                # 1.3.0 — AVR 코어에 미포함, 별도 설치 필요

# 이하 vica_ros2_ws 저장소 루트에서 실행한다
arduino-cli compile --fqbn arduino:avr:nano \
  src/vica_user_guidance/firmware/smart_handle_firmware
```

컴파일 결과 — 사용자 코드 경고 없음(경고는 모두 AVR 코어 `new.cpp` 내부).

```text
Sketch uses 6102 bytes (19%) of program storage space. Maximum is 30720 bytes.
Global variables use 328 bytes (16%) of dynamic memory, leaving 1720 bytes.
```

용량 여유가 충분하므로 향후 햅틱 패턴 추가에 제약이 없다.

업로드와 시험은 `/dev/ttyUSB0`에서 수행했다. `dialout` 그룹 미소속 상태였으므로
`sudo chmod 666 /dev/ttyUSB0`으로 임시 부여했다(USB 재연결 시 초기화되는 임시 조치).
상시 작업에는 `sudo usermod -aG dialout $USER` 후 재로그인이 필요하다.

**색상 동작은 현재 설정을 유지했다.** 기존 0~3 상태의 LED 로직과 `drawLine()`은
수정하지 않았다.

적용한 변경:

| 항목 | 원본 | 확장 |
| --- | --- | --- |
| 상태코드 | 4종 (0~3) | **6종** (`LINK_LOST`=4, `ARRIVED`=5 추가) |
| 수신 허용 범위 | `0~3` (128행) | **`0~5`** — 미수정 시 새 코드가 버려진다 |
| 워치독 트립 | `STATE_ESTOP` | **`STATE_LINK_LOST`** — 비상과 단절을 구분 |
| 부팅 중 워치독 | 즉시 감시 시작 | **`everConnected`로 첫 수신 전까지 보류** (3.4절) |
| 보드레이트 | 9600 | **115200** (ROS 측 파라미터와 동시 변경) |
| 색 상수 | `SKY`, `ORANGE`, `OFF` | **`RED`, `GREEN` 추가** |
| 애니메이션 모드 | 4종 | **`BLINK_ARRIVE` 추가** (재생 횟수 카운터 필요) |

#### 발견해 수정한 버그 4건

**① 도착 점멸 무한 반복 (작성 중 발견)**

3회 점멸 후 `applyState(STATE_NORMAL)`로 복귀시키면 `currentState`가 `NORMAL`이 되어,
젯슨이 `arrival_hold_sec` 동안 계속 보내는 **코드 5가 매번 "상태 변화"로 인식되어
점멸이 무한 반복**된다.

해결: `currentState`는 `STATE_ARRIVED`로 유지하고 표시만 되돌린다.

```c
currentMode = NORMAL;   // 애니메이션만 정지
setBoth(SKY);           // 기본 표시 복귀
// currentState는 STATE_ARRIVED 유지 → 이후 코드 5 반복 수신은 전부 무시된다
```

**② 마지막 점멸이 잘림 (bench 실측)**

OFF 프레임에서 카운트하면 3회차 ON 직후 같은 프레임에 `setBoth(SKY)`가 실행되어
마지막 ON이 눈에 남지 않는다. 카운트를 **ON 시점**으로 옮겼다.

**③ 소등 시간 0ms (bench 실측)**

②를 고친 뒤에도 마지막 OFF가 곧바로 `SKY`로 덮여 "짧게 스치고 마는" 것처럼 보였다.
`arriveTailPending` 플래그로 소등 프레임을 한 주기 확보했다.

**④ 첫 주기가 짧아 전체 타이밍이 밀림 (bench 실측 — 근본 원인)**

`applyState()`가 `lastBlink = 0`, `lastWave = 0`으로 초기화하고 있었다. 그러면
`now - lastBlink`가 `millis()` 전체 값이 되어 **다음 `loop()`에서 즉시 조건을 통과**한다.
첫 점멸이 한 주기를 채우지 못하고 이후 타이밍이 반 박자씩 밀려, 사용자에게 도착이
**"2.5회"** 로 보였다. ①~③은 이 근본 원인의 파생 증상이었다.

```c
lastBlink = millis();   // 0이 아니라 현재 시각으로
lastWave  = millis();
```

> `lastWave`도 같은 문제였다. 회전 물결의 첫 프레임이 즉시 실행되고 있었으므로
> 함께 수정했다. 원본 초안부터 있던 결함이다.

#### bench 시험 절차

`bench_test.py`로 자동 실행한다. 시리얼 모니터에 손으로 입력하는 방식은 7번 항목
(코드 5 빠른 연속 전송)을 재현할 수 없다.

```bash
pip install --user pyserial     # 3.5 확인

# 업로드 (나노 부트로더가 구형이면 --fqbn arduino:avr:nano:cpu=atmega328old)
arduino-cli upload -p /dev/ttyUSB0 --fqbn arduino:avr:nano \
  src/vica_user_guidance/firmware/smart_handle_firmware

cd src/vica_user_guidance/firmware
python3 bench_test.py --list          # 항목 확인
python3 bench_test.py --case 1        # 개별 실행
python3 bench_test.py --all           # 전체 순차 실행 + 요약
python3 bench_test.py --hold 2        # 코드 2를 10Hz로 계속 전송 (수동 관찰)
```

> 포트 권한: `dialout` 그룹 미소속이면 열리지 않는다.
> `sudo usermod -aG dialout $USER` 후 **재로그인**이 필요하다.
> 아두이노 IDE의 시리얼 모니터가 포트를 점유 중이면 먼저 닫는다.

수동 확인 시에는 시리얼 모니터 보드레이트를 **115200**으로 맞춘다(미변경 시 문자 깨짐).

#### bench 시험 결과 (2026-07-28 실측)

| # | 입력 | 기대 동작 | 결과 |
| --- | --- | --- | --- |
| 1 | 전원만 인가, 무송신 30초 | 하늘색 유지, 빨간불 없음 | **PASS** — 하늘색 유지 |
| 2 | `0` | 양쪽 하늘색, 서보 중앙 | **PASS** |
| 3 | `1` | 한쪽 주황 물결 + 서보 | **PASS** — 왼쪽 물결, 서보 왼쪽 |
| 4 | `2` | 반대쪽 물결 + 서보 | **PASS** — 오른쪽 물결, 서보 오른쪽 |
| 5 | `3` | 양쪽 주황 점멸 | **PASS** — 서보 중립 복귀도 확인 |
| 6 | `5` | 3회 점멸 후 하늘색 | **PASS** (버그 ①~④ 수정 후) |
| 7 | `5` 연속 5회 빠르게 | 여전히 3회만 | **PASS** — 반복 없음 |
| 8 | `0` 송신 후 USB 분리 | 1.5초 뒤 빨간색 상시 점등 | **미확인** — 별도 전원 없어 보류 |

8번은 USB가 유일한 전원이라 케이블을 뽑으면 아두이노도 함께 꺼진다. 전송 중단으로
대체 시험이 가능하나(펌웨어 입장에서는 동일하게 "1.5초간 신호 없음") 이번에는
수행하지 못했다. **`LINK_LOST` 표시는 아직 `[미검증]`이다.**

#### 실측으로 확정된 매핑

| 항목 | 결과 |
| --- | --- |
| 코드 1 (`LEFT`) | **왼쪽** 주황 물결 + 서보 **왼쪽** |
| 코드 2 (`RIGHT`) | **오른쪽** 주황 물결 + 서보 **오른쪽** |

> **"서보 방향 반전 의심"은 오판이었다.** 코드는 `STATE_LEFT`에서 `SERVO_RIGHT(0)`을
> 호출하지만 실제 서보는 왼쪽으로 움직인다. 서보가 물리적으로 반대 방향으로 장착되어
> 상수명과 어긋날 뿐, **사용자가 느끼는 방향은 정확하다. 코드 수정은 불필요하다.**
> `.ino`의 `[미검증]` 주석은 이 실측 결과로 대체한다.
>
> LED A/B 매핑도 `WAVE_B`=D9=좌측 주석이 실제와 일치한다.

> `drawLine()`의 색 인자화는 이번 범위에서 **하지 않았다**. 코드 4·5 모두 물결이 아닌
> `setBoth()` 처리라 불필요하다. 향후 방향별 물결 색을 바꿔야 할 때만 검토한다.

### Phase 5 — HIL 통합 (실기, 승인 필요)

AGENTS.md 5장에 따라 **바퀴를 띄운 상태, 주변 통제, 물리 E-stop 확보** 조건에서만
수행한다. 이 단계는 사용자의 명시적 승인 후 진행한다.

- 실제 주행 중 회전 감지 지연·오탐 측정 → 임계값 확정
- E-stop 시 회전 cue가 즉시 무시되는지 확인
- 시리얼 단절 시 펌웨어 워치독 동작 확인

### Phase 6 — 햅틱 (장치 부착 후)

상태코드 3·5에 진동 패턴 추가. 드라이버 회로 검토 선행.

---

## 8. 안전 경계 재확인

이 기능이 **하지 않는** 것을 명시한다.

- `/cmd_vel_req`, `/cmd_vel_safe`를 발행하지 않는다.
- Nav2 goal을 보내거나 취소하지 않는다.
- E-stop 래치를 소유하거나 reset하지 않는다 — `/estop_state`를 구독만 한다.
- 서보는 조향 장치가 아니다. 로봇 진행 방향에 영향을 주지 않는다.
- 햅틱은 알림이지 정지 보증이 아니다.
- Smart Handle 시리얼이 끊겨도 주행 안전 경로에는 영향이 없다. 반대로 **주행 정지가
  필요한 상황을 이 노드가 판단하지도 않는다.**

> AGENTS.md 4장의 미완료 항목("CAN/센서/Smart Handle 단절에 대한 종단 fail-safe")은
> 이 계획으로 해결되지 않는다. Smart Handle 단절을 주행 정지 조건으로 삼을지는 별도
> Safety 결정 사항이며, 현 설계는 단절을 **표시·진단만** 한다.

---

## 9. 결정 사항

### 9.1 확정 (2026-07-28)

| 항목 | 결정 |
| --- | --- |
| LED 색상 체계 | **현재 펌웨어 설정 유지.** 회전=한쪽 `ORANGE` 물결 + 반대쪽 `SKY`, 직진=양쪽 `SKY` 상시 점등 |
| 직진 점멸 여부 | 점멸하지 않고 **상시 점등 유지**. 시나리오 7.1 문구를 실동작에 맞춰 갱신 대상으로 둔다 |
| `drawLine()` 색 인자화 | 이번 범위에서 **하지 않는다** |
| `LINK_LOST` 표시 | **빨간색 상시 점등**. E-stop(주황 점멸)과 색·움직임 모두 구분됨 |
| `ARRIVED` 표시 | **`SKY` 3회 점멸(500ms, 총 3.5초) 후 자동 복귀**. 색 후보 검토 경위는 3.3절 |
| 초록색 용도 | **충전 상태 전용으로 예약**(충전 중=점멸, 완료=상시). `GREEN` 상수만 정의해 둠 |
| E-stop 시 서보 | **중립 복귀**. 원본의 "마지막 방향 유지"에서 변경 — 정지 상태에서 방향 지시는 잘못된 안내 |
| 서보 중립 규칙 | **회전 중(코드 1·2)에만 중립을 벗어난다.** 시작·직진·비상·단절·도착은 모두 중앙 90도 |
| 서보 좌/우 매핑 | **실측 확정.** 상수명과 반대로 보이나 물리 장착이 반대라 동작은 정확. **수정 금지** |
| LED A/B 매핑 | **실측 확정.** `WAVE_B`=D9=좌측 주석이 실제와 일치 |
| 부팅 직후 워치독 | **`everConnected` 플래그로 첫 수신 전까지 보류**(3.4절). 초기 타임아웃 연장 방식은 유예값 근거가 없어 미채택 |
| 처음부터 미연결 | 핸들 LED는 `SKY` 유지. **젯슨 포트 open 실패 → `FAULT_PORT_OPEN` → 관리자 앱**으로 확인. 핸들에 이중 표시하지 않음 |
| 회전 임계값 | **25°/10°/0.6s 초기값 그대로 진행** 후 실주행 시험으로 조정. config 기본값에 `[미검증]` 유지 |
| 시리얼 포트 | **udev 고정 이름 부여 승인.** `/dev/vica_smart_handle` (아래 9.4절) |
| 터치센서 | **미장착 확정.** `user_contact`는 항상 `false` |
| 시나리오 문서 | **직진 = 상시 점등으로 확정.** `guideline/vica_scenario.md` 7.1 문구를 실동작에 맞게 수정 |
| 충전 상태 | **입력원 미정 단계 유지.** 코드 6·7은 구현하지 않고 `protocol.py`에 상수만 `[TARGET]`으로 정의 |
| 펌웨어 경로 | **`vica_user_guidance/firmware/`로 이동 승인.** 로직 구현과 **별도 커밋**으로 분리 |
| 햅틱 하드웨어 | **준비 완료**(6.3절). Phase 6 선행 조건에서 제외 |

### 9.2 udev 규칙 — 파일 작성 완료, 설치 대기 (2026-07-29)

규칙 파일은 `vica_user_guidance/udev/99-vica-smart-handle.rules`에 있다.
`setup.py`가 `share/`에도 설치하므로 소스 트리 없는 배포 환경에서도 꺼내 쓸 수 있다.

**실측한 칩은 CH340이 아니라 FTDI FT232R이었다** (초안의 `1a86:7523`은 추정값이었다).

| 속성 | 값 |
| --- | --- |
| `idVendor:idProduct` | `0403:6001` (FTDI FT232R) |
| `serial` | `B003UMKG` |

```
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001",
  ATTRS{serial}=="B003UMKG", SYMLINK+="vica_smart_handle",
  MODE="0660", GROUP="dialout", ENV{ID_MM_DEVICE_IGNORE}="1"
```

- **`serial`을 반드시 조건에 넣는다.** `0403:6001`은 FT232R 계열 전체가 공유하는
  값이라 다른 FTDI 장치에도 같은 링크가 걸린다. **보드 교체 시 규칙도 갱신한다.**
- **`ID_MM_DEVICE_IGNORE`** — 이 장비의 ModemManager가 `active`다. 시리얼 포트를
  모뎀으로 오인해 AT 명령을 탐침하면 DTR 토글로 나노가 리셋되고 수신 바이트가
  오염된다. 증상이 간헐적이라 원인 파악이 어려우므로 미리 막는다.
- `MODE="0660"` + `GROUP="dialout"`으로 `chmod 666` 임시 조치를 대체한다.
  `dialout` 그룹 가입은 **2026-07-29 반영 확인 완료**.
- config 기본값 변경은 **규칙 적용을 확인한 뒤** 한다. 규칙 없이 먼저 바꾸면 모든
  실행이 `FAULT_PORT_OPEN`이 된다.

> **설치는 사용자가 직접 해야 한다.** `sudo`가 TTY를 요구하는데 에이전트 셸에는
> TTY가 없고 askpass 헬퍼도 설치되어 있지 않다. 일반 터미널에서 실행한다.
>
> ```bash
> cd vica_ros2_ws/src/vica_user_guidance
> sudo cp udev/99-vica-smart-handle.rules /etc/udev/rules.d/
> sudo udevadm control --reload-rules && sudo udevadm trigger
> ls -l /dev/vica_smart_handle
> ```


### 9.3 다른 저장소·패키지로 넘길 항목

| 대상 | 항목 | 요청일 |
| --- | --- | --- |
| `vica_mission_manager` | **도착 후 로봇 대기 시간**을 설정 가능한 파라미터로 추가 | 2026-07-28 |

> `arrival_hold_sec`(이 패키지, 기본 4.0초)는 **핸들 LED에 도착 표시를 보내는 시간**일
> 뿐이며 로봇 동작에 전혀 영향을 주지 않는다. 이름이 비슷해 "도착 후 로봇이 정지한 채
> 기다리는 시간"으로 오해하기 쉬우나 완전히 별개다.
>
> 실제 로봇 대기 시간은 Mission Manager 소관이며 **현재 미구현**이다. Mission Manager
> 작업에 착수할 때 파라미터 이름과 기본값을 사용자와 정한다.

### 9.4 미검증 `[미검증]`

| 항목 | 사유 |
| --- | --- |
| 회전 임계값 25°/10°/0.6s | 실주행 측정 전. Phase 5에서 확정 |
| `/odom` yaw 품질 | AGENTS.md 6장이 D455 IMU 융합을 `[미검증]`으로 규정 |
| `servo_ok`/`*_led_ok` | 상향 통신이 없어 구조적으로 관측 불가 |
| 충전 상태(코드 6·7) | 미구현 |
| 햅틱 전체 | 장치 미장착 |

**2026-07-29 해소:** `LINK_LOST` 빨간색 표시와 워치독 1.5초 발동은 bench 8번을
전송 중단 방식으로 재작성해 검증했다(10.1절).

---

## 10. 진행 상태와 다음 작업

### 10.1 완료 (2026-07-28)

| Phase | 내용 | 검증 |
| --- | --- | --- |
| 4 | 펌웨어 확장 | 컴파일 + bench 7/8 PASS |
| 1 | `TurnGuide`·`SmartHandleState` msg | `colcon build` + `ros2 interface show` |
| 2 | 순수 로직 5개 모듈 + 테스트 | pytest 84 passed |
| 3 | 노드 2개 + launch + config | mock 통합 (상태 전이 로그 확인) |
| 5 | 펌웨어를 패키지 안으로 이동 | pytest 85 passed, 새 경로 컴파일 성공 |

mock 통합에서 확인한 전이:
`estop_stale→ESTOP` → `NORMAL` → `LEFT` → `NORMAL` → `RIGHT` → `NORMAL`,
도착 시 `ARRIVED` 4.0초 유지 후 복귀, `goal_failed`는 도착으로 오인하지 않음.

### 10.1b 실기 검증 완료 (2026-07-29)

| 항목 | 결과 |
| --- | --- |
| bench 8/8 | **PASS**. 8번을 전송 중단 방식으로 재작성해 `LINK_LOST`와 복구를 확인 |
| 실기 시리얼 | **PASS**. `enable_serial:=true`, `connected=true`, `fault_code=0`, `write_error_count=0` |

실제 시리얼로 확인한 전이(펌웨어가 실제로 LED·서보를 구동함을 육안 확인):

```
NORMAL → LEFT → NORMAL → RIGHT → NORMAL → ARRIVED → NORMAL → ESTOP → NORMAL
```

- 도착 유지 시간 **4.000초 실측** (`906.341` → `910.341`). 펌웨어 재생 3.5초보다
  길어 마지막 소등 프레임까지 온전히 재생된다. 2.1절 결함 대응이 실기에서 확인됐다.
- 회전 진입 지연 **0.79초** (30°/s 자극). 25° 임계 도달 이론값 0.83초와 일치한다.

#### 검증 중 겪은 함정 두 가지 — 둘 다 시험 환경 문제였고 제품 결함이 아니다

**① `/vica_goal_event`는 평문이 아니라 JSON이다.**
자극 스크립트가 평문 `"goal_succeeded"`를 발행해 도착이 조용히 무시됐다.
`parse_goal_event`가 `json.loads`에서 실패해 `None`을 반환한 것이다. 실제
`mission_manager_node._publish_goal_event`는 `{"event": ..., "location_id": ...}`
형태의 JSON을 발행한다. **이 계층을 시험할 때는 반드시 JSON으로 보낸다.**

> 파싱 실패 시 아무 로그도 남지 않아 원인 파악에 한 번의 디버깅 주기가 들었다.
> **2026-07-29 조치 완료** — `cb_goal`이 파싱 실패를 경고로 남긴다(payload 120자
> 표시, 5초 throttle). 실기 확인: 평문 payload → 경고 발생, 1초 뒤 다른 잘못된
> payload → 경고 없음(throttle 동작), 정상 JSON → 도착 4.000초 유지(회귀 없음).

**② `ros2 topic pub`가 종료되지 않고 남으면 상태가 진동한다.**
`{ ... } &` 로 띄운 퍼블리셔를 `kill $!` 하면 래퍼 서브셸만 죽고 실제
`ros2 topic pub`는 살아남는다. `/estop_state`에 `false`(10Hz)와 `true`(30Hz)가
동시에 들어와 ESTOP↔NORMAL이 10Hz로 진동했고, LED에 **하늘색과 주황색이 섞여**
보였다. `ros2 topic info <topic>`의 `Publisher count`로 확인한다.

### 10.2 브랜치 방침

| 저장소 | 브랜치 | 방침 |
| --- | --- | --- |
| 루트 (문서) | `dev` | 문서는 `dev`에 직접 커밋한다 |
| `vica_ros2_ws` | `feat/user-guidance` | **실주행 검증 완료 후 `dev`로 머지한다** |

> ROS 구현을 별도 브랜치에 두는 이유: 실기 검증이 끝나지 않은 코드가 `dev`에 들어가면
> 다른 팀원이 `dev`를 받아 쓸 때 미검증 상태임을 알기 어렵다. 브랜치로 격리해 경계를
> 명확히 한다. **머지 조건은 Phase 5(HIL) 통과다.**

### 10.3 남은 작업

1. **udev 규칙 설치**: 9.2절. **사용자가 일반 터미널에서 직접 실행한다**(sudo TTY).
   `/dev/vica_smart_handle` 링크를 확인한 **뒤에** config `serial_port`를 바꾼다.
2. **Phase 5 (HIL)**: AGENTS.md 5장 조건(바퀴 부양·주변 통제·물리 E-stop) 충족 시
   사용자 승인 후 진행. 회전 임계값 25°를 실주행으로 확정한다.
3. **`dev` 머지**: Phase 5 통과 후 `feat/user-guidance`를 머지한다(10.2절).

> 완료: ~~bench 8번~~, ~~실기 시리얼 검증~~ (2026-07-29, 10.1b절).

> Phase 5 전에 **`/odom` yaw 드리프트 측정**을 권한다. AGENTS.md 6장이 D455 IMU 융합을
> `[미검증]`으로 규정하므로, 정지 상태에서 yaw가 흔들리면 회전 오탐이 난다.
