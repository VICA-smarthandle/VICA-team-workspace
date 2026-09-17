# Route Server(레일 주행) 도입 — 1판에서 4판까지 (2026-09-16 ~ 09-17)

Nav2 의 `nav2_route`(Route Server)로 지도 위에 **레일**(GeoJSON 그래프)을 깔고, planner 가
매번 지도 전체에서 길을 새로 찾는 대신 레일을 따라 다니게 했다. 목적은 둘이다 — 코너를
넓게 돌아 뒤·옆이 걸리지 않게 하고, 장애물이 있으면 자유주행으로 피했다가 레일로 돌아오게
하는 것. 이틀 동안 실주행 10회(bag 10개), 판(版) 4개, 사고 6건, 커밋 4개가 나왔다.

- 브랜치: 루트·`vica_ros2_ws` 둘 다 **`test_Route_Server`** (최신 dev + 회전축 수정 d8d3b1a cherry-pick)
- 커밋: ros2 `51213e7`(2판) · `cf73632`(3판), 루트 `4eac44f` · `515d249`. **4판(앞 2.5 m 검사)은 미커밋**
- bag: `~/vica_data/bags/route0916_run1·3·5·6·8`, `noroute0916_run4·7`, `route0917_run9·10`
- 실행: `ros2 launch vica_nav2 nav2_map_test.launch.py map:=.../maps/vica_map_0630.yaml use_route:=true`
  (플래그 하나로 route_server + 전용 lifecycle_manager + 레일 BT 가 같이 켜진다. 끄면 종전과 같다)

## 1. 한 줄 요약

| | 기존 planner (run7) | 레일 4판 (run10) |
| --- | --- | --- |
| 완주 | 7/9 (코너 갇힘 1, 손 개입 1) | **8/8** |
| 코너 | 안쪽으로 파고들어 여유 0.14 m 에서 갇힘 | 가운데로, 여유 ≥0.21 m |
| 남은 문제 | — | 화장실→안내소에서 **휴게실 경유 배회**(46·70 s), 도착 후 한 바퀴 더(31 s) |

남은 문제의 원인은 확정됐다: "레일이 잠깐 무효면 **최종 목적지까지** 자유주행"이라는 구조.
출발 순간 뒤에 선 사람이 레일 첫 0.8 m 를 막아 첫 틱이 무효가 되고, 그 한 번의 자유주행이
로봇을 planner 가 좋아하는 대각선으로 끌고 간다. 수리 방향은 공식 README 의 방식 2
(planner 는 레일 위 3 m 앞 지점까지만) — §7.

## 2. 공식 문서와 우리 구성

nav2_route README 의 "Practical Architectures" 중 우리는 **1번(레일 경로를 controller 에 직접)
+ 4번(마지막 구간은 자유주행)** 조합이다. 2번(성긴 route 의 다음 노드까지 planner)은 1판 때
"Humble 의 `<ComputeRoute>` BT 노드에 route 출력 포트가 없다"(실측: 포트는 start·goal·
start_id·goal_id·use_poses·use_start·server_name·server_timeout·path·planning_time)는 이유로
포기했는데, 09-17 에 **기성 노드 `GetPoseFromPath`(설치돼 있음, 미등록) + `TruncatePathLocal`**
로 같은 것을 만들 수 있음을 확인했다(§7).

설치본은 apt `ros-humble-nav2-route 1.1.20`. 동작 근거는 전부 그 태그의 소스에서 읽었다.

| 파일 | 확인한 사실 | 우리에게 미친 영향 |
| --- | --- | --- |
| `goal_intent_extractor.cpp` | 로봇이 첫 노드를 지나쳤고(dot>0) 0.10 m 넘게 떨어졌으며 엣지에서 8 m 안이면 첫 노드를 지운다. **엣지가 하나뿐이면 지운 뒤 엣지 0개** | 1판 `zero length` 사고 |
| `path_converter.cpp` | 엣지 0개면 경로는 start_node **한 점**. 로봇 위치는 경로에 안 들어간다. 끝 방향은 **마지막 엣지 방향**(목적지 yaw 아님). 코너 둥글리기는 각 0° 코너에서 NaN | 입구 방향 틀림, NaN 사고 |
| `navigate_to_pose.cpp` | 새 goal 을 받아도 blackboard `path` 를 안 지운다 → 첫 feedback 잔여거리는 옛 경로 기준 | 감속 사다리 굳음 |
| `truncate_path_local_action.cpp` | 로봇에서 가장 가까운 경로점을 찾아 앞뒤 적분 거리로 자른다. 빈 경로면 빈 출력·SUCCESS | 4판 |
| `get_pose_from_path_action.cpp` | `index=-1` 이 마지막 점, 방향은 경로점 방향을 그대로 | 방식 2 실현 열쇠 |
| `collision_monitor.cpp`(route op) | 라우트 앞 5 m 를 costmap 으로 검사해 **그래프 위에서 우회** | 고리 하나라 우회 = 반대로 한 바퀴. 안 쓴다 |

## 3. 회차별 기록

| 회차 | 시각 | 구성 | 완주 | 핵심 사건 |
| --- | --- | --- | --- | --- |
| run1 | 09-16 14:52 | 레일 1판 | 0 | `Received plan with zero length` 2739회 |
| run3 | 15:07 | 레일 1판 | 0 | 999회 |
| run4 | 15:12 | 기존 planner (대조) | 4/4 | `zero length` 0. `Starting point in lethal` 17회에도 완주 |
| run5 | 15:38 | 레일 1판 | 0 | 237회. 6.71 m 엣지 한복판에서 정지 |
| run6 | 17:16 | 2판(거름망·2단계·1 m 레일) | 7/7 · 233 s | NaN 경로 34건 → abort **970회**, 입구 도착 제자리 회전 **40 s** |
| run7 | 17:31 | 기존 planner (같은 코스) | 7/9 | 작업실→안내소 코너 갇힘(여유 0.14 m), 화장실→안내소 69 s(감속 사다리 굳음) |
| run8 | 18:00 | 2판 수리(NaN 거부·2 m 인계·smooth off) | 7/7 · **193 s** | NaN 0, abort 53, 입구 7 s |
| run9 | 09-17 10:38 | 3판(코너 fillet·사다리 수리) | 8/8 | 화장실→안내소 **58·68 s 배회**, 유령 띠 |
| run10 | 11:45 | 4판(앞 2.5 m 검사) | 8/8 | 배회 그대로(46·70 s), 안내소→입구 도착 후 한 바퀴 더(31 s) |

## 4. 사고와 원인

### 4.1 1판 — "점 1개짜리 경로" (run1·3·5)

**증상** 복도 한복판에서 멈춤. 다른 목적지를 찍어도 안 움직임. controller 로그
`Received plan with zero length`, route_server `Route found with 1 nodes and 0 edges`.

**배제한 것** 유령 장애물(완주한 run4 도 발자국 안 치명 13.3칸), 목적지 좌표(7곳 전부 free,
벽 여유 0.96~1.67 m), keepout(마스크가 전 구역 128 = 미지 → 무효).

**원인** 두 가지의 결합.
1. 1판 레일은 꺾이는 점만 남겨 작업실→화장실 복도가 **6.71 m 엣지 하나**였다(노드 17개 고리).
2. §2 의 잘라내기 규칙: 로봇이 앞 노드를 1.5 m 넘게 지나치면 그 노드를 지우고, 남은 엣지가
   하나뿐이면 0개 → 경로가 점 1개. 기성 `IsPathValid` 는 빈 경로만 거르고 점 1개는 통과시킨다.
   bag 대조: `zero length` 는 route 회차에만(run1 2739·run3 999·run5 237, run4 0), 로봇이 앞
   노드에서 1.5 m 넘게 멀어질 때만 났다.

**수리 (2판)**
- 레일 엣지 상한 **1.0 m** (`scripts/vica_route_graph.py` `split_long_edges`). 노드 17→42.
- **거름망 `IsRoutePathUsable`** (새 패키지 `vica_nav2_bt_plugins`, BT 플러그인 .so — 프로세스
  아님): 점 2개 미만 / 로봇이 경로에서 1.5 m 초과면 FAILURE → 자유주행. 순수 판정은
  `route_path_check.cpp`, gtest.
- **BT 2단계** (`vica_navigate_to_pose_route.xml`, README 4번): 1단계 레일
  (`ComputeRoute → IsRoutePathUsable → IsPathValid`, 아니면 `ComputePathToPose`) → 2단계
  목적지 자유주행(정확한 위치·yaw).
- 더 촘촘히 쪼개도 마지막 엣지에서는 같은 일이 나므로(거름망이 받는다) 1 m 이하로 줄일 이유가 없다.

### 4.2 run6 — NaN 경로와 abort 970회

**증상** 완주는 했는데 안내소 구간이 5.4 m 에 34 s. controller `Aborting handle` 970회(run4 0·run5 6).

**원인** `smooth_corners: true` 가 일직선 위 중간역 사이(각 0°)를 둥글리다 좌표에 NaN 을 넣었다
(34경로, NaN 앞뒤 방향 차 정확히 0.0°). NaN != NaN 이 항상 참이라 FollowPath BT 노드가
매 틱 "경로가 바뀌었다"며 새 goal 을 보냈고, controller 는 밀린 goal 을 버렸다.

**수리** `smooth_corners: false`(1.1.20 기본값; `Unable to smooth corner` 498회도 함께 사라짐)
+ 거름망이 non-finite 경로 거부. run8: NaN 0, abort 53(1 Hz 경로 교체 수준).

### 4.3 run6 — 입구 도착 제자리 회전 40 s, 방향 바뀜 8회 (run4 8 s·0회)

**원인** 레일은 입구에 남향으로 들어오고 목적지는 북향(90°). 레일 경로 끝 방향 = 마지막
엣지 방향(§2)이라 도착 뒤 제자리 180° 가 남는다. 180° 는 좌우가 같아 DWB 가 1초마다 방향을
바꿨고(8회) 결국 긴 쪽으로 231° 돌았다.

**수리** 거름망에 `goal`·`handoff_dist_to_goal=2.0` 포트 — 목적지 2 m 안에서는 레일을 버리고
planner 가 도착 방향까지 맞춰 그리게 넘긴다. run8: 7.0/8.1 s·방향 바뀜 0.

### 4.4 run7 — 기존 planner 대조 주행

- **코너 갇힘**: 작업실→안내소 코너에서 planner 가 안쪽으로 파고들어 벽 여유 0.14 m, 발자국 치명
  56~80칸(뒤 33·옆 25~41) → `Starting point in lethal` 43회 → Goal failed. 레일(run6)은 같은
  코너를 여유 0.21 m 로 통과. 화장실 출구에서도 8 s 정지(사용자가 밀어 줌).
- **속도 느려짐(69 s)은 planner 무죄**: 구간 시작에 `/speed_limit 60 %` 가 나가 끝까지 0.30 m/s.
  nav2 가 새 goal 때 옛 경로를 안 지워 첫 feedback 잔여거리가 옛 경로 끝 기준 0.2 m → 사다리
  (`approach_speed.py`, 내려가기만 함)가 60 % 로 굳음. run6 은 타이밍으로 안 걸렸을 뿐.
  → **수리(3판)**: 단계에 들어가려면 그 단계 거리보다 먼 곳에 있었던 적이 있어야 한다
  (`_farthest_seen >= threshold`). 시간 안 씀, 내려가기만 하는 성질 유지. 시험 328. run9·10 검증.

### 4.5 run9 — 코너 둥글리기 뒤에도 배회, 유령 띠

**3판 변경** `smooth_corners` 를 끄니 코너가 뾰족해 DWB 가 지나쳤다 되돌아왔다(방2→화장실 w ±0.29
왕복). 생성기가 15~120° 코너를 반지름 ≤0.5 m 호로 굽는다(`fillet_corners`). 노드 42→74,
뾰족 코너 0. w 표준편차 0.20→0.18.

**배회의 원인** `IsPathValid` 가 레일 **전체(11 m)** 를 검사 → 어디든 치명 칸 하나면 레일 통째로
거부 → 자유주행 planner 는 방 한가운데 대각선을 그림 → 다음 틱 레일 복귀 → 1 Hz 로 두 경로가
엇갈려 배회. 치명 칸의 정체는 **유령 띠**: 입구→방2 출발 시 레일 첫 2.5 m 에 치명 30~43칸
(정적 여유 0.6~1.1 m 빈 바닥). 생성 시각 10:41:05~15 = 50 s 전 로봇이 그 복도를 지난 때.
실제 장애물 칸 47개는 옛 로봇 궤적 기준 **앞뒤 0 m, 좌우 0.33 m** — 로봇 옆에서 같이 움직인
동행자의 몸/팔로 본다. global obstacle_layer 는 raytrace 3.5 m 밖을 안 지우고 동행자가 자기
자국을 가려, 로봇이 다시 0.3 m 안에 와야 소거됐다.

**아닌 것** CPU·노드 수(route_server 계산 0.4 ms, 42노드 때 0.5 ms), 서비스 지연(bt_navigator
경고 0), 레일이 벽에 붙음(정적 여유 최소 0.5 m).

**수리 (4판)** `TruncatePathLocal(앞 2.5 m, 뒤 0)` → `IsPathValid` 는 그 조각만. FollowPath 는
전체 경로. 기성 노드.

### 4.6 run10 — 구조 문제 확정

4판으로도 화장실→안내소가 46·70 s. 2.5 m 조각의 치명 칸을 틱마다 찍어 보니:
- 출발 첫 4틱: 치명 2~4칸, **로봇 뒤 0.78~0.80 m, 방위 ±170°** — 뒤에 서 있는 사람. 레일이
  화장실에서 서쪽(로봇 뒤)으로 나가니 사람 위를 지난다. 2.5 m 로 잘라도 첫 0.8 m 가 문제다.
- 무효 → 자유주행 planner 가 **최종 목적지까지** 그리는데 그 경로는 매번 휴게실 경유 대각선
  (inflation 비용이 낮은 넓은 곳 선호; run7 planner 도 같은 길).
- 로봇이 남서로 1~2 m 가면 레일의 "앞 2.5 m" 가 곧 로봇 뒤(사람) → 계속 무효 → 밀림.
  휴게실 근처에서 레일(되돌아가라)↔자유(더 가라)가 1초마다 엇갈려 왔다갔다(w −0.44/+0.38/−0.38/+0.50).
  남서로 충분히 밀리면 고리 남쪽이 더 짧아져 입구 경유(#2), 아니면 북쪽 복귀(#8).
- 같은 구조로 화장실→방2 는 자유주행이 동쪽 복도(5.5 m < 레일 7.75 m)를 찾아 레일에서 1.5 m 넘게
  벗어남("멀리" 판정) — 사용자가 본 "새 경로".
- **안내소→입구 31 s**: 11:46:48 에 yaw 오차 0°·위치 0.17 m 로 이미 도착했는데 2단계 planner 가
  그 0.17 m 를 1.2 m 고리로 그려(lattice 는 제자리 이동을 못 그림) 한 바퀴 더 돌았다.

### 4.7 그 밖의 사고

- **bt_navigator 가 거름망 .so 를 못 찾음**(run6 직전): 새 패키지를 만들기 전에 source 된 터미널이라
  `LD_LIBRARY_PATH` 에 경로가 없었다(/proc/PID/environ 확인). 재-source 로 해결.
  시험(`test_bt_plugin_libraries_exist`)은 내 환경만 보므로 못 잡는다.
- **컴파일 함정**: `BT::Result` 는 bool 로 암시 변환 안 됨 → `static_cast<bool>(getInput(...))`.
- **nav2_params.yaml 되돌림**(09-16 21:13, 편집자 불명): 거름망 등록 줄이 지워지고 `smooth_corners:
  true` 로. run9 는 옛 설치본으로 달려 무사했고 09-17 빌드 직전에 발견해 HEAD 로 복구. 기동 전
  `git status` 를 볼 것.
- `_route.png` 가 앱 지도 목록에 잡혀 keepout 노드가 `vica_map_0630_route.yaml` 을 찾다 실패(4~6회).
  사용자 지시로 아직 안 옮김.
- 안내소→작업실 통로 (-4.06, 3.76)에서 16 s 정지(run9): collision_monitor 가 앞오른쪽 (+0.42, −0.28)
  라이다 점 5~8개로 정지. 정적 지도엔 빈 바닥 — 지도 없는 물체 또는 위치 오차. 현장 확인 필요.

## 5. 수정 목록

| 파일 | 무엇 | 왜 | 검증 |
| --- | --- | --- | --- |
| `scripts/vica_route_graph.py` | destinations.yaml 정본 읽기, 벽 1 m 선호, 엣지 ≤1 m, 코너 fillet | 1판 6.71 m 엣지·안내소 1.03 m 빗나감·뾰족 코너 | 0630: 노드 74, 최대 엣지 0.94, 뾰족 0 |
| `src/vica_nav2_bt_plugins/` (신규) | `IsRoutePathUsable`: 점<2, NaN, 경로 1.5 m 초과, 목적지 2 m 안 | zero length·NaN·입구 180° | gtest 8 |
| `behavior_trees/vica_navigate_to_pose_route.xml` | 1단계 레일(+TruncatePathLocal 2.5 m)·2단계 자유주행 | README 1+4번 | pytest 계약 14 |
| `config/nav2_params.yaml` | route_server 블록, 플러그인 등록, `smooth_corners: false` | NaN | run8 NaN 0 |
| `launch/nav2_map_test.launch.py` | `use_route`/`route_graph` 인자, route_server + 전용 lifecycle_manager | 플래그 하나로 전환 | 시험 |
| `vica_mission_manager/approach_speed.py` | 사다리 `_farthest_seen` 자격 | 옛 경로 잔여거리 경쟁 | 시험 328, run9·10 |
| `test/test_route_bt_contract.py` (신규) | BT 순서·2단계·.so·엣지 ≤1 m·양방향 고리·목적지 통과·코너 | 되돌아가지 않게 | — |

바꾸지 않은 것과 그 근거:
- route_server 잘라내기 파라미터(`prune_goal` 등): 기본값 유지. 점 1개는 거름망이 받는다.
- `obstacle_min_range` 0.12→0.30 **금지**: 08-15 devlog §9 가 실측으로 철회(차체 기둥 반사는
  `footprint_clearing` 이 매 주기 지워 costmap 에 안 들어감; 올리면 0.12~0.30 m 진짜 근접 반사만
  잃음). run9 유령 띠도 자기 자국이 아니라 동행자 자국이다.
- `raytrace_max_range` 3.5→8(global scan): 근거 없는 값(params 주석 "[근거 없음]", 07-31 devlog 는
  5.5 계획)이고 backlog §9 C2 조건(raytrace > obstacle)을 만족하며 global 은 scan 단독 소스라
  카메라 마크를 지울 위험이 없다 → **적용 가능**, 방식 2 다음에 하나씩.

## 6. 실주행 비교 (같은 구간)

| 구간 | run6 2판 | run7 planner | run8 2판 수리 | run9 3판 | run10 4판 |
| --- | --- | --- | --- | --- | --- |
| 화장실→안내소 | 38 s | 69 s (사다리) | **42 s** | 58 / 68 s | 46 / 70 s |
| 방2→화장실 | 20 s | 22 s | 20 s | 20 s | 20 s |
| 입구 도착 맴돌기 | 42 s | — | 7~8 s | 10 s | 31 s (2단계 고리) |
| 출발 3 s 안 60 % | — | 1구간 | 0 | 0 | 0 |
| NaN 경로 / abort | 34 / 970 | 0 / 0 | 0 / 53 | 0 / 62 | 0 / 61 |
| 완주 | 7/7 | 7/9 | 7/7 | 8/8 | 8/8 |

## 7. 남은 문제와 다음 단계

1. **방식 2 로 전환** (기성 노드만): `ComputeRoute → IsRoutePathUsable → TruncatePathLocal(앞 3 m)
   → GetPoseFromPath(index −1) → ComputePathToPose(goal = 그 점)`. planner 는 "레일 위 3 m 앞"까지만
   그리므로 뒤에 사람이 있어도 돌아서 레일로 복귀하고, 최종 목적지까지 그릴 일이 없어 대각선·동쪽
   복도가 안 생긴다. `IsPathValid` 불필요. 매초 당근이 3 m 앞으로 옮겨져 레일 끝까지 간다.
   `nav2_get_pose_from_path_action_bt_node` 등록 필요.
2. **2단계를 `GoalReached` 로 게이트**: 목적지가 레일 위면 1단계가 이미 정확히 도착하므로 건너뛴다.
   레일 밖 목적지(노드에서 2 m 초과)만 2단계.
3. global `raytrace_max_range` 3.5→8 (하나씩).
4. 방2→화장실 고리 우회(+1.4 m): 가시선·여유 되는 노드 쌍에 지름길 엣지.
5. 안내소→작업실 통로의 지도 밖 물체 확인. `_route.png` 는 maps/ 밖으로.
6. 출발 가속(바퀴 3 m/s²)은 `velocity_smoother.max_accel[0]` 2.5→0.5 로 — 레일 안정 뒤.

## 8. 분석 방법

bag 은 끝난 뒤에만 읽었다(기록 중 읽으면 sqlite 잠금으로 기록기가 죽는다, 09-15 사고).
`/rosout` 으로 미션 흐름·경고, `/plan` 첫 점이 레일 노드 0.06 m 안이면 레일 경로로 분류,
`/tf` 합성으로 로봇 위치, `/global_costmap/costmap` 으로 발자국·경로 위 치명 칸, `/speed_limit`
(`nav2_msgs/SpeedLimit`) 으로 사다리, route_server 로그 시각차로 계산 지연. 스크립트는 세션
스크래치에 두었고 정본 도구는 `scripts/vica_route_graph.py`·`vica_turnability_map.py` 뿐이다.
