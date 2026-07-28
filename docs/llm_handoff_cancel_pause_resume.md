# LLM 담당자 인수인계: 목적지 취소 · 일시정지 · 다시 출발

작성일: 2026-07-27
대상: `vica-voice-llm` 담당자
관련 저장소: `vica_ros2_ws`(Mission Manager, 인터페이스), `VICA_Supervisor`(앱, 상태 노드)

---

## 0. 세 줄 요약

1. 안내 중인 로봇을 **취소 / 일시정지 / 다시 출발** 시킬 수 있게 만들었다.
2. 앱 버튼 쪽은 다 됐고, **음성으로 시키는 부분만 LLM에서 채워주면 된다.**
3. LLM이 할 일은 `VicaIntent.msg`의 `intent` 필드에 **`cancel` / `pause` / `resume`
   세 문자열 중 하나를 넣어 발행**하는 것뿐이다. 메시지 구조는 안 바뀐다.

---

## 1. 왜 만들었나

지금까지 움직이는 로봇을 멈추는 방법은 **비상정지밖에 없었다.**

그런데 비상정지는 안전 장치다. 한 번 걸리면

- 중앙 래치가 걸려 모터 출력이 0으로 유지되고
- **로그인한 관리자가 앱에서 reset을 해야만** 풀린다.

즉 사용자가 "아, 그냥 안 갈래요" 하고 마음을 바꾼 상황에도 비상정지를 쓰면
관리자를 불러야 다시 쓸 수 있는 로봇이 된다. 이건 과하다.

그래서 **안전 사건이 아닌, 단순히 목표를 바꾸는 행위**를 위한 경로를 따로 만들었다.

---

## 2. 비상정지와 무엇이 다른가 (제일 중요)

| | 취소 / 일시정지 | 비상정지(E-stop) |
|---|---|---|
| 무엇인가 | **목표 철회** — 안 가겠다는 뜻 | **위험 차단** — 지금 위험하다는 뜻 |
| 어떻게 멈추나 | goal만 취소 → `velocity_smoother`가 부드럽게 감속 | `/cmd_vel_safe=0`으로 즉시 차단 |
| 래치 | 없음 | 중앙 래치가 걸림 |
| 푸는 방법 | **필요 없음** | 관리자가 앱에서 reset |
| 그다음 | 바로 새 목적지 요청 가능 | reset 전까지 아무것도 못 함 |

**판단 기준은 딱 하나다.**

> 위험한 상황인가? → 비상정지
> 그냥 마음이 바뀐 건가? → 취소 / 일시정지

### 감속은 누가 하나 (자주 오해하는 부분)

취소·일시정지에서 Mission Manager는 **Nav2 goal을 취소할 뿐 "감속하라"는 명령을 보내지
않는다.** goal이 취소되면 `controller_server`가 속도 명령 발행을 멈추고, 그 뒤를
`velocity_smoother`가 이어받아 마지막 속도에서 0까지 부드럽게 이어 붙인다.

```
cancelTask()  →  controller_server 발행 중단  →  velocity_smoother 감속 램프  →  정지
```

감속 세기는 `nav2_params.yaml`의 `velocity_smoother.max_decel`이 정하며 LLM과는 무관하다.
비상정지는 이 경로를 타지 않고 Safety가 출력을 직접 0으로 막는다.

애매하면 **비상정지 쪽이 안전하다.** 취소는 편의 기능이고 비상정지는 안전 장치라,
둘을 섞으면 안 된다.

### 기존 긴급어는 그대로 둔다

```
멈춰, 정지, 스탑, 스톱, 안돼, 위험해   → 지금처럼 비상정지 (건드리지 말 것)
```

이 단어들은 `ros_emergency_node`가 LLM보다 **먼저** 가로채서 처리한다.
새로 추가하는 `cancel` / `pause`는 이 목록과 겹치면 안 된다.

---

## 3. 세 가지 동작이 각각 무엇인가

### cancel (목적지 취소)

가던 목적지를 **버린다.** 로봇은 그 자리에 서고, 상태는 `IDLE`로 돌아간다.
다시 가려면 **처음부터 새로 요청**해야 한다.

> 예시 발화: "취소해줘", "안 갈래", "그만 갈래", "됐어요"

### pause (일시정지)

Nav2 goal은 취소하지만 **목적지를 기억해 둔다.** 로봇은 멈춰 서서 기다린다.

> 예시 발화: "잠깐만", "잠시만 기다려", "멈춰줘"(← 긴급어 "멈춰"와 혼동 주의)

### resume (다시 출발)

기억해 둔 목적지로 **다시 출발한다.** 사용자가 명시적으로 요청할 때만 재개한다.

> 예시 발화: "다시 출발해", "계속 가자", "이어서 가줘"

---

## 4. LLM이 해야 할 일

### 4-1. `VicaIntent.msg` — 구조는 안 바뀐다

**메시지 필드는 하나도 추가/삭제되지 않았다.** `intent` 필드에 넣을 수 있는
**값이 3개 늘어났을 뿐**이다.

```
# 기존
string intent    # navigate / question / clarify / unknown

# 지금
string intent    # navigate / question / clarify / unknown
                 # + cancel / pause / resume     ← 이 3개가 추가됨
```

전체 메시지는 그대로다.

```
string intent                  # ← 여기에 cancel / pause / resume 추가
string destination_candidate
string matched_destination_id
float32 confidence
bool need_confirm
string reply
string safety_flag
```

**따라서 `.msg` 파일을 고칠 필요도, 다시 빌드할 필요도 없다.**
(주석은 이미 갱신해 두었다.)

### 4-2. 세 값을 쓸 때 다른 필드는 어떻게 채우나

| 필드 | cancel / pause / resume 일 때 |
|---|---|
| `intent` | `"cancel"` / `"pause"` / `"resume"` |
| `destination_candidate` | `""` (빈 문자열) |
| `matched_destination_id` | `""` — **목적지를 찾을 필요가 없다** |
| `need_confirm` | `false` — 확인은 Mission Manager가 알아서 한다 |
| `confidence` | 평소대로 |
| `reply` | 비워도 된다. 멘트는 Mission Manager가 TTS로 내보낸다 |
| `safety_flag` | `"normal"` — 위험 상황이면 이건 비상정지 경로다 |

**`matched_destination_id`를 안 채워도 되는 이유**는, 이 세 요청의 대상이
"지금 진행 중인 안내"로 이미 정해져 있기 때문이다. 목적지를 새로 고를 일이 없다.

### 4-3. 취소는 되묻는다 — LLM이 확인 대화를 만들 필요 없다

`cancel`을 보내면 Mission Manager가 **바로 취소하지 않는다.**

```
사용자: "취소해줘"
  → LLM이 intent="cancel" 발행
  → Mission Manager가 TTS로 "안내를 취소할까요?" 되물음   ← 자동
  → 로봇은 계속 가고 있음                                 ← 중요
사용자: "응" 또는 "취소해"
  → LLM이 다시 intent="cancel" 발행
  → 이번엔 실제로 취소됨
```

**LLM은 확인 로직을 따로 만들 필요가 없다.** 사용자가 취소 의사를 말할 때마다
`cancel`을 보내면 된다. 첫 번째는 질문이 나가고, 두 번째는 실행된다.

30초 안에 답이 없으면 **취소하지 않고 안내를 계속한다.**

> 확인을 기다리는 동안에도 로봇은 계속 간다. 미리 멈췄다가 사용자가 "아니오"라고 하면
> 되돌릴 수 없기 때문이다.

### 4-4. `is_paused`로 상황을 알 수 있다

`/vica/robot_state`(`RobotState.msg`)에 **필드가 하나 늘었다.**

```
int32 current_floor
string current_building
bool is_moving
bool is_paused      ← 추가됨
```

기존 필드는 그대로라 **지금 코드는 안 고쳐도 그냥 돌아간다.**

다만 이 값을 쓰면 LLM이 더 똑똑해진다.

| `is_moving` | `is_paused` | 상황 | "다시 출발해"라고 하면 |
|---|---|---|---|
| true | false | 주행 중 | resume 보낼 필요 없음 |
| false | **true** | **일시정지 중** | **resume 보내면 됨** |
| false | false | 그냥 서 있음 | 재개할 게 없음 |

전에는 `is_moving=false` 하나뿐이라 **"일시정지 중"과 "그냥 서 있음"이 구분되지 않았다.**
`is_paused`를 프롬프트에 넣어주면 "다시 출발해"를 정확히 해석할 수 있다.

현재 `langchain_intent_parser.py`가 `is_moving`을 `"예"/"아니오"`로 프롬프트에
넣고 있으니, 같은 방식으로 한 줄 추가하면 된다.

---

## 5. 전체 흐름

```
사용자: "잠깐만"
   │
   ▼
LLM  →  /vica/intent  (intent="pause")
   │
   ▼
Mission Manager
   ├─ 지금 주행 중인가? 비상정지 아닌가?  ← 판정은 전부 여기서
   ├─ Nav2 goal 취소 + 목적지 보관
   ├─ TTS: "잠시 멈추겠습니다"
   ├─ /vica_goal_event  "goal_paused"
   └─ /vica/robot_state  is_paused=true
          │
          ├─→ 앱: '다시 출발' 버튼이 나타남
          └─→ LLM: 일시정지 중임을 인식

사용자: "다시 출발해"
   │
   ▼
LLM  →  /vica/intent  (intent="resume")
   │
   ▼
Mission Manager  →  보관해 둔 목적지로 다시 goal 발행
```

---

## 6. 조건 판정은 전부 Mission Manager가 한다

LLM은 **"사용자가 이런 말을 했다"고 전달만** 하면 된다.
가능한지 아닌지는 Mission Manager가 판단하고, 안 되면 이유를 TTS로 말해준다.

| 상황 | Mission Manager 응답 |
|---|---|
| 주행 중이 아닌데 취소 | "지금은 안내 중이 아닙니다." |
| 일시정지가 아닌데 재개 | "다시 출발할 안내가 없습니다." |
| 비상정지 중에 취소/재개 | "지금은 비상 멈춤 상태입니다. 해제 후 다시 말씀해 주세요." |

**LLM이 "지금 주행 중인가?"를 먼저 확인할 필요가 없다.** 확인하려 해도 LLM이 보는
상태는 1초에 한 번 오는 사본이라 최신이 아닐 수 있다. 그냥 보내면 된다.

---

## 7. 하면 안 되는 것

- **긴급어 목록에 "취소" 같은 단어를 넣지 말 것.**
  긴급어는 비상정지로 직행한다. 취소는 그 경로가 아니다.
- **`reply`에 긴급어를 넣지 말 것.**
  TTS로 나간 로봇 목소리를 다시 긴급어로 인식해 스스로 비상정지가 걸린다.
  (`test/test_spoken_text.py`가 이걸 막고 있다)
- **LLM이 Nav2나 `/cmd_vel`을 직접 건드리지 말 것.** 지금까지와 동일하다.
- **비상정지를 취소 용도로 쓰지 말 것.** 관리자 reset이 필요해진다.

---

## 8. 오늘 바뀐 것 전체 목록

### 새로 생긴 것

| 종류 | 이름 | 설명 |
|---|---|---|
| service | `/vica/mission/cancel_destination` | 목적지 취소 (앱이 호출) |
| service | `/vica/mission/pause_navigation` | 일시정지 (앱이 호출) |
| service | `/vica/mission/resume_navigation` | 다시 출발 (앱이 호출) |
| srv 타입 | `vica_interfaces/srv/MissionCommand` | 위 세 서비스가 공용으로 씀 |
| 이벤트 | `/vica_goal_event`의 `goal_paused` | 일시정지 알림 |
| 필드 | `RobotState.is_paused` | 일시정지 여부 |
| intent 값 | `cancel` / `pause` / `resume` | **LLM이 채울 부분** |
| 상태 | Mission Manager의 `PAUSED` | 목적지를 기억한 채 멈춘 상태 |

**토픽은 새로 만들지 않았다.** 기존 `/vica_goal_event`에 이벤트 이름만 늘렸다.

### 안 바뀐 것

- `VicaIntent.msg` 구조 (값만 추가)
- 비상정지 경로 전체
- `/vica/emergency`, `/emergency_stop`, `/cmd_vel_safe`
- LLM 코드 (한 줄도 안 고쳤다)

---

## 9. 확인 방법

인터페이스가 새로 생겼으므로 **빌드가 먼저 필요하다.**

```bash
cd vica_ros2_ws
colcon build --packages-select vica_interfaces vica_mission_manager
source install/setup.bash
```

수동으로 동작을 확인하려면:

```bash
# 일시정지 시켜보기
ros2 service call /vica/mission/pause_navigation \
  vica_interfaces/srv/MissionCommand "{request_id: '$(uuidgen)'}"

# 상태 확인 (is_paused: true 가 보여야 함)
ros2 topic echo /vica/robot_state

# 다시 출발
ros2 service call /vica/mission/resume_navigation \
  vica_interfaces/srv/MissionCommand "{request_id: '$(uuidgen)'}"
```

음성 경로를 흉내내려면 intent를 직접 발행해도 된다.

```bash
ros2 topic pub --once /vica/intent vica_interfaces/msg/VicaIntent \
  "{intent: 'pause', safety_flag: 'normal'}"
```

---

## 10. 현재 상태 (중요)

- Mission Manager 로직은 **단위 테스트 13개로 검증**했다
  (`test/test_mission_logic.py`의 `TestPauseResumeCancel`, `TestVoiceCancelConfirm`)
- **실기기 검증은 아직 안 했다.** `[미검증]`
- **LLM이 `cancel`/`pause`/`resume`을 발행하기 전까지 음성 경로는 동작하지 않는다.**
  앱 버튼으로만 쓸 수 있다.

---

## 11. 궁금하면 볼 파일

| 무엇 | 어디 |
|---|---|
| 판정 규칙 | `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py`의 `check_cancel_gate`, `check_pause_gate`, `check_resume_gate` |
| 음성 intent 분기 | 같은 패키지 `mission_manager_node.py`의 `_on_voice_mission_command` |
| 동작 예시 | `test/test_mission_logic.py`의 `TestPauseResumeCancel` |
| 메시지 정의 | `vica_ros2_ws/src/vica_interfaces/msg/VicaIntent.msg`, `RobotState.msg` |
