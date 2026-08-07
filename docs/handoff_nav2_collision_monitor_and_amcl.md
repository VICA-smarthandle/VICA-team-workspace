# 핸드오프 — NAV2-B5 Collision Monitor 설계 / NAV2-B1 AMCL 튜닝 검토

작성일: 2026-08-07
작성 환경: Windows 개발 PC (편집 전용, ROS 2 미설치)
대상 항목: `docs/nav2_backlog.md` 의 **NAV2-B5**, **NAV2-B1**

기준 리비전 — 이 문서의 모든 줄 번호·수치는 아래 시점 기준이다.

| 저장소 | 커밋 | 비고 |
| --- | --- | --- |
| 루트 `VICA-smarthandle` | `b45c180` | 이 문서의 부모 커밋 |
| `vica_ros2_ws` | `origin/dev` `21ca187` | **로컬 체크아웃이 아니라 원격을 읽었다** (§1) |

`docs/nav2_backlog.md` 는 2026-08-06 판정으로 **B4·B6 가 §9(하지 말 것)로 내려간
상태**를 반영했다. 권장 순서도 `B1 → B2 → B5 → B3` 로 바뀌었다.

> **이 문서 용도**: 다른 장비/세션에서 이 검토를 이어받기 위한 핸드오프다.
> 이어받는 세션은 먼저 `CLAUDE.md`, `AGENTS.md`, `GOVERNANCE.md` 를 읽고,
> `docs/nav2_backlog.md` 특히 **§9 하지 말 것**을 확인한 뒤 이 문서 §1 부터 시작한다.
>
> **범위**: 설계 검토와 근거 정리만 담는다. **코드·설정 변경은 하나도 하지 않았다.**
> 실기 시험도 수행하지 않았다.

---

## 0. 한 줄 요약

Collision Monitor(B5)를 **`/cmd_vel_req` 생산자 자리에 전방 전용 2단(stop + slowdown)**
으로 넣는 설계를 확정했다. Safety·motor·`CLAUDE.md` 계약은 건드리지 않는다. 측면·후방은
통로 폭 실측과 §9 때문에 제외한다. AMCL(B1)은 백로그 5개 항목의 근거를 확인했고 그중
`laser_max_range` 항목의 **우선순위 판단을 교정**했다.

---

## 1. 반드시 먼저 확인할 것 — 저장소 동기화 함정

이 세션에서 가장 먼저 발견한 문제다. **이걸 모르고 시작하면 존재하지 않는 파일을 고치게 된다.**

2026-08-07 기준 실측:

| 저장소 | 현재 브랜치 | 작업 트리 | `dev` 기준 뒤처짐 |
| --- | --- | --- | --- |
| 루트 `VICA-smarthandle` | `dev` | clean | 0 (최신) |
| `vica_ros2_ws` | `app-UI/status-test` | clean | **84 커밋** |
| `vica-voice-llm` | `dev` | clean | 12 커밋 |
| `VICA_Supervisor` | `app-UI/status-test` | **미커밋 6건** | 15 커밋 |

**루트(문서) 저장소만 최신이고 제품 저장소 3개가 뒤처져 있다.** 그래서 문서와 코드가
어긋난다. 구체적으로:

| 항목 | 로컬 체크아웃 | `origin/dev` 실제 |
| --- | --- | --- |
| `nav2_params.yaml` 줄 수 | **385** | **1485** |
| `inflation_radius` | 0.35 | **0.55** (907·1076행) |
| `cost_scaling_factor` | 4.0 | 3.5 |
| planner | NavFn | **SmacPlannerLattice** (1276행) |
| footprint | 사각형 4점 | **실측 육각형 6점** |
| launch `SetRemap` | 1개 | **2개** (behavior_server 포함) |

`nav2_backlog.md` 가 인용하는 `nav2_params.yaml:932`, `:919`, `:901-908` 같은 줄 번호는
**1485줄 파일 기준**이라 로컬 385줄 파일에는 존재하지 않는다.

`app-UI/status-test` 브랜치는 이미 `dev` 에 merge 됐다(사용자 확인). 작업 재개 시:

```bash
git -C vica_ros2_ws checkout dev
git -C vica_ros2_ws pull
```

`VICA_Supervisor` 의 미커밋 6건은 사용자 작업물이므로 **건드리지 않는다.**

이 세션의 설계는 전부 `git show origin/dev:<path>` 로 원격 파일을 직접 읽어 수행했다.
체크아웃/pull 은 하지 않았다.

---

## 2. Humble Collision Monitor 사양 — 최신 문서와 다른 점

`guideline/official_reference_urls.md` 의 *"Nav2 최신 문서의 파라미터를 그대로 복사하지
말 것"* 경고가 이 노드에서 정확히 들어맞는다. **최신 문서를 보고 쓰면 파라미터 선언
단계에서 기동 실패한다.**

Humble 브랜치 소스로 직접 확인한 결과:

| 항목 | 최신 문서(docs.nav2.org) | **Humble 실제** |
| --- | --- | --- |
| `action_type` | stop · slowdown · **limit** · approach | **stop · slowdown · approach 3종만** |
| 감지 임계 파라미터 | `min_points` | **`max_points`** (기본 3) |
| `linear_limit` / `angular_limit` | 있음 | **없음** |
| `polygon_sub_topic` | 있음 | **없음** |
| observation source 타입 | scan · pointcloud · range · polygon | **scan · pointcloud · range 3종** |

근거 파일:

- `nav2_collision_monitor/src/polygon.cpp` — `action_type` 파싱 if/else
- `nav2_collision_monitor/src/collision_monitor_node.cpp` — `configureSources()` if/else
- `nav2_collision_monitor/params/collision_monitor_params.yaml` — `max_points` 사용 확인

### 그 밖에 확인한 Humble 동작

1. **STOP 은 short-circuit 한다.** `process()` 루프에서 STOP 이 결정되면 `break` 로 이후
   polygon 평가를 건너뛴다. → **`polygons` 목록 순서가 동작에 영향을 준다. stop 을 먼저 쓴다.**
2. **stale source 는 무시된다 (fail-safe 아님).** `Source::sourceValid()` 는 데이터가
   `source_timeout` 보다 오래되면 경고만 남기고 `false` 를 반환해 **그 소스를 건너뛴다.**
   정지시키지 않는다.
   ```cpp
   if (dt > source_timeout_) {
     RCLCPP_WARN(logger_, "[%s]: ... Ignoring the source.", source_name_.c_str());
     return false;
   }
   ```
3. **`cmd_vel_in` 이 없으면 아무것도 발행하지 않는다.** 노드는 수동적(passive)이다.
4. **`stop_pub_timeout`** 은 정지 상태가 그 시간을 넘으면 출력 발행을 중단한다(기본 2.0).
5. **Humble `nav2_bringup` 에는 collision_monitor 가 없다.** `navigation_launch.py` 의
   `lifecycle_nodes` 목록에 미포함이라 **별도 노드 + 별도 lifecycle manager** 가 필요하다.
   `nav2_collision_monitor/launch/collision_monitor_node.launch.py` 는 자체 lifecycle
   manager(`node_names: ['collision_monitor']`, autostart True)를 포함한다.

---

## 3. 배치 설계 — `/cmd_vel_req` 생산자 자리

### 현재 배선 (`origin/dev` launch 106~137행)

```
controller_server ──cmd_vel──►(remap)cmd_vel_nav──► velocity_smoother
                                                         │ cmd_vel_smoothed
                                                         │ (remap) ──► /cmd_vel_req
behavior_server ──cmd_vel──(노드지정 remap)───────────────────────────► /cmd_vel_req
```

`CLAUDE.md` 2026-08-01 실측: `/cmd_vel_req` 발행자 **6**(velocity_smoother +
behavior_server) · 구독자 **1**(Safety).

### 제안 배선

```
controller_server ──cmd_vel_nav──► velocity_smoother ──cmd_vel_smoothed──┐
                                                                          ├──► /cmd_vel_raw
behavior_server (Spin·Wait·DriveOnHeading) ──cmd_vel─────────────────────┘         │
                                                                                    ▼
                                                                        collision_monitor
                                                                                    │ /cmd_vel_req
                                                                                    ▼
                                                                        safety_supervisor_node
                                                                                    │ /cmd_vel_safe
                                                                                    ▼
                                                                            motor ──► CAN
```

### 왜 이 자리인가 (4가지)

| 근거 | 내용 |
| --- | --- |
| **배선 함정 회피** | `backlog §5` · `devlog/2026-07-29.md:213-216` 이 경고한 *"velocity_smoother 뒤에만 끼우면 복구 동작이 감시를 통째로 우회한다"* 를 구조적으로 차단 |
| **계약 무변경** | Safety 는 `/cmd_vel_req` 를 계속 구독. **Safety·motor 코드 수정 0**. `CLAUDE.md` 의 "Nav2 최종 요청은 `/cmd_vel_req`" 가 오히려 더 정확해짐 |
| **사망이 정지로** | Monitor 가 죽으면 `/cmd_vel_req` 단절 → Safety 가 `cmd_timeout_sec` 0.5 s 뒤 stale → 출력 0. 새 단일 실패점이 **fail-safe 방향으로** 무너짐 |
| **정책 준수** | `official_reference_urls.md:183` *"Safety Supervisor 를 대체하지 않고 그 앞에 놓는다"* |

**부작용**: `/cmd_vel_req` 발행자가 6 → 1 로 바뀐다. `CLAUDE.md` 실측 기록 갱신 필요.

### launch 변경

```python
# 변경: 기존 두 SetRemap 의 dst 만 /cmd_vel_req → /cmd_vel_raw
SetRemap(src="cmd_vel_smoothed",        dst="/cmd_vel_raw"),
SetRemap(src="behavior_server:cmd_vel", dst="/cmd_vel_raw"),
```

```python
# 추가: GroupAction 밖에 둔다.
# (토픽을 params 로 지정하므로 SetRemap 영향을 받으면 안 된다)
Node(
    package="nav2_collision_monitor", executable="collision_monitor",
    name="collision_monitor", output="screen",
    parameters=[params_file],
),
Node(
    package="nav2_lifecycle_manager", executable="lifecycle_manager",
    name="lifecycle_manager_collision_monitor", output="screen",
    parameters=[{"use_sim_time": use_sim_time},
                {"autostart": True},
                {"node_names": ["collision_monitor"]}],
),
```

기존 `lifecycle_manager_navigation` 은 건드리지 않는다.

---

## 4. params 초안

```yaml
collision_monitor:
  ros__parameters:
    use_sim_time: false
    base_frame_id: "base_footprint"      # Nav2 robot_base_frame 과 동일
    odom_frame_id: "odom"                # EKF 제공
    cmd_vel_in_topic: "/cmd_vel_raw"
    cmd_vel_out_topic: "/cmd_vel_req"
    transform_tolerance: 0.2             # DWB 와 동일
    source_timeout: 0.3                  # §8 한계 ① 참조
    base_shift_correction: True
    stop_pub_timeout: 2.0

    # 순서 중요: Humble 은 STOP 결정 시 break 로 이후 polygon 평가를 건너뛴다
    polygons: ["FrontStop", "FrontSlow"]

    FrontStop:
      type: "polygon"
      points: [0.555, 0.25, 0.555, -0.25, 0.355, -0.25, 0.355, 0.25]
      action_type: "stop"
      max_points: 3                      # Humble 은 min_points 가 아니다
      visualize: True
      polygon_pub_topic: "polygon_stop"
      enabled: True

    FrontSlow:
      type: "polygon"
      points: [0.955, 0.30, 0.955, -0.30, 0.355, -0.30, 0.355, 0.30]
      action_type: "slowdown"
      slowdown_ratio: 0.7                # §6 중첩 문제 참조 (0.5 아님)
      max_points: 3
      visualize: True
      polygon_pub_topic: "polygon_slowdown"
      enabled: True

    observation_sources: ["scan"]
    scan:
      type: "scan"
      topic: "/scan"
      enabled: True
```

---

## 5. Polygon 치수와 근거

### 기준선

실효 전방 경계 = footprint 앞 `x=+0.305` + `footprint_padding 0.05` = **0.355 m**

`origin/dev` footprint (육각형, 487·921행):

```
[[0.305, 0.2275], [0.305, -0.2275], [-0.305, -0.2275],
 [-0.595, -0.035], [-0.595, 0.035], [-0.305, 0.2275]]
```

### 필요 정지 여유 (params 1451~1476행 실측 기반)

```
라이다 지연 (expected_update_rate 0.2 → 5 Hz 최악)   0.26 × 0.2 = 5.2 cm
CAN·드라이버 지연 300 ms  (params:1457, D2 미해결)    0.26 × 0.3 = 7.8 cm  ← 지배적
감속 이동 (velocity_smoother max_decel -1.0)         0.26²/2.0  = 3.4 cm
─────────────────────────────────────────────────────────────────────────
필요 여유                                                        16.4 cm
```

### 확정 치수

| 영역 | 깊이 | 폭 | 로봇 반폭 대비 | 최협 통로 여유 |
| --- | --- | --- | --- | --- |
| `FrontStop` | 0.355 → 0.555 (**0.20 m**) | **±0.25** | +2.25 cm | **10 cm** |
| `FrontSlow` | 0.355 → 0.955 (**0.60 m**) | **±0.30** | +7.25 cm | **5 cm** |

> **주의 — 초안에서 수정된 값이다.** 처음 제안한 `FrontStop ±0.28` / `FrontSlow ±0.33` 은
> 최협 통로 반폭 0.35 m 에 대보면 여유가 각각 7 cm / **2 cm** 밖에 없어 라이다 노이즈로
> 상시 발동할 위험이 있었다. 위 값이 확정안이다.

`FrontStop` 은 "로봇이 실제로 지나갈 자리"만 덮으면 충분하므로 좁혀도 손실이 없다.
`FrontSlow` 가 최협 구간에서 가끔 걸리는 것은 오히려 바람직하다(그 구간은 어차피
천천히 가야 한다).

`max_points: 3` 근거: 0.5 m 거리에서 라이다 점 간격이 약 0.9 cm 이므로 4점 이상 =
**폭 3.5 cm 이상 물체**부터 발동하고, 단발 노이즈(1~2점)는 걸러진다.

### 크기 그림 (`base_footprint` 기준, 위에서 본 평면)

```
                              전방 (+x)  ▲
     y=+0.30                                                y=-0.30
        │                                                      │
+0.955 ─┼──────────────────────────────────────────────────────┼─  FrontSlow 끝
        │░░░░░░░░░░░░░░░  FrontSlow (slowdown 0.7)  ░░░░░░░░░░░│
        │░░░░░░░░░░░░░░░  0.26 → 0.182 m/s          ░░░░░░░░░░░│   0.60 m
        │░░░░░░░░░░░░░░░  폭 0.60                    ░░░░░░░░░░░│
+0.555 ─│░░┌────────────────────────────────────────────────┐░░│─  FrontStop 끝
        │░░│███████████  FrontStop (stop) 폭 0.50  ████████│░░│   0.20 m
+0.355 ─│░░└────────────────────────────────────────────────┘░░│─  영역 시작
        └──────────────────────────────────────────────────────┘   ↑ padding 0.05
+0.305 ─────┌────────────────────────────────────────────┐────────  footprint 앞
            │              로 봇  본 체                    │
            │              폭 0.455                       │        0.61 m
-0.305 ─────└─────────────────┐          ┌───────────────┘────────  본체 뒤
                              │  핸들    │  폭 0.07                 0.29 m
-0.595 ───────────────────────└──────────┘────────────────────────  footprint 뒤 끝
                                   ▲
                          사용자가 여기 선다 — 감시 없음
```

전체 감시 도달 거리는 **본체 앞 0.65 m** 까지로, 라이다 `obstacle_max_range 3.0` 의 1/5 다.
최대속도 0.26 m/s 로 느려 정지에 16.4 cm 면 충분하기 때문이며, 크게 잡으면 복도에서
상시 발동한다.

---

## 6. 측면·후방을 뺀 근거

### 6.1 측면 — 넣을 공간이 없다

```
최협 통로 반폭              0.35   m   (params:271, 296)
로봇 반폭 + padding         0.2775 m   (0.2275 + 0.05)
──────────────────────────────────────
로봇 옆 실제 여유           0.0725 m  ← 7.25 cm
```

측면 polygon 은 이 7.25 cm 안에 들어가야 벽을 물지 않는다. 그 폭은 감시 영역으로서
의미가 없고, 조금만 넓혀도 최협 구간에서 상시 발동한다. 통로 반폭 **중앙값은 0.70 m**
라 여유가 42 cm 나오므로, **넓은 곳에서는 되고 좁은 곳에서만 안 되는데 좁은 곳이
정확히 사고가 나는 곳**이다.

### 6.2 "측면 일부만" 이 왜 답이 아닌가

회전 시 실제로 쓸리는 지점을 계산하면:

| 지점 | 중심에서 거리 | 판정 |
| --- | --- | --- |
| 전방 모서리 | √(0.305² + 0.2275²) + 0.05 = **0.43 m** | `inflation_radius 0.55` 가 덮음 → 구멍 없음 |
| **후방 핸들 끝** | √(0.595² + 0.035²) + 0.05 = **0.65 m** | **외접반경 0.651 — 여기가 구멍** |

`backlog §2` 가 지적한 알려진 구멍이 바로 이 지점이다.

> `inflation_radius 0.55 < 외접반경 0.6506` — 벽에서 **0.55~0.651 m 구간(폭 0.10 m)에서
> planner 가 footprint 검사를 건너뛴다.**

**즉 측면에 실제 구멍이 있는 것은 맞지만 그 구멍은 측'후'방이다.** 핸들 스윕 0.645 m 가
지나가는 자리이고 거기엔 사용자가 서 있다. §9 가 후방을 막은 이유와 같은 자리라
**Collision Monitor 로는 덮을 수 없다.**

> **2026-08-06 사용자 판정 반영**: 이 구멍의 하드웨어 해법이던 **B6(손잡이 지지대
> 59.5 → 30.5 cm)는 구현하지 않기로 확정**되어 §9 로 내려갔다(B4 도 함께). 따라서
> 남은 축은 **`inflation_radius` 를 0.651 이상으로 올리는 것(B3 전제)뿐**이다.
> 그 대가는 통로 반폭 중앙값 0.70 m 에 육박해 통로 회피가 심해지는 것이며,
> 0.55 에서 이미 이동거리 +24 % 가 실측됐다.
>
> 갱신된 backlog §6 이 명시한다 — *"이 항목을 접으면 좁은 통로 제자리 회전
> (1.31 m 필요 vs 통로 1.0 m)은 미해결로 남는다."* 소프트웨어 축 넷이 모두 양쪽
> 실패이므로 다른 해법이 필요하면 backlog §8 로 올려야 한다.
>
> **Collision Monitor(B5)는 이 구멍을 메우지 않는다.** 전방 최후 정지만 담당한다는
> 역할 경계를 흐리지 말 것.

전방 측면(어깨 부근)은 `FrontSlow` 폭 ±0.30 이 로봇 반폭보다 7.25 cm 넓게 잡아 일부
덮고 있다.

### 6.3 사방을 두르는 구성이 안 되는 이유

- **후방은 `§9` 금지 항목** — *"사용자가 핸들을 잡고 뒤에 서므로 상시 발동한다"*.
  뒤 0.595 m 에 핸들이 있고 그 뒤에 사람이 있어 **주행 내내 100 % 발동**한다
- **측면은 최협 통로에서 벽을 문다** (위 7.25 cm)

사방 구성은 넓은 홀에서는 돌지만 실제 다니는 1.0 m 통로에서는 출발조차 못 한다.

### 6.4 참고 — AMCL 오차와 무관하다

Collision Monitor 는 **라이다를 로봇 프레임에서 직접 본다.** 지도·AMCL 을 거치지 않으므로
위 여유 수치는 실측 거리 기준이며 AMCL 30 cm 오차의 영향을 받지 않는다. costmap 경유를
피한 이유이기도 하다(§7).

---

## 7. `action_type` 3종 분석

### 7.1 `limit` 은 Humble 에 없다

```cpp
// nav2_collision_monitor/src/polygon.cpp (humble)
if (at_str == "stop")          { action_type_ = STOP; }
else if (at_str == "slowdown") { action_type_ = SLOWDOWN; }
else if (at_str == "approach") { action_type_ = APPROACH; }
// "limit" 없음 → 파라미터 선언 자체가 실패
```

`linear_limit` · `angular_limit` 파라미터도 Humble 에 없다. `limit` 은 Iron 이후 추가됐고,
VICA 는 JetPack 6.x 제약으로 Humble 고정이라 쓸 수 없다.

### 7.2 `slowdown` vs `limit` 개념 차이

| | `slowdown` (Humble 가능) | `limit` (Iron+) |
| --- | --- | --- |
| 방식 | 입력 속도에 **비율**을 곱함 | **절대 상한**으로 자름 |
| 0.26 m/s 입력 | ratio 0.5 → **0.13** | limit 0.13 → **0.13** |
| 0.182 m/s 입력(접근 감속 중) | → **0.091** | → **0.182** (상한 미만이라 그대로) |
| 0.05 m/s 입력(미세 조정) | → **0.025** | → **0.05** |
| 성격 | 상대적 — 이미 느리면 더 느려짐 | 절대적 — "이 영역에서는 최대 X" |

**VICA 에는 `limit` 이 더 맞는다.** Mission Manager 가 잔여 3 m 에서 이미 70 %(0.182 m/s)로
줄이는데 `slowdown 0.5` 가 겹치면 0.091 m/s 로 기어간다. `limit` 이면 이 중첩이 없다.

**대안(채택)**: `slowdown_ratio` 를 **0.7** 로 잡는다. 0.26 → 0.182, 접근 감속과 겹쳐도
0.127 m/s 는 유지된다.

**비채택**: `nav2_collision_monitor` 만 소스 빌드해 백포트 — 안전 계층에 upstream 과 다른
코드를 넣는 것이라 `GOVERNANCE.md` 승인 대상이고 유지보수 부담이 크다.

### 7.3 `approach` 는 쓰지 않는다

`approach` 는 `footprint_topic`(기본 `/local_costmap/published_footprint`)을 구독해
footprint 전체를 `time_before_collision`(기본 2초)만큼 전진시켜 충돌을 예측한다.

VICA 에서 켜면:

- footprint 에 **뒤 0.595 m 핸들 지지대가 포함**되므로 후방이 자동으로 감시 대상 → **§9 위반**
- 회전 시 스윕 반경이 **외접반경 0.651 m** 라 1.0 m 통로(반폭 0.5)에서 **회전할 때마다
  벽을 물어 상시 발동**
- 이는 `devlog/2026-07-29.md:118-121` 이 기록한 `Spin`/`BackUp` 의 `Collision Ahead` 실패와
  **동일한 메커니즘**이다 — *"`simulate_ahead_time: 2.0` 에 0.905 m 차체로는 통로에서 거의
  항상 막힌다"*

**즉 이미 이 로봇에서 한 번 실패한 방식이다. 후방 제외 방침과 무관하게도 쓸 수 없다.**

---

## 8. nvblox / costmap 연동 검토 — 1단계는 `/scan` 만

### 8.1 Collision Monitor 는 costmap 을 읽을 수 없다

`configureSources()` 의 타입은 `scan` · `pointcloud` · `range` 3종뿐이고 **costmap 이나
OccupancyGrid 소스 타입이 없다.** "받아온다"면 변환 노드를 직접 만들어야 한다.

### 8.2 nvblox 가 실제로 발행하는 것 (release-3.2 `nvblox_node.cpp` 확인)

| 토픽 | 타입 | Collision Monitor 사용 |
| --- | --- | --- |
| `static_map_slice`, `combined_map_slice` | `nvblox_msgs/DistanceMapSlice` | ❌ 타입 미지원 (**현재 costmap 이 쓰는 것**) |
| `static_occupancy_grid` 등 | `nav_msgs/OccupancyGrid` | ❌ 타입 미지원 |
| `static_esdf_pointcloud` 등 | `sensor_msgs/PointCloud2` | ⚠️ **쓰면 안 됨** (아래) |
| `dynamic_points` | `PointCloud2` | ✅ 가능 (dynamic 매핑 필요) |
| `back_projected_depth` | `PointCloud2` | ✅ 가능 (원시 역투영) |

> **⚠️ 함정**: `esdf_pointcloud` 는 이름과 달리 **거리장(ESDF)** 이다. 각 점은 "여기서 가장
> 가까운 장애물까지의 거리"를 값으로 가진 격자점이고 **자유공간 점도 전부 포함**된다.
> Collision Monitor 의 PointCloud 소스는 점 좌표만 보고 영역 안이면 장애물로 세므로,
> 이걸 넣으면 **자유공간까지 장애물이 되어 상시 정지**한다.

### 8.3 costmap 경유를 안 쓰는 이유 (기술이 아니라 설계)

변환 노드를 만들면 기술적으로는 가능하다. 그러나:

1. **독립성이 사라진다.** `backlog §5` 가 이 노드를 도입하려는 이유가 *"costmap/DWB 바깥의
   독립 정지 계층이 없다"* 이다. costmap 을 입력으로 쓰면 최후 방벽이 앞 단계와 같은 것을
   본다. costmap 이 틀리면(2026-07-31 AMCL 30 cm 오차로 없는 의자를 물었다) 최후 방벽도
   같이 틀린다. **방벽이 하나 는 게 아니라 같은 방벽을 두 번 그린 것**이 된다.
2. **유령 장애물이 급정지로 직결된다.** D3 미해결 — nvblox 유령 p95 **43~46초**
   (`backlog §4`, 정상 8~9 s 의 5배). 지금은 planner 우회/DWB 감속으로 끝나지만 최후 정지
   계층에 물리면 **사람이 지나간 빈자리에서 45초간 급정지**한다. 핸들을 잡은 시각장애인에게
   그건 회피 실패보다 나쁘다.
3. **지연이 는다.** `/scan` → monitor 는 직결이지만 costmap 경유는 costmap 갱신 → publish →
   변환 노드가 더 붙는다.

### 8.4 3D 를 넣는다면 (2단계 선택지)

nvblox 를 **거치지 않고** D455 depth 를 직접 받는 쪽이 설계에 맞는다(독립성 유지, 최소 지연).

```yaml
observation_sources: ["scan", "depth"]
depth:
  type: "pointcloud"
  topic: "/camera/camera/depth/color/points"
  min_height: 0.10     # 바닥 제외
  max_height: 1.20     # 로봇 최고점 부근
  enabled: True
```

1단계에서 제외한 이유:

- **대역폭·부하**: 640×480×30 Hz PointCloud2 를 Docker→Host DDS 로 전송. §8.7 GPU 경합이
  이미 관측 대상
- **D5 미해결**: 진행 방향 ±30° 부채꼴 관측률이 측정된 적 없음. 최후 정지 계층이 정면을
  못 보는 구간이 있으면 안 된다
- **D455 FOV 87°, 전방 고정**: 코너에서 측면 관측 단절 (`devlog/2026-07-29.md:203`)

**결론**: 3D 회피는 지금처럼 local costmap 의 `nvblox_layer` 가 담당하고, Collision Monitor 는
*"라이다 평면에서 정면 0.65 m 안에 뭔가 있으면 무조건 선다"* 는 단순·독립 역할만 맡는다.
역할을 겹치지 않게 나누는 것이 이 계층의 값어치다. D3 실기 진단 후 depth 소스 추가를
재검토한다.

---

## 9. 반드시 params 주석에 남길 한계 4가지

**① 라이다가 죽으면 이 계층이 조용히 무력화된다.** `sourceValid()` 가 stale 소스를 무시할
뿐 정지시키지 않는다(§2-2). `source_timeout` 을 길게 잡으면 낡은 데이터로 판단하고, 짧게
잡으면 "장애물 없음"이 된다 — **어느 값도 fail-safe 가 아니다.**
`vica_system_health_monitoring_draft.md` §9.1 의 `LiDAR timeout → STOP` 이 메워야 하며 현재
`[TARGET]` 이다. 성격은 같은 문서 §8.6.1 의 "조용한 실패"와 같다.

**② 급정지가 승차감 배려를 우회한다.** `params:1471` 은 *"2026-08-01: -2.5 → -1.0. 사용자
승차감 요구다. 시각장애인이 핸들을 잡고 걷기 때문에 정지 순간의 충격이 곧 안전이다"* 라고
기록한다. Monitor 는 smoother **뒤**라 이 램프를 거치지 않고 0 을 그대로 낸다. slowdown
영역을 stop 의 3배로 잡은 것이 완충이지만 **stop 이 실제로 얼마나 터지는지는 실기에서
세어야 한다.** → §13 미결

**③ 여전히 지상 38 cm 한 평면만 본다.** (§8)

**④ 하드웨어 E-stop 을 대체하지 않는다.** `official_reference_urls.md:183`

---

## 10. 함께 갱신해야 할 것

| 대상 | 이유 |
| --- | --- |
| `src/vica_nav2/test/test_nav2_launch_contract.py` | `SetRemap` 목적지·개수를 검증 중이라 깨진다 |
| `src/vica_nav2/test/test_nav2_params_contract.py` | `stop_pub_timeout` ↔ Safety `cmd_timeout_sec` 관계를 새 계약으로 추가 |
| `CLAUDE.md` | `/cmd_vel_req` 발행자 **6 → 1** (2026-08-01 실측 기록) |
| `docs/nav2_backlog.md` | B5 진행 상태, §9 에 `approach` 액션 추가 |

---

## 11. 검증 순서

1. **`visualize: True` 로 polygon 만 RViz 에 띄워 확인** — 바퀴 돌지 않음
2. 바퀴 띄운 HIL 에서 손으로 장애물을 넣어 stop/slowdown 발동과 `/cmd_vel_req` 차단 확인
3. 통제 구역 저속 주행에서 **stop 발동 횟수 측정** → 잦으면 slowdown 영역 확대

---

## 12. NAV2-B1 — AMCL 튜닝 검토

### 12.1 왜 최우선인가

`nav2_params.yaml` 의 AMCL 41줄에 **주석이 한 줄도 없다.** 마지막 변경은 좌표계 이름 한 줄
(2026-07-03)이고 나머지는 Nav2 샘플 그대로다. costmap·planner 에는 수백 줄의 실측 주석이
붙어 있는데 위치추정만 비어 있다.

`devlog/2026-08-06-자율주행-설정-점검.md` §5.4 가 결정적 맥락을 준다:

> EKF 에 들어가는 두 입력이 **모두 각'속도'만** 준다(바퀴 엔코더, 자이로). 각도 자체를 주는
> 입력이 하나도 없어서 **yaw 는 순수 적분**이고, 이를 되돌리는 건 AMCL 뿐이다.

절대 방위 센서가 없으므로 **yaw 드리프트를 되돌릴 유일한 장치가 AMCL** 이다. D6(실물
각속도 배율 미측정)이 겹친다.

### 12.2 ① 자기잠금 — 유일하게 사고 기록이 있는 항목 (최우선)

```yaml
update_min_d: 0.25    # 25 cm 이상 움직여야 측정 갱신
update_min_a: 0.2     # 11.5° 이상 돌아야 측정 갱신
```

`devlog/2026-07-31.md:52-64`:

> **틀린 자세 → 못 움직임 → 갱신 조건 미달 → 자세가 계속 틀림.** 실제로 AMCL 추정은
> t+77.6 ~ 85.6 동안 `(1.837, 3.848, 94.4°)` 로 **완전히 고정**돼 있었다.

8초간 추정값이 소수점까지 동일했고 20초를 갇혔다. **제안: 둘 다 0.10.**

크기 감각:

| 값 | 의미 | VICA 에서의 크기 |
| --- | --- | --- |
| `update_min_d 0.25` | 갱신까지 필요한 이동 | 최대속도 0.26 m/s 로 **약 1초치 주행** |
| `update_min_a 0.2` | 갱신까지 필요한 회전 | 11.5°. Spin 복구(`spin_dist 0.30` = 17.2°)는 넘지만 **DWB 미세 자세 보정은 대부분 못 넘음** |

좁은 곳에서 조금씩 더듬는 동작 — 정확히 갇혔을 때 하는 동작 — 이 갱신을 트리거하지 못한다.
갇힐수록 갱신이 안 되는 구조라 되먹임이 발산한다.

### 12.3 ② `max_beams` 60 → 180

`devlog/2026-07-31.md:29-42` 정합점 측정:

| 시각 | AMCL 자세 그대로 | 최적 보정 후 | 어긋남 |
| --- | --- | --- | --- |
| t+76.0 | 92/414 (22 %) | 47~50 % | **31.4 cm** |
| t+81.5 | 52/414 (13 %) | 〃 | **30.5 cm** |
| t+90.0 | 67/417 (16 %) | 〃 | **43.0 cm** |

한 스캔의 유효 반사가 **414개**인데 AMCL 은 **60개(14.5 %)** 만 쓴다. 정합률 13 % 와 50 % 를
가르는 신호가 나머지 85 % 에 있는데 보지 않는다.

**대가는 CPU 3배.** 검증:

```bash
grep -c "missed its desired rate" ~/.ros/log/controller_server_*.log
```

180 이 부담되면 120 부터. 되돌릴 때 1순위가 이 값이다.

### 12.4 ③ `alpha1` 0.2 → 0.4

Humble `differential_motion_model.cpp` 확인 결과:

| 파라미터 | 제어하는 잡음 | VICA 관련성 |
| --- | --- | --- |
| `alpha1` | **회전 → 회전 오차** | 제자리 회전 직후 오차가 컸음 |
| `alpha2` | 병진 → 회전 오차 | — |
| `alpha3` | 병진 → 병진 오차 | — |
| `alpha4` | 회전 → 병진 오차 | — |
| `alpha5` | **이 모델에서 전혀 참조되지 않음** | §12.6 |

`alpha1` 을 올리면 회전 시 입자 분산이 커져 스캔 매칭이 자세를 되돌릴 여지가 생긴다.
t+86 의 AMCL 점프 −10.8° 가 *"오히려 자세를 더 틀리게 만들었다"*(`:48-50`)는 관찰과 맞물린다.

### 12.5 ④ `laser_max_range` — **백로그 판단 교정**

`backlog §1` 은 이것을 **"선행 조건"** 으로 두고 *"이것이 틀리면 나머지 임계값 튜닝이 통째로
무의미해진다"* 고 쓴다. 그런데 Humble `amcl_node.cpp` 의 실제 처리는:

```cpp
if (laser_max_range_ > 0.0) {
  ldata.range_max = std::min(laser_scan->range_max,
                             static_cast<float>(laser_max_range_));
}
```

**`min()` 으로 clamp 된다.** `100.0` 은 드라이버가 준 `scan->range_max`(RPLIDAR 면 12 m 급)로
잘려 들어가므로 실질적으로 "드라이버 값을 그대로 쓴다" 와 같다. **무반사 빔을 유효로
오인하는 경로가 아니다.**

그래도 `range_max` 실측은 해야 한다 — 드라이버가 이 필드를 제대로 채우는지 확인해야 하고
(비정상적으로 크면 그때는 100.0 이 선택된다), 명령이 한 줄이라 비용이 없다.

```bash
ros2 topic echo /scan --field range_max --once
```

**다만 ①②③ 을 여기에 묶어 대기시킬 이유는 없다.** 자기잠금이 훨씬 급하다.

### 12.6 백로그에 없는 추가 관찰 3건

| 항목 | 현재 | 문제 | 제안 |
| --- | --- | --- | --- |
| `alpha5: 0.2` | 설정됨 | `DifferentialMotionModel` 이 **한 번도 참조하지 않음**(소스 확인). 죽은 값인데 튜닝 대상처럼 보임 | 값은 두되 "omni 전용, 이 모델에서 미사용" 주석 |
| `transform_tolerance: 1.0` | 1초 | DWB 0.2, behavior_server 0.1 과 **5~10배 불일치**. `map→odom` 이 1초까지 유효하다고 선언 | ① 로 갱신이 잦아지면 0.3~0.5 로 낮출 여지. **①과 함께 실측** |
| `recovery_alpha_slow/fast: 0.0` | 비활성 | 30 cm 어긋남에서 빠져나올 수단 없음 | **켜지 말 것을 권한다** — D4(정지 중 15 cm/10.8° 점프)가 미해결이라 오작동 시 더 나쁜 곳으로 점프. B2 `pose_bootstrap` 이 더 안전한 답 |

### 12.7 적용 순서

`backlog §3` 의 의존성:

> B2 의 `pose_bootstrap` 은 `/request_nomotion_update` 를 5회 호출한다. B1 에서
> `update_min_d/a` 를 0.10 으로 낮추면 **정지 상태에서도 AMCL 이 스캔을 반영하기
> 시작하므로** 이 호출의 필요성과 횟수가 달라질 수 있다.

**B1 → B2 순서**가 맞다. 바꾸면 B2 임계값 6종을 두 번 튜닝하게 된다.

```
0. range_max 실측 (1줄, 비용 없음)
1. update_min_d/a 0.10/0.10        ← 자기잠금, 최우선
2. max_beams 60 → 180              ← CPU 확인 필수
3. alpha1 0.2 → 0.4
4. transform_tolerance 재검토       ← 1의 효과 확인 후
5. B2 pose_bootstrap
```

### 12.8 검증 — "고쳐졌다"의 판정 기준

`backlog §1` 재현 시험:

> 로봇을 **20~30 cm 어긋난 상태**로 두고 좁은 구간에 진입시켜 `/amcl_pose` 가 고정되는지
> 본다. 고쳐졌다면 **갱신이 계속 일어나야 한다.**

성공 판정을 "완주했는가"가 아니라 **"`/amcl_pose` 가 8초간 소수점까지 동일한 구간이
사라졌는가"** 로 두는 것이 정확하다. 7월 31일 기록이 그 형태로 남아 있어 전후 비교가 된다.

되돌릴 조건: 제어주기 놓침이 늘거나 입자가 과도하게 퍼져 위치가 튀면 **`max_beams` 부터**.

---

## 13. 미결 — 다음 세션이 판단/확인할 것

| # | 항목 | 성격 |
| --- | --- | --- |
| 1 | **`stop` 액션 채택 여부** | §9 한계 ② 는 파라미터로 못 푸는 트레이드오프. slowdown 2단만 쓰고 stop 을 빼는 선택지도 있다. **팀 판정 사항** |
| 2 | `slowdown_ratio` 0.7 확정값 | 접근 감속(0.182)과 중첩 시 0.127 m/s. 실주행 체감으로 확정 |
| 3 | RViz 화면의 사각형 2개 정체 | 사용자가 보낸 스크린샷의 회색/주황 사각형이 직접 그려본 polygon 후보인지 local costmap 경계인지 미확인 |
| 4 | `source_timeout 0.3` 적정성 | §9 한계 ① 때문에 어느 값도 fail-safe 가 아니다. LiDAR health 와 함께 결정 |
| 5 | AMCL `max_beams` 실제 CPU 여유 | Jetson 에서 nvblox·STT 와 경합(§8.7). 실기에서만 판정 가능 |
| 6 | 저장소 pull 후 재확인 | 이 문서의 모든 줄 번호는 `origin/dev`(2026-08-07) 기준 |

---

## 14. 근거 위치 색인

### 이 워크스페이스

| 내용 | 위치 |
| --- | --- |
| B5·B1 항목 정의, §9 하지 말 것 | `docs/nav2_backlog.md` |
| 배선 함정, Collision Monitor 과거 기각 | `devlog/2026-07-29.md:206-217` |
| 후방 Collision Monitor 폐기 | `devlog/2026-07-30.md:152` |
| AMCL 30 cm 오차, 자기잠금 | `devlog/2026-07-31.md:14-64` |
| yaw 순수 적분, AMCL 무주석 | `devlog/2026-08-06-자율주행-설정-점검.md` §5.1, §5.4 |
| `laser_max_range` 미확인 | `devlog/2026-07-31-home-return-implementation.md:268` |
| 외접반경·inflation 부등식 | `devlog/2026-08-05-inflation-외접반경-검증.md` |
| 핸들 스윕·회전 필요폭 | `devlog/2026-08-02-주행테스트.md:223,382` |
| 유령 장애물 | `devlog/2026-07-30-nvblox-ghost-obstacle.md` |
| LiDAR timeout → STOP `[TARGET]` | `guideline/vica_system_health_monitoring_draft.md` §8.6.1, §9.1 |
| Collision Monitor 는 Safety 를 대체하지 않는다 | `guideline/official_reference_urls.md:183` |
| 정지거리·감속 실측 | `vica_ros2_ws` `origin/dev` `nav2_params.yaml:1451-1476` |
| footprint 육각형 | 〃 `:487`, `:921` |
| 최협 통로 반폭 0.35 | 〃 `:271`, `:296` |
| launch 이중 remap | 〃 `src/vica_nav2/launch/nav2_map_test.launch.py:106-137` |

### 외부 (Humble 브랜치 소스)

| 내용 | 위치 |
| --- | --- |
| `action_type` 3종 파싱 | `nav2_collision_monitor/src/polygon.cpp` |
| source 타입 3종, STOP short-circuit | `nav2_collision_monitor/src/collision_monitor_node.cpp` |
| stale source 무시 | `nav2_collision_monitor/src/source.cpp` |
| `max_points` 사용 예 | `nav2_collision_monitor/params/collision_monitor_params.yaml` |
| bringup 에 collision monitor 없음 | `nav2_bringup/launch/navigation_launch.py` |
| `laser_max_range` min() clamp | `nav2_amcl/src/amcl_node.cpp` |
| alpha1~4 역할, alpha5 미사용 | `nav2_amcl/src/motion_model/differential_motion_model.cpp` |
| nvblox 발행 토픽 | `isaac_ros_nvblox` `release-3.2` `nvblox_ros/src/lib/nvblox_node.cpp` |

---

## 15. 이 세션에서 하지 않은 것

- 코드·설정 파일 변경 **0건** (설계 검토만)
- 저장소 checkout / pull / commit **없음** (이 문서 커밋 제외)
- 실기 시험 **없음** — 모든 수치는 기존 devlog 실측과 소스 확인에서 인용
- `vica_ros2_ws` 는 `app-UI/status-test` 체크아웃 상태 그대로 두었다
