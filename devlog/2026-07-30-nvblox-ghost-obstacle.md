# nvblox 유령 장애물 진단 — 2026-07-30

> **이 파일 용도**: 다른 Claude Code 세션/에이전트에 이 경로 하나를 넘겨 nvblox 진단을
> 이어받게 하는 핸드오프 문서다. 이어받는 세션은 먼저 `CLAUDE.md`, `AGENTS.md`,
> `GOVERNANCE.md`를 읽고 아래 §9(하지 말 것)를 반드시 확인한 뒤 §7(진단 절차)부터 시작할 것.
>
> **범위**: nvblox / costmap 진단만 담는다. 같은 날 논의된 스마트핸들 모드 설계와
> health monitor 패키지 구현은 이 문서 범위가 아니다.

---

## 0. 한 줄 요약

주행 테스트 중 **동적 장애물(사람)이 지나간 자리에서 장애물이 사라졌는데도 로봇이 그 지점을
통과하지 못하는** 증상이 발생했다. 설정·소스를 전수 분석해 가설 4개와 그것을 가르는 진단 절차를
준비했다. **실기 시험은 하나도 실행하지 않았다.** 유력 가설은 nvblox static TSDF의 유령이
두 지우기 경로(카메라 관측 / decay)에서 동시에 막히는 자기강화 교착이다.

---

## 1. 환경 / 장비

- **이 분석은 개발 노트북(x86_64)에서 설정·소스 읽기만으로 수행했다.**
- 실기 진단은 **Jetson Orin NX 16GB에서만** 가능하다. 작업 전 `uname -m`으로 장비를 확인할 것.
- **nvblox 소스는 VICA 4개 저장소 밖에 있다.**
  ```
  /mnt/ssd/workspaces/isaac_ros-dev/src/isaac_ros_nvblox/
  ├── nvblox_nav2/src/nvblox_costmap_layer.cpp           (335줄, costmap 플러그인)
  ├── nvblox_ros/nvblox_core/nvblox/                     (TSDF·decay 엔진)
  └── nvblox_examples/nvblox_examples_bringup/config/nvblox/nvblox_base.yaml
  ```

---

## 2. 증상

- 발생 시점: 2026-07-30 주행 테스트 중
- 사람 같은 동적 장애물이 지나간 뒤, 그 자리에 아무것도 없는데 로봇이 그 지점을 통과하지 못한다
- **아직 구분되지 않은 것**: `/plan`이 안 나오는지(global 문제), `/plan`은 나오는데 안
  움직이는지(local 문제). §7 1단계가 이것을 가른다

---

## 3. 조사 결론 ① — `current_` 는 막다른 길이다

`nvblox_costmap_layer.cpp`의 74번째 줄 `current_ = true;`를 `false`로 바꾸는 접근을 검토했으나
**이 문제를 해결하지 못한다.** 재조사하지 말 것.

세 가지 근거다.

**(a) `current_`는 costmap 값을 바꾸지 않는다.**
```cpp
costmap_array[index] = cost;                              // 장애물을 쓰는 곳
updateWithMax(master_grid, min_i, min_j, max_i, max_j);
current_ = true;                                          // 보고용 플래그일 뿐
```
`current_`를 `false`로 해도 유령 LETHAL은 그대로 남는다. 로봇은 여전히 못 간다.

**(b) 영구 `false`는 영구 경보다.** `LayeredCostmap::isCurrent()`가 전 레이어를 AND로 묶으므로
costmap이 항상 "신선하지 않음"이 된다. 제대로 하려면 age 기반이어야 한다(slice 도착 시각 기록 →
매 사이클 age 확인). 한 줄이 아니라 약 10줄이다.

**(c) Nav2가 `isCurrent() == false`로 로봇을 멈추는지 자체가 `[미검증]`이다.**
헤더를 전수 확인한 결과 소비자는 `Costmap2DROS::isCurrent()` 하나뿐이고,
`nav2_controller`·`nav2_core`·`nav2_bt_navigator` 헤더에는 호출부가 없다.
```
/opt/ros/humble/include/nav2_costmap_2d/nav2_costmap_2d/layer.hpp:137
/opt/ros/humble/include/nav2_costmap_2d/nav2_costmap_2d/layered_costmap.hpp:104
/opt/ros/humble/include/nav2_costmap_2d/nav2_costmap_2d/costmap_2d_ros.hpp:185
/opt/ros/humble/include/nav2_costmap_2d/nav2_costmap_2d/observation_buffer.hpp:112
```
경고 로그 수준일 가능성이 높다. 컴파일된 라이브러리라 노트북에서 완전히 확인할 수 없다.

**따라서 플러그인을 fork해도 자동 방어가 생기지 않는다.** 실제 방어가 필요하면 상위
로직(Mission 취소)이 담당해야 한다.

---

## 4. 조사 결론 ② — 유력 가설: nvblox 이중 교착

nvblox가 유령을 지우는 길은 두 개인데 **둘 다 막힐 수 있다.**

### 4.1 길 1 — integration (관측으로 덮어쓰기)이 기하학적으로 막힌다

확정된 기하 (`vica_ros2_ws/src/vica_description/urdf/VICA.xacro:6,12-14,253`):
```
카메라 높이   = base_link 0.190 + camera_z 0.130 = 0.320 m
카메라 전방   = base_link 기준 +0.28683 m
장착 각도     = rpy "0 0 0"   ← 틸트 없음, 수평
D455 수직 FOV = 58°  (반각 29°, tan = 0.554)
```

slice 밴드는 `esdf_slice_min_height: 0.05` ~ `esdf_slice_max_height: 0.9`다.
거리 d에서 카메라가 실제로 보는 높이 = `0.320 ± 0.554 × d`

| 카메라~유령 거리 | 관측 가능 높이 | 밴드(0.05~0.9) 중 사각지대 |
| --- | --- | --- |
| 0.47 m | 0.061 ~ 0.579 m | **0.58 ~ 0.90 m (밴드의 38 %)** |
| 0.75 m | 0.0 ~ 0.736 m | 0.74 ~ 0.90 m |
| **1.05 m** | 0.0 ~ 0.902 m | **없음** |

**0.9 m 높이를 보려면 최소 1.05 m 떨어져야 한다.**

로봇이 유령 앞에서 멈추는 거리:
```
footprint 전방 0.305 + inflation_radius 0.45 = 로봇 중심에서 0.755 m
카메라는 중심보다 0.287 m 앞  →  카메라~유령 ≈ 0.468 m
```

**0.468 m ≪ 1.05 m.** 즉 로봇이 막혀 멈춘 위치에서는 0.58~0.9 m 높이의 유령을 카메라로 볼
수 없다. 사람의 상체·팔·가방이 정확히 그 높이 대역이다.

그리고 `esdf_slice_height: 0.10` 때문에 **밴드 전체의 최소 거리가 0.10 m 평면에 투영된다.**
즉 높은 곳의 유령이 바닥 높이 장애물처럼 costmap에 찍힌다.

### 4.2 길 2 — decay (시간이 지나면 잊기)가 설정으로 막힌다

확정된 값:
```
decay_tsdf_rate_hz               : 2.5    (vica_nvblox_overrides.yaml:73)
tsdf_decay_factor                : 0.95   (nvblox_base.yaml:102)
tsdf_decayed_weight_threshold    : 0.001  (nvblox_base.yaml:103)
exclude_last_view_from_decay     : true   (nvblox_base.yaml:104)  ← 핵심
tsdf_set_free_distance_on_decayed: false  (nvblox_base.yaml:105)
projective_integrator_max_weight : 5.0    (nvblox_base.yaml:78)
```

weight 5.0에서 threshold 0.001까지 감쇠하는 데 필요한 tick:
```
5.0 × 0.95ⁿ ≤ 0.001
n ≥ ln(0.0002) / ln(0.95) = 8.517 / 0.0513 ≈ 166 tick
166 tick ÷ 2.5 Hz ≈ 66초
```

**정상적으로도 66초가 걸린다.** 그런데 `exclude_last_view_from_decay: true`이므로 로봇이 그
지점을 보고 있는 동안은 이 카운트가 **아예 진행되지 않는다.**

`vica_nvblox_overrides.yaml:70-72`가 이미 이것을 기록해 두었다.
> 주의: 이 값을 바꿔도 이미 쌓인 맵은 줄지 않는다. `exclude_last_view_from_decay`가 True라
> 정지한 채 같은 곳을 보고 있으면 감쇠가 걸리지 않는다. nvblox에는 맵 초기화 서비스가
> 없으므로(save_map/load_map만 있다) 재시작해야 한다.

### 4.3 자기강화 교착

```
유령 장애물 (0.6~0.9 m 높이)
      ↓ esdf_slice_height 0.10 평면에 투영
  costmap LETHAL + inflation 0.45
      ↓
  DWB 유효 궤적 0 → 로봇 정지 (유령 앞 카메라 기준 0.47 m)
      ↓                              ↓
  ① 너무 가까워 그 높이를        ② 계속 보고 있으니
     카메라로 못 봄                  decay 제외
      ↓                              ↓
  integration으로 못 지움         decay로도 못 지움
      ↓
  영구히 못 감  ←────────────────────┘
```

두 지우기 경로가 동시에 막히고, **막힌 결과가 다시 원인을 유지한다.**
`decay_integrator_deallocate_decayed_blocks: true`도 decay가 걸려야 동작하므로 함께 막힌다.

---

## 5. costmap 설정 전체 지도

costmap이 **두 개**이고 레이어 구성이 다르다. 이것이 진단의 출발점이다.
(정본: `vica_ros2_ws/src/vica_nav2/config/nav2_params.yaml`)

```
global_costmap  (map frame, update 1.0 Hz, track_unknown_space: true)   :358
├── static_layer      ← SLAM 지도.       지우기 없음 (영구)
├── obstacle_layer    ← LiDAR /scan.     raytrace clearing, persistence 0.5 s
└── inflation_layer   ← radius 0.45, cost_scaling_factor 3.5
    ※ nvblox 없음

local_costmap   (odom frame, update 5.0 Hz, rolling 6×6 m)              :233
├── voxel_layer       ← LiDAR /scan.     raytrace clearing, persistence 0.5 s
├── nvblox_layer      ← 카메라 3D slice. nvblox TSDF가 지우기를 담당
└── inflation_layer   ← radius 0.45, cost_scaling_factor 3.5
    ※ static_layer가 정의만 있고 plugins 목록에 없음 = 죽은 설정
```

`/plan`은 global이 만들고 실제 바퀴 명령은 local(DWB)이 만든다.

### 5.1 레이어별 "지우기" 능력

| 레이어 | 지우는 방법 | 지우는 시간 | 유령이 남을 수 있나 |
| --- | --- | --- | --- |
| `obstacle_layer` / `voxel_layer` (LiDAR) | raytrace clearing + `observation_persistence: 0.5` | **0.5초** | 거의 없음 |
| `static_layer` (SLAM 지도) | **없음** | ∞ | **영구** |
| `nvblox_layer` (카메라) | nvblox TSDF integration + decay | §4 참조 | **가능 — 유력** |
| `inflation_layer` | 원본 레이어를 따라감 | 원본과 동일 | 없음 |

LiDAR 두 레이어는 `clearing: True`, `raytrace_max_range: 3.5`,
`observation_persistence: 0.5`, `expected_update_rate: 0.2`로 모두 정상값이다.
**LiDAR는 원인이 아닐 가능성이 높다.**

### 5.2 nvblox_layer 파라미터 (전부)

```yaml
nvblox_layer:                                    # nav2_params.yaml:278
  plugin: "nvblox::nav2::NvbloxCostmapLayer"
  enabled: True
  nav2_costmap_global_frame: odom                # local costmap global_frame과 일치 필수
  nvblox_map_slice_topic: /nvblox_node/static_map_slice
  convert_to_binary_costmap: True                # LETHAL 또는 FREE만
```
플러그인이 선언하는 파라미터는 이 5개 + `max_obstacle_distance`, `inflation_distance`,
`max_cost_value`뿐이다(`nvblox_costmap_layer.cpp:39-56`).
**timeout / expected_update_rate에 해당하는 파라미터가 없다.**

LiDAR `scan`에는 `expected_update_rate: 0.2`가 있으나(`nav2_params.yaml:324,391`) nvblox에는
대응물이 없다. 이 비대칭이 `guideline/vica_system_health_monitoring_draft.md` §8.5·§9.1·§19-11에
안전 공백으로 기록되어 있다.

### 5.3 mapping_type과 slice 토픽의 짝

현재 `mapping_type: static_tsdf` + `static_map_slice` 조합이다.
`dynamic`으로 바꾸면 `combined_map_slice`를 구독해야 하며, **짝이 어긋나면 nvblox_layer가
아무것도 받지 못한다**(`nav2_params.yaml:286-290` 주석). 두 파일을 반드시 함께 바꿔야 한다.

---

## 6. 감속·정지 관련 수치 (참고)

진단 중 확인한 값이다. `guideline/vica_architecture.md:675`가 `max_decel`을
`[-1.0, 0.0, -1.2]`로 적고 있으나 **실제 설정은 다르다. 문서가 뒤처졌다.**

```yaml
velocity_smoother:                # nav2_params.yaml
  max_velocity: [0.26, 0.0, 1.0]
  max_decel:    [-2.5, 0.0, -3.2]
  velocity_timeout: 0.4
safety_supervisor_node:
  cmd_timeout_sec: 0.5            # velocity_timeout(0.4) < 이 값 관계를 테스트가 강제
```
계산: 정지 시간 `0.26 ÷ 2.5 = 0.104초`, 정지 거리 `0.26² ÷ (2×2.5) = 1.35 cm`.

---

## 7. 진단 절차 — 아직 아무것도 실행하지 않았다

**여기서부터 시작할 것.** 순서대로 하면 가설이 좁혀진다.

### 1단계 — global인가 local인가
```bash
ros2 topic echo /plan --once
```
| 결과 | 의미 | 다음 |
| --- | --- | --- |
| `/plan`이 안 나온다 | **global 문제** — `static_layer` 또는 `obstacle_layer` | 3단계 |
| `/plan`은 나오는데 안 움직인다 | **local 문제** — nvblox 또는 DWB | 2단계 |

`/plan`이 나오는데 `/cmd_vel_nav`에 공백이 반복되면 2026-07-28에 기록된
"DWB 유효 궤적 0" 증상과 같다(`nav2_params.yaml`의 `ObstacleFootprint.scale` 주석 참조).

### 2단계 — 어느 레이어의 유령인가 (RViz 비교)
`publish_voxel_map: True`라서 LiDAR 쪽도 볼 수 있다.

| 토픽 | 여기에 유령이 있으면 |
| --- | --- |
| `/nvblox_node/static_map_slice` | **nvblox 확정** |
| `/local_costmap/voxel_grid` | LiDAR 확정 |
| `/local_costmap/costmap` | 합쳐진 결과 |

### 3단계 — SLAM 지도 확인
```bash
ls vica_ros2_ws/maps/
```
지도 이미지를 열어 유령이 박혀 있는지 눈으로 확인한다. `static_layer`는 decay가 없어
지도에 박힌 것은 **영구**다. 지도 작성 시점에 사람이 있었다면 이것이다.

### 4단계 — 결정적 시험: 로봇을 뒤로 물린다
근거: `map_clearing_radius_m: 7.0`, `map_clearing_frame_id: "base_link"`
(`nvblox_base.yaml:49-50`)

| 물린 거리 | 기대 결과 | 확인되는 원인 |
| --- | --- | --- |
| **1.1 m 이상** | 카메라가 0.9 m 높이를 보게 됨 → integration으로 수 초 내 지워짐 | **FOV 사각지대 (§4.1)** |
| 시야에서 완전히 빼고 66초 대기 | decay로 지워짐 | **exclude_last_view 교착 (§4.2)** |
| **7 m 이상** | 해당 블록이 즉시 삭제됨 | nvblox 누적 맵 |

### 5단계 — nvblox 노드만 재시작
풀리면 **nvblox 누적 맵 확정**이다. 맵 초기화 서비스가 없어 재시작이 유일한 초기화 수단이다.

### 6단계 (선택) — slice 실측
```bash
ros2 topic hz /nvblox_node/static_map_slice     # 정상 ~9 Hz 기대
```
`update_esdf_rate_hz: 10.0`, `publish_layer_rate_hz: 5.0` 설정과 대조한다.

---

## 8. 원인 후보 우선순위

| 순위 | 원인 | 근거 | 확인법 |
| --- | --- | --- | --- |
| **1** | nvblox 유령 + **FOV 사각지대**(0.58~0.9 m) | 계산: 정지 위치 0.47 m ≪ 필요 거리 1.05 m. `esdf_slice_height 0.10`이 높은 유령을 바닥에 투영 | 4단계 (1.1 m 후진) |
| **2** | nvblox 유령 + **exclude_last_view 교착** | `nvblox_base.yaml:104` true. decay 66초가 0회로 정지 | 4단계 (시야 밖 66초) |
| **3** | SLAM 지도(`static_layer`)에 박힌 유령 | decay 없음. global만 영향 | 1·3단계 |
| **4** | DWB 유효 궤적 0 (2026-07-28 기록) | `inflation_radius 0.45` > 최협 통로 반폭 0.35 | 1단계 |
| 5 | LiDAR 레이어 | `observation_persistence: 0.5`로 짧고 raytrace clearing 정상 | 2단계 |

**1번과 2번은 배타적이지 않고 함께 작용한다.** 둘 다 "로봇이 막혀 가까이 멈추는 것"이 원인
유지 조건이므로 4단계 후진 시험이 두 가설을 동시에 검증한다.

---

## 9. ⚠️ 하지 말 것

### 9.1 baseline을 잃지 말 것 — 가장 중요

`~/.claude/plans/stateless-honking-hartmanis.md` §7.2(B)가 **실측 전 수정 금지** 대상을
지정해 두었다. nvblox 관련으로는 다음이 걸린다.

- **`nav2_params.yaml`의 시각화 플래그**(`publish_evaluation`, `publish_voxel_map`,
  `always_send_full_costmap`)를 끄면 `controller_server` CPU가 줄어 **전체 부하 조건이
  바뀐다.** EKF 30 Hz 미달 원인 판정(H1~H5) A/B가 오염된다. 지금까지의 실측이 전부 시각화를
  켠 상태에서 나왔다.
- **nvblox 부하 삭감**(mesh/debug→0, max dist↓, voxel↑)은 GPU 경합 실측이 경합을 입증한
  뒤에만 한다(`devlog/2026-07-30-gpu-nvblox-stt-contention.md`의 게이트 E).

### 9.2 설정 주석의 A/B 이력을 먼저 읽을 것

`vica_ros2_ws/src/vica_nvblox_bringup/config/vica_nvblox_overrides.yaml`의 주석에
2026-07-28~29 실험 결과가 기록되어 있다. **값을 바꾸기 전에 반드시 읽을 것.** 요약:

| 시도 | 결과 |
| --- | --- |
| `decay_tsdf_rate_hz: 5.0` (nvblox 기본값) | X자 책상다리를 잊어 **실제 충돌**(2026-07-28) |
| `decay_tsdf_rate_hz: 0.0` (감쇠 없음) | 서행 2회→0회, 측면 여유 0.416→0.543 m로 개선. 단 `dynamic` 모드에서 costmap이 두 배로 차 방2에서 출발조차 못 함 |
| `decay_tsdf_rate_hz: 0.5` | inscribed 38.4 %, 1구간에서 갇힘 |
| `mapping_type: dynamic` + decay 2.5 (r1_dyn25) | 4구간 완주 268초. static(231초)보다 16 % 느리고 정지 1→32초. 단 그 static 기록은 복구 배선이 죽어 있던 때라 완전한 대조군이 아니다 |
| **현재: `static_tsdf` + decay 2.5** | 배선을 고친 상태에서 `mapping_type`만 바꿔 재측정하려는 구성 |

즉 **현재 설정은 진행 중인 A/B 실험의 한 조건이다.** 임의로 바꾸면 실험이 무효가 된다.

### 9.3 그 밖에 배제된 항목

`stateless-honking-hartmanis.md` §4에서 이미 실측으로 배제된 것들이다. 다시 시도하지 말 것.

- `vx_samples`/`vtheta_samples` 감소 — 갇힘 원인이 "유효 궤적 0"이라 표본을 줄이면 악화
- `inflation_radius` 0.45 → 0.38/0.35 — 실측 실패(61초 갇힘)
- `debug_trajectory_details: False` — 발행 플래그가 아니다. 진단 수단만 잃는다
- `/imu/base_link`·`/wheel/odom`을 확인 없이 BEST_EFFORT — QoS 비호환으로 토픽이 통째로 끊긴다
- QoS 전환 일반 — `ros2 topic info -v`로 읽기 전에는 바꾸지 않는다

### 9.4 `[GAP]`을 구현 완료로 표현하지 말 것

중앙 E-stop 래치, 관리자 앱 단일 reset, Nav2 `/cmd_vel` → `/cmd_vel_req` 종단 검증 —
이 셋 중 어느 것도 이 진단으로 종결되지 않는다.

---

## 10. 관련 파일 경로

**VICA 저장소** (`vica_ros2_ws`, 이 진단 시점 브랜치 `feat/system-monitor`)
```
src/vica_nav2/config/nav2_params.yaml                      # costmap 정본
src/vica_nvblox_bringup/config/vica_nvblox_overrides.yaml   # nvblox override + A/B 이력 주석
src/vica_nvblox_bringup/launch/vica_nvblox.launch.py        # camera_info remap
src/vica_description/urdf/VICA.xacro                        # 카메라·LiDAR 기하 (:6,12-14,253)
src/vica_nav2/vica_nav2/dependency_checks.py                # nvblox_nav2/nvblox_msgs symlink 감시
src/vica_nav2/test/test_nvblox_dependency_contract.py
maps/                                                       # SLAM 지도 (static_layer 입력)
```

**Isaac ROS workspace** (VICA 저장소 밖)
```
/mnt/ssd/workspaces/isaac_ros-dev/src/isaac_ros_nvblox/
├── nvblox_nav2/src/nvblox_costmap_layer.cpp                       # :39-56 파라미터, :74 current_, :224 sliceCallback
├── nvblox_ros/nvblox_core/nvblox/src/mapper/mapper.cpp            # :302,368,400 exclude_last_view 분기
├── nvblox_ros/nvblox_core/nvblox/include/nvblox/mapper/mapper_params.h  # :46 기본값 false
└── nvblox_examples/nvblox_examples_bringup/config/nvblox/nvblox_base.yaml
```

**Nav2 헤더** (`current_` 소비자 조사용)
```
/opt/ros/humble/include/nav2_costmap_2d/nav2_costmap_2d/{layer,layered_costmap,costmap_2d_ros,observation_buffer}.hpp
```

**문서**
```
guideline/vica_system_health_monitoring_draft.md   # §8.5·§9.1·§19-11 nvblox slice 감지 항목
guideline/vica_architecture.md                     # :675 max_decel 값이 실제와 불일치
devlog/2026-07-29.md                               # 복구 배선 결함, 갇힘 원인
devlog/2026-07-30-gpu-nvblox-stt-contention.md     # GPU 경합, slice staleness 게이트
docs/nav2_tuning_log_2026-07-28.md
~/.claude/plans/stateless-honking-hartmanis.md      # §4 배제 항목, §7.2 baseline 보존
```

---

## 11. health monitor와의 연결

nvblox slice 신선도 감지는 `vica_system_monitor` 패키지(별도 진행)의 편입 대상이다
(`guideline/vica_system_health_monitoring_draft.md` §8.5). **이 진단 세션에서 감지 기능을
구현하지 말 것** — 중복 구현이 된다. 이 문서는 원인 규명과 실제 방어까지만 다룬다.

---

## 12. 다음 세션이 판단해야 할 것

진단이 끝난 뒤 결정할 사항이다. 지금 정하지 않는다.

1. **감지 vs 방어**. health monitor가 slice stale을 감지해 앱에 띄우는 것과, 실제로 오래된 3D
   장애물로 주행하는 것을 막는 것은 다르다. 후자가 필요하면 상위 로직(Mission 취소)이
   담당해야 한다 — 초안 §3.1이 진단을 정지 경로로 쓰지 말라고 하므로.
2. **nvblox slice stale의 등급**. 초안 §19-11이 STOP / DEGRADED와 판정 임계(Hz/age)를
   팀 확정 항목으로 올려두었다.
3. **`mapping_type` 재검토**. 사용자 증상이 정확히 `dynamic` 모드가 해결하려던 문제
   (사람을 빠르게 잊기, `decay_dynamic_occupancy_rate_hz: 10.0`)다. 단 §9.2의 A/B 이력과
   `combined_map_slice` 짝 변경을 함께 고려해야 한다.
4. **`esdf_slice_max_height` 재검토**. 0.9는 로봇 최고점(0.86 m) 보호를 위한 값이지만, 근거리
   FOV 사각지대(§4.1)를 만든다. 상충하는 두 요구를 어떻게 조정할지.
