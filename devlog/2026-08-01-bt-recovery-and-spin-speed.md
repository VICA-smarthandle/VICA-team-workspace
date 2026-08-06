# BT 복구 구성과 Spin 회전 속도 (2026-08-01)

주행 중 회전 속도를 확인하다가 **Spin 복구가 주행보다 2.5배 빠르게 돈다**는 것을
알게 됐다. 이 로봇은 시각장애인이 핸들을 잡고 따라 걷기 때문에 속도 변화가 곧
사용자 경험이다. 조치는 나중으로 미루고 근거만 남긴다.

## 1. 지금 활성인 트리에는 몸을 움직이는 복구가 없다

`nav2_map_test.launch.py:35-39`가 `vica_navigate_to_pose_clearing_only.xml`을
`default_nav_to_pose_bt_xml`로 주입한다. 그 트리의 복구는 하나뿐이다.

```text
RoundRobin "RecoveryActions"
  └─ Sequence "ClearingActions"
       ├─ ClearEntireCostmap  local
       └─ ClearEntireCostmap  global
```

`Spin` / `Wait` / `BackUp` 노드 수는 **0개**로 확인했다. 파일 상단이 뺀 이유를 적고 있다.

```tex
<BackUp/>   핸들 뒤에 사람이 따라온다
<Spin/>     253 밴드에서 회전하면 후방 꼭짓점이 반경 0.675 m를 쓴다
<Wait/>     실패를 시간으로 덮는다. 종전 복구 시간의 79 %가 이것이었다
```

**즉 지금 로봇은 갇히면 지도를 지우고 다시 계획할 뿐, 빠져나오려 움직이지 않는다.**
이것은 결함이 아니라 순수 주행 실력을 재기 위한 의도다. 복구가 실패를 흡수해 버려서
지금까지의 완주 성적으로는 실력을 알 수 없다는 것이 그 근거다.

예비 트리 `vica_navigate_to_pose_no_backup.xml`은 4개를 순환한다.

```text
ClearingActions -> Spin(+0.30 rad) -> Spin(-0.30 rad) -> Wait(5 s)
```

되돌리는 비용은 launch 한 줄이다. 다만 `test_recovery_bt_contract.py`의 `ACTIVE_BT`도
함께 바꿔야 한다.

## 2. 복구가 발동하는 조건

3단계로 걸러진다.

| 단계 | 실패 시 | 재시도 |
| --- | --- | --- |
| `ComputePathToPose` | global costmap 초기화 | 1회 |
| `FollowPath` | local costmap 초기화 | 1회 |
| 위가 모두 실패 | `RecoveryActions` | **6회** |

`FollowPath`가 실패하는 실제 조건은 controller 쪽 파라미터가 정한다.

```text
progress_checker  required_movement_radius   0.10 m
                  movement_time_allowance   20.0 s
```

**20초 안에 10 cm를 못 가면 실패**다. 이것이 가장 흔한 경로다. 07-31에 이 값을
`0.5 m / 10 s`에서 완화한 이유는 좁은 구간 서행이 정확히 그 속도라 정상 주행을 실패로
오판했기 때문이다. 복구가 있을 때는 Spin 한 번으로 흡수됐지만, 지금은 오판이 곧
주행 종료다.

Wait가 없어 6회가 몇 초 만에 소진된다. 13회차에서 12초 만에 끝난 기록이 있다.

## 3. Spin의 실제 속도 프로파일

`/opt/ros/humble/share/nav2_behaviors/plugins/spin.cpp:138-139`이 전부다.

```cpp
double vel = sqrt(2 * rotational_acc_lim_ * remaining_yaw);
vel = std::min(std::max(vel, min_rotational_vel_), max_rotational_vel_);
```

남은 각도만 보고 정한다. **`min`은 하한이 아니라 바닥을 끌어올리는 값**이라는 점이
중요하다 — 끝에서 기어가듯 느려지는 것을 막는다.

우리 값은 `nav2_params.yaml:894-897`이다.

```yaml
max_rotational_vel: 1.0
min_rotational_vel: 0.4
rotational_acc_lim: 3.2
simulate_ahead_time: 2.0
```

`spin_dist = 0.30 rad`(17.2°)에 대입하면 이렇게 된다.

| 남은 각 | 계산값 | 실제 명령 |
| --- | --- | --- |
| 0.30 rad (17.2°) | 1.386 | **1.0** (max에 걸림) |
| 0.15 rad | 0.980 | 0.980 |
| 0.05 rad | 0.566 | 0.566 |
| 0.01 rad | 0.253 | **0.4** (min이 올림) |

**최고 1.0 rad/s에 도달한다. 주행 중 회전(`max_vel_theta` 0.4)의 2.5배다.**
한 번에 약 0.4초 걸린다(감속 구간 포함 계산값).

`simulate_ahead_time: 2.0`은 속도를 낮춰도 문제가 없다. 2초 앞을 보는데 1.0 rad/s면
2 rad, 0.4 rad/s면 0.8 rad를 훑는다. 우리 spin은 0.30 rad라 **어느 쪽이든 전 구간을
덮는다.**

## 4. `[TARGET]` max 1.0 -> 0.4, min 0.4 -> 0.15

**지금 바꾸지 않는다.** Spin이 활성 트리에 없어 효과를 확인할 방법이 없다.
**제품 트리를 복원할 때 함께** 바꾸고, 그 자리에서 사람이 핸들을 잡고 확인한다.

```yaml
max_rotational_vel: 0.4     # 주행 중 회전과 같게
min_rotational_vel: 0.15    # 함께 내려야 한다. 아래 이유
```

**`max`만 내리면 안 된다.** `min`이 0.4로 남으면 `clamp(vel, 0.4, 0.4)`가 되어 늘
0.4가 나오고, **끝에서 부드럽게 멈추는 감속 곡선이 통째로 사라진다.**

근거는 사용자 경험이다. 앞이 보이지 않는 상태에서 핸들이 갑자기 2.5배 빠르게 돌면
중심을 잃을 수 있다. 이 로봇에서는 복구가 빠른 것보다 **예측 가능한 것**이 중요하다.

대가는 작다. 0.30 rad를 0.4 rad/s로 돌면 0.75초로, **회전 한 번에 0.36초** 늘어난다.
아래 5절대로 6회 재시도에서 Spin은 2회뿐이므로 총 0.7초다.

## 5. 회전 누적량 — BT 주석이 틀렸다

`vica_navigate_to_pose_no_backup.xml:66`이 "6회 재시도에서 최대 100도"라고 적고 있으나
**산술이 틀렸다.** `RoundRobin`은 자식이 성공하면 인덱스를 하나만 전진시킨다.

```text
1회 ClearingActions
2회 SpinLeft   +17.2°
3회 SpinRight  -17.2°
4회 Wait 5 s
5회 ClearingActions
6회 SpinLeft   +17.2°
────────────────────────
순 회전 +17.2°     총 쓸린 각 51.6°
```

그 주석은 Spin이 하나였고 자식이 3개였을 때 쓴 것인데, 그때조차 6회 중 Spin은
2회(34.4°)였다. **기본 Nav2 트리의 Spin 한 번(90°)보다도 작다.**

이 수치는 인내(`number_of_retries`) 상향을 검토할 때 근거가 된다. 6 -> 12로 올리면
순 회전 +34.4°, 총 쓸린 각 103.2°가 되어 기본값 Spin 한 번보다 많이 쓸게 된다.
Spin은 253 밴드에서 후방 꼭짓점이 반경 0.675 m를 쓰므로 **총 쓸린 각이 늘어나는 만큼
핸들이 무언가에 닿을 확률이 커진다.** 12회는 권장하지 않는다.

주석 수정은 `vica_ros2_ws`의 planner 담당 작업과 같은 파일이라 여기서 하지 않는다.

## 6. 참고 — 회전 속도를 정하는 관문은 4개다

가장 낮은 것이 실질 상한이다.

| 계층 | 값 | 실효 |
| --- | --- | --- |
| **DWB `max_vel_theta`** | **0.4 rad/s** | **여기서 결정** |
| velocity_smoother `max_velocity[2]` | 1.0 | 안 걸림 |
| Safety `max_angular_radps` | 2.0 | 안 걸림 |
| 모터 knob (48 % 기준) | 0.96 | 안 걸림 |

`nav2_params.yaml:185`에 `max_vel_theta: 0.4 # 1.0 회전 속도 줄임`, `:193`에
`acc_lim_theta: 2.0 # 3.2 회전 시작 속도 줄임`이라 적혀 있다. **주행 쪽은 이미
한 번 낮춘 상태이고, Spin만 옛 값으로 남아 있다.**

슬로우스탑(`/speed_limit`)은 회전에도 같은 비율로 적용된다. 40 % 단계에서
`max_vel_theta`는 0.16 rad/s(9°/s)까지 떨어지므로, **목적지 직전 0.7 m에 코너가 있으면
도착이 지연된다.** 목적지별 마지막 접근 구간이 직선인지 실기에서 확인해야 한다.
