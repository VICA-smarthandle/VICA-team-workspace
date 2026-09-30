# 앱 레일(route graph) 편집 + 갈림길 V자 수리 — 설계 (2026-09-28)

상태: **구현 완료·실기 전(2026-09-30).** 실기 절차와 커밋은 `devlog/2026-09-30-앱-레일-편집-구현.md`.
B단계 시안(레일 칸) https://claude.ai/artifact/HJoZLSx1qcNibuujqpbwZ1 · 팝업 시안 https://claude.ai/artifact/Uj76d7tQa3kM1utzWt8h1J
(사용자 확정: 팝업 C 삭제, 앱 용어 '역'→'노드', 선이 벽을 가로지르면 표시 없이 막음, 먼 장소는 경고).

설계와 달라진 점(구현 중 결정)
- 편집 중 미리보기: SaveRoute 에 `preview_only` 를 두어 서비스 3개를 유지했다.
- 충돌(팝업 F): SaveRoute 에 `base_version`·`overwrite`. 판 = 레일 파일 mtime·크기.
- 덮어쓰기 전 옛 레일을 `maps/.route_backup/` 에 남긴다(점 폴더라 앱 지도 목록에 안 뜸).
- 벽에 붙은 노드 자동 밀기(2.7-5)는 넣지 않았다. 검사가 위치를 돌려주고 관리자가 옮긴다
  (확정 문구 "노드를 복도 가운데로 옮겨주세요"와 맞춤).
- 장소 변화 알림(2.3-7)은 노드가 아니라 앱이 장소 저장 직후 띄운다(팝업 E). 노드 쪽 자동
  초안 생성은 하지 않는다.
- 레일 칸은 GetRoute 의 레일 파일 요약(노드·길이·갈림길, 장소별 거리)을 보인다.
관련: `devlog/2026-09-28-방향지시등-레일-사전예고.md` 11절(계획 요약),
`devlog/2026-09-17-route-server-레일주행-1~4판.md`, `devlog/2026-09-17-route-0903d-복도-레일-실주행.md`,
`docs/superpowers/specs/2026-09-24-vcc-controller-design.md` §4.1·§12.4.

## 0. 한 줄 요약

- **1부(먼저)**: 갈림길을 직진할 때 레일 경로가 곁가지 쪽으로 V자로 꺾이는 결함을 **갈림길 호 엣지에
  `penalty` 0.1 + `PenaltyScorer`** 로 막는다. 앱과 무관하게 먼저 할 수 있다.
- **2부(나중)**: 관리자가 앱에서 레일을 **스케치**하면 젯슨의 새 노드 `route_graph_node` 가 공통 처리
  (호·1 m 쪼개기·양방향·검사)를 하고 공식 서비스 `/route_server/set_route_graph` 로 재시작 없이 갈아 끼운다.
  금지구역(`keepout_map_node`) 구조를 그대로 따른다.

---

# 1부. 갈림길 V자 경로 수리

## 1.1 증상 (실측)

지금 0903_d 레일(`maps/vica_map_0903_d_route.geojson`, 09-17 21:08, 노드 59) 로 달린 run40~46 의 갈림길
**직진 통과 6회 중 4회(run41·43·45·46)** 에서, 로봇이 x≈40.0~40.1 에 있을 때 레일 경로가
큰길(y −0.83)에서 화장실 입구 쪽 노드 45(y −1.81)까지 V자로 내려갔다 올라왔다.

| 회차 | 직진 | V자 | 몸 이탈 | w 최대 |
|---|---|---|---|---|
| run41·43·45·46 | 4 | 4 (각 1틱) | ≤ 0.07 m | 0.12 rad/s |
| run40·44 | 2 | 0 | ≤ 0.07 m | 0.09 rad/s |
| run15(옛 레일) | 2 | 1 | — | — |

run16~22 는 코스가 모두 화장실 경유라 직진 표본이 0 이었다. 몸이 안 끌려간 것은 V자가 **한 틱(1 s)** 으로
끝났기 때문으로 본다. 저속 통과·갈림길 근처 정지 후 출발이면 여러 틱 이어질 수 있다 **[미검증]**.
bag 의 `/plan` 에는 당시 route_server 출력이 섞여 있었다(09-28 부터 `/rail_plan` 으로 분리).

## 1.2 원인

1. route_server 는 출발 노드로 **로봇에서 가장 가까운 노드**를 쓴다
   (`goal_intent_extractor.cpp` humble `findStartandGoal` → `findNearestGraphNodesToPose`). BT 는
   이 계산을 1 Hz 로 반복한다(`vica_navigate_to_pose_route.xml:53`, `use_start="false"`).
2. 생성기 `fillet_junction`(`scripts/vica_route_graph.py:357`) 이 만든 Y 호의 첫 점 56·52 는 큰길에서
   **0.05 m**, 다음 점 57·53 은 0.19 m 다. 큰길 노드 간격은 약 0.96 m 라, 갈림길 양옆 약 0.5 m 씩 두 구간에서
   가장 가까운 노드가 **호 위 노드**가 된다.
3. 호 노드에서 출발하면 "뒤 노드(8)로 되돌아가 큰길"(2.56 m)보다 "호로 내려가 45 를 돌아 반대 호로 올라옴"
   (2.42 m)이 짧아 V자가 뽑힌다. 시뮬레이션(아래)의 V자 위치가 실측 위치와 겹친다.

```
 큰길  ─ 8 ─(56)────── 7 ──────(52)─ 6 ─
              57                  53
                58              54
                  59          55
                       45
                       │ 화장실
```

## 1.3 왜 VCC 가 아니라 레일에서 고치나

- VCC 는 받은 경로를 따라가는 controller 다(`setPlan`). 어느 노드를 거칠지는 route_server 와 그래프가 정한다.
- VCC 설계서 §12.4 가 "레일 BT 의 1 Hz 재계획 … 경로가 바뀌는 흔들림은 범위 밖" 이라고 적었다.
- 방향지시등 레일 예고(`/rail_plan` 구독, 09-28)도 같은 경로를 읽는다. V자 한 틱은 45° 넘는 꺾임 두 개로 보여
  **직진 중 헛 예고**가 날 수 있다 **[추정 — 09-28 오프라인 계산기가 매초 움직이는 출발점에서 레일을 다시
  받는 것까지 흉내 냈는지 확인 필요]**.

## 1.4 대안 비교 (시뮬레이션)

방법: 지금 레일 파일, humble 출발 노드 규칙(최근접 + `pruneStartandGoal` 의 dot/0.10 m), DistanceScorer
(+ 벌점). 큰길 x 38.0~41.3 을 1 cm 간격, 좌우 ±0.15 m 7줄, 407호·409호 양방향. 컨트롤러 흉내: 경로 앞 3 m
안에서 로봇 최근접 점을 찾고 0.6/1.2 m 앞 조준점이 큰길에서 0.15 m 넘게 벗어나면 "샘". 스크립트는
세션 scratchpad(`sim.py`·`opt.py`·`harm.py`) — 구현 때 시험으로 옮긴다(1.6).

| 방법 | 조준점 샘 | 화장실 꺾기 꺾임각 | 벽 여유 최소 |
|---|---|---|---|
| 지금 | **6.7 %** | 9~18° | 0.92 m |
| A. 큰길 0.25 m 안 호 노드 제거 | 2.3 % | **26~36°** | 0.92 m |
| **B. 갈림길 호 엣지 벌점** | **0 %** | 9~18° | 0.92 m |
| A + B | 0 % | 26~36° | 0.92 m |

- **A 는 버린다.** 호가 각져 `test_route_graph_corners_are_rounded`(30~120° 금지)에 걸리고 2.3 % 가 남는다.
- B 는 "뒤로 10~30 cm 에서 출발"하는 경로를 만들지만, 그 경로엔 로봇 옆을 지나는 큰길 구간이 들어 있어
  컨트롤러 최근접 점이 그쪽에 잡힌다. 해로운 것은 V자뿐이다.
- 벌점 0.05 부터 효과가 있었다. V자에는 호 엣지가 8개라 칸당 0.02 를 넘으면 진다.

## 1.5 결정

| 항목 | 값 | 근거 |
|---|---|---|
| 벌점 대상 | `fillet_junction` 이 만든 호 사슬의 엣지**만** | 일반 코너 호(0630 등)에 붙이면 고리 좌/우 선택이 코너 수로 흔들린다 |
| 벌점 값 | 엣지당 `penalty: 0.1` | V자 방지 5배 여유. 사용자가 고리를 그리면 갈림길 한 번 통과당 0.4 m 치 편향 — 무시 가능 |
| 곡선을 꼭 타야 하는 경로 | 영향 없음 | 큰길→곁가지는 어느 쪽이든 호 4칸을 지나므로 모든 후보에 같은 값이 붙는다. 시뮬레이션 꺾임각·벽 여유 동일 |
| 공식 기능 | `nav2_route::PenaltyScorer` | humble `penalty_scorer.cpp`: `cost = weight * metadata[penalty_tag]`, 기본 tag `"penalty"`·weight 1.0. 설치본 `plugins.xml` 에 있음 |

## 1.6 구현 (다음 세션이 그대로 따라 할 것)

작업 브랜치: 루트·ros2 각각 새 브랜치(예 `fix/route-junction-penalty`). **실주행 전 dev 머지 금지.**

1. **생성기** `scripts/vica_route_graph.py`
   - `build_tree` 의 `fillet_junction` 호출 전후로 `node_chains` 길이를 재서 새로 붙은 호 사슬 번호를 모은다
     (`fillet_junction` 은 `chains.append(arc_w)`, `chains.append(arc_e)` 로 끝에 붙인다, `:398-399`).
   - `edges` 를 만들 때(`:582`) 그 사슬에서 나온 엣지에 표시를 단다(예: 튜플 → dict `{'a','b','junction_arc'}`).
     `build_loop` 은 갈림길이 없으니 표시 없음.
   - `write_geojson`(`:651`) 이 표시 달린 엣지에 `"metadata": {"penalty": JUNCTION_PENALTY}` 를 쓴다.
     상수 `JUNCTION_PENALTY = 0.1` 을 위쪽 상수 묶음에 근거 주석과 함께 둔다.
   - 출력 요약에 "벌점 엣지 N개" 한 줄.
2. **route_server 설정** `vica_ros2_ws/src/vica_nav2/config/nav2_params.yaml` `route_server:`(`:2151` 부근)
   ```yaml
   edge_cost_functions: ["DistanceScorer", "PenaltyScorer"]
   PenaltyScorer:
     plugin: "nav2_route::PenaltyScorer"   # 이 줄을 빼면 configure FATAL (09-16 실측, 같은 블록 주석)
   ```
   주석에 이 설계서와 1.4 표를 가리킨다. weight 는 기본 1.0(생략).
3. **시험** `vica_ros2_ws/src/vica_nav2/test/test_route_bt_contract.py`
   - **발견: 레일 파일 시험은 `MAP = 'vica_map_0630'`(`:27`) 하나만 본다 — 0903_d 레일은 지금 아무 시험도
     안 받는다.** 레일 시험 4개를 지도 목록(`0630`, `0903_d`)으로 매개변수화한다. 0903_d 는 나무형이라
     `test_route_graph_is_a_bidirectional_ring` 의 "이웃 ≥ 2"(등뼈 끝은 이웃 1)에 걸린다 → 고리 조건은
     0630 에만, 공통은 "방향 엣지 쌍 + 한 덩어리 연결"로 나눈다. 코너 시험(`:248`)은 id 순서를 고리 순서로
     가정하므로 "실제로 이어진 엣지끼리의 각"으로 바꾼다.
   - `test_route_graph_no_junction_detour`: 레일 파일을 읽어 1.4 의 방법(최근접 노드 + prune + 거리+벌점
     다익스트라)으로 차수 3 노드 주변 ±1.5 m 큰길을 5 cm 간격·좌우 ±0.15 m 로 훑어, 경로 앞 3 m 조준점
     (0.6/1.2 m)이 큰길에서 0.15 m 넘게 벗어나는 경우 0 을 요구한다. 곁가지로 가는 목적지는 제외.
   - `test_route_graph_junction_arcs_have_penalty`: 차수 3 노드에서 곁가지로 드는 호 엣지가 모두
     `metadata.penalty > 0` 이고, 그 밖의 엣지는 벌점이 없다.
4. **0903_d 레일 재생성**: 09-17 이후 추가된 장소(학과사무실 등)가 빠져 있다. 09-28 임시 생성 결과
   노드 75(지금 59). `python3 scripts/vica_route_graph.py vica_map_0903_d --tree` → `vica_route_repair.py`
   로 벽 여유 확인 → png 로 사람 확인. **1(벌점)과 같은 회차에 넣지 않는다**(한 번에 하나).
5. 빌드: `vica_nav2` 만. 설정·레일은 install 로 복사되는지 확인(설치본은 복사본이다).

## 1.7 실주행 판정 (미리 정한 숫자)

코스에 **갈림길 직진을 동·서 각 3회 이상** 넣는다(407호↔409호/테스트).

| 지표 | 합격 | 실패 |
|---|---|---|
| `/rail_plan` 에서 V자(갈림길 ±1 m 안 경로가 큰길에서 0.3 m 초과) | 0 틱 | 1 틱 이상 |
| 화장실 진입·진출 경로 모양 | 벌점 전과 같은 노드 순서 | 다른 순서 |
| 갈림길 직진 몸 이탈 | ≤ 0.10 m | > 0.15 m |
| 방향지시등 헛 예고(직진 중) | 0 | 1 이상 |

## 1.8 되돌리기

`edge_cost_functions` 에서 `"PenaltyScorer"` 를 빼면 metadata 는 무시된다(파일은 그대로 둬도 된다).

---

# 2부. 앱 레일 편집

## 2.1 목표

- 젯슨에 모니터를 붙이거나 Claude 에게 부탁하지 않고, 관리자가 앱에서 레일을 만들고 고친다.
- 저장된 장소와 무관하게 원하는 곳에 노드·엣지를 둘 수 있다. 공통 처리(코너 호·갈림길·1 m 쪼개기·양방향·
  검사)는 로봇이 한 곳에서 한다.
- 고리형/나무형 양자택일이 아니라 **그물형(일반 그래프)** 을 허용한다. 공식 README: 노드 `id`·좌표,
  엣지 `startid`·`endid`·`id` 외 모양 제약 없음. 두 형은 자동 초안의 출발점일 뿐이다.

## 2.2 비유와 원칙

앱 = 스케치, 로봇 = 제도사, route_server = 역무실(노선도 보관·길 안내). 금지구역의 `zones_json`(원본) →
`_keepout.pgm`(가공본) 짝과 같다. 규칙은 로봇 한 곳에만 둔다 — 앱을 고치지 않고 코너 규칙을 바꿀 수 있게.

## 2.3 관리자 흐름

1. 지도 그리기 [있음] → 2. 장소 저장 [있음]
3. **[레일 만들기]** — 자동 초안(고리·나무 둘 다 만들어 검사 통과·짧은 쪽). 약 6 s(09-28 실측 6.4 s, png 포함)
4. **초안 확인·수정** — 지도 위에서 노드 찍기·옮기기·지우기, 엣지 잇기·끊기. 앱은 스케치만 다룬다
5. **[저장·적용]** — 실패면 이유+위치를 빨갛게. 통과면 적용, 주행 중이면 "적용 대기" 후 주행 끝에 자동 적용
6. 주행 화면 — 현재 지도 위에 확정 레일을 겹쳐 표시(`drive_map_canvas.dart` 의 금지구역 겹치기와 같은 방식)
7. 장소 추가·이동 — 새 장소가 레일에서 **2 m 밖**이면 곁가지만 덧붙인 초안을 만들고 "초안 보기/적용/나중에"
   알림. **자동 적용하지 않는다**(관리자 스케치 보호, 레일 변경 = 주행 경로 변경). 적용 전에도 BT 가
   자유주행으로 넘기므로 막히지 않는다(`test_route_bt_falls_back_to_freespace_when_route_unusable`,
   레일 끝→자유주행 전환은 실주행 [미검증])

## 2.4 구조

```
[앱] ─rosbridge 9090─▶ route_graph_node [새로] ──/route_server/set_route_graph──▶ route_server
  │   /vica/route/draft      │ route_graph_build.py [새로, ROS 없음]                  │
  │   /vica/route/save       │ hold 판정: keepout_mask.hold_apply 재사용               ▼
  │   /vica/route/get        │ 구독: /robot_status, /location_list               BT ComputeRoute (1 Hz)
  │ ◀─ /vica/route/state ────┤                                                     ▼
  │ ◀─ HTTP 8000 /maps/ ──── maps/<지도>_route.geojson · _route_edit.json    controller (RPP→VCC)
  │                                                                              ▼
  └─ 장소 저장 ─▶ destination_manager_node [있음] ─/location_list─▶        /cmd_vel_req→Safety→motor
```

| 노드 | 역할 | 하지 않는 일 | 상태 |
|---|---|---|---|
| `route_graph_node` | 초안·저장·검사·적용, 장소 변화 감지, 상태 알림 | 금지구역, 주행 판단 | **새로 — 선승인 필요** |
| `keepout_map_node` | 금지구역 | 레일 | 있음, 수정 없음 |
| `destination_manager_node` | 장소 저장 후 `/location_list` 발행(`destination_manager_node.py:34`) | — | 있음, 수정 없음 |
| `map_http_server` | `maps/` 전체를 앱에 전달(`PUBLIC_PREFIX="/maps/"`) | — | 있음, 수정 없음 |
| `route_server` | 그래프 보관·경로 계산 | 파일 생성 | 있음, 1부 설정만 |
| 미션 매니저·Safety·motor | — | — | 수정 없음 |

**노드를 따로 두는 이유**(사용자 제안, 09-28 확인)
- 맡는 Nav2 서버가 다르다(`/keepout_filter_mask_server/load_map` vs `/route_server/set_route_graph`).
- 계산 무게가 다르다(사각형 칠하기 vs 지도 거리장·다익스트라 수 초).
- 한쪽이 멈춰도 다른 쪽이 산다 — 응답 없는 서비스 하나가 rosbridge 전체를 막은 2026-08-21 사고
  (`supervisor_bringup.launch.py:56` 주석).
- 실행기 스레드는 `MultiThreadedExecutor(num_threads=2)`. 인자 없으면 스레드 28개·idle 12.6 % 사례
  (pose_bootstrap). **발견: `keepout_map_node.py:381` 도 인자 없이 쓴다 — 별도 측정·수리 후보.**

## 2.5 인터페이스 (`vica_interfaces/srv`, `SaveKeepout.srv` 모양을 따른다)

```
# DraftRoute.srv — 자동 초안
string map_id
string shape          # "auto" | "loop" | "tree"
---
bool accepted
string reason         # '' | bad_map_id | no_map | no_destinations | build_failed | busy
string message
string draft_file     # maps/ 기준 상대경로, 앱은 HTTP 로 받는다
string checks_json    # 검사 결과(2.7) 배열
```

```
# SaveRoute.srv — 스케치 저장(+적용)
string map_id
string sketch_json    # {"nodes":[{"id":1,"x":..,"y":..}], "edges":[[1,2],...]}  map 좌표(m), 무방향
bool apply_now
---
bool accepted
string reason         # '' | bad_map_id | no_map | bad_sketch | check_failed | io_error | busy_driving
string message
string checks_json    # 실패 위치 포함 — 앱이 빨간 표시
int32 node_count      # 가공 후
int32 edge_count      # 가공 후(방향 엣지 수)
bool applied          # false 면 '적용 대기'
```

```
# GetRoute.srv — 편집 원본 조회
string map_id
---
bool found
string sketch_json
string status         # latest | draft_pending | apply_pending
```

- 앱은 언제나 **스케치 전체**를 보낸다(빠진 엣지 = 지운 엣지, 삭제 전용 서비스 없음 — `SaveKeepout` 규약).
- 스케치는 **무방향**. 양방향 엣지 쌍은 로봇이 만든다.
- 상태 알림 토픽 `/vica/route/state`(std_msgs/String JSON): 요청 없이 생긴 변화만(주행 끝 자동 적용, 장소
  변화로 초안 생성). 요청 결과는 서비스 응답으로만 — 두 경로가 겹치면 앱이 두 번 알린다(keepout 과 같은 규칙).

## 2.6 파일

| 파일 | 뜻 | 쓰는 쪽 / 읽는 쪽 |
|---|---|---|
| `maps/<지도>_route_edit.json` | 관리자 스케치(다음 수정의 출발점) | route_graph_node / 앱(GetRoute) |
| `maps/<지도>_route.geojson` | 가공된 정식 그래프 | route_graph_node / route_server, launch(`nav2_map_test.launch.py:114`), 앱(표시) |
| `maps/<지도>_route_draft.geojson` | 자동·장소 변화 초안 | route_graph_node / 앱 |
| `maps/<지도>_route.png` | 사람 확인용 그림 | 선택 |

- `vica_map_save.sh` 덮어쓰기 확인·지도 삭제 경로에 `_route*` 를 금지구역 파일처럼 함께 넣는다
  (다른 장소 파일이 새 지도에 붙는 사고 방지, 같은 스크립트 08-31 주석).
- 쓰기는 임시 파일 → rename(반쯤 쓴 파일을 route_server 가 읽지 않게).

## 2.7 공통 처리와 검사 (`route_graph_build.py`)

지금 `scripts/vica_route_graph.py` 의 순수 계산을 ROS 없는 모듈로 옮기고, 입력을 "목적지"뿐 아니라
"스케치"로도 받게 한다.

처리 순서:
1. 스케치 엣지끼리 교차하면 교차점에 노드 삽입(환승역). route_server 는 기하 교차를 모른다.
2. 코너 호: 15~120°, R 1.0 → 0.75 → 0.5 (`FILLET_*`). 120° 초과는 둥글리지 않는다(`FILLET_MAX_DEG`).
3. 갈림길(차수 ≥ 3): Y 호(`fillet_junction`) + 호 엣지 `penalty` 0.1(1부). T 가 아닌 X·다갈래는
   [미설계] — 우선 뾰족하게 두고 경고.
4. `MAX_EDGE_M` 1.0 쪼개기, 양방향 엣지.
5. 벽에 붙은 노드 밀기(`vica_route_repair.py` 로직, 최대 0.5 m, 위상 유지).

검사(하나라도 실패면 적용 거부, 위치 반환):

| 코드 | 조건 | 근거 |
|---|---|---|
| `too_close_to_wall` | 노드·엣지 5 cm 훑기 최소 여유 < 0.70 m | 외접 0.620 + 0.08 (`vica_route_repair.py`) — 벽 정의는 `img == 0` |
| `disconnected` | 섬이 둘 이상 | 방향 엣지 쌍 + 연결성 |
| `dest_unreachable` | 장소가 레일 노드에서 2 m 초과 | BT `handoff_dist_to_goal=2.0` — **경고로 둘지 거부로 둘지 결정 필요** |
| `sharp_corner` | 30~120° 한 번에 꺾임 | `test_route_graph_corners_are_rounded` |
| `long_edge` | > 1.0 m | `test_route_graph_edges_are_short` |
| `junction_detour` | 1부 V자 시험 | 1.6-3 |

## 2.8 적용

- `nav2_msgs/srv/SetRouteGraph`: 요청 `graph_filepath`, 응답 `success`. 공식 README "Service interface to
  change navigation route graphs at run-time". 설치본 `SetRouteGraph.srv`·`libroute_server_core.so` 문자열로 확인.
- 주행 중이면 미룬다: `/robot_status` + `keepout_mask.hold_apply` 재사용(목적지가 살아 있는 동안 전부).
- 재부팅: launch 가 `<지도>_route.geojson` 을 읽으므로 유지된다.
- **[확인 필요]** 적용 직후 BT 가 쥔 옛 경로(`{rail_path}`)와 route tracking 상태가 어떻게 되는지 —
  주행 중 적용을 막으므로 위험은 낮지만 구현 첫 단계에서 로그로 본다.

## 2.9 부하

| 시점 | 부하 | 근거 |
|---|---|---|
| 초안·저장 | 약 6 s 한 번, 주행 중 금지 | 09-28 생성기 실측 6.4 s(계산 4.9 s, png 포함) |
| 적용 | 파일 1회 재적재 | 노드 수십 개 |
| 주행 중 | 지금과 같음: route_server 0.06코어, 계산 0.4~1.1 ms | `devlog/2026-09-17-route-server-레일주행-1~4판.md:248`, 0903d devlog `:99` |
| 벌점 추가 | 엣지당 덧셈 1회 — 측정 불가 수준 | `penalty_scorer.cpp` |
| route_graph_node 대기 | CPU ≈ 0(스레드 2 제한 시), 메모리 파이썬 노드 1개 [미측정] | — |

## 2.10 앱 화면 (VICA_Supervisor)

- 설정: `app_settings.dart` 에 `routeDraftService`·`routeSaveService`·`routeGetService`·`routeStateTopic`
  (금지구역 4개 항목 옆).
- 편집 화면: 지도 위 노드(점)·엣지(선) 편집, 검사 실패 빨간 표시, 상태 3종(최신/초안 있음/적용 대기).
- 주행 화면: 확정 레일 레이어(초안은 편집 화면에서만).
- 레일 파일은 HTTP(`http://<젯슨>:8000/maps/<지도>_route.geojson`)로 받는다 — 서버 수정 불필요.

## 2.11 시험

| 시험 | 위치 | ROS 필요 |
|---|---|---|
| 스케치 → 가공(교차점·호·쪼개기·양방향·벌점) | `VICA_Supervisor/ros2/test_route_graph_build.py` | 아니오 |
| 검사 코드 6종 각 1 사례 | 같은 파일 | 아니오 |
| 0903_d·0630 재생성 결과가 계약 시험 통과 | `test_route_bt_contract.py` | 아니오 |
| 주행 중 저장 → applied false → 주행 끝 자동 적용 | 노드 시험(`hold_apply` 공유) | 예 |
| 앱 편집 → 저장 왕복 | Flutter 위젯 시험 | 아니오 |

## 2.12 착수 순서

1. 1부(벌점) 실주행 통과 → 2. `route_graph_build.py` 분리(생성기와 결과 동일 확인) →
3. 인터페이스·노드(선승인) → 4. 앱 편집·주행 표시 → 5. 장소 변화 알림 → 6. 실기.

## 2.13 결정 대기

1. `route_graph_node` 새 노드 추가 승인.
2. `dest_unreachable` 을 거부로 할지 경고로 할지.
3. X자·다갈래 교차의 호 처리 방식.
4. 1부 벌점과 0903_d 재생성의 회차 순서, VCC 실주행과의 순서.
