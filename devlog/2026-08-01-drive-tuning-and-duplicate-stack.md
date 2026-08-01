# 주행 튜닝과 중복 실행 사고 (2026-08-01)

앱 종단 검증에서 시작해 주행 3회차까지 갔다. 하루의 절반은 **설정이 아니라 중복
실행**을 디버깅하는 데 썼다. 그 사실 자체가 이 문서의 가장 중요한 내용이다.

## 1. 중복 실행 — 오늘의 근본 원인

### 1.1 무슨 일이 있었나

두 번 겪었다.

**① 스택 전체가 두 벌 (오후)**

터미네이터를 `:1`(젯슨 물리 화면)과 `:10`(xrdp 원격)에 각각 띄웠다. 자동 실행
칸이 양쪽에서 돌아 노드 10종이 2개씩 떴다.

```text
encoder_feedback  x2      ekf_node          x2
amcl · planner · controller · bt_navigator  x2
lidar · imu · safety · robot_state_publisher x2
/odom 발행자 2개
```

`/odom`을 두 노드가 발행하니 값이 번갈아 나왔다. 한 표본은 `x=3.172`, 다음 표본은
`x=0.0`이었다. AMCL이 그것을 보고 판단하니 RViz에서 로봇이 튀었다.

**② RViz만 두 개 (저녁)**

```text
rviz2  146 %  +  rviz2  128 %      load 20.9 (코어 8개)
```

RViz 하나가 코어 1.5개를 쓴다. CPU가 모자라 **EKF가 설정 30 Hz의 절반인 15.5 Hz로
떨어졌다.** RViz를 끄자 24.7 Hz로 회복했다 — 같은 조건에서 잰 before/after다.

### 1.2 왜 오래 걸렸나

두 경우 모두 증상이 **"위치추정 오류"**로 나타났다. 앱 화면에 "주행 불가 ·
위치추정 오류"가 떴고, planner가 경로를 못 냈다. 설정을 의심하며 시간을 썼다.

`ros2 node list`가 죽은 노드를 한동안 캐시해 오판을 키웠다. 프로세스 테이블과
DDS 그래프가 어긋난 상태에서 DDS 쪽을 믿었다.

### 1.3 대책

`scripts/vica_terminator_layout.py`의 rc에 중복 검사를 넣었다. 15칸에 적용된다.

```bash
vica_guard "rplidar_node" || return 2>/dev/null || exit 0
```

이미 떠 있으면 pid와 경과 시간을 보여주고 **명령을 내보내지 않는다.** 의도적으로
두 벌 띄워야 할 때는 `VICA_FORCE=1`로 넘어간다.

`ros2` CLI를 쓰지 않는다. DDS 그래프의 캐시가 오탐을 만들고 조회도 느리다.
프로세스 테이블이 지금 이 순간의 사실이다.

## 2. 감시 계층이 만든 거짓 오류 두 건

### 2.1 robot_localization의 죽은 진단

`/robot/health`가 `localization_readiness: 1`(NOT_READY)을 상시 보고했다. 그런데
aggregator의 `/VICA/Localization`은 전부 OK였다. 원본을 열어 보니 이랬다.

```text
name: 'ekf_filter_node: odometry/filtered topic status'
message: No events recorded.
Events since startup: 0        <- 기동 이후 단 한 번도 세지 않았다
Actual frequency: 0.000000
Minimum acceptable: 25.2 Hz
```

같은 시각 `/odom`은 24.7 Hz로 정상 발행 중이었다. `Events since startup: 0`이
핵심이다 — 주기가 낮은 것이 아니라 카운터가 아예 돌지 않는다.

`ekf.yaml`에 `print_diagnostics: false`를 넣었으나 사라지지 않았다(설정을 읽는
것은 `--params-file` 경로로 확인했다). robot_localization의 `.cpp`가 설치돼 있지
않아 정확한 기전은 확인하지 못했다. **한 번도 참인 적이 없는 진단**이므로
`agg_parser.IGNORED_NAME_FRAGMENTS`로 소비 쪽에서 뺐다.

`/odom` 주기 감시는 우리 프로브가 대신한다(`probes.yaml`, min 20 / max 35 Hz).
1.2의 15.5 Hz를 실제로 잡아낸 것이 그 프로브다.

### 2.2 `bt_navigator/get_state` 무응답

`navigation_readiness`가 `NAV2_NOT_ACTIVE`였는데 `lifecycle_manager`는
"Nav2 is active"를 정상 발행하고 있었다. 감시 노드가 `/bt_navigator/get_state`를
폴링하는데 그 서비스가 응답하지 않았다. CLI로 같은 서비스를 부른 명령도 10분간
반환되지 않아 세션이 멈췄다(그때는 "느리다"고만 판단했다).

서비스가 안 될 때 `lifecycle_manager` 진단을 대신 읽도록 `_nav2_active_by_diagnostic()`
을 넣었다. 서비스 응답보다 약한 근거라 **서비스가 실패할 때만** 쓴다.

두 건을 고친 뒤 `/robot/health`가 처음으로 이렇게 나왔다.

```text
state: 1 (READY)      active_fault_count: 0
motor 2 · safety 2 · localization 2 · navigation 2 · lidar 2 · perception 2
```

### 2.3 이름 분류 순서 버그

`lifecycle_manager_localization: Nav2 Health`가 위치추정으로 분류됐다.
`_NAME_HINTS`가 위에서부터 부분 문자열로 매칭하는데 `localization`이 `nav2`보다
위에 있었다. Nav2 lifecycle 상태가 위치추정 상태로 보고되면 정비하는 사람이
엉뚱한 곳을 본다. 순서를 바꾸고 시험 2건으로 고정했다. 규칙은
**"더 구체적인 이름을 위에"**다.

## 3. planner 축 전환 — 두 번 바꿨다

### 3.1 Lattice -> NavFn (오후)

1차 주행(run01, Lattice + ObstacleFootprint)에서 안내소 -> 방2 7.1 m를 간 뒤
목표 3 m 앞에서 ABORT했다. 그 자리 라이다는 정면 1.17 m, 좌앞 0.60 m,
**우측 3.75 m**를 보고 있었다. 오른쪽이 뚫려 있는데 우회 경로가 나오지 않았다.

사용자가 "NavFn 시절이 훨씬 잘 달렸다"고 했고, 그때 설정을 뽑아 보니 결정적
차이가 planner가 아니라 **DWB critic**이었다.

```text
NavFn(점)    + BaseObstacle(점)       -> 일치. 잘 달렸다
Lattice(면)  + ObstacleFootprint(면)  -> 일치. 2026-08-01 실패
2D(점)       + ObstacleFootprint(면)  -> 불일치. 2026-07-28 갇힘
```

그래서 `test_planner_contract`의 계약을 **"planner가 footprint를 봐야 한다"**에서
**"planner와 controller가 같은 자로 재야 한다"**로 바꿨다. 불일치가 재발을 부르는
축이고, 어느 축으로 맞출지는 실측으로 고르는 튜닝 사항이다.

run02(NavFn + BaseObstacle)는 9.8 m를 가서 목표 0.24 m 앞까지 접근했다
(도착 기준 0.25 m). 방향도 3.6도 차이로 기준 안이었다.

### 3.2 NavFn -> SmacPlanner2D (저녁)

run03에서 사용자가 보고했다.

- 코너에서 부딪힘
- **"경로 생성할 때부터 고정 장애물에 거의 붙어서 생성되니까 몸체가 부딪혔다"**

`inflation_radius`를 0.45 -> 0.60으로 올리자 부딪힘은 사라졌으나 **코너에서
멈추고 yaw가 좌우로 지그재그**하는 증상이 심해졌다.

이 증상은 이 파일이 이미 예언해 둔 것이었다. `inflation_layer` 주석의
"0.65로 올렸을 때" 문단이 그대로다.

> 통로 전체가 비용 지대가 되어 최소비용 경로가 거의 동점이 되고, LiDAR
> 노이즈마다 경로가 뒤바뀌며 주춤거렸다(2026-07-27 실주행).

반대쪽 문단은 "0.35일 때 경사 구간이 폭 7 cm뿐이라 중앙 유도력이 없어 벽에
붙었다"고 적었다. **좁히면 붙고 넓히면 진동하는 것이 NavFn의 구조적 한계다.**

원인은 NavFn에 **비용 회피 가중치가 없다**는 것이다. 파라미터가
`tolerance`/`use_astar`/`allow_unknown` 셋뿐이라, 경로를 벽에서 떼는 유일한 수단이
`inflation_radius`를 키우는 것이고 그 대가가 진동이다.

SmacPlanner2D는 `cost_travel_multiplier`로 비용을 명시적으로 가중한다. 좁은
inflation(0.45)으로도 중앙을 유지할 수 있어 두 증상이 분리된다. 로봇을 점으로
보는 것은 NavFn과 같으므로 BaseObstacle과 축이 그대로 일치한다.

**`BaseObstacle` + `SmacPlanner2D` 조합은 아직 실주행으로 시험한 적이 없다.**
내일 첫 검증 대상이다.

## 4. 사용자 체감으로 고친 것

### 4.1 Spin 급회전

"도착 직전 천천히 가다가 훽 돌아버린다"는 보고를 받았다. 낙차를 계산했다.

```text
슬로우스탑 40 % 구간   max_vel_theta  0.16 rad/s  (9도/초)
Spin 복구              max_rotational_vel 1.0     (57도/초)   -> 6.3배
```

`max_rotational_vel` 1.0 -> 0.4로 주행 중 회전과 같게 맞췄다. `min`도 0.4 -> 0.15로
함께 내렸다 — `spin.cpp`가 `clamp(sqrt(2*acc*remaining), min, max)`이므로 min이
0.4로 남으면 늘 0.4가 나와 끝의 감속 곡선이 사라진다.

대가는 0.30 rad Spin 한 번에 0.39 -> 0.75초다. RoundRobin 6회에서 Spin은 2회뿐이라
총 0.7초 손해다.

### 4.2 접근 감속이 답답함

초안 `(1.5, 70)(1.0, 55)(0.5, 40)`에 "감속이 너무 느려서 답답하다"는 보고를 받았다.
원인은 이 제한이 **직진뿐 아니라 회전에도 같은 비율로 걸린다**는 점이었다.

```text
40 % 구간에서 max_vel_theta 0.4 -> 0.16 rad/s = 9도/초
-> 도착 직전 제자리 회전 90도에 10초
```

단계를 셋에서 둘로 줄이고 시작을 1.5 -> 1.0 m로 늦췄다.

| | 초안 | 확정 |
| --- | --- | --- |
| 단계 | 1.5/70, 1.0/55, 0.5/40 | **1.0/80, 0.5/60** |
| 마지막 1.5 m 소요 | 11.0초 | **7.5초** |
| 마지막 회전 속도 | 9도/초 | **14도/초** |
| 정지 시 Δv | 0.104 m/s | 0.156 m/s |
| 정지 거리 | 3.3 cm | 5.2 cm (기준 25 cm의 1/5) |

### 4.3 점멸등 좌우 — **임시 조치**

"서보는 좌우 피드백이 맞는데 황색 점멸등만 반대"라는 보고를 받았다.

올바른 자리는 펌웨어(`.ino`)의 `WAVE_A`/`WAVE_B`지만 **젯슨에 `arduino-cli`도
Arduino IDE도 없어 올릴 수 없다.** 그래서 `guidance_priority.py`에서 좌우를
뒤집었다. **정본은 펌웨어이며, 올릴 수 있게 되면 이 교환을 되돌리고 `.ino`를
고쳐야 한다. 양쪽을 다 뒤집으면 원위치가 된다.**

기록이 서로 어긋나 있다는 점도 남긴다.

```text
.ino 주석 : "bench에서 좌/우 모두 LED 방향과 서보 방향이 일치함을 확인했다.
             ... 변경하지 말 것."
devlog    : "LED 좌우 매핑 [미검증] — A/B 스트립의 물리적 좌·우 위치를
             실측으로 확인만 하면 된다"
```

오늘 실주행은 devlog 쪽을 지지한다. **A/B 스트립의 물리적 좌우 실측**이 남은 숙제다.

이 과정에서 실수를 했다. `.ino`에 "변경하지 말 것"이 명시돼 있는데 확인 없이
고쳤다가 되돌렸다. 그 표시가 있는 곳은 근거를 먼저 읽고 사용자 판단을 받아야 한다.

## 5. 도구

- `scripts/vica_drive_record.sh` — 사전 점검 + bag 기록. 점검이 실패하면 기록을
  시작하지 않는다. 배선이 끊긴 채로 기록하면 그 회차가 통째로 무효라서다.
  `/cmd_vel_req` 발행자 수가 여기서 처음 실기 확인됐다(발행 6 / 구독 1).
- `scripts/vica_set_initial_pose.sh` — AMCL 초기 위치를 명령으로 넣는다. RViz가
  원격에서 CPU 170 %를 쓰며 느려지면 클릭-드래그가 완성되지 않는다. 실제로 그래서
  못 찍었다.
- `scripts/vica_goto.sh` — 목적지를 **번호로** 고른다. 목적지 이름이 한글인데
  xfreerdp에서 한영 전환이 동작하지 않아 이름을 칠 수 없었다. 서비스가 받는 것은
  UUID라 이름은 표시용이다. `request_id`도 UUID여야 한다(처음에 `cli-$$`를 보내
  거부당했다).
- 터미네이터 레이아웃에 5칸 추가: `initpose` · `record` · `⑭ handle` · `rviz` ·
  `gui`. 오늘 손으로 치던 것들이다.

## 6. `/cmd_vel_req` 배선 확인 `[GAP]` 해소

`CLAUDE.md`가 `[GAP]/[TARGET]`으로 적어 둔 항목이 실기에서 처음 확인됐다.

```text
/cmd_vel_req    발행자 6 (velocity_smoother + behavior_server)  구독자 1 (Safety)
/cmd_vel_safe   발행자 1 (Safety)                               구독자 1 (motor)
```

과거에 복구 동작이 `/cmd_vel`(구독자 0)로 나가던 사고가 있었는데, **발행자 6**은
`behavior_server`가 제대로 붙었다는 뜻이다. 노드 지정 remap 수정이 유효하다.

## 7. 내일 이어서

측정으로 답이 나와야 하는 것부터 적는다.

1. **`BaseObstacle` + `SmacPlanner2D` 첫 검증.** 벽 붙음과 진동이 동시에 사라지는지.
   벽 붙음이 남으면 `cost_travel_multiplier`를 먼저 올리고 `inflation_radius`는
   건드리지 않는다.
2. **코너에서 멈추는 현상.** 오늘 "측면을 잘못 보는 게 강해서 돌다가 멈춘다"는
   관찰이 있었다. 경로 진동이 원인이면 1번으로 풀리고, 아니면 DWB 쪽을 본다.
3. **동적 장애물 회피.** BT `RateController` 1 Hz와 global costmap 1 Hz를 **함께**
   올려야 의미가 있다. 다만 종전 13회차 실측이 전부 1 Hz 기준이라 비교 기준을
   잃는다. 측정 단계 종료 결정과 묶여 있다.
4. **도착 후 "주행중" 표시**, **도착 시 "경고" 표시** — Mission Manager 도착 판정.
5. **점멸등 A/B 스트립 물리 좌우 실측.** 4.3의 기록 모순 해소.
6. **APK** — 젯슨(ARM64)에서는 만들 수 없다. Flutter가 `linux-arm64` 호스트용
   Android `gen_snapshot`을 배포하지 않는다. x86_64 노트북에서 빌드해야 한다.

## 8. 오늘 시험 결과

```text
vica_nav2              69건  실패 0  (12건 skip — Lattice 전용)
vica_mission_manager  135건  실패 0
vica_safety            96건  실패 0
vica_system_monitor   204건  실패 0
vica_user_guidance     87건  실패 0
vica_localization       2건  실패 0
Flutter (앱)           80건  실패 0
```

기록한 bag: `~/vica_data/bags/run01`(361 MB) · `run02`(463 MB) · `run03`.
run02는 안내소 -> 방2 -> 화장실 -> 안내소 한 바퀴가 들어 있다.
