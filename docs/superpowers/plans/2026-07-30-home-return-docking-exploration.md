# 홈 위치 복귀 구현 + 도킹·자동탐사 방향 설계 + 2D/3D 맵 판정

## Context

사용자 질문 3가지에서 출발한다.

1. Cartographer로 자동 탐사(미탐험 구역 자율 매핑)를 구현하는 방법
2. 도킹 스테이션을 만들어 배터리 30% 이하 시 자동 충전 복귀 + 초기 위치를 도킹 스테이션으로 지정 + 목적지 주행 후 항상 복귀
3. 2D 맵과 3D 맵의 차이, 이 프로젝트에서 3D 맵 사용 가능 여부, 어떤 차원의 맵이 좋은지 근거

조사 결과 이 중 **2번의 홈 복귀 부분은 신규 기능이 아니라 원래 기획의 미구현분**이었다.
개발보고서(`source_file/20260714023741117.pdf` p.6)와 설계서(`…175.pdf` p.5-6)의 서비스 흐름도
33단계에 `③ 로봇 홈 위치 이동`, `④ 대기 상태 진입`, `㉝ 로봇 홈 위치 복귀`가 명시돼 있고,
담당 노드는 설계서 p.30에서 **"구현예정(현재 미구현) — goal 단계 안전 판단 노드(state_machine_node)"**
로 선언돼 있다. 관리자 앱 기능 설명(보고서 p.13)에도 "대기 위치 복귀"가 들어 있다.
반면 「S/W 전체 구현 현황」 19개 항목·「프로그램 노드 목록」 21개 어디에도 이 기능이 없다.

즉 이번 작업은 **기획서에 있으나 구현되지 않은 항목을 채우는 일**이다. `GOVERNANCE.md` §4의
"제품 시나리오 변경"에 해당하지 않는다.

반면 **도킹 스테이션·충전·자동 탐사는 두 문서 어디에도 없다.** `충전`이라는 단어는 BMS 설명의
"과충전" 1회뿐이고, `도킹`·`frontier`·`자율 탐사`는 0회다. 이 둘은 진짜 신규 범위다.

사용자 확정 사항:
- 홈 복귀를 **먼저 구현**, 도킹은 나중에 같은 위치를 충전소로 승격
- 기동 시 **AMCL 자동 초기화 + 스캔 매칭 검증**
- 복귀 트리거는 **도착 후 일정 시간 대기 → 자동 복귀**
- 자동 탐사는 **설계·방향만**
- 배터리 계측은 **Junctek KG110F 기준으로 작성하되 `[미정]`** (변경 가능), 방향만
- 임계값은 **30%로 통일하고 개발보고서를 갱신**
- 브랜치는 **`integration/app-ui-system-monitor`에서 새로 딴다**

---

## 질문 3 답변: 2D 맵과 3D 맵 — 판정과 근거

### 지금 이 로봇은 이미 3D를 쓰고 있다

질문을 "3D를 쓸 수 있는가"로 두면 답이 틀린다. 이미 쓰고 있기 때문이다.

```
D455 depth ─► nvblox TSDF(3D 표면 재구성) ─► ESDF(3D 거리장)
                                              └─► z 0.05~0.9 m 구간을 잘라 2D slice
                                                   └─► /nvblox_node/static_map_slice
                                                        └─► Nav2 local costmap 의 nvblox_layer
```

근거: `vica_nvblox_bringup/config/vica_nvblox_overrides.yaml`(static/dynamic mapper의
`esdf_slice_min_height 0.05`, `max_height 0.9`), `vica_nav2/config/nav2_params.yaml:277`
(`plugins: ["voxel_layer","nvblox_layer","inflation_layer"]`), 개발보고서 p.15·p.21-22
("Isaac ROS nvblox 기반 3D 장애물 인식 구성 … 완료", "nvblox Nav2 local costmap plugin 연동 … 완료").

**따라서 정확한 질문은 "3D 정보를 어떤 형태로 소비할 것인가"다.** 3D는 세 층위로 나뉜다.

| 층위 | 내용 | 현재 상태 |
|---|---|---|
| ① 3D 인식(perception) | depth로 실시간 3D 표면·거리장 계산 | **하고 있다** (nvblox) |
| ② 3D 맵 저장(persistent 3D map) | 3D 복셀/메시를 파일로 저장·재사용 | 하지 않는다 |
| ③ 3D 경로계획(3D planning) | 3D 공간에서 경로를 푼다 | 하지 않는다 |

설계서 p.32 「데이터 수집 정의서」가 이 구분을 이미 못 박고 있다 —
`3D costmap | nvblox | static_map_slice | costmap layer | **(실시간)**` 대
`지도 | SLAM(Carto) | PGM+YAML·PNG | Nav2·앱 표시 | **maps/ 저장**`.

### 2D 저장 맵 + 실시간 3D slice 조합을 유지해야 한다 — 근거 4가지

**근거 1 — 기구학. 이 로봇은 z 자유도가 없다.**
차동구동 지상 로봇이다. 갈 수 있는 위치는 (x, y, θ) 3자유도이고 z는 바닥에 구속된다.
3D 경로계획은 드론·다관절 팔처럼 z를 스스로 고를 수 있는 시스템에서 의미가 있다.
이 로봇에서 3D 정보의 유일한 쓸모는 **"어떤 높이의 물체가 내 통과 단면을 막는가"** 판정인데,
그건 이미 ESDF를 0.05~0.9 m로 잘라 2D로 투영하는 현재 방식이 정확히 답한다.
슬라이스 상한 0.9 m는 로봇 최고점 0.86 m + 4 cm 여유로 실측 근거가 있다.

**근거 2 — localization 센서가 2D다.**
`nav2_params.yaml:1-40`의 AMCL은 `laser_model_type: likelihood_field`로 `/scan`(2D LaserScan)을
2D occupancy grid와 대조한다. 3D 맵으로 위치추정을 하려면 3D LiDAR(Velodyne/Ouster급)와
3D 매칭기(NDT, FAST-LIO 등)가 필요한데, 이 로봇에는 **3D LiDAR가 없다.**
D455는 FOV 87°, 유효거리 6 m 안팎이라 전방만 본다 — 360° 커버리지가 없어 위치추정 주 센서가 못 된다.
게다가 Isaac ROS Visual SLAM은 4 m 구간 lateral drift로 **이미 보류 판정**을 받았다
(개발보고서 p.24, 설계서 p.27: "4m drift로 현재 보류").

**근거 3 — 연산 예산이 없다.**
Orin NX 16GB는 UMA다. LLM `gemma4:e2b`가 **VRAM 7.1 GB를 상주 점유**하고(보고서 p.56),
nvblox가 상시 GPU를 쓰며, STT/TTS가 온디바이스 CUDA다. 이 경합은 이미
`devlog/2026-07-30-gpu-nvblox-stt-contention.md`에 문서화돼 있고, 거기서 발견된
**"nvblox_layer에는 `expected_update_rate`가 없어 slice가 멈춰도 costmap이 낡은 3D 장애물로
주행한다"**는 안전 공백이 아직 미해결이다. 영구 3D 맵을 얹으면 이 공백 위에 부하를 더한다.
보고서 자신도 리스크로 지목한다(p.15: "Jetson Orin NX GPU·메모리 부하 … 장시간 reconstruction
안정성 검증 필요").

**근거 4 — 2D 저장 맵은 이미 검증됐고 앱 전체가 그 위에 서 있다.**
`vica_ros2_ws/maps/`의 PGM+YAML(해상도 0.05), 앱의 `map_list_node.py`가 읽는 `.png`,
`locations.json`의 픽셀↔map 좌표 변환, 목적지 카탈로그의 map bounds 검증까지
전부 2D 격자 전제다. 이걸 3D로 바꾸면 앱·목적지·홈 위치 체계를 전부 다시 만들어야 한다.

### 결론과, 그럼에도 3D를 더 써야 할 곳 2군데

**결론: 저장 맵은 2D(Cartographer PGM+YAML)를 유지하고, 3D는 실시간 인식으로만 쓴다.
현재 구조가 이 로봇에 맞는 답이다.** 3D 맵 저장·3D 경로계획은 이득이 없고 비용만 크다.

다만 3D를 **덜 쓰고 있는** 실제 결함이 두 개 있다. 이건 별개 과제로 기록한다.

1. **global costmap에 `nvblox_layer`가 없다** (`nav2_params.yaml:373`은
   `["static_layer","obstacle_layer","inflation_layer"]`뿐). 3D 장애물이 전역 경로에 반영되지 않아
   planner가 테이블 밑 같은 곳으로 경로를 그은 뒤 local에서 막히는 패턴이 나온다. `[GAP]`
2. **local costmap의 `static_layer`가 정의만 있고 plugins 목록에 없다** — 죽은 설정.
   `devlog/2026-07-30-nvblox-ghost-obstacle.md:181`이 이미 지적.

이 두 가지는 이번 범위 밖이며 nvblox 유령 장애물 조사와 함께 다뤄야 한다.

---

## Phase A — 홈 위치·자동 초기화·자동 복귀 (이번 구현 대상)

브랜치: `integration/app-ui-system-monitor`에서 `feat/home-return` 분기.
이 브랜치의 `mission_logic.py`는 655줄이고 `State.PAUSED`·pause/resume·`check_cancel_gate`·
`check_pause_gate`·`check_resume_gate`가 이미 있다(`dev`의 482줄 버전과 다르다).

### A-1. 홈 좌표 데이터 모델 — 별도 `home.yaml`

경로: `~/vica_data/destinations/<map_id>/home.yaml` (목적지 카탈로그와 같은 디렉터리, 다른 파일)

```yaml
schema_version: 1
map_id: vica_map_0630
home:
  id: <canonical UUID v4>
  name: "대기 위치"
  pose: {frame_id: map, x: <실측>, y: <실측>, yaw: <실측 deg>}
  calibrated: true
  initial_pose: {enabled: true, sigma_xy_m: 0.30, sigma_yaw_deg: 12.0}
  arrival_tolerance: {xy_m: 0.40, yaw_deg: 25.0}
```

**`destinations.yaml`에 넣지 않는 이유**: 앱이 `/save_location`·`/delete_location_request`로
그 파일을 CRUD 한다(`vica_destination_manager/storage.py`). 관리자가 실수로 삭제하면 **다음 부팅에서
초기화 자체가 실패**한다. 홈은 사용자가 고르는 목적지가 아니라 기동 전제 좌표다.

**`arrival_tolerance`가 Nav2 goal tolerance(0.25 m / 0.25 rad)보다 커야 한다.** 작으면
"도착했는데 아직 안 왔다"고 판정해 즉시 재출발하는 루프가 생긴다. 로더가 이 조건을 강제한다.

신규 파일: `vica_mission_manager/vica_mission_manager/home.py` (rclpy 비의존,
`destinations.py`의 로더 패턴을 따른다). 로드 실패 시 예외가 아니라 `None`을 반환하고
**자동 복귀·자동 초기화를 둘 다 끈다**(fail-closed). 안내 기능 자체는 계속 동작해야 한다.

앱에서의 홈 편집은 v1 범위 밖. 홈 좌표 변경은 나중에 물리 도크 이동을 동반하므로 가볍게 바꿀 값이 아니다.

### A-2. 기동 시 AMCL 자동 초기화 + 스캔 매칭 검증

신규 노드: `vica_localization/vica_localization/pose_bootstrap_node.py`
(`AGENTS.md` §6이 localization 정본을 이 패키지로 규정한다. 현재 이 패키지에 노드가 없어 추가 비용이 작다)
순수 로직 분리: `pose_bootstrap.py`(상태기계), `scan_match.py`(정합 점수)

**`/initialpose` 토픽 발행 방식을 쓴다. AMCL의 `set_initial_pose` 파라미터는 쓰지 않는다.**
근거 — AMCL `on_activate()`가 파라미터 경로에서 `initialPoseReceived()`를 부를 때
**공분산을 전혀 설정하지 않아 전부 0이 된다.** 입자 2000개가 한 점에 모이고,
`nav2_params.yaml:26-27`의 `recovery_alpha_fast/slow: 0.0` 때문에 무작위 입자 주입도 없다.
결과적으로 초기 오차를 스스로 고칠 수단이 없고 **공분산 기반 검증이 원리적으로 불가능**해진다.
`BasicNavigator.setInitialPose()`도 같은 결함이 있다(`msg.pose.pose`만 채우고 covariance 미설정).

`nav2_params.yaml`에 `set_initial_pose: false`를 **명시**하고 계약 테스트로 잠근다.

시퀀스:
```
WAIT_STACK  /amcl/get_state == active + /map 1건(transient_local) + /scan 신선도 + TF 조회 확인
PUBLISH     /initialpose 발행. covariance[0]=σxy², [7]=σxy², [35]=σyaw²  (AMCL 은 이 3개만 읽는다)
SETTLE      /amcl_pose 수신 대기 후 /request_nomotion_update 를 0.4s 간격 5회 호출
VERIFY      아래 6조건 AND
FAILED/READY
```

**`/request_nomotion_update`(`std_srvs/Empty`) 호출이 이 설계의 핵심이다.**
`update_min_d: 0.25`, `update_min_a: 0.2` 때문에 **정지 상태에서 AMCL은 스캔을 아예 반영하지 않는다.**
이걸 부르지 않으면 `/amcl_pose`의 공분산은 우리가 준 초기값 그대로이고 검증이 무의미해진다.

검증 6조건 (기본값, 전부 `[미검증]` — 실측 후 확정):
- `cov_xx`, `cov_yy` ≤ (0.15 m)²  — 초기 σ 0.30의 절반 이하로 **수축**했는가
- `cov_yaw` ≤ (7°)²
- 수렴 평균이 홈 좌표에서 이동한 거리 ≤ 0.30 m — 크면 **다른 장소에 정합된 것**
- yaw 이동 ≤ 10°
- 자체 스캔–맵 정합 inlier 비율 ≥ 0.70 (AMCL 내부 상태와 독립적인 교차 검증)

초기 공분산을 **일부러 넓게**(σ_xy 0.30 m, σ_yaw 12°) 주는 이유: 좁게 뿌리면 틀린 위치에서도
응집이 유지된다. 넓게 뿌려야 맵과 맞는 입자만 살아남아 수축하고, **그 수축 자체가 증거**가 된다.

`nav2_util`에 스캔–맵 정합 유틸은 **없다**(헤더 목록 확인). `scan_match.py`를 직접 쓴다 —
합성 맵·합성 스캔으로 완전히 unit test 가능한 순수 함수로 만든다.

**선행 수정 필요**: `nav2_params.yaml:17`의 `amcl.laser_max_range: 100.0`이 실제 센서와 괴리가 크다.
`likelihood_field`가 무반사 빔을 유효 반사로 오인해 점수가 왜곡되면 위 임계값 튜닝이 통째로 무의미해진다.
`ros2 topic echo /scan --field range_max` 실측 후 맞춘다.

**검증 실패 시(fail-closed)**: `/vica/localization_status`(JSON String, TRANSIENT_LOCAL)에 사유 발행 +
TTS "현재 위치를 확인하지 못했습니다. 관리자를 불러 주세요." + **주행 게이트 차단**.
`/reinitialize_global_localization`을 자동 호출하지 않는다 — 전역 재추정은 수렴하려면 로봇이
움직여야 하는데, 위치를 모르는 채로 자율 주행하는 것이 곧 fail-closed 위반이다.

### A-3. 자동 복귀 상태머신

`mission_logic.py`에 상태 2개 추가:
```python
RETURN_PENDING = "return_pending"   # 도착 후 복귀 대기 (정지)
RETURNING      = "returning"        # 홈으로 주행 중
```

**기존 `NAVIGATING`을 플래그로 재사용하지 않는다.** `State.NAVIGATING`을 검사하는 지점이 8곳이고
그중 5곳이 복귀 시 동작이 다르다(새 목적지 → 안내 중엔 거부/복귀 중엔 선점, pause → 허용/거부,
SUCCEEDED → ARRIVED/IDLE 직행, 거리 안내 → 함/안 함). 플래그면 8곳에 조건을 붙여야 하고
하나만 빠뜨려도 **복귀 중 E-stop이 goal을 취소하지 않는** 안전 결함이 된다.

흐름:
```
NAVIGATING ─SUCCEEDED→ ARRIVED (dwell_sec 2.0, 현행 유지)
                          ├ 복귀 가능 → RETURN_PENDING
                          └ 아니면    → IDLE (현행)
RETURN_PENDING
   ├ (delay − warn) 경과 → Say("잠시 후 대기 위치로 돌아갑니다.")  1회
   ├ delay 경과         → 전제조건 재검사 → RETURNING 또는 IDLE
   ├ 어떤 intent든 수신 → 타이머 연장 (대화 중 로봇이 떠나면 안 된다)
   ├ navigate 수락      → NAVIGATING
   └ E-stop            → ESTOPPED (복귀 무장 폐기)
RETURNING
   ├ SUCCEEDED → Say("대기 위치로 돌아왔습니다.") → IDLE 직행 (ARRIVED 경유 금지)
   ├ FAILED    → IDLE + 실패 멘트, 자동 재시도 없음
   ├ navigate  → CancelNav(home) 후 NAVIGATING (선점)
   ├ cancel    → 즉시 취소, 되묻지 않음
   ├ pause     → 거부
   └ E-stop    → SetNavSpeedLimit(0) + CancelNav(home) → ESTOPPED
```

`RETURNING → SUCCEEDED → IDLE`(ARRIVED 경유 금지)이 **무한 복귀 루프를 원천 차단**한다.

**`ARRIVED` 상태를 늘리지 않는 것이 중요하다.** `mission_manager_node.py`의
`_on_destination_request`가 `state != IDLE`이면 거부하므로, ARRIVED에 오래 머물면
앱 목적지 요청이 그동안 전부 막힌다. 대신 `RETURN_PENDING`을 **요청 허용 상태에 추가**해야 한다.

**E-stop 원칙과의 관계 (반드시 지킬 것)**: 개발보고서 p.16·p.28은
"해제 후에도 새 goal 입력 전까지 HOLD 상태를 유지하여 기존 목적지의 자동 재개를 차단"을 규정한다.
따라서 **복귀 진입점은 `ARRIVED` 단 하나**로 못 박는다. `_enter_estopped()`가
`RETURN_PENDING`/`RETURNING`을 덮고 복귀 무장을 폐기하며(현재 `paused_destination = None` 처리와 동일),
E-stop 해제 후 도달하는 `IDLE`에서는 복귀가 시작되지 않는다.
`FAILED`·`cancel` 이후에도 복귀를 무장하지 않는다.

복귀 시작 전제조건(순수 함수 `_should_start_return`, 전부 AND):
홈 로드 성공 / `localization_ready` / E-stop 비활성 / `nav_ready` /
`distance_to_home_m is not None`(None이면 자기 위치를 모르는 것 → 진행 금지) /
현재 위치가 홈 tolerance 밖(이미 홈이면 조용히 IDLE, 멘트 없음)

### A-4. 스마트핸들 모드와의 상호작용 — 이 설계에서 가장 미묘한 지점

`guideline/vica_scenario.md` §2-1의 스마트핸들 활성 모드는 **터치 미감지가 정지 사유**다.

**활성 모드를 유지한 채 복귀하면 데드락이 확정적으로 발생한다.** 사용자는 목적지에서 반드시 손을 놓는다
→ 0.5초 유예 후 손 놓음 판정 → pause + 목적지 보관 → LLM이 "핸들을 잡아주세요" 반복
→ 사용자는 이미 떠났으므로 재접촉이 영원히 오지 않음 → **로봇이 복도에서 무한 대기**.

규약 `[TARGET]` (터치센서·상향 통신이 아직 미장착이므로 지금은 문서로만 못 박는다):
1. `RETURN_PENDING` 진입 시 핸들 모드를 **비활성으로 강제 전이**한다. 도착이 곧 안내 세션의 끝이다.
2. 복귀 중에는 터치 3초로 활성 모드에 **진입하지 않는다**(모드 진입 게이트에 명시적 거부).
3. 복귀 중 사람이 핸들을 잡아도 아무 일도 일어나지 않는다. 새 안내를 원하면 음성으로 목적지를 말하고,
   그러면 선점 규칙으로 복귀가 중단된다.
4. **knob(가변저항) 감속은 모드와 무관하게 항상 살아 있다**(`vica_scenario.md` §2-1, 커밋 `4dacc6a`).
   복귀 중에도 사람이 핸들을 당기면 감속·정지한다 — 이것이 복귀 중 사람 보호의 실질적 수단이다. **변경 금지.**

### A-5. `/vica_goal_event` — 새 이벤트명을 만들지 않는다

기존 payload에 `"trip": "guidance" | "return_home"` 키만 추가한다.

근거: `VICA_Supervisor/ros2/vica_goto_goal.py`의 `_TERMINAL_GOAL_EVENTS`에 없는 이름을 쓰면
CLI가 무한 대기하고, `vica_status_app_node.py`의 `navigation_active`도 안 꺼진다.
반대로 기존 이름을 쓰면 홈 이름 "대기 위치"가 앱에 그대로 표시되어 **앱 수정이 0줄**이다.

### A-6. TTS 멘트

```
"잠시 후 대기 위치로 돌아갑니다." / "대기 위치로 돌아갑니다." / "대기 위치로 돌아왔습니다."
"대기 위치로 돌아가지 못했습니다. 도움이 필요합니다."
"아직 현재 위치를 확인하는 중입니다. 잠시 후 다시 말씀해 주세요."
```
`HARD_EMERGENCY_KEYWORDS = {멈춰, 정지, 스탑, 스톱, 안돼, 위험해}` 미포함 확인 — 특히
**"복귀를 정지합니다" 류 표현 금지**. `test_spoken_text.py`가 `MSG_*`를 자동 수집해 감시한다.

### A-7. 작업 순서

| # | 작업 | 검증 | 실기 |
|---|---|---|---|
| 1 | `home.py` 로더 + `test_home.py` | pytest | ✗ |
| 2 | `scan_match.py` + 합성 데이터 테스트 | pytest | ✗ |
| 3 | `pose_bootstrap.py` 순수 상태기계 + 테스트 | pytest | ✗ |
| 4 | `State.RETURN_PENDING/RETURNING` + `on_tick`/`on_intent`/게이트 확장 + 테스트 | pytest | ✗ |
| 5 | **`on_estop`/`on_emergency`의 `RETURNING` 확장 + 안전 테스트 — 4와 같은 커밋** | pytest | ✗ |
| 6 | 홈 좌표 실측 캘리브레이션 → `home.yaml` | 값 확보 | ✓ |
| 7 | `/scan`의 `range_max` 실측 → `laser_max_range` 수정 | 계약 테스트 | ✓ |
| 8 | `pose_bootstrap_node` + launch + `set_initial_pose: false` 명시 | RViz 입자 수축 관측 | ✓ |
| 9 | 검증 임계값 튜닝 — **로봇을 일부러 2 m 어긋난 곳에 두고 실패하는지 확인** | 재현 | ✓ |
| 10 | 노드 배선: 홈 로드, TF 거리, `trip` 필드, `RETURN_PENDING` 요청 허용 | 계약 테스트 | 부분 |
| 11 | 종단: 안내 → 도착 → 대기 → 복귀 → IDLE 1사이클 | 바퀴 띄운 HIL 먼저 | ✓ |
| 12 | 문서: bringup 매뉴얼 단계 추가, `vica_architecture.md`/`vica_scenario.md` 갱신, devlog | 리뷰 | ✗ |

4와 5를 분리하면 그 사이 커밋에 **복귀 중 E-stop이 goal을 취소하지 않는 상태**가 실재한다. 반드시 한 커밋.
1~5는 실기 없이 개발 노트북에서 전부 검증 가능하다.

---

## Phase B — 배터리·도킹 방향 설계 (문서 산출물, 계측 하드웨어 `[미정]`)

### B-1. 계측 하드웨어 — Junctek KG110F `[미정]` (션트 내장 완제품, RS485)

> **`[미정]` — KG110F 기준으로 작성하되 최종 선정은 확정되지 않았다.**
> 사용자가 확정 후 재공유할 예정이며, **바꾼다면 더 저렴한 방향**이 될 가능성이 높다.
>
> **그래서 부품 후보를 두 부류로 나눠 둔다. 이 경계를 넘느냐가 작업량을 가른다.**
>
> | 부류 | 후보 | 가격 | SOC 계산 주체 | 우리 작업량 |
> |---|---|---|---|---|
> | **0. 부품 불필요** | 산타리 BMS 직결 (통신 제공 시) | **0원** | BMS | 파서 1개 |
> | **1. SOC 완제품** | **KG110F(채택)**, KH110F, Victron SmartShunt | 3~20만원 | **기기** | **파서 1개** |
> | **2. 전류·전압만** | INA226/INA228 + 외부 션트 | **1~3만원** | **우리** | **+ 몇 주** |
>
> **부류 1 안에서 바꾸는 것은 안전하다.** 아래 설계는 `sensor_msgs/BatteryState` 인터페이스에
> 의존하지 부품에 의존하지 않으므로, 교체 시 영향 범위는 **드라이버 노드 한 개**다.
> B-2·B-4·B-5는 그대로 유효하다.
>
> ⚠️ **부류 2로 내려가면 B-4가 통째로 바뀐다.** 쿨롱 카운팅 자체 구현 + 완충–방전 전 사이클 실측
> + OCV-SOC 테이블 작성 + Peukert 계수 추정 + 드리프트 리셋 규칙 검증이 추가된다.
> 부품값 2~4만원을 아끼는 대신 **개발 일정 몇 주**를 쓴다. 10/30 마감에 Nav2 70 %·앱 60 %·
> LLM 통합 30 %가 남은 상황에서 이 교환은 권하지 않는다.
> **가격 비교는 부품값이 아니라 "부품값 + 개발기간"으로 해야 한다.**
>
> 우선순위: **부류 0 확인 → 부류 1 내에서 최저가 → (일정 여유가 생기면) 부류 2.**

사용자 확정 조건: 션트 내장 완제품 / **RS485 허용** / 저렴·설치 용이 / 디스플레이 불필요 / SOC 출력.

**KH-F가 아니라 KG-F를 쓴다.** RS485 배제 조건이 풀리면서 판단이 뒤집혔다 —
KH-F를 택했던 유일한 이유가 "TTL 직결 가능"이었는데 그것이 1차 자료로 확인되지 않았다.
KG-F는 **RS485가 공식 인터페이스이고 Modbus over RS485를 지원**하며, 검증된 구현체가 훨씬 많다
(`tfyoung/esphome-junctek_kgf` 원본, Arduino 라이브러리, Tasmota, Home Assistant).
**"통신 방식이 무엇인지 모른다"는 불확실성이 사라진다.**

| 모델 | 측정 범위 | 전류 분해능 | 판정 |
|---|---|---|---|
| **KG110F** | 0~100 A | 0.01 A | **채택** — 연속 20 A가 20 %, 유휴 0.8 A도 잡힌다 |
| KG140F | 0~400 A | 0.01 A | 과대 |
| KG160F | 0~600 A | 0.1 A | 분해능 부족 — 대기 방전 추적 불가 |

| 항목 | KG110F |
|---|---|
| 션트 | 측정 유닛 내장 (외부 션트 불필요) |
| 통신 | **RS485 4P4C, 115200 baud, Modbus 지원** |
| 전압 정격 | 0~120 V — 드라이버 과전압 임계 41 V를 여유 있게 덮는다 |
| 전류 정격 | 100 A → 연속 20 A는 20 %, 돌입 40 A도 여유 |
| SOC | **기기가 쿨롱 카운팅 수행** |
| 가격 | 3~5만원 + USB-RS485 어댑터 5천~1만원 |

**USB-RS485 어댑터를 쓴다.** MAX485 트랜시버 회로·납땜·GPIO 배선이 전부 불필요하고,
J401 USB 포트에 꽂으면 `/dev/ttyUSB*`로 잡힌다(USB 3.2 포트 6개 중 3개만 사용 중).
설치 난이도가 가장 낮은 구성이다.

디스플레이는 세트 동봉되는 경우가 많으나 쓰지 않아도 된다 — 측정·적산은 션트 유닛이 수행한다.
단 **디스플레이 없이 단독 동작하는지는 `[미검증]`** (ESPHome·Tasmota 사용자들이 RS485만 뽑아 쓰는
사례가 있어 문제 가능성은 낮다).

**이 선택으로 앞선 전압 문제가 소멸한다.** MDT 매뉴얼 p.16의 과전압 임계 `DC24V(DC41V)`와
p.14의 "53V 이상 유입 금지"는 INA226의 36 V 정격에 대한 위협이었지만, KG110F는 120 V 정격이라
회생 전압 구간 전체를 덮는다. 외부 TVS 클램프·분압 회로가 필요 없다.

**설치**: 하이사이드, 배터리 직결측(차단기·E-stop 앞).
```
배터리(−) ─[볼트]─ KG110F 측정 유닛(션트 내장) ─[볼트]─ 부하 GND 전체
배터리(+) ─ 전압 감지선 → 측정 유닛
측정 유닛 RS485(4P4C) ─ USB-RS485 어댑터 → J401 USB 포트 → /dev/ttyUSB*
```
로우사이드를 피하는 이유: CAN·USB·섀시 본딩으로 접지 루프가 생겨 전류가 션트를 우회한다.
이 로봇은 공유 접지 주변장치가 많아 전형적인 실패 사례가 된다.
E-stop 앞에 두는 이유: E-stop 중에도 적산이 끊기지 않고, 배터리 총 전류를 한 점에서 잡는다.

**소프트웨어 부담이 거의 없다.** 파싱 구현체가 이미 여럿 있다 —
`tfyoung/esphome-junctek_kgf`(ESPHome 원본), Arduino 라이브러리,
`AnalogThinker/junctek_monitor`(Python/RS485), Tasmota. ROS 노드는 pyserial로 읽어
`sensor_msgs/BatteryState`로 변환하는 얇은 껍데기가 된다.

**주문 전 확인**: ① 모델명 `KG110F`(100 A) — 140F/160F는 과대하고 160F는 분해능이 거칠다
② 4P4C RS485 케이블 동봉 여부 ③ USB-RS485 어댑터 동시 주문.

### B-2. 완제품 SOC를 쓸 때의 대가 — CAN 전압 대조가 필수다

기기가 SOC를 계산해 주면 소프트웨어가 단순해지는 대신 **알고리즘이 블랙박스가 되어
값이 틀려도 우리가 모른다.** `vica_system_monitor`의 설계 철학("UNKNOWN은 정상이 아니다")과 배치되므로
검증 경로를 반드시 둔다.

CAN `PID_PNT_IO_MONITOR`(0xF1) **두 번째 패킷(`d[1]==1`)의 D2·D3**가 드라이버 입력전압이다
(0.1 V 단위, CAN 매뉴얼 p.80). 이미 10 Hz로 수신 중인데 현재 코드
(`mdrobot_can_keyboard_knob_node.py`의 `drain_can_rx`)가 `if d[1] == 0`만 처리하고 버린다.

세 가지 용도:
1. **타당성 검사** — KG110F 보고 전압과 1.5 V 이상 차이가 5초 지속되면 `BATTERY_SENSOR_DISAGREE`
2. **폴백** — 시리얼 두절 시 전압만이라도 유지 (`current`/`percentage`는 NaN, `BATTERY_MONITOR_DEGRADED`)
3. **배선 저항 진단** — `V_khf − V_can` = 배선·차단기·커넥터 저항 × 전류.
   단자 이완·접점 부식을 조기 감지한다. 개발보고서 p.49의
   "장시간 연속 운용 시 전압 강하, 배선 발열 추이 모니터링 예정"에 직접 답한다.

**구현 시 주의: `mdrobot_can_keyboard_knob_node.py`를 수정하지 않는다.** 안전 임계 경로다.
SocketCAN은 브로드캐스트라 같은 인터페이스를 여러 프로세스가 동시에 읽어도 충돌이 없고,
`encoder_feedback`이 이미 read-only 수신자로 존재하는 선례가 있다. **별도 read-only 리스너 노드**로 만든다.

**드라이버 상태비트로는 저전압을 판정할 수 없다.** CAN 매뉴얼 p.78의 `PID_ALARM_LOG` D2 필드명이
**"과전압/저전압(OVER_VOLT)의 발생횟수"**로 되어 있어 BIT2가 OR임을 문서가 직접 인정한다
(p.90 펌웨어 `(fgOverVolt || fgUnderVolt)<<2`도 일치). LED 점멸(3회/4회)만 둘을 구분한다.

### B-3. 배터리 사양 확인 — 구매보다 먼저 할 일

**산타리 SLB2418의 상세 사양이 공개돼 있지 않다 `[미검증]`.**
개발보고서 p.48의 "연속 방전 20A"가 유일한 근거다. 제조사(031-981-8118)에 확인할 항목:
연속/피크 방전전류, 셀 구성(8S 추정), BMS 과방전 차단 전압, 만충 전압, 저온 충전 차단 유무,
그리고 **BMS 통신(UART/CAN/SMBus) 유무**.

**BMS 통신 유무 확인이 KG110F 구매보다 먼저다.** 배터리가 이미 UART로 SOC를 준다면
추가 부품이 0이 되고 이 절 전체가 불필요해진다.

MDUI 경유 경로는 쓸 수 없다 — `PID_ROBOT_MONITOR` D11(배터리 %)과 도킹·충전 상태 비트는
전부 MDUI 보드 전용이고 우리는 CAN 직결이다.

### B-4. SOC — 왜 완제품에 맡기는가

LiFePO₄ 8S 기준 20~90 % 구간의 OCV 폭은 약 **26.2~26.6 V(0.4 V)**로 용량의 70 %를 차지한다.
배선·차단기·커넥터 저항을 25~60 mΩ로 잡으면 **10 A 부하에서 IR 강하가 0.25~0.6 V** —
평탄 구간 전체 폭보다 크다. **전압만으로 SOC를 내는 것은 원리적으로 불가능하고, 쿨롱 카운팅이 필수다.**

직접 구현하려면 완충–방전 전 사이클 실측, OCV-SOC 테이블 작성, Peukert 계수 추정,
드리프트 리셋 규칙 검증이 필요하다 — 몇 주짜리 작업이다. 개발 기간이 2026-10-30까지인데
Nav2 70 %, 관리자 앱 60 %, LLM-ROS 통합 30 %가 남아 있고, 배터리는 원래 범위 제외였다가
새로 들어온 항목이다. **여기에 몇 주를 쓰면 본류가 밀린다.**

따라서 KG110F가 계산한 SOC를 받아 쓰고, 우리 몫은 세 가지로 한정한다:
1. **시리얼 신선도 감시** → `BATTERY_SENSOR_STALE`.
   `vica_system_monitor/config/probes.yaml`에 블록 하나를 추가하면 `external_diagnostics_node`가
   코드 수정 없이 처리한다.
2. **CAN 전압 대조** → `BATTERY_SENSOR_DISAGREE` (B-2)
3. **30 % 임계 정책 상태머신** (B-5)

부팅 시 SOC 복원·만충 동기화·온도 보정은 전부 기기가 한다.
다만 기기 초기 설정(배터리 용량 18 Ah, 화학종 LiFePO₄, 만충 전압)을 반드시 넣어야 한다 —
기본값 그대로면 SOC가 통째로 틀린다.

**ROS 인터페이스는 `sensor_msgs/BatteryState`를 쓴다.** 커스텀 메시지가 아니다. 근거:
① `nav2_is_battery_low_condition_bt_node`가 이미 `nav2_params.yaml:97`에 로드돼 있고 이 타입을 쓴다
② `opennav_docking`의 `SimpleChargingDock`이 `state->current > charging_threshold_`로 충전을 판정한다
③ `POWER_SUPPLY_TECHNOLOGY_LIFE`(LiFePO₄) 상수가 있다.
**부호 규약은 방전 음수 / 충전 양수**를 지켜야 도킹 서버와 그대로 물린다.

`vica_interfaces`에는 `BatteryState`로 표현 못 하는 것만 추가한다 —
`wiring_drop_volt`(B-2의 배선 저항 진단), `soc_source`, `estimated_runtime_sec`.

### B-5. 저배터리 정책 — 30% 기준, 단일 임계값 금지

사용자 확정: **30%로 통일하고 개발보고서 p.37의 "35%" 서술을 갱신한다.**

단일 임계값은 경계에서 진동하고, 무엇보다 **안내 중인 사용자를 복도에 두고 갈 수 없다.**
계층 + 히스테리시스로 설계한다:

| 단계 | 진입 | 재무장 | 동작 |
|---|---|---|---|
| NORMAL | SOC ≥ 40 % | — | 정상 |
| LOW | SOC ≤ **30 %** | ≥ 40 % | 앱 알림 + **신규 안내 요청 거부**. 진행 중 안내는 계속 |
| CRITICAL | SOC ≤ 15 % 또는 부하보정 V_oc < 22.0 V | ≥ 50 % | 안내 중단 → **가까운 대기 장소까지 안내 후** 종료 → 복귀 |
| SHUTDOWN | SOC ≤ 5 % 또는 V < 20.8 V | 충전만 | 주행 금지, 비필수 노드 종료, graceful shutdown |

안내 중 중단 판정은 SOC 단일값이 아니라 **에너지 예산**으로 한다 —
`ComputePathToPose`로 실제 잔여 경로 길이를 받아 `E_남은안내 + E_도크복귀 + 여유`와 비교한다.
5 m 남은 안내와 60 m 남은 안내는 같은 SOC에서 다른 결정을 요구한다.
평균 소비전력은 계측 하드웨어 장착 후 실측이 전제다 `[미검증]`.

**배터리는 주행 승인 게이트에만 관여하고 정지 경로에는 넣지 않는다.**
`battery_monitor_node`가 죽어도 안전 정지는 유지되어야 한다
(`vica_system_health_monitoring_draft.md` §3.1 원칙과 동일).

### B-6. ★ 운용시간이 실제 제약이다

```
460.8 Wh (25.6 V × 18 Ah)  ÷  340 W (개발보고서 p.48 합계)  =  1.36 시간
SOC 30 % 를 남기면 실사용 약 0.95 시간
```

**개발보고서에 운용시간 계산이 한 줄도 없다.** 위 환산은 이 플랜이 처음 한 것이다.
340 W도 실측이 아니라 산정치다. 즉 **자동 충전 복귀는 편의 기능이 아니라 운용 필수 조건**이며,
계측 하드웨어 실측으로 이 숫자를 확정하는 것이 도킹 설계의 선행 과제다.

### B-7. 도킹 — 전진 도킹 + 후진 이탈

`opennav_docking`은 apt에 **존재한다**(0.0.2, Apache-2.0, humble 브랜치 있음).
단 확인은 amd64 인덱스 기준이므로 **Jetson arm64 가용성은 `[미검증]`** — 젯슨에서 재확인.

**후진 도킹을 채택하지 않는다.** footprint 후방이 −0.565 m로 길고 **후방 센서가 0개**다
(LiDAR x=+0.185, 카메라 x=+0.28683 둘 다 전방). `opennav_docking`의 `rotate_to_dock` 모드는
0.565 m를 완전 맹목으로 후진하는데, 이는 `devlog/2026-07-29.md`가 위험하다고 판정해
BT에서 제거를 권고한 `BackUp`과 정확히 같은 위험이다.

전진 도킹이면 접근(움직이는 환경 + 정밀 정렬)을 센서가 있는 쪽으로 하고,
이탈(정지 상태에서 시작하는 짧고 확정적인 궤적)만 후진이 된다. 남는 위험은 명시한다 `[GAP]` —
도크 전방 1.5 m keepout, 이탈 전 음성·LED 예고, 이탈 속도 0.13 m/s.

정밀 접근: **AprilTag(`apriltag_ros`, CPU 검출) + 기구 V자 가이드 + LiDAR 형상 백업.**
Isaac ROS AprilTag(GPU)는 nvblox와 경합하므로 배제한다.

충전 시작·종료 판정은 **KG110F가 보고하는 전류 부호**로 한다 — `sensor_msgs/BatteryState`를 쓰는 결정적 이유다
(`SimpleChargingDock`이 `state->current > charging_threshold_`를 그대로 쓴다. 부호 규약: 방전 음수).

**J401은 Auto-Power-On이 출하 기본 활성이다**(데이터시트 p.31-32: REC 헤더 핀5-6을 단락해야
비활성화, 회로도 sheet 9 `open:auto ON`). 도킹 접점에 19~54 V가 인가되면 자동 부팅된다 —
도킹 자동 기동의 하드웨어 근거이며, 24 V 직결이 가능하다.

LiFePO₄ 충전기: **8S CC/CV, CV 29.2 V, CC 0.3C ≈ 5.4 A, 종료 I < 0.9 A.**
리튬이온용 33.6 V 충전기를 절대 쓰면 안 된다. **Float 금지** — 완충 후 릴레이로 끊고
SOC 95 % 아래에서 재개하는 히스테리시스가 필요하다.

충전 중에는 nvblox·D455·STT·TTS를 끄고 Nav2를 `inactive`로 내린다. 충전 5.4 A × 25.6 V ≈ 138 W인데
로봇이 스스로 상당 부분을 먹으므로 순 충전 전류가 직접 늘어난다.

### B-8. 승인 필요 항목 (`GOVERNANCE.md` §4)

| # | 대상 |
|---|---|
| 1 | `vica_scenario.md:38`의 "배터리 잔량에 따른 서비스 정책" 범위 제외 해제 |
| 2 | 개발보고서 p.37의 35% → 30% 갱신 |
| 3 | `RobotHealth.msg`에 `power_readiness` 추가 (공용 message 계약) |
| 4 | `/robot_status` JSON에 배터리 필드 추가 (공용 JSON 계약) |

Phase A(홈 복귀)는 기획서에 이미 있으므로 이 목록에 들어가지 않는다.

---

## Phase C — 자동 탐사 방향 설계 (문서 산출물)

### C-1. 판정: 완전 자동 frontier exploration은 현재 이 로봇에 부적합하다

구현 순서의 문제가 아니라, 자동 탐사가 성립하기 위한 전제 5개가 지금 전부 깨져 있다.

| # | 전제 | 상태 | 근거 |
|---|---|---|---|
| 1 | 갇혔을 때 스스로 빠져나온다 | **깨짐** | `devlog/2026-07-29.md` §4 — BackUp 0.0005초, Spin 0.10초 만에 `Collision Ahead` |
| 2 | planner가 차체를 안다 | **깨짐** | `SmacPlanner2D`는 점 로봇. 내접 0.277 m만 보장, 외접과 2.4배 차이 |
| 3 | 정지거리 < 여유 | **깨짐** | 실측 정지거리 7.8~9.4 cm > `footprint_padding` 5 cm |
| 4 | 낭떠러지를 감지한다 | **없음** `[GAP]` | 2D LiDAR는 z=0.382 m 평면만. ESDF slice는 "위에 뭐가 있나"지 "바닥이 없나"가 아니다 |
| 5 | 유리를 감지한다 | **없음** `[GAP]` | 2D LiDAR 투과 → Cartographer가 벽을 안 그림 → **frontier 알고리즘이 유리 너머를 미탐사로 보고 돌진한다** |

개발보고서 p.20도 5번을 인정한다("완전히 투명한 유리벽이나 유리문은 LiDAR만으로 안정적인 인식이 어려우므로").

**"사람이 없으면 전제가 달라지는가"에 대한 답: 일부만.**
`devlog/2026-07-29.md`의 판정은 위험 사유("뒤에 사람이 있다")와 실패 사유("0.9 m 차체로는
padded footprint 스윕이 통로에서 거의 항상 막힌다")가 섞여 있다. 전자는 무인이면 사라지지만
후자는 기하 문제라 그대로 남는다. 그리고 무인이면 **갇혔을 때 꺼내줄 사람이 없어 더 나빠진다.**

3·4번의 위험도가 탐사에서 최대가 되는 구조적 이유: `allow_unknown: true` +
`track_unknown_space: true` + 점 로봇 planner 조합이 **미지 셀을 통과 가능으로 본다.**
안내 주행은 static map이 있어 이 결함이 덜 드러났지만, **탐사는 정의상 미지 영역으로 가는 일이라
이 결함에 100 % 노출된다.**

투자 대비 효과도 맞지 않는다. 운용 지도 free 면적은 106.4 m²(실측)로 건물 1개·층 1개다.
사람이 몰면 10~20분이면 끝난다. 자동 탐사를 안전하게 만드는 데는 몇 주가 들고,
그 사이 위 5개 GAP은 하나도 해소되지 않는다.

### C-2. 권고 대안 — 사람 주도 매핑 + 미탐사 영역 실시간 표시

frontier 계산은 하되 **goal을 발행하지 않는다.** exploration의 위험한 절반(자율 주행)을 빼고
유용한 절반(어디가 안 그려졌나)만 취한다. 나중에 완전 자동으로 승격할 때 goal 발행부만 추가하면 된다.

이 로봇에 특히 잘 맞는 이유: VICA는 원래 **사람이 손잡이를 잡고 미는 물건**이다.
앱 조이스틱 teleop 범위 제외(`vica_scenario.md:704`)와도 충돌하지 않는다 — 손으로 미는 것은 teleop이 아니다.
단 MDH100이 백드라이브 가능한지 `[미검증]`. 안 되면 기존 `teleop_twist_keyboard`로 몬다.

### C-3. 그래도 구현한다면 — 반드시 해결해야 할 3가지

**(a) launch 구조.** `bringup_launch.py`에 `slam:="True"`를 주면 안 된다 —
`nav2_bringup/launch/slam_launch.py:43-44`가 **slam_toolbox를 하드코딩**해서 Cartographer와
`map→odom` 발행자가 2개가 된다. `navigation_launch.py`를 직접 include해야 한다
(controller/planner/behavior/bt_navigator만 띄우고 map_server·amcl·slam_toolbox 미포함).
`cmd_vel_smoothed → /cmd_vel_req` 등 SetRemap 2종은 그대로 유지하고 계약 테스트 대상에 넣는다.

**(b) loop closure 뒤틀림 — 가장 어려운 문제.**
현재 설정(`optimize_every_n_nodes 35`, `motion_filter 0.05 m`)이면 약 **1.75 m 주행마다 전역 최적화**가
돈다. 그때 `map→odom`이 점프해 map 프레임 goal의 물리적 의미가 바뀌고,
global costmap 장애물이 통째로 이동해 **`Starting point in lethal space`**를 유발한다 —
`devlog/2026-07-29.md`가 기록한 실제 실패 모드와 동일하다.
`bt_navigator`의 `GoalUpdated`는 goal 값 변경만 보고 **프레임 뒤틀림은 못 본다.**
대응: goal을 3~5 m로 짧게 자르고 / `map→odom` 점프(>0.15 m, >3°)를 감지해 goal 취소 + costmap clear +
frontier 재계산 / 탐사 중 `max_velocity`를 0.26 → 0.15 m/s로 낮춘다.
**기존 `m-explore-ros2`에는 이 훅이 없다** — 직접 구현을 권하는 결정적 근거다.

**(c) 지도 저장 파이프라인.** 현재 `[GAP]`이다.
`nav2_params.yaml:414-420`의 map_saver 블록은 `map_saver_server`용이고 `map_saver_cli`는 이걸 읽지 않는다.
정석은 pbstream 경유 — `/finish_trajectory` → `/write_state` → `cartographer_pbstream_to_ros_map`
(세 도구 모두 설치본에 존재 확인). 최종 최적화를 반영하고 `.pbstream` 원본을 보관해 나중에 이어 그릴 수 있다.

**★ 놓치면 조용히 실패하는 것**: `VICA_Supervisor/ros2/map_list_node.py`의 `publish_maps()`가
`glob("*.png")`를 순회한다. **pgm/yaml만 저장하면 앱 지도 목록에 새 지도가 안 뜬다.**
저장 산출물은 `.pbstream` / `.pgm` / `.yaml` / **`.png`** / 빈 `destinations.yaml` **5종**이다.

`map_id`는 파일 stem과 같아야 한다(`vica_status_app_node.py`가 map yaml 경로에서 자동 추출).
`storage.py:18`의 `^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$`를 재사용해 검증한다.
단 2026-07-26 `map_id` 절단 사고의 진짜 원인은 명명 규칙이 아니라 **fail-fast 부재**였다
(카탈로그가 없어도 WARN 한 줄만 남기고 빈 목록으로 진행). 저장 스크립트가 5종 존재를 검증하고
비영 종료코드를 반환하도록 하는 것이 우선이다.

### C-4. 안전 제약과 Goal 권한

**무인 자율 탐사는 금지한다.** 허용 형태는 사람이 시야 내에서 따라다니며 물리 E-stop을 든
**감독 탐사**뿐이다. exploration 노드는 `/cmd_vel_req`를 직접 발행하지 않고 `NavigateToPose`만 쓴다.

Goal 권한자 문제는 **모드 배타**로 푼다 — SLAM 모드에서는 Mission Manager를 아예 띄우지 않아
exploration 노드가 유일한 goal 발행자가 되게 한다. `vica_scenario.md` §2-1이 이미
"SLAM 모드 / Nav2 자율주행 모드"를 배타적으로 정의하므로 정합한다.
(Mission Manager 경유는 불가능하다 — `check_gate`가 등록된 UUID 목적지만 통과시키는데
탐사 goal은 카탈로그에 없는 임의 좌표다.)

탐사 중에는 **nvblox를 켜고 음성 스택 전체를 끈다.** 사용자가 없으므로 긴급어 STT·대화 STT·TTS가
불필요하고, GPU 경합의 다른 두 축이 사라져 nvblox가 GPU를 거의 독점한다.

### C-5. 발견한 문서·코드 불일치 (부수, 이번 범위 밖)

- `vica_2d.lua:54`의 `max_range 8.0`은 YDLIDAR G2 기준 주석인데 실 센서는 RPLIDAR다.
  costmap은 3.0~3.5 m로 제한되어 **지도와 costmap의 관측 반경이 2.3배 다르다** —
  탐사에서 "frontier는 보이는데 안전하게 갈 수 없는 구간"이 생긴다.
- `vica_architecture.md` §7.2의 footprint 후방 −0.60 / 외접 0.707은 실제 −0.565 / 0.675와 다르다(문서가 낡음).
- `maps/map_keepout.yaml`이 어디서도 참조되지 않고, `image:`가 편집본이 아닌 원본 pgm을 가리킨다.

---

## 검증

**Phase A 단위(개발 노트북)**
```bash
cd ~/VICA-smarthandle/vica_ros2_ws
colcon test --packages-select vica_mission_manager vica_localization vica_nav2
colcon test-result --verbose
```
새로 추가할 테스트 클래스: `TestReturnHome`, `TestReturnPreemption`,
**`TestReturnEstopInteraction`**(복귀 중 E-stop이 goal을 취소하는가, E-stop 해제 후 자동 복귀하지 않는가),
`TestLocalizationGate`, `test_home.py`, `test_pose_bootstrap_logic.py`, `test_scan_match.py`.
계약 테스트: `set_initial_pose: false` 고정, 홈 tolerance > Nav2 goal tolerance,
`/vica_goal_event` payload에 `trip` 존재 + terminal 이벤트명이 `_TERMINAL_GOAL_EVENTS` 안.

**Phase A 실기(Jetson, 바퀴 띄운 상태 우선)**
1. `ros2 topic echo /scan --field range_max` → `laser_max_range` 확정
2. `/initialpose` 발행 후 `ros2 topic echo /amcl_pose` → 공분산 수축 관측, RViz 입자 구름 확인
3. `/request_nomotion_update` 호출 유무에 따른 공분산 차이 실측 (설계 전제 검증)
4. **로봇을 일부러 2 m 어긋난 곳에 두고 검증이 실패하는지 확인** — 거짓 통과 방지가 이 설계의 존재 이유
5. 복귀 중 E-stop → `/cmd_vel_safe = 0` 및 goal 취소 종단 확인
6. 안내 → 도착 → 대기 → 복귀 → IDLE 1사이클

**Phase B 실기(하드웨어 장착 전에 가능한 것)**
- CAN `PID_PNT_IO_MONITOR` 2번째 패킷(`d[1]==1`) 전압 파싱 리스너를 **별도 read-only 노드**로 만들어
  `/battery_state` 발행. `mdrobot_can_keyboard_knob_node.py`는 안전 임계 경로이므로 건드리지 않는다.
- 이것만으로 `nav2_is_battery_low_condition_bt_node`(이미 plugin_lib에 로드됨)와
  `SimpleChargingDock`이 실제로 이 토픽을 받는지 **하드웨어 없이 인터페이스 계약을 검증**할 수 있다.
- 회생 전압 로깅 시험 → KG110F(120 V 정격)면 불필요. **대안 ⓒ(INA228, 85 V)로 선회할 때만 필요**

## 문서 산출물

- `devlog/2026-07-30-home-return-and-docking-design.md` — 결정 근거, 계산 과정, 실측 대기 항목
- `guideline/vica_scenario.md` §2-1 — 복귀 중 스마트핸들 규약 7항 (승인 후)
- `guideline/vica_architecture.md` — 홈 좌표·`/vica/localization_status`·`trip` 필드 계약 (승인 후)
- `docs/vica_robot_bringup_manual.md` §5 — 자동 초기화 단계 추가, SLAM 매핑 모드 절 신설

## 미결 항목

| 항목 | 확인 방법 |
|---|---|
| **계측 하드웨어 최종 선정 `[미정]`** | KG110F 기준으로 설계. **사용자가 확정 후 재공유 예정.** 부류 1 내 교체면 드라이버 노드 1개만 영향(B-1 표). 부류 2로 내려가면 B-4 재작성 필요 |
| 산타리 SLB2418 BMS 통신 유무 | 제조사 문의 031-981-8118 — **KG110F 구매보다 먼저.** 있으면 추가 부품 0 |
| 산타리 SLB2418 연속/피크 방전전류·셀 구성·차단 전압 | 같은 문의 |
| KG110F 디스플레이 없이 단독 동작 여부 | 판매처 확인 또는 실물 시험. 문제 가능성은 낮음 |
| KG110F 국내 조달처·실제 가격 | 알리 기준 3~5만원 추정 `[미검증]` |
| 홈 좌표 | 로봇을 실제 위치에 세우고 `/amcl_pose` 기록 |
| `return_home_delay_sec` | 제안 60초. 운영 정책 결정 필요 |
| 검증 임계값 6종 | 실측 후 확정 `[미검증]` |
| `/scan` 실제 `range_max` | 런타임 echo |
| `opennav_docking` arm64 가용성 | Jetson에서 `apt-cache policy` |
| MDH100 백드라이브 가능 여부 | 실물 시험 (사람 주도 매핑 채택 시) |
