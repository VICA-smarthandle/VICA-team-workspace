# 2026-07-31 — 상태 감시 계층 구현

앱에 "무엇이 / 어느 부품에서 / 얼마나 심각하게 / 언제부터 / 몇 번 / 무엇을 해야 하는지"를
띄우기 위해 `vica_system_monitor` 패키지를 새로 만들고 앱까지 연결했다. **노트북에서 할 수 있는 검증은 전부 끝냈고
실기(Jetson) 검증은 아직 하지 않았다. dev에 머지하지 않는다.**

## 1. 왜 만들었나

`/diagnostics` 발행자가 모터 노드의 CAN link 항목 **하나뿐**이었다. 앱의 오류 표시는
`vica_status_app_node.py`가 ERROR 첫 메시지 **문자열 하나**를 뽑는 게 전부라 부품·등급·
조치·발생시각·횟수·지속시간이 전부 없었다.

`vica_architecture.md`가 이미 결함을 기록해 두었다 — 마지막 `/diagnostics` 메시지 하나만
보관하므로 ERROR 발행자와 정상 발행자가 번갈아 오면 **표시가 깜빡인다.**

두 번째 역할이 더 중요하다. 워크스페이스 최적화 작업(imu adapter CPU 38.6 %, EKF 30 Hz
미달)의 **before가 지금밖에 없고 재현할 수 없다.** 최적화를 먼저 하면 baseline을 영영
잃는다. 이 노드가 그 계측 장비다.

## 2. 설계에서 바꾸지 않은 것

초안(`vica_system_health_monitoring_draft.md`)의 표준 체인을 그대로 썼다.

```
노드 /diagnostics → diagnostic_aggregator → /diagnostics_agg → robot_health_monitor_node
                                                                        ↓
                                                      /robot/health + /robot/events → 앱
```

`diagnostic_aggregator`를 쓰는 이유는 **나중에 다른 노드에 진단을 붙일 때 모니터 코드를
고치지 않기 위해서**다. aggregator yaml에 항목만 추가하면 `DIAG_COMPONENT_ERROR`/`WARN`/
`STALE` 통로로 앱까지 표시된다. 지금 발행자가 하나뿐인데도 표준 체인을 먼저 까는 유일한
이유가 이것이다.

**안전 신호는 이 체인을 타지 않는다.** `/emergency_stop`, `/safety_state`, TF는 모니터가
직접 구독한다. aggregator는 기본 1 Hz로 집계하므로 ESTOP 표시가 최대 1초 늦는다.
*진단성 정보는 표준 체인, 안전 상태는 직접 입력* — 이게 설계의 뼈대다.

## 3. 초안과 의도적으로 다르게 한 것

| # | 초안 | 실제 | 이유 |
| --- | --- | --- | --- |
| 1 | 노드 1개 | **2개** (`robot_health_monitor_node` + `external_diagnostics_node`) | rplidar·nvblox·D455는 외부 패키지라 `/diagnostics`를 안 낸다. 대신 낼 주체가 필요했고, `nvblox_msgs` 의존을 모니터에서 격리해야 했다 |
| 2 | `RobotEvent`에 결함 필드를 평면으로 | **`RobotFault` 분리** | `RobotHealth.active_faults`와 필드가 완전히 같아 중복된다 |
| 3 | `primary_fault_code` 하나 | **`RobotFault[] active_faults` 추가** | 앱이 재접속했을 때 나머지 결함을 복원할 수 없다 |
| 4 | `event_id` | **없음** | 중복 키는 `component`+`fault_code`로 충분. 목록 id는 앱이 `_uuid.v4()`로 만든다 |
| 5 | 문구 소유자 미정 | **로봇의 `fault_catalog.py`가 정본** | 앱에 두면 fault 추가마다 앱을 다시 배포하고 정본이 두 저장소로 갈라진다 |
| 6 | `*_ready` bool | **`*_readiness` 3상태** | 아래 4장 |

## 4. bool을 3상태로 바꾼 이유 — 이 작업의 가장 큰 설계 수정

처음 계획에는 `bool guidance_ready`가 있었다. 이건 결함이다.

Smart Handle은 아두이노에서 젯슨으로 올라오는 **상향 경로가 없다.** 서보가 실제로 돌았는지,
LED가 켜졌는지, 햅틱이 울렸는지 확인할 방법이 원리적으로 없다.

- `false`로 두면 → 정상인데 고장으로 보인다
- `true`로 두면 → **관측하지 못한 것을 정상이라고 보고한다**

두 번째가 위험하다. 시각장애인 안내 로봇에서 "핸들 정상"이라는 초록불은 그 자체가 안전
주장이다. `SmartHandleState.msg`가 경고하는 실패 모드와 정확히 같다.

그래서 `UNKNOWN`(0) / `NOT_READY`(1) / `READY`(2)로 만들고, 앱은 `UNKNOWN`을 **"관측 불가"**
로 표시하며 화면에 *"고장이 아니라 상태를 확인할 수단이 없다는 뜻입니다. 정상이라고 볼 수
없습니다."* 설명을 붙인다. 위젯 테스트가 이 문구를 고정한다.

## 5. 임계값을 하나도 확정하지 않았다

`vica_system_monitor`의 모든 임계값은 `[미검증]`이다. 하드코딩하면 최적화 이후 오탐이 나거나
반대로 회귀를 못 잡는다.

| 예정된 변경 | 하드코딩하면 |
| --- | --- |
| `/imu/base_link` 400 → 60 Hz 다운샘플 | 400 Hz 기준이면 FAULT 오탐 |
| `voxel_layer.publish_voxel_map: False` | 토픽이 소멸 → "발행자 없음" 오탐 |
| `behavior_plugins`에서 `backup` 제거 | `/backup` action 소멸 → 동일 |
| `/vica/tts_state` edge → 10 Hz heartbeat | **토픽 의미 자체가 바뀜** |
| imu adapter CPU 38.6 % → 10 % 미만 | 임계 40 %면 개선 후에도 통과해 **회귀를 못 잡음** |

방어책 3가지를 걸었다.

1. 임계값과 기대 토픽 목록을 **코드에 두지 않는다.** 전부 YAML이다.
2. `test_config_contract.py`(33건)가 `probes.yaml`·`diagnostic_aggregator.yaml`·
   `required_components.yaml`·`fault_catalog.py`의 이름 집합 일치를 강제한다. 노드를 고칠 때
   YAML 한 줄을 같은 커밋에서 바꾸도록 테스트가 누락을 잡는다. 실제로 이 테스트가
   `LOCALIZATION_WHEEL_ODOM_STALE`이 `probes.yaml`에만 있고 카탈로그에 없는 것을 잡았다.
3. **토픽 부재를 자동으로 fault로 만들지 않는다.** 토픽이 사라지는 게 정상 변경일 수 있으므로
   부재 판정은 반드시 YAML의 `required` 플래그를 거친다.

## 6. 감시 도구가 스스로 오탐을 만들 수 있다

가장 조용한 실패 모드다. `/scan`을 RELIABLE로 구독하면 rplidar가 sensor_data(BEST_EFFORT)로
발행할 때 QoS 비호환으로 **한 건도 받지 못하고** `LIDAR_SCAN_STALE`이 영구히 뜬다. LiDAR는
멀쩡한데 감시가 거짓 경보를 만든다.

방어: 구독 QoS를 `probes.yaml`에 빼고, 어댑터가 **"구독자는 붙었는데 메시지 0건"**을 진단
message에 구분해 남긴다(`classify_zero_message()` → `ZERO_NO_PUBLISHER` /
`ZERO_QOS_SUSPECTED`). 실제 값은 Jetson `ros2 topic info -v`로 확정한다.

## 7. 기존 동작을 바꾸지 않았다

`vica_status_app_node.py`의 오류 판정 교체는 의미가 바뀌는 변경이라 파라미터로 감쌌다.

```python
self.declare_parameter('error_source', 'diagnostics')   # 'diagnostics' | 'health'
```

기본값이 현재 동작이다. 빌드·머지해도 거동이 그대로다. 실기에서 파라미터 한 줄로 A/B하고,
검증 후 기본값을 `health`로 바꾸는 것은 **별도 커밋**으로 한다. 롤백 단위가 커밋이 아니라
파라미터가 된다.

`safety`·`motor`·`guidance`·`encoder`는 **한 줄도 건드리지 않았다.**

## 8. 개발 중 잡은 실수

- **`?초` 자리표시자가 사용자 문구로 샜다.** 실행 중 `Safety 상태가 ?초 동안 갱신되지
  않았습니다`가 나왔다. 한 번도 수신하지 못한 경우와 오래된 경우를 같은 문구로 처리한 탓이다.
  `SafetyInput.age_sec: Optional[float]`을 추가해 문구를 나누고, **모든 fault detail에
  `{`·`?`가 없음**을 검사하는 회귀 테스트 4건을 걸었다.
- **CPU % 계산 테스트가 틀렸다.** 386 jiffies / 10초 / 100 tick을 3.9 %로 적었는데 38.6 %가
  맞다. 구현이 옳고 테스트가 틀린 쪽이었다.
- **위젯 테스트가 영문 등급을 찾고 있었다.** 화면은 `주행 불가`를 보여주고 영문 `STOP`은
  쓰지 않는다. 기계 판독 코드는 `fault_code` 줄이 따로 담당한다.
- **`pubspec.lock`을 커밋하려다 되돌렸다.** 이 노트북 Flutter(3.41.9)가 팀(≥3.44.0)보다
  낮아 diff가 전부 다운그레이드였다. 커밋하면 팀 전체를 낮은 패키지로 끌어내린다.
- **`test_pep257`이 D213으로 실패했다.** D212/D213은 상호 배타이고 이 워크스페이스는 D212
  스타일이다. `--add-ignore D213`으로 맞췄다. 같은 문제가 `mdrobot_can_control`에도 있으나
  범위 밖이라 손대지 않았다.

## 8-1. 실행 검증에서 나온 결함 4건 (모두 수정)

노트북 실기동에서 순수 로직 테스트가 원리적으로 잡을 수 없는 결함이 드러났다.

| # | 결함 | 원인 |
| --- | --- | --- |
| 1 | 기동 유예가 aggregator 경로에서 무력화 | aggregator가 "Missing"을 1 Hz로 계속 발행해 입력이 항상 신선했다. `not fresh` 조건을 쓰던 유예 분기에 도달조차 못 했다. grace 15~45초인 컴포넌트가 기동 1.3초에 전부 결함으로 떴다 |
| 2 | 영문 요약어 누출 | `detail: Missing`·`Error`·`Stale`이 관리자 화면에 그대로 떴다 |
| 3 | E-stop 없는 `ESTOPPED` | 모터 진단이 없다는 이유로 앱에 "비상 정지"가 표시됐다 |
| 4 | 알림 폭주 | `severity >= ESTOP`으로 폭주 억제를 풀어, 모터 진단 미수신이 초당 한 건씩 알림을 냈다(occurrence_count 223회) |

유예 판정 기준을 신선도에서 **`ever_ok`**(한 번이라도 정상이었나)로 바꿨다. 한 번 정상이었다가
고장 난 것은 유예 안이라도 즉시 보고한다 — 유예의 목적은 "아직 안 뜬 것"을 봐주는 것이지
"떴다가 죽은 것"을 감추는 게 아니다.

3·4번의 뿌리는 같다. **`severity`가 두 질문에 답하고 있었다.**

```
얼마나 나쁜가   OK / WARN / DEGRADED / STOP / FAULT
어떤 모드인가   비상정지 래치가 걸렸다
```

E-stop을 등급 축에서 뺐다. `RobotFault.latched`와 `RobotHealth.state == ESTOPPED`가
그 사실을 나타낸다. 폭주 억제 해제 조건도 `record.latched`로 바꿨다.

공용 계약 변경이지만 아직 어느 저장소에도 머지되지 않아 지금은 커밋 하나다. 머지 후였다면
세 저장소 동시 마이그레이션이었다.

잃은 것은 "E-stop을 걸어야 할 만큼 심각"과 "주행만 막으면 됨"의 구분이다. 지금 그 구분을
쓰는 코드가 없고(모니터는 정지 권한이 없다), 필요해지는 시점은 자동 복구다. **그때는 복구
정책 필드로 표현한다. 표시용 등급에 다시 싣지 않는다.**

### 검증

- 테스트 188건(ROS) + 66건(앱) 통과
- 기동 60초 타임라인이 설정값과 일치: `1.4s STARTING 0건 → 15.4s STOPPED 3건 →
  20.4s 4건 → 30.4s 5건 → 45.4s 7건`
- 55초 동안 이벤트 11건, reminder가 30초 간격 규칙을 지켰다(이전에는 매 tick)
- 결함 문구 전부 한국어, 영문 요약어·자리표시자 누출 없음

## 8-2. rosbridge 실측과 앱 종단

앱 모델은 rosbridge가 커스텀 메시지를 어떤 JSON으로 직렬화하는지 **추론만** 했었다.
실측 결과 필드가 평면으로 1:1 대응하고 `active_faults`는 평범한 JSON 배열,
시각은 `{sec, nanosec}` 객체였다. 추론이 맞았지만 그 사실을 테스트로 고정했다 —
실제 수신한 payload를 한 글자도 고치지 않고 `rosbridge_payload_test.dart`에 박았다.

Flutter Linux desktop 앱을 실제로 띄워 시스템 진단 화면까지 확인했다. 등급 배지·부품
한국어 이름·기계 판독 코드·문구·발생시각·횟수·지속시간·조치가 모두 표시됐다.

`error_source` A/B:

| 설정 | `error_reason` |
| --- | --- |
| `diagnostics`(기본) | `'No events recorded.'` |
| `health` | `'진단 항목이 보고되지 않았습니다.'` |

기본값이 현재 동작 그대로임을 확인했고, 이 작업이 해결하려던 문제가 A/B로 직접 드러났다.

## 9. 지금 상태

**`vica_ros2_ws` — `integration/app-ui-system-monitor`** (미머지)

```
472e104  등급 축에서 비상정지를 떼어내 래치로 표현 (계약 변경)
22eac98  실기동에서 드러난 기동 유예·문구·상태 결함 3건 수정
faed36a  모니터 노드와 aggregator 설정·launch
d93c56f  app-UI/status-test 통합 머지 (CMakeLists 1줄 충돌 해소)
029883d  외부 대상 대행 어댑터 노드
bec43c1  관측 계층 메시지와 순수 판정 로직
```

메시지 3종, 노드 2개, 순수 모듈 7개, config 3개, launch 1개. 패키지 테스트 **188건**
(8-1절의 회귀 테스트 포함).

**`VICA_Supervisor` — `integration/app-ui-system-monitor`** (미머지)

```
3b79269  등급 축에서 비상 정지 제거 (계약 변경)
99ffd7b  rosbridge 실측 payload로 모델 파싱 고정
b157f3c  시스템 진단 화면과 대시보드 결함 배너
4a3aa1c  error_source 파라미터
```

`dart format` exit 0, `flutter analyze` 무결함, `flutter test` **66건 통과**.

## 10. Jetson에서 해야 할 것 (아직 안 함)

착수 전 **노트북·Jetson 둘 다** `sudo apt install -y ros-humble-diagnostic-aggregator`.
현재 양쪽 다 미설치라 aggregator 경로는 한 번도 실행된 적이 없다.

### 1차 — 측정만. 바퀴 안 굴림

| 측정 | 방법 | 산출 |
| --- | --- | --- |
| 발행 QoS | `ros2 topic info -v` × 6토픽 | `probes.yaml` QoS 확정 |
| 실제 주기 | `ros2 topic hz` × 6토픽 | 기대 주기 확정. slice 정상 ~9 Hz 확인 |
| 노드별 CPU | 어댑터 `process_cpu` 출력 | **imu adapter 38.6 % baseline 기록** |
| `/odom` 실효 Hz | 어댑터 출력 | **EKF 30 Hz 미달 baseline 기록** |
| Docker `/proc` 가시성 | nvblox·D455 프로브 동작 여부 | 안 보이면 미구성 처리 확정 |
| aggregator 트리 | `rqt_robot_monitor` | `/VICA/Hardware/*` 표시 확인 |

**이 시점의 측정값이 최적화 작업의 유일한 before다.** 측정 뒤 이 devlog에 값을 적는다.

### 2차 — fault injection. 바퀴 무부하, 물리 E-stop 확보, 별도 승인

모터 CAN 단절 / safety 노드 종료 / TF 제거 / LiDAR USB 분리 / nvblox slice 강제 지연 /
카메라 종료 / 어댑터 종료 / aggregator 종료 / 모니터 종료 / 앱 재접속 / 알림 폭주 /
`error_source` A/B.

**모니터가 죽어도 모터·safety 경로가 유지되는지**를 반드시 확인한다. 이게 승인 기준이다.

CAN 격리는 `docs/superpowers/specs/2026-07-27-motor-can-health-design.md` 6.2절을 따른다 —
이 장비는 CAN이 끊기면
드라이버 동력이 차단되어 전원 재투입이 필요하므로 `tc` ingress drop 또는
`CMD_PNT_IO_MONITOR_OFF(86)`를 쓴다.

## 11. 범위 밖으로 남긴 것

- **자동 복구.** 관측·보고만 한다. `recovery_policy.yaml`은 초안 11절 `[TARGET]`
- **nvblox slice stale의 실제 방어(Mission 취소).** 감지는 넣었지만 방어는 아니다. 지금
  넣으면 "유령 때문에 못 감"과 "slice stale이라 멈춤"이 섞여 원인 분리가 어려워진다.
  유령 장애물 진단이 끝난 뒤 결정한다 (`2026-07-30-nvblox-ghost-obstacle.md` 12절)
- **다른 노드에 `diagnostic_updater` 추가.** 우선순위는 초안 17절 1단계 표에 있다.
  1위가 **마이크 무입력**(`vica-voice-llm/src/emergency_monitor.py`, 20~30줄) — 긴급어
  감시가 조용히 멈추는 실패 모드라 크기가 아니라 위험도로 1위다.
  `safety_supervisor_node` 수정은 E-stop 경로 전체 재검증을 요구하므로 마지막
- GPU·온도·디스크(초안 8.7의 `diagnostic_common_diagnostics`, 미설치), rosbag2 snapshot,
  Mission start gate, systemd
