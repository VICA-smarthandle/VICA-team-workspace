# VCC(VICA Customized Controller) 설계

작성일: 2026-09-24
대상 저장소: `vica_ros2_ws` (구현), `VICA-smarthandle` (본 문서)
브랜치: 두 저장소 모두 `feat/vica_customized_controller`
관련 문서: `docs/nav2_backlog.md` §11(하지 말 것), NAV2-B3(몸통 검사 사각지대),
`devlog/2026-09-17-route-0903d-복도-레일-실주행.md`, `devlog/2026-09-18-controller-mppi-전환.md`,
`devlog/2026-09-21-mppi-제어주기-temperature.md`, `devlog/2026-09-24-rpp-도착정렬-초음파-collision-monitor.md`

## 1. 목적

DWB·MPPI·RPP 를 47회 실주행한 결과, 세 컨트롤러는 각자 한 가지씩을 구조적으로 못 한다.

| 컨트롤러 | 잘한 것 (최선 기록) | 구조적으로 못 한 것 |
|---|---|---|
| RPP | 직진 손잡이 좌우 속도 0.042 m/s(run36), controller CPU 10.6 % | 피하지 못하고 멈춘다. 유턴은 제자리 회전(42~51 %). 도착 회전이 ±16~21° 넘쳐 헌팅(run41) |
| MPPI | 궤적 전멸 0, 사람 사건당 정지 0.55 s(run25), 벽 여유 0.95 m | 평균을 내는 계산이라 방향 바뀜 43회/분. U턴 제자리가 50 % 아래로 안 내려감(wz_std 가 두 지표를 반대로 돌림) |
| DWB | 유턴 레일 이탈 0.46 m(run16), 일반코너 속도 0.464 m/s | 레일을 버린다(당근 6 m 에서 이탈 0.75~0.87 m). sim_time·ObstacleFootprint 는 닫힌 축 |

VCC 는 상황을 나눠 각 상황에 가장 잘한 방식을 맡긴다. 평소에는 RPP 식으로 레일을 따라가고,
장애물 앞에서는 차선을 옮겨 부드럽게 비켜 가며, 유턴은 작은 호로 돌고, 도착 방향은 한 번에 맞춘다.

## 2. 요구사항 (2026-09-24 사용자 제시, 요약)

1. **직진** — 손잡이가 좌우로 흔들리지 않고 레일을 따라간다. 3~4 m 앞 레일 위를 지나가는 사람에 예민하게 반응하지 않는다.
2. **유턴** — 정지 상태에서 60° 까지는 제자리 회전을 허용한다. 그 이상은 호로 돈다(반지름 = DWB 최소 기록).
3. **코너** — 각지지 않게 이어서 돈다. 레일에서 0.5~0.6 m 벗어나 있어도 멈추고 트는 대신 부드럽게 합류한다.
4. **초음파** — 멈추거나 감속만 하지 않고 15~20 cm 이상 비켜 간다. 너무 예민하지 않게 한다.
5. **도착 yaw** — 남은 각만큼 한 번에 돌고, 끝난 뒤 확인한다. 흔들기는 최소로 하고 허용오차는 기존 값을 쓴다. 빨리 끝내는 것이 좋다.
6. **회피** — collision_monitor 는 그대로 둔다. 회피는 MPPI 처럼 부드럽게, 휘청거리지 않게 한다.
7. **레일 복귀** — 각지게 꺾거나 섰다 갔다 하지 않고 부드럽게 돌아온다.
8. **가속** — 첫 출발과 정지 후 재출발은 목표 속도의 1/2 까지 살짝 올린 뒤 1.5~2 s 에 본래 속도까지 올린다. 도착 감속은 지금 값을 유지한다.
9. **장소** — 0630·0903_d 둘 다에서 잘 달려야 한다. 둘이 충돌하면 0630(좁음, 시연 장소도 좁음)을 우선한다.
10. **계산량** — RPP 보다 늘려도 되고 DWB 수준까지 허용한다. RPP 수준으로 잘 달리면 그대로 둔다.
11. **inflation 분리** — 생각만 하고 반영하지 않는다(§13).

사용자 확인으로 확정한 해석:

- 제자리 회전은 **정지 상태에서 출발할 때만, 60° 까지** 쓴다. 달리는 중 60° 미만 방향 변화는 곡선으로 잇는다.
- 유턴 반지름은 0.2 m 를 쓴다. 폭이 모자라면 0.1 m, 그래도 모자라면 제자리 회전으로 대신한다.
- 출발 가속은 0 → 0.25 m/s 를 약 0.5 s, 0.25 → 0.5 m/s 를 1.5~2 s 에 올린다.
- 초음파는 VCC 가 `/ultrasonic/*` 를 직접 읽고 1 s 안의 값만 쓴다. local costmap 초음파 층은 끈다.
- 도착 정렬은 최대 3회 돈다. 3회 뒤에도 허용오차 밖이면 "주행 불가"로 알린다.
- 방식은 C안(레일 추종 + 차선 고르기 + 상황 전환)이다.

## 3. 근거 — 사실 확인

### 3.1 Humble 1.1.20 의 컨트롤러 인터페이스

설치본은 `nav2_core`·`nav2_controller`·RPP·MPPI·`dwb_core` 모두 1.1.20 이다(`/opt/ros/humble/share/*/package.xml`).
docs.nav2.org 의 현재 튜토리얼은 rolling 판이다(`newPathReceived`, `cancel`, 인자 5개 `computeVelocityCommands`,
`ControllerTFError` 사용). **Humble 에서는 그대로 컴파일되지 않는다.** 기준은 설치 헤더
`/opt/ros/humble/include/nav2_core/controller.hpp:75-126` 와
`navigation2_tutorials` 저장소 `humble` 브랜치의 `nav2_pure_pursuit_controller` 로 삼는다.

- 필수 메서드: `configure(WeakPtr, name, tf, costmap_ros)`, `cleanup`, `activate`, `deactivate`,
  `setPlan(Path)`, `computeVelocityCommands(pose, velocity, goal_checker*)`, `setSpeedLimit(double, bool)`
- 예외: Humble 에는 `nav2_core::PlannerException` 만 있다(`exceptions.hpp:46`).
- `controller_server` 는 `PlannerException` 일 때만 `failure_tolerance` 를 적용한다. 다른 예외는
  곧바로 중단한다(`controller_server.cpp:489-507`, `427`). **VCC 는 반드시 `PlannerException` 만 던진다.**
- 도착 판정은 plugin 밖에서 한다. 받은 경로의 **마지막 점**을 goal checker 에 넘긴다(`controller_server.cpp:455, 589-607`).
- 출력은 `cmd_vel`(Twist) 이다. launch 가 이것을 `cmd_vel_nav` → velocity_smoother → `/cmd_vel` →
  collision_monitor → `/cmd_vel_req` → Safety → `/cmd_vel_safe` → motor 로 잇는다(`nav2_map_test.launch.py:349-392`).
  VCC 는 이 배선을 바꾸지 않는다.

### 3.2 내장 컨트롤러의 공통 성질 (VCC 가 따르는 것)

세 컨트롤러가 모두 가진 것은 다음이다.

- `transform_tolerance`
- `setSpeedLimit` 처리
- 경로 변환: 지나온 점 버리기, costmap 절반 밖 버리기
- costmap 기반 충돌 판정

RPP·MPPI 는 `max_robot_pose_search_dist` 도 가진다. VCC 의 경로 변환은 RPP `transformGlobalPlan`
(rpp.cpp:697-765, Apache 2.0)을 가져와 쓰고, 저작권 문구를 유지하며 바꾼 곳을 표시한다.

경로 창은 Nav2 Jazzy+ 의 FeasiblePathHandler 개념(가까운 점 범위·끝 2점 유지·1점 경로 거부 선택)을
옮긴 별도 부품(`core/path_window`)이다. 후진 전환점·제자리 회전 지키기는 쓰지 않는다(§11 후진 금지, 호 유턴 요구).

### 3.3 유턴 기하 (09-15 base_link 이동 뒤 첫 계산)

footprint 는 지금 값에 padding 0.05 를 넣었다. 180° 유턴에 필요한 통로 폭은 다음과 같다(몸 윤곽을 0.5° 간격으로 쓸어 계산).

| 방식 | 필요 폭 |
|---|---|
| 제자리 180° | 0.965 m |
| R 0.1 | 1.072 m |
| R 0.2 | 1.212 m |
| R 0.3 | 1.377 m |
| R 0.5 | 1.728 m |

- DWB 최소 유턴(run16)의 레일 이탈은 0.46 m 이고, R ≈ 0.2 에 해당한다.
- 0630 화장실 통로는 약 1.3 m(backlog B8)다.
- 그래서 R 0.2 를 기본으로 하고 R 0.1 을 예비로 둔다.
- R 0.89 m 로 돈 유일한 DWB 기록(08-29 run1241)은 lethal 에 들어가 60 s 갇힌 실패다.

### 3.4 inflation 사각지대

- inflation 0.55 는 padding 포함 외접 0.625 보다 작다. 벽에서 0.55~0.625 떨어진 띠는 중심 칸 비용이 0 이다.
- 그래서 비용을 보는 컨트롤러는 몸통 검사를 건너뛴다(backlog NAV2-B3, `nav2_params.yaml:338-346`).
- RPP·MPPI 는 "장애물까지 거리"를 inflation 비용에서 역산한다(rpp.cpp:648-655, obstacles_critic.cpp:92-116).
- VCC 는 **LETHAL 칸까지의 거리를 직접 계산**하고 **항상 몸 전체**로 검사한다. 사각지대가 구조적으로 없다.

## 4. 구조

### 4.1 패키지

`vica_ros2_ws/src/vica_vcc_controller/`

```
include/vica_vcc_controller/
  core/            ROS 를 모르는 순수 계산 (gtest 대상)
    geometry.hpp       footprint·호·거리 계산
    clearance.hpp      LETHAL 거리장(chamfer 2-pass)·초음파 점과의 거리
    path_window.hpp    경로 창(FeasiblePathHandler 개념 이식) — 가까운 점 범위·끝 2점 유지
    lanes.hpp          차선 후보 생성·채점·선택(줏대 규칙)
    speed_profile.hpp  코너 미리보기 감속·출발 가속·도착 감속
    turn_planner.hpp   유턴 방식 고르기(R 0.2 → 0.1 → 제자리)
    align_planner.hpp  도착 한 번 회전·넘침 보정
    state_machine.hpp  상황 4개·전환표·문턱·유지 시간
    output_stage.hpp   공용 출력단(가감속·회전 한계)
  vcc_controller.hpp nav2_core::Controller 어댑터
src/ ...
plugins.xml          pluginlib 등록 (base_class_type = nav2_core::Controller)
test/                gtest (core) + launch 없는 plugin 적재 시험
```

- plugin 이름은 `vica_vcc_controller::VccController` 다.
- CMake 는 `vica_nav2_bt_plugins` 모양을 따른다: 순수 계산 라이브러리, 얇은 plugin `.so`, `ament_add_gtest`.
- 여기에 `pluginlib_export_plugin_description_file(nav2_core plugins.xml)` 을 추가한다.
- **새 노드는 없다.** VCC 는 `controller_server` 안에서 돈다.

### 4.2 한 주기의 흐름 ("운전대 하나, 발판 하나")

```
setPlan ──> 경로 보관
computeVelocityCommands(pose, velocity, goal_checker):
  1. 경로 변환 (RPP transformGlobalPlan)
  2. 주변 5×5 m LETHAL 거리장 계산(`clearance_window`) + 초음파 점 모으기(1 s 이내)
  3. 상황 판단 (state_machine)
  4. 상황별 "가고 싶은 v, w" 계산
  5. 공용 출력단 (모든 상황이 같은 한계 통과)
  6. 안전 검사 (정지거리 안 몸통 충돌 → PlannerException)
  7. /vcc/state 발행, cmd 반환
```

## 5. 상황별 동작

### 5.1 ① 주행 — 레일 따라가기 + 차선 옮기기 + 코너

**조준점 따라가기(RPP 식)**

- 조준 거리는 속도 비례이며 `lookahead_time` 2.5 s, 범위 0.6~1.2 m 다.
- 근거: run36·39 직진 최고치다. `min_lookahead` 를 올리면 코너를 질러간다(yaml:417-418).
- 조준점은 "레일을 옆 간격 d 만큼 평행 이동한 경로" 위에 잡는다.

**코너**

- 달리는 중에는 조준점 각이 60° 미만이면 멈추지 않고 곡률 명령으로 잇는다.
- 레일에서 0.5~0.6 m 떨어져 있어도 조준점이 앞쪽 레일에 있으므로 비스듬히 합류한다.
- 이 상황에는 제자리 회전이 없다.

**차선 옮기기(비켜 가기)**

1. 후보: d ∈ {−0.6, −0.5, …, +0.6} m (13개, `lane_max_offset`, `lane_step`)
2. 차선마다 **지금 d 에서 후보 d 로 옮겨 가는 S자 경로**를 앞 `avoid_horizon` 1.5 m 까지 0.1 m 간격으로 만든다.
   각 자세에서 몸 전체(padding 포함) 최소 여유 c 를 잰다.
   - 벽·장애물: local costmap 의 LETHAL(254) 칸까지의 거리장이다. NO_INFORMATION 은 RPP 규칙대로 추적 중이면 충돌로 보지 않는다.
   - 초음파: 최근 1 s 안의 점까지의 거리다.
3. 채점
   - c < 0(접촉)이면 후보에서 뺀다.
   - 점수 = `w_clear`·max(0, 0.20 − c) + `w_rail`·|d| + `w_change`·|d − d_now|
   - 목표 간격 0.20 m 는 요구 4의 15~20 cm 에서 나왔다.
4. **예민하지 않게**
   - 1.5 m 밖의 물체는 채점에 들어가지 않는다. 3~4 m 앞 사람에는 반응하지 않는다.
   - 멀리 있는 사람 때문에 레일 BT 가 경로를 새로 짜는 것은 이번 범위 밖이다(§12.4).
5. **줏대(히스테리시스)**
   - 새 차선 점수가 지금 차선보다 `switch_margin` 이상 좋아야 한다.
   - 그 판단이 `switch_persist_cycles` 3주기(0.3 s) 연속돼야 바꾼다.
   - 예외: 지금 차선이 정지거리 안에서 접촉이 되면 즉시 바꾸거나 ④로 간다.
6. **부드럽게**: 옆 이동 속도 일정(≤ `lane_rate` 0.10 m/s), 차선을 옮기는 동안은 20 cm 가 나오는 가장 빠른
   속도(`lane_shift_speeds` 0.3 / 0.2 / 0.1 m/s)로 달린다.
   - 근거: smoothstep(S자)은 가운데 옆 속도가 평균의 1.5 배라 손잡이 상한 0.115 m/s(§11 탈락선)를 넘는다.
     0.4 m/s 그대로 달리면 0.6 m 옮기는 데 2.4 m 가 들어 1.5 m 앞 물체를 못 비킨다.
7. **복귀**: d = 0 차선이 `return_clear_time` 1.0 s 동안 막힘 없으면 같은 속도 상한으로 돌아온다.
8. **근접 감속**: 최소 여유 c 가 `slow_clearance` 0.35 m 미만이면 비례 감속하고 하한은 0.12 m/s 다.
   RPP `cost_scaling_dist` 0.35·`regulated_linear_scaling_min_speed` 0.12 와 같은 값이지만, 비용 역산이 아니라 **직접 잰 거리**를 쓴다.

비켜 가기와 복귀는 **상황 전환이 아니다.** ① 안에서 d 라는 숫자 하나가 연속으로 변할 뿐이다.

### 5.2 ② 유턴

**들어가기**

- 달리는 중: 조준점 각과 조준점 구간의 레일 방향 각이 **둘 다** |θ| > 60°(`turn_enter_angle`)일 때만 유턴으로 본다.
  - 근거: 레일과 나란히 0.55 m 떨어져 저속으로 달릴 때 조준점 각만 보면 66° 로 나와 유턴으로 오판한다(요구 3
    "0.5~0.6 m 이탈은 멈추지 않고 합류"와 충돌). 조준점 구간의 레일 방향까지 함께 봐야 "나란히 벗어난 것"과
    "정면으로 꺾인 것"을 가른다.
- 정지 상태(0.5 s 이상 v < 0.05)에서 출발: 둘 다 |θ| > 35°(`pivot_start_angle`)면 제자리 회전을 허용한다. 60° 까지만이며, 그 이상은 호 판정으로 간다.

**방식 고르기** (들어갈 때 1회, 이후 매 주기 남은 구간 재검사)

1. R 0.2 호를 가상 주행한다. 진입 전 감속 구간(v → w·R, 0.3 m/s²)을 포함해 몸 전체 여유 c ≥ `turn_clearance` 0.05 면 채택한다.
2. 실패하면 R 0.1 로 같은 검사를 한다.
3. 실패하면 제자리 회전을 검사한다(반지름 0.625 원 안 LETHAL 없음).
4. 모두 실패하면 ④ 대기로 간다.

**방향**

- 조준점 쪽으로 돈다.
- |θ| > 170° 로 양쪽이 비슷하면 여유가 큰 쪽으로 돈다.

**속도**

- w 는 호 방식이면 `turn_angular_vel` 0.45 rad/s, 제자리 방식이면 `pivot_angular_vel` 0.35 rad/s 다(smoother 상한 0.5 는 그대로 두되 직접 쓰지 않는다).
  근거: DWB U턴 실측 0.42~0.47(devlog 09-17 §5.4)과 RPP `rotate_to_heading_angular_vel` 0.35.
- v = w·R 이다. R 0.2 면 0.09 m/s 다.
- 남은 각이 줄면 5.3 의 넘침 보정 규칙으로 미리 감속한다.

**나오기**: |θ| < 25°(`turn_exit_angle`) 가 되면 ① 로 간다. 벌어진 간격(약 2R)은 ① 의 차선 복귀 규칙으로 좁힌다.

### 5.3 ③ 도착 정렬

**들어가기**

- 경로 끝점까지 거리 < goal checker 의 xy 허용오차(0.25, `getTolerances` 로 매 주기 읽음)
- 그리고 yaw 오차 > yaw 허용오차(0.25 rad)

**동작**

1. 멈춘다(도착 감속은 지금 RPP 규칙: 0.6 m 안에서 감속, 하한 0.05).
2. 남은 각 Δ 를 사다리꼴 속도로 돈다. 최고 0.35 rad/s, 각가속 1.2 rad/s² 로 지금 RPP 값이다(run41 되돌림 근거).
3. **넘침 보정**: 남은 각 < |w|·`motor_lag` 가 되면 회전 명령을 0 으로 끊는다.
   - `motor_lag` 기본 0.35 s 는 run41 에서 모터 지연 0.3~0.5 s 로 넘침 ±16~21° 를 낸 기록에서 나왔다.
4. 회전 속도(`velocity.angular.z` 실측)가 0.05 rad/s 아래로 떨어지고 `align_settle` 0.3 s 가 지나면 확인한다.
5. 허용오차 안이면 goal checker 가 도착을 선언한다. 밖이면 다시 돈다.
   - 이번 회차의 실제 넘침(끊은 뒤 더 돈 각)을 재서 다음 회차의 `motor_lag` 추정에 반영한다.
6. 최대 3회(`align_max_attempts`) 돈다. 3회 뒤에도 밖이면 `PlannerException("vcc: align failed")` 을 던진다.

- yaw 목표는 **경로 마지막 점의 방향**이다. goal checker 가 같은 점으로 판정하므로 둘이 일치한다(3.1).
- 도착 반경 경계에서 +145° 대회전(run39)이 나와도, 한 번에 도는 방식이라 헌팅은 생기지 않는다.
- 정지 기준(0.05 rad/s)은 goal checker 의 `rot_stopped_velocity` 를 매 주기 받아 쓴다. 최악(180° + 보정 3회)도
  15 s 안에 끝나 SimpleProgressChecker 20 s 안이다. goal/progress checker 는 컨트롤러 밖 부품이라 VCC 에 넣지
  않고, Humble 에 없는 Axis·AdaptiveTolerance 는 쓰지 않는다(Humble GoalChecker 에 경로 인자가 없어 핵심
  기능을 옮길 수 없다).

### 5.4 ④ 대기

- 모든 차선·유턴 방식이 막히면 출력단 최대 감속으로 멈춘다. 멈춘 뒤 매 주기 `PlannerException("vcc: blocked")` 을 던진다.
- 그 뒤는 지금과 같다: `failure_tolerance` 10 s → BT 복구(costmap 지우기·Wait 1 s).
- 정지거리 안에 몸통 접촉이 예측되면 멈추기를 기다리지 않고 즉시 던진다(RPP `isCollisionImminent` 와 같은 태도).
- 길이 열리면 ① 로 가고, 출발 가속을 적용한다.

## 6. 상황 전환 규칙

### 6.1 전환표

| 지금 \ 다음 | ① 주행 | ② 유턴 | ③ 도착 정렬 | ④ 대기 |
|---|---|---|---|---|
| ① 주행 | — | \|θ\| > 60° (달리는 중) / > 35° (정지 출발) | 끝점 0.25 안 + yaw 밖 | 모든 방식 막힘 |
| ② 유턴 | \|θ\| < 25° | — | 끝점 0.25 안 + yaw 밖 | 남은 구간 막힘 |
| ③ 도착 정렬 | 끝점 밖으로 0.35 m 넘게 밀림(새 경로 등) | **금지** | — | 3회 실패 / 회전 원 막힘 |
| ④ 대기 | 한 방식이라도 열림 (① 로만 나감) | 금지(① 거쳐서) | 금지(① 거쳐서) | — |

### 6.2 규칙

1. **들어가는 문턱과 나오는 문턱이 다르다.** 유턴은 60°/25°, 도착은 0.25/0.35 m 다.
2. **최소 유지 0.5 s**(`min_state_time`): 한 번 바뀐 상황은 0.5 s 유지한다. ④ 로 가는 안전 전환만 예외다.
3. **우선순위**: ④ 안전 대기 > ③ 도착 > ② 유턴 > ① 주행
4. **새 경로(setPlan)**: 상황을 초기화하지 않는다. 지금 상황의 조건을 새 경로로 다시 평가하고, 여전히 유효하면 이어간다.
   - 레일 BT 가 1 Hz 로 경로를 바꿔도 유턴·도착 정렬이 중간에 끊기지 않는다.
5. **새 goal**: 상황과 d, 도착 회차를 초기화한다. goal 이 바뀐 것은 경로 끝점이 0.5 m 넘게 이동한 것으로 판단한다.
6. `deactivate`·`cleanup` 은 모든 내부 상태를 지운다.
7. 전환표의 모든 칸(허용·금지)을 gtest 로 하나씩 확인한다.

## 7. 공용 출력단

모든 상황이 같은 한계를 거친다. 상황이 바뀌어도 **직전 실제 명령에서 이어서** 출발하므로 속도가 튀거나 0 으로 떨어지지 않는다.

| 항목 | 값 | 근거 |
|---|---|---|
| v 범위 | 0 ~ 0.5 m/s | 후진 금지(§11), 최고 속도 지금 값 |
| w 범위 | ±0.5 rad/s, 좌우 대칭 | smoother 상한·대칭 규칙(yaml:2567-2577) |
| 각가속 | 1.2 rad/s² | 지금 RPP `max_angular_accel` |
| 출발 가속 | 0 → 0.25: 0.5 m/s² (0.5 s), 0.25 → 0.5: 0.143 m/s² (1.75 s) | 요구 8 |
| 출발 가속 적용 조건 | v < 0.05 가 0.5 s 이상 지속된 뒤 | 요구 8(첫 출발 + 정지 후 재출발) |
| 일반 재가속 (코너 뒤) | 0.143 m/s² | 코너 뒤 "천천히 다시 올리기" |
| 코너 미리보기 감속 | 0.3 m/s² | 아래 설명 |
| 안전 감속 | 최대 1.25 m/s² | smoother `max_decel` 과 같음, 완화 금지(yaml:2606-2612) |
| 도착 감속 | 0.6 m 안 비례, 하한 0.05 | 지금 RPP 값(요구 8 "현재가 좋음") |
| speed_limit | `setSpeedLimit` 으로 최고 속도 제한 | RPP 와 같은 처리(rpp.cpp:680-696) |

**코너 미리보기 감속**(MPPI 의 "미리 보고 미리 줄이는" 성질만 가져옴):

- 앞 1.5 m 경로 점마다 곡률 κ 를 계산한다. 한계 속도 = 0.5·min(1, (1/κ)/1.2) 이고 하한은 0.12 다(RPP 규칙과 같은 값).
- 뒤에서 앞으로 v_i ≤ √(v_{i+1}² + 2·0.3·s) 를 적용해, 곡선 앞부터 서서히 줄인다.
- MPPI 의 확률 계산 전체는 가져오지 않는다. 가져오면 비틀거림(방향 바뀜 43회/분)도 따라온다.
- **곡률은 0.2 m 간격 세 점으로 재고, 거리는 그 세 점 중 가장 가까운 점까지로 계산한다**(구현 중 발견).
  가운데 점을 기준으로 삼으면 한 칸(0.2 m) 늦게 줄인다. 대가로 첫 세 점에는 코너 앞 직선이 섞여 곡률이
  옅게 잡혀, 0.2 m 앞 코너에서 이론값 0.404 대신 0.374(조금 이르고 느리게)가 나온다. 이론값보다 이르게
  줄이는 쪽이라 안전하며, 시험은 값 하나가 아니라 0.35~0.434 범위로 확인한다.

smoother `max_accel` 2.5 는 그대로 둔다. VCC 가 더 완만한 곡선을 내므로 smoother 는 상한 역할만 한다.

## 8. 초음파 입력

- 구독 토픽은 `ultrasonic_topics` 로 정하며 기본은 front_left, front_right, left_wheel, right_wheel 이다(sensor_msgs/Range).
- 이들은 controller_server 노드 안의 구독이다(새 노드 아님). 콜백과 제어 주기 사이는 mutex 로 보호한다.
- **나이는 받은 시각(steady clock) 기준 1.0 s** 다. stamp 기준이 아니다.
  - 근거: run44 에서 collision_monitor 가 stamp 지연 때문에 소스를 660회 무시했다.
  - 좌표 변환은 최신 TF 를 쓴다.
- `min_range < range < max_range` 인 값만 쓴다. 최대값(물체 없음)과 무효값은 버린다.
- 한 측정값은 센서 방향 ± `field_of_view`/2 호 위의 점 여러 개로 바꾼다.
  - field_of_view 는 드라이버가 채널별로 준다. 바퀴 옆 60°, 앞 30° 다(`ultrasonic_fov_rad_per_channel`).
- 초음파 점은 차선 채점과 정지거리 검사에만 쓴다. 1.5 m 밖은 쓰지 않는다.
- 예민함 억제
  - 펌웨어가 이미 3개 중앙값을 낸다.
  - VCC 는 같은 채널의 연속 2개가 서로 0.15 m 안에서 일치할 때만 점으로 인정한다(`us_confirm_count`).
  - 벤치 시험에서 바퀴 옆 60° 로도 바닥 유령이 없었다.
- **local costmap 의 range 층 4개는 `enabled: False`** 로 바꾼다(§12.2). 지워지지 않는 표시가 몸통 검사를 막는 일(run43 정지 9회)을 없앤다.

## 9. 거리 계산과 계산량

- 거리장: 로봇 중심 5×5 m 창(`clearance_window`, 0.05 m 격자, 100×100 칸)이다. LETHAL 칸을 시작점으로 chamfer 2-pass 거리 변환을 매 주기 1회 한다.
  - 근거: 앞 1.5 m(`avoid_horizon`) + 몸 외접 0.625 m 를 덮으려면 반폭이 2.2 m 필요하다. 3×3 m(반폭 1.5 m)로는
    코너 미리보기·차선 끝점이 창 밖으로 나가 여유를 못 잰다.
- 몸 여유: footprint 윤곽을 0.05 m 간격으로 표본해 거리장에서 최소값을 찾는다. 초음파 점과는 다각형까지 직접 거리를 구한다.
- 한 주기 계산 = 거리장 1회 + (차선 13 × 자세 15) 몸 여유 + 코너 미리보기 30점 + (유턴 중) 호 가상 주행이다.
- 조절 손잡이: `lane_step`, `lane_max_offset`, `avoid_horizon`, `controller_frequency` 로 계산량을 늘리거나 줄인다.
- **예산**: 출발점은 RPP 수준(controller CPU 10.6 %)이다. 부드러움·속도가 부족하면 DWB 수준(19.1 %, run23)까지 올린다(사용자 지시).
- 젯슨에서 한 주기 시간을 재는 벤치 시험을 둔다.

## 10. 실패 처리

| 상황 | 동작 |
|---|---|
| 정지거리 안 몸통 접촉 예측 | 즉시 `PlannerException("vcc: collision ahead")` |
| 모든 방식 막힘 | 멈춘 뒤 `PlannerException("vcc: blocked")` |
| 도착 정렬 3회 실패 | `PlannerException("vcc: align failed")` |
| 로봇 위치가 costmap 밖 / TF 실패 | `PlannerException` (RPP 와 같음) |
| 경로가 비었거나 점 1개 | 점 1개면 그 점을 끝점으로 ③ 판단, 0개면 `PlannerException` |
| 초음파 전부 오래됨 | 라이다만으로 동작하고 `/vcc/state` 에 표시(멈추지 않음). collision_monitor 가 라이다 쪽 안전을 따로 맡는다 |

`std::runtime_error` 등 다른 예외는 던지지 않는다(3.1).

## 11. 설정 파라미터 (`FollowPath.*`)

| 이름 | 기본값 | 근거 |
|---|---|---|
| `desired_linear_vel` | 0.5 | 지금 RPP |
| `lookahead_time` / `min_lookahead_dist` / `max_lookahead_dist` | 2.5 / 0.6 / 1.2 | run36·39 |
| `transform_tolerance` | 0.2 | 지금 RPP |
| `max_angular_vel` / `max_angular_accel` | 0.5 / 1.2 | smoother 상한 / 지금 RPP |
| `lane_max_offset` / `lane_step` | 0.6 / 0.1 | 요구 3(0.5~0.6 m 이탈 허용) |
| `avoid_horizon` | 1.5 | 요구 1(3~4 m 앞 무시) |
| `target_clearance` | 0.20 | 요구 4 |
| `w_clear` / `w_rail` / `w_change` / `switch_margin` | 10 / 1 / 0.5 / 0.05 | `test_lanes` 시나리오 9개(구현 중 확정) |
| `switch_persist_cycles` | 3 | 0.3 s |
| `lane_rate` | 0.10 m/s | §11 손잡이 0.115 탈락선 |
| `return_clear_time` | 1.0 s | — |
| `slow_clearance` / `min_speed` | 0.35 / 0.12 | 지금 RPP 값 |
| `curve_min_radius` / `curve_decel` | 1.2 / 0.3 | 지금 RPP / 새 값 |
| `turn_enter_angle` / `turn_exit_angle` / `pivot_start_angle` | 60° / 25° / 35° | 요구 2, 사용자 확인 |
| `turn_radii` | [0.2, 0.1] | 3.3 |
| `turn_clearance` | 0.05 | padding 과 같은 두께 |
| `turn_angular_vel` / `pivot_angular_vel` | 0.45 / 0.35 | DWB U턴 실측 0.42~0.47(devlog 09-17 §5.4) / RPP `rotate_to_heading_angular_vel` |
| `align_angular_vel` / `motor_lag` / `align_settle` / `align_max_attempts` | 0.35 / 0.35 / 0.3 / 3 | run41·42, 사용자 결정 |
| `start_ramp` | [0.25, 0.5 s, 1.75 s] | 요구 8 |
| `approach_velocity_scaling_dist` / `min_approach_linear_velocity` | 0.6 / 0.05 | 지금 RPP |
| `min_state_time` | 0.5 s | 6.2 |
| `ultrasonic_topics` / `us_max_age` / `us_confirm_count` | 4개 / 1.0 / 2 | 8 |
| `publish_state` | true | 판정용 |

- 가중치 값은 설계에서 숫자를 정하지 않는다. 근거 없는 숫자를 쓰지 않기 위해서다.
- 대신 구현 계획에서 "무엇이 무엇보다 우선해야 하는가"를 gtest 시나리오로 먼저 적고, 그 시나리오를 통과하는 값으로 정한다. 예: 20 cm 간격 확보 > 레일 가까움 > 차선 유지.
- 구현 뒤: 위 표의 10 / 1 / 0.5 / 0.05 는 `test_lanes` 9개 시나리오를 전부 통과하는 값으로 확정했다.

## 12. 지킬 선과 바꾸는 것

### 12.1 그대로 지키는 것

| 항목 | 값 | 근거 |
|---|---|---|
| 후진 금지 | 후진 명령 없음, BackUp·Spin 복구 없음 | §11 |
| footprint | 지금 육각형 + padding 0.05, local = global | `test_footprint_contract`, §11 |
| inflation | 0.55 / `cost_scaling_factor` 3.5 | §11(0.50 이하 금지), C6 |
| 도착 판정 | StoppedGoalChecker xy 0.25 / yaw 0.25, 0.03 / 0.05, stateful False | 08-28 사용자 확정, run41 되돌림 |
| planner·레일 | Lattice R 0.10, tolerance 0.2, rotation_penalty 5.0, 당근 3 m, smooth_corners false | §11, C7, NaN 970회 사고 |
| collision_monitor | 지금 그대로(앞쪽, 라이다만, 입력 `/cmd_vel`) | 요구 6, §11 후방 금지 |
| velocity_smoother | ±0.5 / ±0.5(대칭), 감속 완화 금지, timeout 0.4 | yaml:2567-2621 |
| 배선 | controller → smoother → CM → `/cmd_vel_req` → Safety | CLAUDE.md |
| 참기 규칙 | failure_tolerance 10 s, 진행 검사 0.10 m / 20 s | yaml:246-278 |
| 제어 주기 | 10 Hz | 지금 값. 올리면 계산량 예산 안에서 |
| BT | 손대지 않음 | 범위 밖 |

### 12.2 바꾸는 것

1. **`FollowPath.plugin` 을 RPP 에서 `vica_vcc_controller::VccController` 로 바꾼다.**
   - 지금 RPP 블록은 `FollowPathRPP` 로 이름을 바꿔 보존한다. 한 줄로 되돌릴 수 있다.
   - DWB·MPPI 보존 블록은 그대로 둔다.
2. **local costmap range 층 4개(front_left, front_right, left_wheel, right_wheel)를 `enabled: False` 로 바꾼다.**
   - 이유: run43 정지 9회, 사용자 결정.
   - 대가: 라이다 높이(0.38 m) 아래의 낮은 물체는 이제 VCC 만 안다(collision_monitor 는 라이다 전용). VCC 는 비켜 갈 수 없으면 반드시 멈춘다. 이를 시험 항목에 넣는다.
3. **계약 시험 2개에 VCC 분기를 추가한다**(`test_planner_contract.py:147-203`, `test_nav2_params_contract.py:18-60`).
   - 지금은 plugin 이름으로 종류를 나누므로 VCC 를 DWB 로 오분류한다.
   - 기준은 느슨하게 하지 않는다. VCC 분기도 몸 전체 충돌 검사, 후진 금지, 감속 ≥ 1.0, 가감속 정합을 검사한다.
4. **문서 정정**(사용자 승인 2026-09-24)
   - `docs/nav2_backlog.md` §11 RPP 항목에 09-21 재도입 사실을 적는다.
   - `CLAUDE.md` 의 "§9 하지 말 것"을 "§11" 로 고친다.

### 12.3 바꿔도 되지만 일부러 안 바꾸는 것

- **inflation 0.62 이상 인상**(B3 의 "컨트롤러 바꾸기 전" 조건)은 하지 않는다.
  - 이 조건이 막으려던 위험은 "중심 비용 0 이면 몸통 검사를 건너뜀"이다.
  - VCC 는 항상 몸 전체를 LETHAL 과 대조하므로 위험이 구조적으로 없다.
  - 올리면 사람을 비켜 가는 폭이 넓어진다는 기존 우려도 피한다.
- **smoother `max_accel` 2.5 → 0.5**(09-17 보류안)는 하지 않는다. VCC 가 출발 가속을 직접 만든다.

### 12.4 범위 밖 (알고 넘어가는 것)

- 레일 BT 의 1 Hz 재계획, IsPathValid 판단, 멀리 있는 사람 때문에 경로가 바뀌는 흔들림은 범위 밖이다.
- controller_server 의 "경로 끝점으로 도착 판정" 구조도 범위 밖이다(Nav2 쪽).
- planner tolerance 0.2 로 1점 경로가 나오는 문제(−104° 사건)도 범위 밖이다. VCC 는 1점 경로에서도 그 점의 방향으로 정렬할 뿐이다.

## 13. inflation 분리 — 생각만 (반영하지 않음, 사용자 "나중에 적용")

- global 과 local 은 서로 다른 costmap 이라 inflation 을 따로 줄 수 있다.
- 지금까지 잘 안 된 이유가 있다.
  - planner 는 global inflation 으로 경로를 그린다.
  - RPP·MPPI 는 local inflation 비용에서 벽까지 거리를 역산하며, 역산 값이 costmap 과 같아야 했다.
  - 그래서 한쪽을 바꾸면 다른 쪽 판단이 어긋났다.
  - Humble 에는 층마다 inflation 을 달리 주는 `PluginContainerLayer` 도 없다(Jazzy 이후 기능).
- VCC 뒤에는 역할이 나뉜다.
  - global inflation 은 "경로를 가운데로 끌어오는 힘"만 맡는다.
  - "실제로 얼마나 붙어도 되는가"는 VCC 가 직접 잰 거리가 맡는다.
  - 유턴 가능 여부는 몸 모양으로 호를 가상 주행해서 판단한다.
- 나중 후보(VCC 실기 안정 뒤):
  - (1) local inflation 을 얇게 해 표시용으로만 둔다.
  - (2) VCC 에 벽 전용 여유값을 둔다. 예: 벽 0.05, 사람·초음파 물체 0.20.

## 14. 성공 판정 기준

- 정규화 지표를 쓴다(초 단위 절대값은 쓰지 않음).
- 0630 과 0903_d 는 따로 판정한다. 0630 벽 근처 비율은 "run13(11.2 %) 보다 나쁘지 않게"로 본다.

| 요구 | 지표 | 합격 | 탈락 | 근거 |
|---|---|---|---|---|
| 직진 | 곧은 구간 손잡이 좌우 속도 | ≤ 0.060 m/s | > 0.084 | RPP run39 0.057 / DWB run23 0.084 |
| 직진 | 큰 좌우 반전 | ≤ 20 /분 | > 35.8 | run36 18.8 / DWB 35.8 |
| 직진 | 1.5 m 밖 물체로 차선 바꿈 | 0 | ≥ 1 | 새 기준(`/vcc/state`) |
| 유턴 | 유턴 시간 중 제자리 비율 | ≤ 30 % | > 42 % | DWB 최선 32 % / RPP 42 % |
| 유턴 | 레일 이탈 최대 | ≤ 0.50 m | > 0.75 | DWB run16 0.46 / 당근 6 m 0.75 |
| 코너 | 일반 코너 제자리 비율 | ≤ 5 % | > 7 % | MPPI 0~3 % / DWB 7 % |
| 코너 | 코너 정지 | 0 | — | 요구 3 |
| 초음파 | 콘 옆 간격 | ≥ 0.15 m, 접촉 0 | 접촉 | 요구 4 / run46 접촉 |
| 초음파 | 빈 길 초음파 정지 | 0 | ≥ 1 | run43 9회 |
| 도착 | yaw 오차 | 전부 ≤ 14° | 1건 초과 | goal checker |
| 도착 | 첫 회 성공률 / 최대 횟수 | ≥ 80 % / 3 | 4회 이상·헌팅 | run42 |
| 도착 | 정렬 시간 중앙값 | ≤ 3 s | > 7.7 s | run39 0.6~1.1 / run13 최대 7.7 |
| 회피 | 회피 중 손잡이 좌우 속도 최대 | ≤ 0.115 m/s | 초과 | §11 |
| 회피 | 사람 사건당 정지 | ≤ 0.64 s | > 2.67 s | DWB run23 / MPPI run24 |
| 복귀 | 레일 이탈 평균 | ≤ 0.15 m | > 0.25 | DWB 0.15 / RPP 0.11 |
| 복귀 | 복귀 중 정지 | 0 | — | 요구 7 |
| 가속 | 바퀴 0 → 0.25 m/s | 0.4~0.7 s | < 0.3 s | 설계 / 옛 0→0.3 이 0.43 s 로 급함 |
| 가속 | 바퀴 0.25 → 0.5 m/s | 1.5~2.0 s | — | 요구 8 |
| 전체 | 완주 / 손 개입 | 100 % / 0 | 손 개입 ≥ 1 | run13 15/15, run15~22 62/62 |
| 부하 | controller CPU | ≤ 19.1 % | > 19.1 % | 사용자 지시(DWB 수준) |
| 부하 | 제어 주기 놓침 경고 | 0 | 반복 | run20 0 |

## 15. 시험 순서

1. **책상 시험 (로봇 안 움직임)**
   - core gtest: 전환표 전 칸, 3.3 유턴 폭 표 재현, 차선 채점 시나리오, 출발 가속 곡선, 코너 미리보기, 넘침 보정.
   - plugin 적재 시험과 계약 시험.
   - 젯슨 한 주기 시간 벤치.
2. **바퀴 띄운 시험**
   - AGENTS.md §4 에 따라 바퀴를 띄우고 물리 E-stop 을 확인한 뒤에만 한다.
   - plugin 적재, 출발 가속과 도착 회전의 명령 모양을 본다.
3. **0903_d 실주행 (넓은 곳 먼저)**: run23·36 과 같은 목적지 순서로 짝 비교한다.
4. **0903_d 특수 시험**: 30 cm 콘(초음파), 가로지르는 사람, 레일 위 3~4 m 앞 사람.
5. **0630 실주행**: 좁은 곳, 화장실 유턴, 시연 조건.
6. **다듬기**: 탈락 항목만 한 번에 값 하나씩, 성공과 실패 숫자를 미리 정하고 조정한다. 매 주행 뒤 커밋한다.

매 주행에는 rosbag(`/vcc/state` 포함)을 건다. 기록 중인 bag 은 읽지 않는다.

## 16. 위험과 미확정

| 항목 | 내용 | 대응 |
|---|---|---|
| 모터 지연 | 0.35 s 는 run41 의 0.3~0.5 s 범위에서 고른 값이다 [추정] | 회차마다 실측 넘침으로 갱신(5.3 ⑤) |
| 호 추종 정확도 | CAN·드라이버 지연 300 ms 로 추종 오차 12 cm(backlog D2) | 호 가상 주행 여유 0.05 + 매 주기 남은 구간 재검사 |
| 초음파 위치 | URDF 초음파 6개 좌표는 추정값 [미검증] | 콘 시험에서 실제 간격으로 확인 |
| 구독 스레드 | controller_server 에서 plugin 구독 콜백이 어느 executor 에서 도는지 | 구현 첫 단계에서 확인, mutex 로 보호 |
| 가중치 | `w_*` 값 | 11절 방식(시나리오 먼저) |
| 레일 U턴 경로 | 레일 생성기는 120° 넘는 코너를 둥글리지 않아 조준점 각이 튄다(FILLET_MAX_DEG) | ② 의 문턱·유지 시간으로 흡수 |
| 몸 여유 계산 창 경계 | 몸 상자(bounding box)가 거리장 창 밖으로 나가는 자세(먼 자세·창 경계 자세)에서 자르지 않은 칸 범위로 돌면 반복이 커진다(구현 중 발견) | 몸 상자의 칸 범위를 거리장 창 안으로 자른다. 상자가 창과 아예 안 겹치면 안쪽-칸(접촉) 검사만 건너뛴다(`clearance.cpp`) |

## 17. 요구사항 대응표

| 요구 | 반영 위치 |
|---|---|
| 1 상황별 동작 (직진·유턴·코너·초음파·도착·회피·복귀·가속) | 5.1 / 5.2 / 5.1 / 5.1·8 / 5.3 / 5.1 / 5.1 ⑦ / 7 |
| 2 컨트롤러별 장점 조합 | 1, 5.1(RPP 조준), 5.1·7(MPPI 식 미리보기·부드러운 차선 이동), 5.2(DWB 식 작은 호) |
| 3 지킬 선 가이드라인·바꾼 이유 | 12 |
| 4 성공 기준 | 14 |
| 5 장소(0630 우선) | 3.3(0630 통로 기준 R), 14, 15 |
| 6 inflation 분리 | 13 (반영 안 함) |
| 7 기존 결정·기록 참고 | 1, 3, 12, 14 의 근거 열 |
| 8 Nav2 공식 문서·공통 성질 | 3.1, 3.2, 4.1 |
| 9 근거 기반 | 모든 값에 근거 열, 가중치는 시나리오로 정함 |
| 10 헷갈리면 확인 | 2절 "사용자 확인으로 확정한 해석" |
| 11 이름 vcc | 4.1 |
| 12 자체 점검 | 구현 뒤 이 표로 다시 점검 → 17.1 |

### 17.1 구현·시험 대조 (요구 12, 구현 뒤 채움)

각 행의 시험을 grep 으로 실제 존재를 확인했다(빈 행 없음).

| 요구 | 구현·시험 |
|---|---|
| 직진 흔들림 | `pure_pursuit` + `test_vcc_core StraightStartRampsWithoutTurning` |
| 3~4 m 앞 사람 무시 | `lanes horizon` + `test_lanes FarObstacleBeyondHorizonIsIgnored` |
| 유턴 호 R 0.2/0.1/제자리 | `turn_planner` + `test_turn_planner` 4개 |
| 정지 출발 60° 까지 제자리 | `test_state_machine StationaryPivotFromThirtyFiveDegrees`, `test_turn_planner StationarySmallTurnPrefersPivot` |
| 코너 0.5~0.6 m 이탈 부드럽게 | `test_state_machine ParallelOffsetRailIsNotAUturn`, `test_vcc_core ParallelOffsetRejoinsWithoutStopping` |
| 코너 감속 부드럽게 | `test_speed_profile CornerIsAnticipatedNotSudden` |
| 초음파 15~20 cm 비켜 가기 | `test_lanes PoleOnRailIsPassedWithTwentyCentimetres`, `test_ultrasonic` 5개 |
| 도착 한 번에·최대 3회·허용오차 유지 | `test_align_planner` 4개, goal checker 값 불변(`test_nav2_params_contract`) |
| 회피 부드럽게·휘청 금지 | `test_lanes NearlyEqualLanesDoNotFlipFlop`, `OffsetMovesAtLaneRate` |
| 레일 복귀 부드럽게 | `test_lanes ReturnsToRailOnlyAfterOneSecondClear` |
| 출발 가속 | `test_output_stage StartRampHalfSpeedThenSlow`, `ResyncsToMeasuredSpeedAfterExternalStop` |
| collision_monitor 동일 | yaml diff 에 collision_monitor 변경 0 |
| 지킬 선 | `test_vcc_limits_match_the_smoother`, `test_planner_contract` VCC 분기, 후진 금지 `NoReverseAndSymmetricTurnLimit` |
| inflation 분리는 반영 안 함 | yaml diff 에 inflation 변경 0 |
| 계산량 DWB 이하 | bench p99(9절, 15절) |
| 이름 vcc | 패키지·플러그인 이름 |
| 경로 처리 분리(FeasiblePathHandler 개념, 09-28 추가) | `core/path_window` + `test_path_window` 8개 |
| goal/progress checker 정합(09-28 추가) | 정지 기준을 goal checker 에서 받음(Task 13 `rot_stopped`), `test_align_planner WorstCaseFinishesInsideProgressCheckerWindow`, `StoppedVelocityFollowsGoalChecker` |
