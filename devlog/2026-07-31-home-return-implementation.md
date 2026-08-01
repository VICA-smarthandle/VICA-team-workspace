# 홈 위치 복귀와 기동 시 위치 자동 초기화 구현 — 2026-07-31

> **상태**: 순수 로직·노드 배선 구현 완료, 실기 미검증. 임계값은 전부 `[미검증]`.
> **정본 반영**: `guideline/` 는 갱신하지 않는다. **실기 검증이 끝난 뒤 한 번에 반영한다**
> (2026-07-31 결정). 검증 임계값 6종이 전부 `[미검증]` 이라 실기에서 바뀔 가능성이 높고,
> 정본을 두 번 고치지 않기 위해서다. `devlog/2026-07-30-smart-handle-mode-decisions.md` 와
> 같은 방식이다. 반영 대상은 §2의 인터페이스 계약과 §7의 스마트핸들 규약이며,
> `GOVERNANCE.md` §4의 "공용 topic/JSON 계약 변경"에 해당하므로 그때 승인을 받는다.
>
> `docs/vica_robot_bringup_manual.md` 는 갱신했다 — 코드가 새 기동 단계(⑨-1)를 요구하므로
> 운영 절차 문서는 지금 따라가야 한다.
> **브랜치**: `vica_ros2_ws` 의 `feat/home-return` (`integration/app-ui-system-monitor` 에서 분기).
> 아직 commit 하지 않았다.
> **범위**: 홈 복귀와 기동 시 AMCL 초기 pose 자동 설정만 담는다. 같은 세션에서 조사한
> 도킹 스테이션·배터리 계측·자동 탐사는 설계 방향만 잡았고 구현하지 않았다.

---

## 0. 요약

**이 작업은 신규 기능이 아니라 기획서의 미구현분을 채운 것이다.**

개발보고서(`source_file/20260714023741117.pdf` p.6)와 설계서(`…175.pdf` p.5-6)의 서비스 흐름도
33단계에 `③ 로봇 홈 위치 이동`, `④ 대기 상태 진입`, `㉝ 로봇 홈 위치 복귀`가 이미 있고,
담당 노드는 설계서 p.30에서 **"구현예정(현재 미구현) — goal 단계 안전 판단 노드"**로 선언되어
있었다. 관리자 앱 기능 설명(보고서 p.13)에도 "대기 위치 복귀"가 들어 있다. 반면
「S/W 전체 구현 현황」 19개 항목과 「프로그램 노드 목록」 21개 어디에도 이 기능이 없었다.

구현한 것은 세 가지다.

1. **홈 좌표 정의와 로드** — `home.yaml` 로 목적지 카탈로그와 분리
2. **기동 시 AMCL 초기 pose 자동 설정 + 검증** — 신규 `pose_bootstrap_node`
3. **도착 후 자동 복귀 상태머신** — `RETURN_PENDING` / `RETURNING` 두 상태 추가

테스트 177개 통과(`vica_mission_manager` 142, `vica_localization` 35). 전부 TDD 로 작성했고
구현 전에 실패하는 것을 확인했다.

---

## 1. 구현한 파일

### 신규

| 경로 | 역할 |
| --- | --- |
| `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/home.py` | `home.yaml` 로더. 로드 시점에 전부 검증 |
| `vica_ros2_ws/src/vica_localization/vica_localization/pose_bootstrap.py` | 초기화 순수 상태기계 (rclpy 비의존) |
| `vica_ros2_ws/src/vica_localization/vica_localization/scan_match.py` | 스캔–맵 정합 점수 (rclpy 비의존) |
| `vica_ros2_ws/src/vica_localization/vica_localization/pose_bootstrap_node.py` | 위 둘의 ROS 배선 |
| `vica_ros2_ws/src/vica_localization/launch/pose_bootstrap.launch.py` | 신규 launch |

테스트: `test_home.py`(11), `test_pose_bootstrap.py`(23), `test_scan_match.py`(10),
`test_goal_event_contract.py`(3).

### 수정

| 경로 | 내용 |
| --- | --- |
| `…/vica_mission_manager/mission_logic.py` | `RETURN_PENDING`/`RETURNING` 상태, `localization_ready` 게이트, 선점·E-stop·취소 확장 |
| `…/vica_mission_manager/mission_manager_node.py` | 홈 로드, TF 거리, `trip` 필드, `/vica/localization_status` 구독 |
| `…/vica_mission_manager/launch/mission_manager.launch.py` | 복귀·위치추정 파라미터 노출 |
| `…/vica_mission_manager/package.xml` | `tf2_ros` 의존 추가 |
| `…/vica_localization/package.xml`, `setup.py` | 노드 의존과 entry point |

---

## 2. 새 인터페이스 계약 (정본 반영 대상 — 승인 필요)

### 2.1 `/vica/localization_status` (신규 토픽)

`std_msgs/String`, JSON. QoS **RELIABLE + TRANSIENT_LOCAL + KeepLast(1)**.

```json
{"state": "ready|failed|wait_stack|settle", "reason": "...", "detail": {...},
 "timestamp": "2026-07-31T..."}
```

발행: `pose_bootstrap_node` / 구독: `mission_manager_node`.
`state == "ready"` 일 때만 주행을 승인한다. **파싱 실패도 미준비로 본다.**

TRANSIENT_LOCAL 인 이유: Mission Manager 가 나중에 떠도 마지막 상태를 받아야 한다.

### 2.2 `/vica_goal_event` 에 `trip` 필드 추가

기존 payload 에 `"trip": "guidance" | "return_home"` 한 키만 더한다.
**새 이벤트 이름을 만들지 않는다.** 근거:

- `VICA_Supervisor/ros2/vica_goto_goal.py` 의 `_TERMINAL_GOAL_EVENTS` 에 없는 이름은
  CLI 가 무한 대기한다.
- `vica_status_app_node.py` 의 `navigation_active` 도 안 꺼진다.
- 기존 이름을 쓰면 홈 이름 "대기 위치"가 앱에 그대로 표시되어 **앱 수정이 0줄**이다.

이 규약은 `test_goal_event_contract.py` 가 강제한다(§4.4).

### 2.3 `home.yaml` (신규 파일)

경로: `~/vica_data/destinations/<map_id>/home.yaml` — 목적지 카탈로그와 같은 디렉터리, 다른 파일.

```yaml
schema_version: 1
map_id: vica_map_0630
home:
  id: <canonical UUID v4>
  name: "대기 위치"
  calibrated: true
  pose: {frame_id: map, x: <실측>, y: <실측>, yaw: <실측 deg>}
  initial_pose: {enabled: true, sigma_xy_m: 0.30, sigma_yaw_deg: 12.0}
  arrival_tolerance: {xy_m: 0.40, yaw_deg: 25.0}
```

**`destinations.yaml` 에 넣지 않은 이유**: 앱이 `/save_location`·`/delete_location_request` 로
그 파일을 CRUD 한다(`vica_destination_manager/storage.py`). 관리자가 실수로 지우면
**다음 부팅에서 위치 초기화 자체가 실패**한다. 홈은 사용자가 고르는 목적지가 아니라 기동 전제
좌표다. 앱에서의 홈 편집은 v1 범위 밖으로 두었다 — 홈 좌표 변경은 나중에 물리 도크 이동을
동반한다.

**`arrival_tolerance` 하한을 로더가 강제한다.** Nav2 goal tolerance(0.25 m / 0.25 rad =
14.32도)보다 작으면 Nav2 가 "도착"이라 한 지점을 우리가 "아직 아니다"로 읽어 제자리에서
재출발하는 루프가 생긴다.

### 2.4 Mission Manager 상태 2종 추가

`idle / confirming / navigating / arrived / failed / estopped / paused` 에 두 개를 더한다.

- `return_pending` — 도착 후 복귀까지 기다리며 정지해 있는 상태
- `returning` — 홈으로 주행 중

---

## 3. 설계 결정과 근거

### 3.1 AMCL `set_initial_pose` 파라미터를 쓰지 않는다

`/initialpose` 토픽 발행 방식을 택했다. 근거는 AMCL 소스다 —
`on_activate()` 가 파라미터 경로에서 `initialPoseReceived()` 를 부를 때 **covariance 를 전혀
설정하지 않아 전부 0 이 된다.** 입자 2000개가 한 점에 모이고,
`nav2_params.yaml:26-27` 의 `recovery_alpha_fast/slow: 0.0` 때문에 무작위 입자 주입도 없다.
결과적으로 초기 오차를 스스로 고칠 수단이 없고 **공분산 기반 검증이 원리적으로 불가능**해진다.

`BasicNavigator.setInitialPose()` 도 같은 결함이 있다(`msg.pose.pose` 만 채운다).

→ `nav2_params.yaml` 에 `set_initial_pose: false` 를 명시하고 계약 테스트로 잠글 것 `[TODO]`.

### 3.2 초기 분포를 일부러 넓게 준다 (σ_xy 0.30 m, σ_yaw 12도)

좁게 뿌리면 **틀린 위치에서도 응집이 유지**되어 공분산 수축이 "맵과 맞았다"는 증거가 되지
못한다. 넓게 뿌려야 맵과 맞는 입자만 살아남아 수축하고, 그 수축 자체가 증거가 된다.
통과 임계는 초기값의 절반(σ_xy 0.15 m, σ_yaw 7도)으로 두었다.

### 3.3 `/request_nomotion_update` 호출이 이 설계의 핵심이다

`update_min_d: 0.25`, `update_min_a: 0.2` 때문에 **정지 상태에서 AMCL 은 스캔을 아예
반영하지 않는다.** 이 서비스를 부르지 않으면 `/amcl_pose` 공분산은 우리가 준 초기값 그대로이고
검증이 통째로 무의미해진다. 0.4초 간격 5회 호출한 뒤에야 판정한다.

### 3.4 복귀 진입점은 `ARRIVED` 하나뿐이다

개발보고서 p.16·p.28 은 "해제 후에도 새 goal 입력 전까지 HOLD 상태를 유지하여 기존 목적지의
자동 재개를 차단"을 규정한다. 복귀 goal 은 이전 goal 이 아니지만, E-stop 직후 자동으로
출발하면 **같은 사고**를 낸다. 그래서:

- `_enter_estopped()` 가 `RETURN_PENDING`/`RETURNING` 을 덮고 복귀 무장을 폐기한다
  (기존 `paused_destination = None` 처리와 같은 패턴)
- E-stop 해제 후 도달하는 `IDLE` 에서는 복귀가 시작되지 않는다
- `FAILED`·`cancel` 이후에도 무장하지 않는다 — 실패 원인을 모르는 채로 사람 없이 다시
  달리는 것이 더 위험하다

`RETURNING → SUCCEEDED → IDLE` 로 **`ARRIVED` 를 거치지 않는 것**이 무한 복귀 루프를 막는다.

### 3.5 `NAVIGATING` 을 플래그로 재사용하지 않았다

`State.NAVIGATING` 을 검사하는 지점이 8곳이고 그중 5곳이 복귀 시 동작이 다르다
(새 목적지 → 거부/선점, pause → 허용/거부, SUCCEEDED → ARRIVED/IDLE 직행,
거리 안내 → 함/안 함). 플래그면 8곳에 조건을 붙여야 하고 **하나만 빠뜨려도
복귀 중 E-stop 이 goal 을 취소하지 않는** 안전 결함이 된다.

### 3.6 `localization_ready` 를 `MissionLogic` 의 상태로 두었다

`estop_active` 와 같은 패턴이다. `on_localization_status(ready)` 로 갱신하고 기본값은
`False`(fail-closed). 이렇게 하면 `on_tick`/`on_intent` 시그니처가 계속 늘어나지 않는다.

`check_gate` 의 `localization_ready` 인자는 기본값 `True` 다 — 순수 판정 함수이고
fail-closed 책임은 호출자가 진다.

### 3.7 `pose_bootstrap_node` 는 `home.py` 를 import 하지 않는다

`home.py` 는 `mission_logic` 의 `Destination` 타입에 묶여 있어, `vica_localization` 에서
import 하면 **의존 방향이 뒤집힌다**(localization → mission). `PoseBootstrap` 은 좌표를
float 로 받으므로 그 타입이 필요 없다. 필요한 필드만 읽는 `read_home_pose()` 를 두었고,
`map_id` 일치와 `frame_id` 검증은 양쪽 모두 한다.

---

## 4. 구현 중 확인한 사실

### 4.1 ★ `inlier_ratio` 임계값 0.70 은 사실상 무력하다

설계 단계에서 검증 조건 중 하나로 "스캔 정합 inlier 비율 ≥ 0.70"을 두었으나,
합성 데이터로 재보니 **특징 없는 사각 방에서 1 m 를 틀려도 0.68 이 나온다.**
x 축으로 움직여도 위·아래 벽 방향 빔은 그대로 벽에 맞기 때문이다.

`hit_tolerance` 를 좁혀도 소용없다 — 오차가 커지면 빔 끝점이 다른 벽 위에 **정확히 떨어지거나
완전히 빗나가서** 여유값과 무관해진다. 여유값이 작동하는 것은 소량 오차 구간뿐이다.

→ 이 특성을 `test_scan_match.py::test_featureless_room_discriminates_weakly` 로 박제하고
`scan_match.py` docstring 에 적었다. **이 점수 하나로 통과시키면 안 되고, 공분산 수축·이동량과
AND 로 묶어야 한다.** 실기 임계값 설정 시 이 점을 반드시 고려할 것.

### 4.2 `on_intent` 의 숨은 결함

게이트 실패 시 `self._to_idle()` 을 부른다. 복귀 중에 잘못된 요청이 오면 복귀가 조용히 끊겼다.
사용자가 말을 건 상황에서 로봇이 그냥 떠나는 것보다는 서 있는 편이 낫다고 판단해,
**복귀 중 navigate 의도가 오면 게이트 통과 여부와 무관하게 복귀를 선점 취소**하도록 했다.

### 4.3 앱 경로가 게이트를 우회하고 있었다

음성 경로는 `on_intent` → `check_gate` 를 지나는데, 앱의 목적지 요청
(`_on_destination_request`)은 `check_gate` 를 **직접** 호출한다. 여기에
`localization_ready` 를 넘기지 않으면 위치 검증을 음성만 받고 앱은 안 받게 된다. 고쳤다.

같은 함수의 `state != State.IDLE` 조건도 `RETURN_PENDING` 을 허용하도록 바꿨다 —
없으면 복귀 대기 시간 동안 앱 요청이 통째로 막힌다.

### 4.4 계약 테스트는 red-green 으로 검증했다

`test_goal_event_contract.py` 가 처음부터 통과해서, 실제로 무언가를 잡는지 확인했다.

- `trip` 필드 제거 → `test_goal_event_payload_carries_trip` 실패 ✓
- `goal_sent` → `return_sent` 로 변경 → `test_node_only_publishes_known_event_names` 실패 ✓
- 복원 → 3개 통과 ✓

### 4.5 이 노트북에서 `colcon build` 가 실패한다 (코드 무관)

```
The build time path "/home/msk/vica_ros2_ws/install/encoder_feedback" doesn't exist.
```

기존 `install/` 이 **옛 경로(`/home/msk/vica_ros2_ws`)에서 빌드된 것**이다. 워크스페이스가
`/home/msk/VICA-smarthandle/vica_ros2_ws` 로 옮겨진 뒤 재빌드되지 않아, colcon 이 의존 패키지
환경을 로드하는 단계에서 sh/bash/zsh 확장이 전부 실패한다. `build/`·`install/` 을 지우고 전체
재빌드하면 풀리지만 다른 패키지에 영향을 주므로 실행하지 않았다.

이번 작업물은 전부 rclpy 비의존 순수 로직이라 pytest 직접 실행으로 검증했다.

---

## 5. 실기 투입 전 반드시 알 것

1. **`home.yaml` 이 아직 없다.** 홈 좌표는 로봇을 실제 위치에 세우고 `/amcl_pose` 를 읽어
   만들어야 한다. 그전까지 자동 복귀는 꺼진 상태로 동작한다(안내 기능은 정상).
2. **`require_localization_ready` 는 기본 `true` 다.** `pose_bootstrap` launch 를 함께 띄우지
   않으면 `/vica/localization_status` 가 오지 않아 **모든 주행이 승인되지 않는다.**
   기존 방식으로 운용하려면 `require_localization_ready:=false` 를 넘긴다(경고 로그가 남는다).
3. **검증 임계값 6종이 전부 `[미검증]` 이다.** 특히 §4.1 때문에 `scan_match_min` 은 신뢰도가
   낮다. **로봇을 일부러 2 m 어긋난 곳에 두고 검증이 실패하는지 확인**하는 절차가 이 설계의
   존재 이유다. 그것을 확인하기 전에는 자동 초기화를 신뢰하지 않는다.
4. **`amcl.laser_max_range: 100.0`(`nav2_params.yaml:17`)을 먼저 고쳐야 한다.**
   `likelihood_field` 가 무반사 빔을 유효 반사로 오인해 점수가 왜곡되면 임계값 튜닝이 통째로
   무의미해진다. `ros2 topic echo /scan --field range_max` 실측 후 맞춘다.

---

## 6. 실측 대기 항목

| 항목 | 현재 | 확인 방법 |
| --- | --- | --- |
| 홈 좌표 | 미정 | 로봇을 실제 위치에 세우고 `/amcl_pose` 기록 |
| `/scan` 실제 `range_max` | 미확인 | 런타임 echo → `laser_max_range` 반영 |
| `cov_xy_max` 0.0225 | `[미검증]` | 실기 수렴 관측 |
| `cov_yaw_max` 0.0149 | `[미검증]` | 〃 |
| `pose_shift_max_m` 0.30 | `[미검증]` | 〃 |
| `yaw_shift_max_deg` 10.0 | `[미검증]` | 〃 |
| `scan_match_min` 0.70 | `[미검증]`, §4.1 로 신뢰도 낮음 | 2 m 오프셋 재현 시험 |
| `return_home_delay_sec` 60.0 | 제안값 | 운영 정책 결정 |
| `/request_nomotion_update` 효과 | 미측정 | 호출 유무에 따른 공분산 차이 실측 |

---

## 7. 다음 단계

- 실기: 홈 좌표 캘리브레이션 → `laser_max_range` 실측 → 임계값 튜닝 → 종단 1사이클
  (안내 → 도착 → 대기 → 복귀 → IDLE)
- 문서: 승인 후 `guideline/vica_architecture.md`(§2 계약),
  `guideline/vica_scenario.md`(복귀 중 스마트핸들 규약), `docs/vica_robot_bringup_manual.md`
  (pose_bootstrap 단계 추가)
- 스마트핸들 규약은 터치센서·상향 통신이 미장착이라 문서로만 못 박는다 —
  **활성 모드를 유지한 채 복귀하면 데드락이 확정적으로 발생한다**(사용자가 목적지에서 손을
  놓으면 pause → "핸들을 잡아주세요" 반복 → 사용자는 이미 떠났으므로 무한 대기).
  `RETURN_PENDING` 진입 시 핸들 모드를 비활성으로 강제 전이해야 한다.
