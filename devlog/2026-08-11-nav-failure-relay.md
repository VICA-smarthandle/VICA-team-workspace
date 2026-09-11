# 2026-08-11 · 주행 실패를 관리자 앱까지 전달 — 구현과 실기 검증 절차

`docs/proposal_nav_failure_to_app.md`(2026-08-06 제안, 승인 대기였음)를 구현했다.
**판정 전이다.** 결과는 8절 표에 채운다.

| 항목 | 값 |
| --- | --- |
| 저장소 | `vica_ros2_ws` |
| 브랜치 | `feat/nav-failure-to-app` |
| 커밋 | `c6e3433` |
| 변경 | 8 files, +698 / −3 |
| 앱 변경 | **없음** |
| 공용 메시지 변경 | **없음** |
| 노트북 시험 | 248 passed / 1 skipped (이전 221). 신규 25건 |

---

## 1. 무엇이 문제였나

주행이 실패해도 관리자 앱에는 아무 표시가 없었다. 실패가 나가는 문이 둘인데 **둘 다 앱으로
가지 않는다.**

```text
State.FAILED ─┬─ /vica/tts_request ──▶ 스피커 "이동에 실패했습니다"
              └─ /vica_goal_event ───▶ 손잡이 LED·햅틱     ✗ 앱은 이 토픽을 안 본다
```

그런데 미션 매니저가 1 Hz로 `robot_state`를 계속 보내므로 **박동은 살아 있다.** 감시 계층은
결함 없음으로 판정한다.

| 실제 상황 | 관리자 앱 |
| --- | --- |
| 로봇이 갇혀 몇 분째 못 움직임 | 정상 |
| 시각장애인이 손잡이를 잡고 서 있음 | 정상 |
| Nav2 ABORT | 정상 |

**앱의 수신 경로는 이미 다 있었다.** `supervisor_provider.dart:223`이 `/robot/events`를
구독하고 `_handleRobotEvent`(677행)가 파싱·표시까지 한다. 없던 것은 **주행 실패를 그
파이프에 얹는 쪽**이다.

모니터가 구독하던 토픽은 넷뿐이었고 `/vica_goal_event`가 없었다.

```
/diagnostics_agg   /emergency_stop   /safety_state   /vica/robot_state
```

## 2. 일회성 사건을 지속 상태로 — 이 구현의 핵심

감시 계층은 **지속 상태**를 다룬다. 매 tick "지금 참인 결함" 목록을 다시 만들고, 이번 tick에
없는 결함은 해소로 처리한다(`event_deduplicator` 규칙 4).

`goal_failed`는 **한 번 오고 끝나는 사건**이다. 받은 tick에만 넣으면 바로 다음 tick에
CLEARED가 나가 RAISED/CLEARED가 붙어서 지나간다 — 관리자가 볼 틈이 없다.

그래서 **보류 창**을 둔다. 이 창은 두 가지 일을 한다.

1. 창이 닫힐 때까지 결함을 붙들어 관리자가 볼 시간을 번다
2. **"반복"의 정의가 된다** — 창이 열려 있는 동안 또 실패하면 같은 곤경이다

반복 판정에 별도 기준("몇 초 안에 몇 번")을 두지 않은 이유는, 값이 둘이 되면 서로 어긋날 수
있고 어느 쪽이 이기는지 모호해지기 때문이다.

## 3. 결정한 값과 근거

제안서 §7이 로봇 팀에 물은 4건이다. 2026-08-11에 사용자 판정과 함께 닫았다.

| # | 미결 | 결정 | 근거 |
| --- | --- | --- | --- |
| 1 | 중계를 `vica_system_monitor`가 맡는가 | **예** | 앱이 이미 `/robot/events`를 구독한다. 새 경로를 만들 이유가 없다 |
| 2 | `hold_sec` 기본값 | **60.0** | `reminder_interval_sec`(30.0)의 2배라 창 안에서 재알림이 **정확히 한 번** 끼어든다. 관리자가 볼 기회가 RAISED와 REMINDER 두 번이다 |
| 3 | 등급과 승격 임계값 | **DEGRADED → 창 안 2회째 STOP** (사용자 판정) | 의미가 정확하고(로봇은 새 goal을 받을 수 있다) 반복될 때만 알림이 뜬다 |
| 4 | `evaluate()`에 `extra_faults` | **동의** | 아래 4절 |

### 왜 hold가 재알림보다 길어야 하는가

창이 `reminder_interval_sec`보다 짧으면 RAISED 한 번만 나가고 닫힌다. 관리자가 그 순간
앱을 보고 있지 않으면 놓친다. 이 관계를 계약 시험
`test_navigation_failure_hold_outlives_one_reminder`가 잠근다.

## 4. 삽입 지점 — 왜 `extra_faults`인가

`publish_health()`가 만든 observation 목록에 그냥 덧붙이면 안 된다. 그렇게 하면
`active_faults`(dedup 출처)에는 들어가지만 `highest_severity`·`primary_fault_code`
(snapshot 출처)에는 반영되지 않아 **한 메시지 안에서 값이 어긋난다**(제안서 3.4절).

`navigation` 이름으로 probe를 하나 더 만드는 방법도 쓰지 않는다 — `health_logic.py`의
`readiness[item.name]`이 같은 이름을 덮어써 기존 `NAV2_NOT_ACTIVE` 판정을 망가뜨린다.

```python
def evaluate(probes, safety, now_ns, started_ns, extra_faults=()) -> HealthSnapshot:
```

**`extra_faults`는 readiness를 건드리지 않는다.** `NAV2_NOT_ACTIVE`가 "스택이 없다"라면
이쪽은 "스택은 멀쩡한데 못 갔다"다. goal 하나가 실패해도 Nav2 lifecycle은 active이고 다음
goal을 받는다. readiness까지 끌어내리면 관리자가 "주행 스택이 죽었다"로 오해한다.
`test_extra_faults_do_not_touch_readiness`가 이것을 잠근다.

## 5. 등급을 승격시키는 이유

앱은 **STOP(3) 이상만 알림 목록에 남긴다**(`fault_severity.dart:47` `blocksDriving`,
`supervisor_provider.dart:689` 필터). 그 필터에는 근거 주석이 달려 있다 — *"WARN·DEGRADED까지
넣으면 알림이 진단 화면과 중복되면서 정작 중요한 항목이 묻힌다."*

즉 **승격 여부가 곧 알림 여부**다.

등급만 올리고 `fault_code`는 그대로 둔다. 그래야 `EventDeduplicator`가
`TRANSITION_ESCALATED`를 낸다 — 다른 문제가 새로 생긴 것이 아니라 **같은 문제가 나빠진
것**이기 때문이다. 코드를 나누면 키가 달라져 "하나 해소 + 하나 발생"으로 보인다.

`test_escalation_keeps_the_same_fault_code`가 잠근다.

## 6. 노트북 실측 — 실제 노드로 확인

빌드 후 모니터를 띄우고 `/vica_goal_event`에 이벤트를 직접 발행해 종단을 확인했다.

| 보낸 것 | `/robot/health` | 문구 |
| --- | --- | --- |
| `goal_succeeded` | **결함 없음** | — |
| `goal_failed` | `severity=2` | `화장실까지 가지 못했습니다. 사유: Nav2 task failed (실패 1회)` |
| `goal_rejected` (창 안) | `severity=3` | `… (실패 2회)` |

`/robot/events`를 기록해 전이도 봤다.

```
transition 2  (REMINDER)  +30 s
transition 3  (CLEARED)   +60 s   → 활성 목록에서 사라짐
```

**`hold 60 = reminder 30 × 2`라는 근거가 실제로 성립했다.** 창 안에 재알림이 정확히 한 번
들어온다.

## 7. 실기 검증 절차 (Jetson)

이 브랜치는 로봇을 움직이지 않는다 — 발행이 `/robot/health`·`/robot/events` 둘뿐이고
`/cmd_vel*`을 내지 않는다(2026-08-09 검증에서 실측). 다만 R-2~R-4는 실패를 만들어야 하므로
로봇이 주행한다. 3절 안전 조건은 `2026-08-11-amcl-b1-실기검증.md`와 같다.

### R-1. 빌드와 기동 `[정지]`

```bash
git checkout feat/nav-failure-to-app
colcon build --packages-select vica_system_monitor --symlink-install
source install/setup.bash
cd src/vica_system_monitor && python3 -m pytest test/ -q   # 248 passed / 1 skipped

# 브링업 매뉴얼 ⑪-1 로 띄운 뒤
ros2 param get /robot_health_monitor_node nav_failure_hold_sec   # 60.0
ros2 param get /robot_health_monitor_node goal_event_topic       # /vica_goal_event
ros2 node info /robot_health_monitor_node | grep vica_goal_event
```

### R-2. 정상 주행이 경보를 만들지 않는가 `[주행]`

**이것을 먼저 한다.** 정상 흐름을 실패로 읽으면 주행할 때마다 경보가 가고, 그러면 진짜
실패가 묻힌다. 이게 깨지면 아래 측정은 전부 무의미하다.

```bash
ros2 topic echo /robot/health --field active_faults
# 평소처럼 목적지 하나를 안내시킨다 (도착까지)
```

기대: `NAV_GOAL_FAILED`가 **한 번도 나오지 않는다.** `goal_sent`·`goal_accepted`·
`goal_succeeded`·`goal_canceled`는 전부 정상 흐름으로 걸러진다.

### R-3. 실패를 만들고 앱에서 확인한다 `[주행]`

실패를 만드는 가장 쉬운 방법은 **로봇 앞을 박스로 막는 것**이다. 도달 불가능한 목적지를
주면 `goal_rejected`로도 만들 수 있다.

| 보는 곳 | 기대 |
| --- | --- |
| `/robot/health` | `severity 2` |
| 결함 문구 | 목적지 이름과 사유가 들어 있다 |
| **앱 대시보드** | 상단 배너가 뜬다 |
| **앱 진단 화면** | 활성 결함 카드에 나온다 |
| 앱 알림 목록 | 아직 안 뜬다 (DEGRADED라서) |

### R-4. 반복하면 알림 목록까지 올라가는가 `[주행]`

**60초 안에** 같은 목적지로 한 번 더 보내 다시 실패시킨다.

| 보는 곳 | 기대 |
| --- | --- |
| `/robot/health` | `severity 3` |
| `/robot/events` 전이 | `1` (ESCALATED) |
| 결함 문구 | `(실패 2회)` |
| **앱 알림 목록** | **여기서 뜬다** |
| `fault_code` | 1회째와 **같아야 한다** |

### R-5. hold 60초가 적절한가 — 이 값을 정하는 단계 `[정지]`

마지막 실패로부터 시간을 재면서, **관리자가 다른 일을 하다가 앱을 보기까지 실제로 얼마나
걸리는지** 잰다. 이것이 `nav_failure_hold_sec`의 근거가 된다.

| 관측 | 기대 |
| --- | --- |
| +30초 재알림 | `transition 2` |
| +60초 해소 | `transition 3` |
| 해소 후 활성 목록 | `NAV_GOAL_FAILED` 없음 |
| **관리자가 알아채기까지** | — |

60초로 부족하면 값을 올린다. 다만 **길면 이미 해결된 실패가 화면에 남는다.** 그때는 hold를
늘리는 대신 소리·푸시 알림을 검토하는 쪽이 맞다 — **화면을 안 보고 있으면 hold를 아무리
늘려도 소용없다.**

## 8. 판정 기록

| 단계 | 확인 내용 | 기대 | 결과 | 비고 |
| --- | --- | --- | --- | --- |
| R-1 | 패키지 시험 | 248 / 1 skipped | | |
| R-1 | `nav_failure_hold_sec` | 60.0 | | |
| R-2 | **정상 주행에 경보 없음** | 결함 0건 | | 깨지면 나머지 무의미 |
| R-3 | 1회 실패 등급 | 2 | | |
| R-3 | **앱 배너** | 뜬다 | | |
| R-3 | 앱 진단 화면 카드 | 나온다 | | |
| R-4 | 2회째 등급 | 3 | | |
| R-4 | **앱 알림 목록** | 뜬다 | | |
| R-5 | 재알림 / 해소 | +30 s / +60 s | | |
| R-5 | **관리자 인지까지 시간** | — | | hold 값의 근거 |

## 9. 되돌리는 법

값 하나로 끌 수 있다. 나머지 감시는 그대로 둔다.

```yaml
# config/required_components.yaml
nav_failure_hold_sec: 0.0
```

전부 되돌리려면:

```bash
git checkout dev
colcon build --packages-select vica_system_monitor --symlink-install
```

## 10. 이 검증으로 덮지 않는 것

- **소리·팝업.** 배너든 팝업이든 앱을 안 보고 있으면 소용없다. 화면 밖으로 나가는 신호가
  필요하며 그것은 `VICA_Supervisor` 저장소 작업이다. **R-5 결과를 보고 판단한다.**
- **`/robot_status` 죽은 구독.** 앱이 구독하지만 워크스페이스 전체에서 발행자가 0건이다
  (제안서 1.3절). 앱 팀이 따로 정리할 사항이며 이 범위가 아니다.
- **갇힘에서 빠져나오는 수단.** 이 변경은 **알리는 것**만 다룬다. 후진은
  `docs/nav2_backlog.md` §9가 닫은 축이다.
- **실패 전 침묵.** 갇힌 뒤 ABORT까지 사용자에게 아무 안내가 없다. `vica-voice-llm` 몫이다.

## 11. 판정 후

전 항목 통과면 `dev` 머지 대상이다. **머지 시점은 사용자가 판정한다.**

머지 시 함께 갱신할 것:

- `docs/proposal_nav_failure_to_app.md` — 상태를 "제안·승인 전"에서 "구현·검증 완료"로 바꾸고
  §7의 결정 4건에 답을 적는다(3절 표를 옮긴다)
- `guideline/vica_system_health_monitoring_draft.md` — 주행 실패가 감시 입력에 들어왔다는
  사실을 정본에 반영한다
