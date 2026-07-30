# 스마트핸들 운영 모드 설계 결정 — 2026-07-30

> **상태**: 구현 전 설계 확정. 값들은 실기 테스트로 조정될 수 있다.
> **정본 반영**: `guideline/vica_scenario.md` §2-1은 아직 갱신하지 않았다. 구현·실기 검증이
> 끝난 뒤 한 번에 반영한다(현재 §2-1은 `[구현 목표]`이며 값을 "예: 3초"로 열어둔 상태다).
> **범위**: 스마트핸들 모드 전환과 손 놓음 처리만 담는다. 같은 날 조사한 nvblox 유령 장애물은
> `devlog/2026-07-30-nvblox-ghost-obstacle.md`에 별도로 있다.

---

## 0. 요약

`guideline/vica_scenario.md` §2-1이 `[구현 목표]`로 남겨둔 스마트핸들 활성/비활성 모드에 대해
다음을 확정했다.

1. **모드 진입에 LLM 질문 경로를 추가한다.** 기존 문서는 터치센서만으로 모드를 판정했다.
   LLM이 이용 의사를 묻고 YES일 때만 터치 활성화를 허용하는 **2단계 확인** 구조가 된다.
2. **손 놓음 정지는 E-stop이 아니라 일시정지(pause) 계열이다.** 이 결정으로
   `safety_supervisor_node` 수정이 불필요해졌다.
3. **판정 유예를 0.5초로 줄였다.** 문서 원안(유예 1~2초 + TTS + N초, 정상 속도 주행)의 이동
   거리 2.60 m가 0.14 m가 된다.

§4에 코드·설정으로 확인한 사실과 그것이 설계를 바꾼 지점을 남겼다. §6이 미정 항목이다.

---

## 1. 확정 설계 — 모드 전환

```text
[IDLE]
   │  LLM: "스마트 핸들을 이용하시겠습니까?"
   │      ※ 상향 통신이 끊겨 있으면 묻지 않는다 (§4.4)
   ├── NO ──▶ [비활성 모드] 터치와 무관하게 자율주행
   │                        터치로 활성화 불허 (§6-3)
   ▼ YES
[활성화 대기]
   │  터치센서 3초 연속 감지
   │  TTS "스마트 핸들 모드가 작동되었습니다. 핸들을 놓으시면 …"
   ▼
[활성 모드 주행]   knob 게이팅 활성 · LED·서보 피드백
   │
   │ 터치 미감지
   ▼
[판정 유예 0.5초]   센서 순간 끊김만 걸러낸다. 주행 유지
   │
   ├── 다시 감지 ──▶ [활성 모드 주행]   (아무 일도 없던 것처럼)
   │
   │ 여전히 미감지
   ▼
[정지·대기]   Nav2 goal 취소 + 목적지 보관 + 감속 램프
   │           LLM "손잡이를 잡아주세요" 반복 안내
   │           ※ Nav2 progress_checker(10초)보다 먼저 능동 취소해야 한다 (§4.1)
   │
   ├── 재접촉 ──▶ "다시 출발합니다" ──▶ [활성 모드 주행]  보관 목적지로 새 goal
   │              반복 횟수 제한 없음 (§6-4)
   │
   └── 중단 트리거 ──▶ [IDLE]  목적지 폐기
```

비활성 모드에서도 LED·서보 피드백은 그대로 준다. `user_guidance_driver_node`가 모드를
참조하지 않고 `/vica/turn_guide`만 구독하므로 **현행 구현 그대로이며 변경이 없다.**
모드에 따라 달라지는 것은 knob 게이팅뿐이다.

---

## 2. 확정값

| 항목 | 값 | 비고 |
| --- | --- | --- |
| 초기 활성화 터치 지속 | **3초** | 오인식 불가한 물리적 의사표시 |
| 판정 유예 (센서 노이즈 필터) | **0.5초** | 이동 13 cm |
| 정지 방식 | **goal 취소 + 목적지 보관** | E-stop 아님. §3 참조 |
| 재개 조건 | 재접촉 (초기 활성화보다 짧게) | 값 미정 |
| 반복 놓침·재개 | **제한 없음** | §6-4. 추후 N회 제한 가능 |
| LLM NO 직후 우발적 터치 활성화 | **불허** | 추후 수정 가능 |
| LED·서보 | 두 모드 모두 동작 (현행 유지) | 변경 0 |
| **잡아당겨 감속** | **두 모드 모두 유지** | 리코일 기반. 모드와 무관하게 항상 살아 있다 |
| knob 게이팅 | **`[미검증]`** | §4.7. 리코일 중립값 실측으로 결정 (§6.2) |
| 터치센서 배선 | **Normally Closed** | 단선 = 놓음 = 정지 (fail-safe) |
| 상향 프로토콜 | 1바이트 비트필드, 20 Hz 주기 발행 | 침묵 = 놓음 판정 가능 |

### 2.1 이동 거리 비교

`max_velocity: [0.26, 0.0, 1.0]` 기준이다.

| 방식 | 손 놓음부터 정지까지 | 누적 이동 |
| --- | --- | --- |
| 문서 원안 (유예 3초 + TTS 4초 + N 3초, 정상 속도) | 10초 | **2.60 m** |
| **확정안** (판정 유예 0.5초 + 감속 램프) | 0.6초 | **0.14 m** |

시각장애인이 핸들을 놓쳤을 때 2.60 m는 흰지팡이 탐색 범위를 넘는다. 0.14 m는 손을 뻗으면
닿는 거리다. **"사용자가 다시 잡을 시간"은 유예가 아니라 정지 후 대기가 담당한다**는 것이
이 개선의 핵심이다.

---

## 3. 손 놓음 정지가 일시정지여야 하는 이유

| | E-stop 경로 | 일시정지 경로 |
| --- | --- | --- |
| 정지 방식 | `/cmd_vel_safe = 0` 강제 | goal 취소 → 감속 램프 |
| 래치 | **중앙 래치** | 없음 |
| 해제 방법 | **관리자가 앱에서 reset** | **손을 다시 잡으면 됨** |
| 사용자 혼자 재출발 | **불가능** | 가능 |

E-stop으로 만들면 핸들을 놓칠 때마다 관리자를 불러 앱에서 초기화해야 하므로 시각장애인이
혼자 쓸 수 없다. `guideline/vica_system_health_monitoring_draft.md` §9.1도 활성 모드 터치
미감지의 재개 조건을 "**터치 재감지** 또는 새 주행 승인"으로 적어두었다.

**결과: `safety_supervisor_node`를 수정하지 않는다.** 초기 검토에서 가장 무거운 작업(E-stop
경로 전체 실기 재검증)으로 잡았던 항목이 빠졌다.

`safety_supervisor_node` 수정이 필요한 경우는 하나 남는다 — 핸들 **통신 단절**을 STOP 등급으로
올릴 때다. 이는 손 놓음과 다른 사건이다(§4.4).

### 3.1 E-stop 상호작용은 이미 처리되어 있다

`guideline/vica_architecture.md:687`이 규정한다.
> E-stop이 활성화되면 보관분을 폐기해 "E-stop 해제 후 이전 Goal을 자동 재개하지 않는다"는
> 원칙을 유지한다.

대기 중 비상정지가 걸리면 보관 목적지가 폐기된다. 추가 작업이 없다.

---

## 4. 코드·설정으로 확인한 사실

설계를 바꾼 근거들이다.

### 4.1 Nav2 progress_checker가 10초 후 goal을 abort한다

```yaml
# vica_nav2/config/nav2_params.yaml:134-137
progress_checker:
  plugin: "nav2_controller::SimpleProgressChecker"
  required_movement_radius: 0.5
  movement_time_allowance: 10.0
```

**10초 안에 0.5 m 이상 움직이지 않으면 Nav2가 스스로 goal을 실패 처리한다.**
"잡을 때까지 정지해 있고"를 goal을 살려둔 채 구현하면 10초 후 재개할 목표가 사라진다.

→ **판정 유예 직후 goal을 능동적으로 취소하고 목적지를 보관해야 한다.** 10초를 기다리면 안 된다.

### 4.2 `SetNavSpeedLimit`의 `0.0`은 정지가 아니라 제한 해제다

```python
# vica_mission_manager/vica_mission_manager/mission_logic.py:123-126
class SetNavSpeedLimit:
    """Nav2 controller 최대속도 제한율. 0.0은 제한 해제다."""
    percent: float
```

`/speed_limit`으로 완전 정지를 만들 수 없다. 0%를 주면 오히려 제한이 풀린다. 점진 감속을
`speed_limit`으로 구현하려면 10% 정도까지만 내리고 완전 정지는 goal 취소로 마감해야 한다.
확정안은 판정 유예를 0.5초로 줄였으므로 `speed_limit` 램프를 쓰지 않는다.

### 4.3 감속 램프는 0.1초·1.35 cm다

```yaml
# vica_nav2/config/nav2_params.yaml velocity_smoother
max_velocity: [0.26, 0.0, 1.0]
max_decel:    [-2.5, 0.0, -3.2]
velocity_timeout: 0.4
# safety_supervisor_node
cmd_timeout_sec: 0.5     # velocity_timeout(0.4) < 이 값 관계를 test_nav2_params_contract가 강제
```

`0.26 ÷ 2.5 = 0.104초`, `0.26² ÷ (2×2.5) = 1.35 cm`.
최고 속도가 0.26 m/s(시속 0.94 km)라서 어떤 감속률이든 사실상 즉시 정지다. 따라서 "천천히
감속"의 실질은 정지 방식이 아니라 **정지 후 대기**에 있다.

📌 **문서 불일치**: `guideline/vica_architecture.md:675`가 `max_decel`을 `[-1.0, 0.0, -1.2]`로
적고 있으나 실제 설정은 `[-2.5, 0.0, -3.2]`다. 별도 정합화가 필요하다.

### 4.4 상향 통신 단절은 손 놓음과 다른 사건이다

아두이노 → 젯슨 방향 시리얼 통신이 끊긴 상태다(USB 빠짐, 아두이노 리셋·멈춤, 포트 오류).

| | 손 놓음 | 통신 단절 |
| --- | --- | --- |
| 젯슨이 받는 것 | `user_contact = false` **데이터가 온다** | **아무 데이터도 안 온다** |
| 해결 방법 | 다시 잡으면 됨 | **다시 잡아도 해결 안 됨** |

**통신이 끊기면 "다시 잡았다"를 감지할 수단도 함께 사라진다.** 손 놓음과 같이 "일시정지 →
다시 잡으면 재개"로 처리하면 영원히 재개되지 않는다.

권고 등급 (팀 확정 필요, §6-1):

| 모드 | 등급 | 이유 |
| --- | --- | --- |
| 활성 모드 (주행 중) | **STOP** | 손 놓음을 감지할 수단이 사라졌다 |
| 비활성 모드 | **DEGRADED** | 핸들을 쓰지 않는 모드다. LED·서보 안내만 잃는다 |

ESTOP은 과하다. 통신 단절은 폭주가 아니고 로봇은 이미 정지 상태다. 게다가 ESTOP은 관리자 앱
reset이 필요해 사용자가 혼자 쓸 수 없게 된다.

**파생 규칙**: 통신이 끊긴 상태에서는 LLM이 "핸들 쓰시겠습니까?"를 **묻지 않는다.** 물어서
YES를 받아도 터치 3초를 감지할 수 없어 활성화되지 않고, 사용자는 이유를 알 수 없다.
"핸들 연결에 문제가 있어 일반 안내로 진행합니다"를 안내한다.

### 4.5 현재 상향 통신이 존재하지 않는다

| 위치 | 현재 | 확인 |
| --- | --- | --- |
| 아두이노 펌웨어 | `Serial.available()` / `Serial.read()`만. 송신 코드 없음 | `smart_handle_firmware.ino:194,209,210` |
| 젯슨 | `self._port.write(bytes([state_code]))`만. `read` 없음 | `serial_link.py:87` |
| 프로토콜 | 1바이트 **하향 전용** | `protocol.py` |
| `/vica/smart_handle_state` 구독자 | **0개** | 발행만 하고 아무도 듣지 않는다 |

터치센서를 달려면 상향 프로토콜 신설이 선행된다. MDROBOT CAN F1 경로에 얹는 대안은 배제했다 —
제조사 매뉴얼(PID 241) 확인 결과 D2/D3의 비트가 전부 모터 드라이버 기능 입력
(`INT_SPEED`, `ALARM_RESET`, `DIR`, `RUN/BRAKE`, `START/STOP`, `ENC_A/B`)이라 자유 비트가 없다.
물리 E-stop이 D2·D3의 BIT4(`START/STOP`, mask `0x10`)를 이중 확인으로 쓴다.

**상향 프로토콜 권고**: 하향과 대칭으로 1바이트 비트필드, **20 Hz 주기 발행**.

```text
bit 0 : user_contact       터치 감지          ← 지금 필요
bit 1 : servo_at_target    서보 도달          [나중]
bit 2 : haptic_ok          진동 동작 확인      [나중]
bit 3~: 예약
```

주기 발행이어야 **침묵을 고장으로 판정**할 수 있다. "변할 때만 보내기"로 하면 조용한 것이
"변화 없음"인지 "죽음"인지 구분되지 않는다. 아두이노는 이미 반대 방향에 같은 패턴을 쓴다
(`FIRMWARE_WATCHDOG_TIMEOUT_MS = 1500`, 젯슨이 1.5초 조용하면 스스로 `LINK_LOST`).

### 4.6 3중 방어

| 겹 | 대상 | 실패 시 판정 |
| --- | --- | --- |
| 1. 배선 | 터치센서 Normally Closed | 단선 = 놓음 |
| 2. 프로토콜 | 상향 20 Hz + 타임아웃 | 침묵 = 놓음 |
| 3. 관측 | health monitor가 상향 링크 신선도 감시 | 앱에 "핸들 통신 고장" 표시 |

NC는 센서와 아두이노 사이만 지킨다. **아두이노가 죽거나 USB가 빠지면 NC와 무관하게 아무
신호도 오지 않으므로** 2번이 필요하다.

⚠️ **NC는 입력 개념이며 출력에는 그대로 적용되지 않는다.**

| 장치 | 전원·통신 끊김 시 | 문제 |
| --- | --- | --- |
| 터치센서 (입력) | 열림 → 놓음 판정 → 정지 | 안전 ✅ |
| LED (출력) | **꺼진다** | `vica_scenario.md` §7.1의 "통신 단절 = 빨간색 상시 점등" 규약이 작동하지 못한다 |
| 서보 (출력) | **무동력** (중립도 아님) | 방향 안내가 조용히 사라진다 |

→ **"LED가 완전히 꺼진 것도 이상 신호"**라는 별도 규약과 사용자·보호자 교육이 필요하다.

### 4.7 knob 26 %가 분기점이다 — 게이팅이 불필요할 수 있다

motor node에서 knob는 속도를 만드는 입력이 아니라 **속도 상한**이다.

```python
# mdrobot_can_keyboard_knob_node.py:482
allowed_linear = self.max_linear_mps * speed_ratio      # max_linear_mps 기본 1.0
limited_linear_x = clamp(raw_linear_x, -allowed_linear, allowed_linear)
```

| 파라미터 | 값 | 위치 |
| --- | --- | --- |
| `max_linear_mps` | 1.0 (knob 100 % 기준 허용 속도) | `mdrobot_can_keyboard_knob_node.py:84` |
| `deadzone_pct` | 5 (이하는 정지) | 같은 파일 `:99` |
| Nav2 `max_velocity` | 0.26 m/s | `nav2_params.yaml` velocity_smoother |

가변저항은 **0~10 kΩ이 0~100 %로 선형 환산**된다.

Nav2가 요청한 0.26이 잘리지 않을 조건은 `1.0 × knob_pct/100 ≥ 0.26` → **`knob_pct ≥ 26 %`**

| knob 값 | 저항 | 동작 |
| --- | --- | --- |
| 26 % 이상 | 2.6 kΩ 이상 | **Nav2 속도에 아무 영향 없음** (상한이 요청보다 높다) |
| 5 ~ 26 % | 0.5 ~ 2.6 kΩ | Nav2 속도를 제한 — **잡아당겨 감속하는 구간** |
| 5 % 이하 | 0.5 kΩ 이하 | 정지 (deadzone) |

**따라서 모드별 knob 게이팅이 불필요할 수 있다.**

```text
리코일 중립값(핸들 미접촉 상태의 knob)이 26 % 이상이면
  → 비활성 모드: 자동으로 Nav2 속도 그대로. 게이팅 불필요
  → 잡아당김:    26 % 아래로 내려가 감속. 두 모드 모두 동작
  → 같은 코드로 두 모드가 성립한다
26 % 미만이면
  → 비활성 모드에서 로봇이 느려지거나 움직이지 못한다. 하한 적용이 필요하다
```

**리코일 중립값은 어디에도 문서화되어 있지 않다 `[미검증]`.** 코드 주석,
`mdrobot_can_control/README.md`, `guideline/*.md`, `docs/*.md`를 검색해 확인했다.
§6.2의 실측으로 확정한다.

**knob 값 사용과 F1 프레임 신선도 감시는 분리한다.** F1 미수신은 CAN 통신 이상이므로 모드와
무관하게 항상 정지 근거로 유지한다(`motor_watchdog.motor_speed_ratio`의 `knob_fresh`).
게이팅이 필요해지더라도 무시하는 것은 knob **값**이며 프레임 **수신 여부**가 아니다.
구현 시 순수 함수를 고치지 않고, 노드가 `knob_pct`만 덮어쓰고 `knob_last_ns`는 실제 수신
시각을 그대로 넘기는 방식을 쓴다.

---

## 5. 구현 시 영향 범위

| # | 작업 | 저장소 | 크기 | 비고 |
| --- | --- | --- | --- | --- |
| 1 | 터치센서 NC 배선 + 아두이노 읽기 | 하드웨어 | 작음 | |
| 2 | 상향 프로토콜 (펌웨어 송신 + 젯슨 수신) | `vica_ros2_ws` | 중간 | 신규 프로토콜 검증 |
| 3 | `SmartHandleState`에 상향 신선도 필드 추가 | `vica_ros2_ws` | 작음 | **공용 계약 변경** |
| 4 | `/vica/handle_mode` 신설 + 모드 상태 기계 | `vica_ros2_ws` | 중간 | **공용 계약 신설** |
| 5 | 손 놓음 → 기존 pause/resume 호출 | `vica_ros2_ws` | 작음 | **선행 조건 있음. §5.2** |
| 6 | motor node knob 게이팅 | `vica_ros2_ws` | 작음 | 속도 거동 변화 |
| 7 | LLM에 핸들 모드 질문·intent | `vica-voice-llm` | 작음 | |
| 8 | LED·서보 | — | **0** | 현행 유지 |
| ~~9~~ | ~~`safety_supervisor_node` 정지 판정~~ | — | **불필요** | §3 |

### 5.1 소유 구조

```text
아두이노 터치센서 (NC)
    │ 상향 시리얼 20 Hz
    ▼
user_guidance_driver_node          ← 상향 수신 추가. LED·서보는 현행 유지
    │ /vica/smart_handle_state
    ▼
mission_manager_node               ← 모드 상태 기계 + 손 놓음 pause 판정
    │  입력: LLM YES/NO, 터치 3초, 판정 유예 0.5초
    ├─▶ 기존 pause/resume
    ├─▶ /vica/handle_mode (신규) → motor node knob 게이팅
    └─▶ TTS 안내

safety_supervisor_node             ← 수정 불필요 (통신 단절 등급 확정 시에만)
robot_health_monitor_node          ← 관측만. 상향 링크 신선도 감시
```

정지 판정을 health monitor가 하지 않는 이유: 집계 지연 때문이다
(`vica_system_health_monitoring_draft.md` §3.1).

### 5.2 선행 조건 — `origin/app-UI/status-test` 병합

손 놓음 정지에 쓸 pause/resume이 **`origin/dev`에 없다.** 미병합 브랜치
`origin/app-UI/status-test`(`5d6d365`)에만 있다.

```text
origin/dev                : pause/resume 없음, MissionCommand.srv 없음
origin/app-UI/status-test : pause/resume 있음 (MissionLogic.paused_destination)
```

`guideline/vica_architecture.md:685-687`이 설명하는 "목적지를
`MissionLogic.paused_destination`에 보관하고 재개 요청 시 그 목적지로 새 goal을 만든다"가
정확히 필요한 기능이며, **새로 만들 필요가 없다.**

→ **스마트핸들 손 놓음 처리는 `app-UI/status-test` 병합 이후에 착수한다.**

---

## 6. 미정 항목 (팀 확정 필요)

| # | 항목 | 현재 | 필요한 결정 |
| --- | --- | --- | --- |
| 1 | 상향 통신 단절 등급 | 활성 STOP / 비활성 DEGRADED 권고 | 확정. STOP이면 `safety_supervisor_node` 수정 여부도 함께 |
| 2 | 대기 중 LLM 안내 반복 간격 | 미정 | 예: 10초. 한 번만 말하면 못 들었을 때 영원히 대기 |
| 3 | 재개 조건 (재접촉 지속 시간) | 미정 | 초기 활성화(3초)보다 짧게. 예: 0.5~1초 |
| 4 | **반복 놓침 처리** | **제한 없음 (원칙대로)** | **아래 참조** |
| 5 | 중단 트리거 | 미정 | 시간 제한 값 + 음성 취소 문구 + 앱 취소 |
| 6 | LLM NO 직후 활성화 억제 시간 | 미정 | "직후"의 길이 |
| 7 | **knob 게이팅 필요 여부** | **`[미검증]`** | **리코일 중립값 실측이 선행된다. §6.2** |
| 8 | 비활성 모드 knob 하한값 | 미정 | 7번이 "필요"로 나올 때만 결정한다 |

### 6.1 반복 놓침 — 지금은 제한하지 않는다

```text
놓침 → 정지 → 잡음 → 재개 → 놓침 → 정지 → 잡음 → 재개 → …
```

**현재 결정: 반복 횟수를 제한하지 않는다.** 사용자가 몇 번을 놓치든 다시 잡으면 재개한다.
단순하고, 사용자에게서 재개 권한을 빼앗지 않는다.

**`[TARGET]` — 추후 N회 제한을 도입할 수 있다.** 다음 두 상황을 무한 반복과 구별해야 할
필요가 실기에서 확인되면 도입한다.

| 실제 상황 | 증상 |
| --- | --- |
| 사용자가 잠깐 놓쳤다 | 1~2회. 정상 |
| **터치센서 접촉 불량** | 계속 반복. 장치 고장으로 판정해야 한다 |
| **사용자가 잡을 수 없는 상태** | 계속 반복. 사람을 불러야 한다 |

도입 시 형태: 짧은 시간 창(예: 60초) 안에 N회(예: 3회) 반복되면 재개를 멈추고
"핸들 연결에 문제가 있는 것 같습니다" 안내 후 비활성 모드로 전환하거나 안내를 중단한다.
초안 §11의 복구 재시도 횟수 관리와 같은 구조다.

### 6.2 실측 대기 항목 — 리코일 중립 knob 값 `[미검증]`

**§4.7의 knob 게이팅 필요 여부가 이 측정 하나로 결정된다.** 구현 착수 전에 재는 것이 좋다.

가변저항은 **0~10 kΩ이 0~100 %로 선형 환산**된다. 따라서 두 방법 중 하나로 잴 수 있고,
방법 A가 훨씬 간단하다.

#### 방법 A — 멀티미터로 저항 측정 (권장)

**로봇을 실행할 필요가 없다.** 장비도 Jetson이 필요 없다. 핸들의 가변저항 단자에 멀티미터를
대고 아래 네 상태의 저항을 읽는다.

| knob % | 저항 | 의미 |
| --- | --- | --- |
| 100 % | 10 kΩ | 상한 1.0 m/s |
| **26 %** | **2.6 kΩ** | **Nav2의 0.26 m/s와 같아지는 지점** |
| 5 % | 0.5 kΩ | deadzone. 이하는 정지 |
| 0 % | 0 kΩ | 정지 |

#### 방법 B — 로그로 확인 (Jetson)

CAN 경로까지 함께 검증하려면 이 방법을 쓴다. 바퀴 무부하, 주변 통제, 물리 E-stop 확보.
주행하지 않는다. motor node가 knob1을 로그로 출력한다
(`mdrobot_can_keyboard_knob_node.py:556` `f"knob1={self.knob1:3d}%"`).

```bash
ros2 launch mdrobot_can_control motor_bringup.launch.py
```

#### 측정 항목

| # | 측정 상태 | 저항 | knob % | 판정에 쓰는 곳 |
| --- | --- | --- | --- | --- |
| 1 | **핸들 미접촉 (리코일 중립)** | ? kΩ | ? % | **게이팅 필요 여부** |
| 2 | 핸들을 가볍게 잡음 | ? kΩ | ? % | 잡기만 해도 감속하는지 |
| 3 | 감속 의도로 당김 | ? kΩ | ? % | 사용자가 실제로 감속시킬 수 있는지 |
| 4 | 최대로 당김 | ? kΩ | ? % | 정지 가능 여부 |

#### 판정 기준

| 1번 값 | 결론 |
| --- | --- |
| **2.6 kΩ (26 %) 이상** | **게이팅 불필요.** 두 모드가 같은 코드로 동작한다. §6 항목 7·8이 닫힌다 |
| 2.6 kΩ 미만 | **게이팅 필요.** 비활성 모드 하한값(§6 항목 8)을 정해야 한다 |

#### 함께 확인할 것

- **4번이 0.5 kΩ 이하에 도달하지 못하면 사용자가 당겨서 완전히 정지시킬 수 없다.**
  안전 항목이다. `deadzone_pct` 조정 또는 리코일 기구 조정이 필요하다.
- 2번이 이미 2.6 kΩ 미만이면 핸들을 잡는 것만으로 감속이 걸린다. 활성 모드에서 의도한
  동작인지 확인이 필요하다.
- 방법 A와 B의 값이 다르면 CAN 전송·환산 경로에 문제가 있다는 뜻이다.
- 측정값은 이 devlog에 추가 기록하고, 확정 후 `guideline/vica_scenario.md` §2-1의
  `[미검증]` 표기를 해소한다.

---

## 7. `guideline/vica_scenario.md` §2-1과의 차이

정본 반영 시 반드시 다룰 항목이다.

| 항목 | 현재 문서 | 이 결정 |
| --- | --- | --- |
| 모드 판정 입력 | 터치센서만 | **LLM 질문 + 터치센서 (2단계)** |
| 활성화 지속 | "예: 3초" | **3초 확정** |
| 손 놓음 유예 | "짧은 유예(예: 1~2초)" | **판정 유예 0.5초** (목적 재정의) |
| 유예 후 | TTS 안내 → N초 → 감속 정지 | **즉시 정지 → 무한 대기 → 안내 반복** |
| 재개 | 명시 없음 | **재접촉 시 보관 목적지로 재개** |
| 정지 등급 | "STOP `[TARGET]`" | **일시정지(pause) 계열로 확정** |
| 모드 판정 담당 노드 | "미정 `[TARGET]`" | **`mission_manager_node`** |
| 비활성 모드 knob | "knob 값을 읽지 않고(또는 기존 디폴트값 고정)" | **잡아당겨 감속은 두 모드 모두 유지.** 게이팅 필요 여부는 `[미검증]` (§4.7) |

LLM 질문 경로 추가는 **제품 시나리오 변경**이므로 GOVERNANCE §4에 따라 정본 반영 전에 승인이
필요하다.

---

## 8. 관련 파일

```text
guideline/vica_scenario.md                      # §2-1 운영 모드, §7.1 장치 역할
guideline/vica_architecture.md                  # §10.3.1 취소·일시정지·재개, :675 max_decel 불일치
guideline/vica_system_health_monitoring_draft.md # §8.3 핸들 감지, §9.1 등급, §19 팀 확정 항목

vica_ros2_ws/src/vica_interfaces/msg/SmartHandleState.msg
vica_ros2_ws/src/vica_user_guidance/vica_user_guidance/{serial_link,protocol}.py
vica_ros2_ws/src/vica_user_guidance/firmware/smart_handle_firmware/smart_handle_firmware.ino
vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py   # :123 SetNavSpeedLimit
vica_ros2_ws/src/vica_nav2/config/nav2_params.yaml                            # :134 progress_checker
vica_ros2_ws/src/vica_safety/vica_safety/{safety_supervisor_node,emergency_stop_node}.py
source_file/MDROBOT-CAN communication protocol on controllers[KR].pdf         # PID 241 정의
```
