# 제안: 주행 실패를 관리자 앱까지 전달한다

- 작성: 2026-08-06 / TONY0043
- 대상: 로봇 팀 (`vica_ros2_ws/src/vica_system_monitor/` 소유자)
- 상태: **제안. 승인 전이며 코드는 아직 바꾸지 않았다.**
- 관련: `guideline/vica_system_health_monitoring_draft.md`, `devlog/2026-07-31-health-monitor-implementation.md`

---

## 0. 한 줄

주행이 실패해도 관리자 앱에는 아무 표시가 없다. 이미 실패 정보를 다 담고 있는
`/vica_goal_event`를 `robot_health_monitor_node`가 구독해 `/robot/events`로 중계하면,
**공용 메시지 계약을 바꾸지 않고** 앱까지 닿는다.

---

## 1. 문제

### 1.1 `State.FAILED`는 프로세스 밖으로 나가지 않는다

`vica_ros2_ws/src/vica_interfaces/msg/RobotState.msg`에는 상태 필드가 없다.

```
int32 current_floor
string current_building
bool is_moving
bool is_paused
```

`mission_manager_node.py:493-500`이 채우는 값은 두 개뿐이다.

```python
msg.is_moving = self.logic.state == State.NAVIGATING
msg.is_paused = self.logic.state == State.PAUSED
```

결과적으로 내부 상태 6개가 2비트로 뭉개진다.

| 내부 상태 | `is_moving` | `is_paused` |
| --- | --- | --- |
| `IDLE` | false | false |
| `ARRIVED` | false | false |
| **`FAILED`** | **false** | **false** |
| `ESTOPPED` | false | false |
| `PAUSED` | false | **true** |
| `NAVIGATING` | true | false |

일시정지만 `is_paused`로 탈출했고 나머지 넷은 구분되지 않는다. `RobotState.msg` 1행
주석이 이유를 말한다 — 이 메시지는 원래 감시용이 아니라 **"지금 몇 층이야?" 같은 사용자
질문에 LLM이 답하려고** 만든 것이다.

### 1.2 실패가 나가는 문은 두 개, 둘 다 앱으로 가지 않는다

```text
State.FAILED
   ├─ /vica/tts_request ──▶ 스피커 ("죄송합니다. 이동에 실패했습니다.")
   └─ /vica_goal_event ───▶ vica_user_guidance (LED·햅틱)
      {"event":"goal_failed", ...}      ✗ 앱은 이 토픽을 구독하지 않는다
```

### 1.3 앱이 구독하는 상태 토픽에는 발행자가 없다

`VICA_Supervisor/lib/core/app_settings.dart:24`

```dart
this.robotStatusTopic = '/robot_status',
```

`/robot_status`는 `vica_ros2_ws/`, `vica-voice-llm/`, `vica-wakeword/` 전체에서 발행자가
**0건**이다. 미션 매니저는 `/vica/robot_state`로 보내고 앱은 `/robot_status`를 본다.
이름이 다르다. **[GAP]**

부수 영향: `current_location_screen.dart:100`의 "주행 상태" 표시는 이 경로에서 값을 받으므로
현재 채워지지 않는다.

### 1.4 중계 노드가 내용을 읽지 않는다

`robot_health_monitor_node.py:257`

```python
def handle_robot_state(self, _msg: RobotState) -> None:
    """Track the mission heartbeat."""
    self.last_robot_state_ns = self.steady_clock.now().nanoseconds
```

인자 이름의 밑줄(`_msg`)이 말하듯 내용은 쓰지 않는다. 수신 시각만 찍는다.

### 1.5 그래서 관리자 화면은 계속 "정상"이다

미션 매니저가 1 Hz로 `robot_state`를 계속 보내므로 **박동은 살아 있다.** 모니터는 결함
없음으로 판정한다.

| 실제 상황 | 관리자 앱 |
| --- | --- |
| 로봇이 갇혀 몇 분째 못 움직임 | 정상 |
| 시각장애인 사용자가 손잡이를 잡고 서 있음 | 정상 |
| Nav2 ABORT | 정상 |

---

## 2. 왜 이렇게 됐나

감시 체계를 갈아탄 흔적이다. 앱은 옛 배선을 지우지 않았고, 새 배선에는 주행 실패가
연결되지 않았다.

| 시점 | 사건 |
| --- | --- |
| 2026-06-25 | `vica_status` 노드 생성 → `/robot_status` 발행. 앱이 여기에 맞춰짐 |
| 2026-07-24 | `/vica_goal_event` 도입 (mission flow) |
| 2026-07-30 | `robot_health_monitor_node` 도입 → `/robot/health` + `/robot/events` |
| — | `vica_status_app_node`는 제거됨. 코드에는 주석 참조만 남음 |

`devlog/2026-07-31-health-monitor-implementation.md`가 배경을 적어 두었다 — 옛 앱 오류
표시는 ERROR 첫 문자열 하나였고, 부품·등급·조치·횟수가 전부 없었다. 새 체계는 그것을
해결했지만 **입력이 `/diagnostics` 계열로 한정**됐고, 주행 실패는 그 계열이 아니다.

---

## 3. 제안

### 3.1 왜 `RobotState` 확장이 아닌가

| 방안 | 계약 변경 | 앱 변경 | 정보량 |
| --- | --- | --- | --- |
| `RobotState.msg`에 상태 필드 추가 | **필요** (공용 메시지, 3저장소 영향) | 필요 | 상태 코드만 |
| **`/vica_goal_event` → `/robot/events` 중계** | **불필요** | **불필요**(조건부, 4절) | 목적지·사유·시각 포함 |

`/vica_goal_event`의 payload는 `mission_manager_node.py:626-643`에서 이미 다음을 담는다.

```json
{"event":"goal_failed", "map_id":"...", "location_id":"...", "destination_id":"...",
 "name":"화장실", "x":..., "y":..., "yaw":..., "reason":"Nav2 task failed",
 "timestamp":"2026-08-06T14:22:31"}
```

관리자에게 필요한 것이 전부 들어 있다. **새로 만들 데이터가 없다.**

### 3.2 변경 범위

전부 `vica_ros2_ws/src/vica_system_monitor/` 안이다.

| 파일 | 변경 |
| --- | --- |
| `robot_health_monitor_node.py` | `/vica_goal_event` 구독 추가, 실패 이벤트를 보류 상태로 기록 |
| `fault_catalog.py` | `NAV_GOAL_FAILED` 항목 추가 |
| `health_logic.py` | `evaluate()`에 `extra_faults` 인자 추가 (3.4 참조) |
| `test_fault_catalog.py` 외 | 위에 대응하는 테스트 |

JSON 파서는 새로 쓸 필요가 없다. `vica_user_guidance/guidance_priority.py:39`의
`parse_goal_event()`가 같은 계약을 이미 다룬다(예외를 던지지 않는 방어 포함). 같은 형태로
복제하거나 공용 위치로 옮긴다.

### 3.3 새 fault code (초안)

`fault_catalog.py`의 `navigation` 절에 추가한다. 현재 이 컴포넌트에는
`NAV2_NOT_ACTIVE` 하나뿐이다.

```python
'NAV_GOAL_FAILED': FaultSpec(
    'navigation',
    SEVERITY_DEGRADED,          # 3.5의 결정 대상
    '{name}까지 가지 못했습니다. 사유: {reason}',
    '로봇 주변에 장애물이 있는지 확인해 주세요.',
),
```

대상 이벤트는 두 개다.

- `goal_failed` — Nav2 ABORT (경로 없음 / 복구 소진 / 갇힘)
- `goal_rejected` — Nav2가 goal 자체를 거부

`goal_succeeded`, `goal_canceled`, `goal_sent`, `goal_accepted`는 정상 흐름이므로 제외한다.

### 3.4 결정 필요 ① — 일회성 사건을 지속 상태로 바꾸는 방법

**이것이 이 제안의 핵심 설계 문제다.**

현재 감시 계층은 **지속 상태**를 다룬다. `publish_health()`가 매 tick마다 "지금 참인 결함"의
목록을 만들고, `EventDeduplicator.update()`가 이전 tick과 비교해 RAISED / CLEARED를 낸다.
이번 tick에 없는 결함은 **해소된 것으로 처리한다**(`event_deduplicator.py` 규칙 4).

그런데 `goal_failed`는 **한 번 오고 끝나는 사건**이다. 받은 tick에만 observation을 넣으면
바로 다음 tick에 CLEARED가 나가 RAISED/CLEARED가 붙어서 지나간다.

제안: **보류 시간(hold)** 을 둔다.

```text
goal_failed 수신 → nav_failure_until_ns = now + hold_ns
publish_health() 매 tick: now < nav_failure_until_ns 이면 fault를 목록에 넣는다
```

`hold_sec`은 파라미터로 두고 기본값을 정한다. 30~60초 범위를 제안하되 **적정값은 로봇 팀
판단이다.** 짧으면 관리자가 앱을 보기 전에 사라지고, 길면 이미 해결된 실패가 남는다.

삽입 지점에 주의가 필요하다. `publish_health()`가 만든 observation 목록에 그냥 덧붙이면
`_to_health_msg()`의 `active_faults`(dedup 출처)에는 들어가지만
`highest_severity`·`primary_fault_code`(snapshot 출처)에는 반영되지 않아 **한 메시지 안에서
값이 어긋난다**. 그래서 `evaluate()`가 추가 fault를 받도록 인자를 늘리는 쪽을 제안한다.

```python
def evaluate(probes, safety, now_ns, started_ns, extra_faults=()) -> HealthSnapshot:
```

`navigation` 이름으로 probe를 하나 더 만드는 방법은 쓰지 않는다 —
`health_logic.py:140`의 `readiness[item.name]`이 같은 이름을 덮어써 기존 `NAV2_NOT_ACTIVE`
판정을 망가뜨린다.

### 3.5 결정 필요 ② — 등급

앱은 등급에 따라 **표시 위치가 다르다**. `VICA_Supervisor/lib/core/fault_severity.dart:47`

```dart
bool get blocksDriving => value >= FaultSeverity.stop.value;
```

`supervisor_provider.dart:688`이 이 값으로 거른다. **STOP(3) 이상만 알림 목록에 남고**,
WARN·DEGRADED는 진단 화면 이력에만 들어간다. 그 필터에는 근거 주석이 달려 있다 —
"WARN·DEGRADED까지 넣으면 알림이 진단 화면과 중복되면서 정작 중요한 항목이 묻힌다."

여기서 의미와 효과가 충돌한다.

| 안 | 의미 | 효과 |
| --- | --- | --- |
| DEGRADED(2) | 정확하다. 로봇은 새 goal을 받을 수 있다 | 알림이 안 뜬다 |
| STOP(3) | 부정확하다. "안전 확인 전 주행 불가"가 아니다 | 알림이 뜬다 |
| **DEGRADED → 반복 시 STOP 승격** | **정확하다** | **반복될 때만 뜬다** |

세 번째를 제안한다. 한 번의 실패는 흔한 일이고, **같은 자리에서 반복되는 실패가 곧
갇힘**이다. `EventDeduplicator`는 `occurrence_count`와 `TRANSITION_ESCALATED`를 이미
지원하므로(`event_deduplicator.py:144`) 기존 기계를 그대로 쓴다.

승격 임계값(예: 연속 2회 또는 3회)은 로봇 팀이 정한다.

---

## 4. 앱은 수정하지 않아도 된다 — 단, 조건부

`supervisor_provider.dart:223-227`이 `/robot/events`를 `vica_interfaces/msg/RobotEvent`
타입으로 이미 구독하고 있고, `_handleRobotEvent`(677행)가 파싱·표시까지 처리한다.
**새 fault code가 와도 앱 코드 변경 없이 표시된다.**

조건은 3.5다. 알림까지 띄우려면 등급이 STOP 이상이어야 한다.

별건으로, 1.3의 `/robot_status` 죽은 구독은 앱 팀이 따로 정리할 사항이다. 이 제안의 범위가
아니다.

---

## 5. 검증

노트북에서 가능한 것:

1. `fault_catalog` / `health_logic` / `event_deduplicator`는 ROS 의존이 없는 순수 모듈이다.
   `colcon test --packages-select vica_system_monitor`로 검증한다.
2. 보류 시간 동작(RAISED 1회 → hold 유지 → CLEARED 1회)을 단위 테스트로 고정한다.
3. `goal_succeeded` 등 정상 이벤트가 결함을 만들지 않는지 테스트로 고정한다.

실기(Jetson)가 필요한 것 — **[미검증]**:

4. 실제 갇힘 상황에서 ABORT → `/robot/events` → 앱 표시까지의 종단.
5. 관리자가 알림을 보기까지 걸리는 실제 시간.

---

## 6. 범위 밖

이 제안은 **알리는 것**만 다룬다. 다음은 별건이다.

- **갇힘에서 빠져나오는 수단.** 후진은 planner·controller·BT 3중으로 차단돼 있고
  (`nav2_params.yaml:1170`, `test_recovery_bt_contract.py`) 그 근거는 유효하다 —
  핸들 뒤에 사람이 따라온다. `docs/nav2_backlog.md` §9가 `BackUp` 복구와 후방
  Collision Monitor를 모두 **닫힌 축**으로 확정했다. 다만 `behavior_plugins`에
  `backup`이 남아 있어 (`nav2_params.yaml:1394`) `/backup` 액션 서버는 살아 있다.
  관리자가 뒤를 확인한 뒤 명시적으로 호출하는 "탈출 후진"은 §9와 정면으로 부딪히므로
  **제안하지 않는다.** 후방을 볼 수단이 없다는 것이 §9의 근거이고, 그 조건은 그대로다.
- **갇힘의 다른 원인.** `docs/nav2_backlog.md` **B1(AMCL 튜닝)** 이 자기잠금으로 인한
  20초 갇힘을 최우선 항목으로 잡고 있다. 이 제안이 다루는 "실패를 알리는 것"과 층이
  다르며 서로 독립이다.
- **실패 전 침묵.** 갇힌 뒤 ABORT까지 사용자에게 아무 안내가 없다. 이것은 음성 저장소
  (`vica-voice-llm/`) 몫이며 이 제안과 독립적으로 진행한다.
- **`RobotState.msg` 확장.** 3.1에서 채택하지 않았다. 다른 목적으로 필요해지면 그때 별도
  안건으로 올린다.

---

## 7. 로봇 팀에 요청하는 결정

1. 이 중계를 `vica_system_monitor`가 맡는 것에 동의하는가?
2. `hold_sec` 기본값 (3.4)
3. `NAV_GOAL_FAILED` 등급과 승격 임계값 (3.5)
4. `evaluate()`에 `extra_faults` 인자를 추가하는 방식에 동의하는가? 다른 삽입 지점을
   선호한다면 어디인가?
