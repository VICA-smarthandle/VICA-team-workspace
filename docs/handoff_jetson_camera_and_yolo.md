# 핸드오프 — 젯슨 카메라 점검과 YOLO 도입 준비

작성일: 2026-08-23
작성 환경: 개발 노트북 (x86_64, 센서·주행 불가)
대상: 카메라 costmap 암전 원인 규명 → nvblox 존폐 판정 → 사람 접근 기능 착수

| 저장소 | 브랜치 | 커밋 |
| --- | --- | --- |
| 루트 `VICA-smarthandle` | `docs/person-approach-design` | `8011391` |
| `vica_ros2_ws` | `dev` | `a4aa874` |
| `vica-voice-llm` | `dev` | `cb183ef` |
| `VICA_Supervisor` | `dev` | `58a97f4` |

> **이 문서 용도**: 노트북에서 한 조사·설계를 젯슨에서 이어받기 위한 핸드오프다.
> **코드·설정은 하나도 바꾸지 않았다.** 문서만 만들었다.
>
> 함께 볼 것: `devlog/2026-08-23-사람접근-구현설계.md`(설계 정본),
> `docs/nav2_backlog.md` **§9 하지 말 것**.

---

## 0. 한 줄 요약

카메라를 켜고 nvblox 또는 voxel_layer 를 costmap 에 넣으면 **바닥을 뺀 주변이 전부
lethal 로 차서 주행을 못 한다.** 구현이 전혀 다른 두 시스템이 같은 증상을 내므로 범인은
둘이 공유하는 입력(**depth 와 TF**)이다. 젯슨에서 §2 를 순서대로 밟아 원인을 좁힌다.

그와 별개로 **사람 접근 기능**(YOLO 로 시각장애인 감지 → 1.1 m 앞 접근 → 음성 질문)의
설계가 끝났다. **Phase A 는 카메라와 무관하므로 노트북에서 병행할 수 있다.**

---

## 1. 지금까지 정해진 것

### 1.1 확정

| 항목 | 값 | 근거 |
| --- | --- | --- |
| 인식 노선 | **nvblox = 장애물, YOLO seg = 사람 접근** | 2026-08-22 사용자 결정 |
| nvblox 모드 | `static_tsdf` 유지 | `dynamic` 은 실측 lethal 2배로 제외 |
| 추론 위치 | **Isaac ROS 컨테이너 안 단일 노드** | 카메라가 거기서 돈다. 호스트로 넘기면 초당 27 MB 복사 |
| 추론 주기 | **5 Hz** | CPU 병목 |
| 정지 거리 | **1.1 m** | 하한 1.00 m, 여유 10.4 cm |
| 접근 속도 | **0.3 m/s** | 주행 상한 0.5 의 60 % |
| 출발 조건 | `stable`(0.6·1초) **그리고** `approachable`(3초 정지·1.5~4.0 m) | 로봇이 걷는 사람을 못 따라잡는다 |

### 1.2 판단 보류

| 항목 | 상태 |
| --- | --- |
| nvblox 존폐 | **§2 점검 결과로 정한다.** 지금 끄지 않는다 |
| 낮은 장애물 대책 | nvblox 복귀 vs 초음파 연결. 초음파 계약이 아직 없다 |
| Ultralytics AGPL-3.0 | 배포·상용화 판단 없음 |

### 1.3 현재 상태 (사용자 보고)

- `nvblox_layer` 는 local costmap plugins 에 **들어 있다**
- `nvblox_node` 는 `human_with_static_tsdf` 로 돌지만 **segmentation 이 비활성**이라
  사용자 관찰로는 "작동 안 하는 것과 동일"
- 다만 **nvblox 를 완전히 끄면 코너에서 더 붙어서 간다**는 관찰이 있다 →
  정말 무해한지 확인이 필요하다. **§2-2 가 이것을 판정한다**

---

## 2. 점검 절차

각 단계는 앞 단계 결과와 무관하게 독립이다. 시간이 없으면 **2-2 를 먼저** 한다.

### 2-1. nvblox 가 살아 있는가 (1분)

```bash
ros2 node list | grep nvblox
ros2 topic hz /nvblox_node/static_map_slice
ros2 topic echo /nvblox_node/static_map_slice --once --field width
ros2 topic echo /nvblox_node/static_map_slice --once --field height
```

| 결과 | 판정 |
| --- | --- |
| 토픽이 안 나옴 | nvblox 완전 무해. 코너 관찰은 다른 원인 |
| Hz 는 나오는데 width/height 가 0 | 지도가 안 만들어짐 (8/15 `dynamic_map_slice` 0칸과 같은 상황) |
| 크기 정상 | 뭔가 만들고 있다 → 2-2 로 |

기록 — **2026-08-24 실행. nvblox 는 살아 있고 지도를 만들고 있다.**

```
주기            9.32 Hz
width x height  105 x 160        resolution 0.050 m   frame odom
아는 칸         6453 / 16800 (38.4 %)   미탐색 10347
장애물 근처     1366 칸 (거리 < 0.3 m)
거리값          최소 -0.25 / 중앙 0.95 / 최대 2.00 m   (음수 = 장애물 안쪽, 정상)
```

판정표의 **"크기 정상 → 뭔가 만들고 있다"** 에 해당한다. slice 가 비어 있다는
가설((가))은 제외된다. 타입은 `nvblox_msgs/msg/DistanceMapSlice` 이고 구독자는 2 다.

측정은 `ros2 topic hz` 대신 rclpy 로 직접 받는다 — CLI 를 timeout 으로 죽이면
`/dev/shm` 고아 세그먼트가 쌓여 DDS 가 막힌다.

### 2-2. slice 가 costmap 에 들어가는가 ★ (10분)

**Nav2 를 재기동하지 않고 `nvblox_node` 만 죽였다 살린다.** plugins 는 그대로 두고
입력만 끊으므로, 차이가 곧 nvblox 의 기여분이다.

```
① 로봇을 코너나 벽 가까이 세운다 (이후 움직이지 않는다)
② costmap 스냅샷 저장                  <- nvblox 켜진 상태
③ nvblox_node 종료
④ 10초 대기 후 스냅샷 저장             <- nvblox 없는 상태
⑤ 두 스냅샷의 "253 이상 칸 수" 비교
```

| 결과 | 판정 |
| --- | --- |
| 칸 수가 거의 같다 | nvblox 무해. 코너 관찰은 착각이거나 다른 변수 |
| 칸 수가 줄어든다 | **nvblox 가 벽 근처에 비용을 넣고 있었다.** 코너 관찰이 사실 |
| 껐는데도 안 줄어든다 | nvblox_layer 가 **마지막 slice 를 붙잡고 있다.** 이것도 중요한 발견 |

한 번의 실험으로 **기여도와 잔상 두 가지가 동시에 판정된다.**

> 측정 도구가 아직 없다. `scripts/` 에 costmap 을 직접 재는 스크립트가 없어
> `vica_costmap_probe.py`(스냅샷·비교)를 새로 만들어야 한다. **노트북에서 만들 수 있다.**

기록 — **2026-08-24 1차 시도. 판정 불가로 끝났고, 대신 더 근본적인 것을 찾았다.**

| 스냅샷 | 253 이상 | 0 초과 | 최댓값 |
| --- | --- | --- | --- |
| nvblox ON | 0 칸 | 0 칸 | 0 |
| nvblox_node 종료 10초 후 | 0 칸 | 0 칸 | 0 |
| `nvblox_layer.enabled=false` | 0 칸 | 0 칸 | 0 |

**켜든 끄든 costmap 이 통째로 비어 있어 비교 자체가 성립하지 않았다.** 그런데 같은
순간 `/local_costmap/voxel_grid` 에는 **MARKED 157 voxel**(장애물 있는 열 157개)이
들어 있었다. **`voxel_layer` 는 라이다를 제대로 마킹하는데 2D costmap 으로 내려오며
전멸한다.** 입력은 모두 정상이었다 — `/scan` 유효 519점(정면 0.24 m), stamp 지연
+0.088 s, `odom→base_footprint` 정상, 라이다 높이 0.382 m 는 voxel 범위(0~0.8 m) 안,
`obstacle_min_range 0.12` 도 0.24 m 를 막지 않는다.

레이어 순서가 `voxel_layer → nvblox_layer → inflation_layer` 이고 nvblox_layer 는
`convert_to_binary_costmap: True` 로 자기 slice 를 다시 칠하므로 그것을 의심했지만
**확정하지 못했다.** `ros2 param set nvblox_layer.enabled false` 가 성공 응답을 냈는데도
0 칸 그대로였다(nav2 플러그인이 enabled 를 동적 반영하지 않았을 가능성).

**다음에 할 것 — 이것부터 확정한다. §2-2 는 그 뒤다.**
`nav2_params.yaml` 의 local_costmap `plugins` 에서 **nvblox_layer 를 빼고 Nav2 재기동** →
costmap 재측정. 157 칸이 살아나면 nvblox_layer 가 범인이고, 그대로 0 이면 다른 곳이다.

**측정 조건 주의.** 이 회차는 노드를 개별로 띄운 비정석 구성이었다 — **세그멘테이션
칸이 빠져** nvblox 가 `human_with_static_tsdf` 모드에서 마스크를 못 받았고, odom 이
Nav2 보다 늦게 올라왔다. 재현은 **터미네이터 12칸 정석 기동**으로 한다.

**기동 순서에서 배운 것.** ① `local_costmap` 이 `active` 여도 **AMCL 초기위치를 안 찍으면
`global_costmap` 이 `activating [13]` 에 머물고 `Managed nodes are active` 가 안 뜬다** —
그 전 스냅샷은 전부 무효다. `scripts/vica_set_initial_pose.sh <장소>` 로 RViz 없이 찍는다.
② CAN 을 올려도 **모터 노드를 띄우기 전에는 CAN RX/TX 가 0** 이라 엔코더가 안 오고
odom TF 가 없다. `ip -s link show can1` 로 패킷 수를 먼저 본다.

---

**2026-08-24 2차 — 터미네이터 정석 기동(세그멘테이션 포함)에서 측정 성립.**

정석으로 띄우니 costmap 이 정상으로 찼다. 1차의 "전부 0" 은 비정석 기동 탓이었다.

| 스냅샷 | INSCRIBED | 그중 LETHAL | 0 초과 |
| --- | --- | --- | --- |
| nvblox ON (1회차) | 1078 칸 | 291 | 2123 |
| nvblox ON (2회차, 0점 측정) | 1131 칸 | 306 | 2141 |
| **nvblox_node 종료 후** | **1159 칸** | 293 | 2258 |

**흔들림 폭(0점 측정) = ±53 칸.** 같은 조건 두 장이 1078↔1131 로 변한다. 이 값을
`--noise 53` 으로 넣어야 판정이 짐작이 아니게 된다.

**결과: 켠 것과 끈 것의 차이 +28 칸 — 흔들림 안이다.** 오른 칸 370 · 내린 칸 334 로
양방향으로 뒤섞였다(한쪽으로 밀렸다면 nvblox 기여다).

§2-1 에서 slice 가 장애물 1366 칸을 담고 있음이 확인됐으므로 (가)"아무것도 안 넣는다"는
아니다. **가장 자연스러운 설명은 중복이다** — nvblox 가 보는 벽을 라이다도 보고 있어,
빼도 그 자리를 라이다가 채운다. 문서의 (나)"잔상"도 완전히 배제되진 않지만, 12 초 대기
후에도 변화가 없고 차이가 양방향인 점이 잔상보다 중복을 가리킨다.

> **일반화 금지.** 이 자리는 정면에 벽이 있는 **라이다가 잘 보는 환경**이다. nvblox 의
> 값어치는 라이다 사각(낮은 의자다리·테이블 상판·사람 몸통)에서 나온다. 오늘 확정된
> 것은 **"nvblox 가 local costmap 을 망치지는 않는다"** 까지다. 존폐 판정에 필요한
> 나머지는 **라이다 사각이 있는 자리에서의 같은 측정**이다.

측정 조건: `camera_z 0.720`(실측 반영, `0a7057e`), 지도는 현재 장소와 불일치했으나
**local costmap 은 odom 기준이라 무관**하다. 로봇 정면 벽 0.24 m(라이다 기준).

### 2-3. 자원을 얼마나 쓰는가 (2분)

```bash
top -b -n 5 -p $(pgrep -f nvblox_node) | grep nvblox
tegrastats --interval 1000 | head -5
```

CPU 가 병목이므로(코어 81 %, load 14.16/8, GPU 35 %) **끄면 돌아오는 양이 곧 YOLO 에
쓸 수 있는 여유**다.

기록: `nvblox_node CPU ______ %`

### 2-4. TF 점검 (5분)

```bash
ros2 run tf2_tools view_frames
ros2 topic echo /camera/camera/depth/image_rect_raw --field header.frame_id --once
ros2 topic echo /camera/camera/depth/camera_info --once | head -20
ros2 run tf2_ros tf2_echo base_footprint camera_link
```

확인할 것.

1. `view_frames` 그림에서 **카메라 frame 이 중복 발행되는지**.
   `VICA.xacro` 는 `camera_optical_frame` 을 발행하는데 주석에 *"실물은 RealSense
   드라이버가 자체 발행"* 이라고 적혀 있다. 둘이 겹치면 `AGENTS.md` §6 위반이고,
   depth 가 매번 다른 곳에 찍힌다.
2. depth 의 `frame_id` 가 TF 트리에 제대로 이어지는지.
3. `camera_info` 의 width/height 가 **실제 이미지 크기와 같은지**.
   decimation 을 걸면 초점거리도 같이 줄어야 한다. 안 맞으면 3D 로 펼칠 때 전부 틀어진다.
4. `tf2_echo` 의 z 가 **1.04 근처인지**. 현재 URDF 는 `1.075` 라고 선언한다
   (`camera_z: 0.885` + base_link `0.190`).

기록 — **2026-08-24 실행, 네 항목 전부 통과.**

| 확인 | 결과 |
| --- | --- |
| 1. frame 중복 | **없음.** URDF 는 `camera_link`·`camera_optical_frame`, 드라이버는 `camera_depth_frame`·`camera_depth_optical_frame` 을 발행해 이름이 겹치지 않는다 |
| 2. depth frame_id | `camera_depth_optical_frame` — 트리에 정상 연결 |
| 3. camera_info | 640×480, `fx 383.91` — 요청 해상도와 일치 |
| 4. tf2_echo z | **1.075** — URDF 선언과 동일. 회전도 `0 0 0` |

```
base_footprint → base_link → camera_link ┬→ camera_depth_frame → camera_depth_optical_frame
                                          └→ camera_optical_frame
```

`camera_optical_frame` 과 `camera_depth_optical_frame` 은 **위치·방향이 완전히 같게**
나왔다(둘 다 `[-0.225, 0, 1.075]`, RPY `-90 0 -90`). 이름만 둘이고 실제로는 겹쳐 있어
"depth 가 매번 다른 곳에 찍힌다"는 시나리오는 **해당 없음**이다.

> **이름을 통일하지 말 것.** 지금은 이름이 달라 각자 자기 트리를 갖는다. 같게 만들면
> 실물에서 드라이버와 URDF 가 같은 프레임을 두고 서로 덮어써 진짜 중복 발행이 된다.
> URDF 쪽은 Isaac 용이다(드라이버가 없어 URDF 가 제공). 혼란을 줄이려면 이름 통일이
> 아니라 xacro 인자로 실물에서 안 만들게 하는 쪽이다.

### 2-4b. 카메라 정렬과 마스트 진동 (2026-08-24 실측)

D455 내장 IMU 로 쟀다. `realsense-viewer` 화면으로는 안 되고 Motion Module 을 봐야 한다.
호스트에서는 `No HID info provided, IMU is disabled` 로 막히므로 **컨테이너에서 띄운다**
(`privileged` + `/dev` 마운트가 있어야 HID 가 보인다).

**정렬 — `rpy="0 0 0"` 유지가 정답이다.**

| 항목 | 값 |
| --- | --- |
| roll | **+0.24°** |
| pitch | **+0.49°** |
| 판정 | 4 m 앞에서 3.5 cm. URDF 에 넣을 값이 없다 |

yaw 는 중력으로 잴 수 없다(미측정). `\|g\|` 가 9.65 로 나오는데 IMU 공장보정이 없어서다
(`IMU Calibration is not available`). 각도는 정규화해 계산하므로 ±0.2° 수준 영향뿐이다.

**진동 — 주범이 아니다.** 손으로 밀며 60초 기록했다.

| 구간 | roll | pitch | pitch 폭 | 4 m 앞 어긋남 |
| --- | --- | --- | --- | --- |
| 정지 | ±0.004° | ±0.019° | 0.25° | — |
| 주행 전체 | ±0.130° | ±0.212° | 4.49° | ±15.7 cm |
| **자율주행 범위(<23 °/s)** | **±0.113°** | **±0.167°** | **2.38°** | **평상 ±1.2 / 최악 ±8.3 cm** |

최악값은 진동이 아니라 **손으로 홱 돌린 순간**에 나왔다(각속도 267 °/s). 로봇의 회전
상한은 0.4 rad/s = **23 °/s** 라 그런 값이 나올 수 없어, 그 구간을 뺀 줄이 실제 예상치다.
평상시 1.2 cm 는 nvblox 격자 한 칸(5 cm)도 못 넘는다. 주진동수 **36.9 Hz** 로 카메라
프레임률(15~30 Hz)보다 빨라 프레임마다 위상이 흩어져 누적하며 상쇄되는 쪽이다.

**측정 방법 주의 — 가속도계만으로는 못 잰다.** 첫 시도에서 roll 164°, pitch 142° 라는
불가능한 값이 나왔다. 가속도계는 중력과 운동 가속도를 구분하지 못해 미는 충격이 통째로
기울기로 둔갑한다. 자이로 적분 + 가속도계 저주파 보정(상보 필터)으로 바꿔야 한다.
도구: `~/workspaces/isaac_ros-dev/mast_vibration3.py`(60초 기록·구간 자동 판정),
`mast_vib_split.py`(저장된 CSV 재분석). 카운트다운에 사람을 맞추게 하면 안 된다 —
시작 신호를 볼 수 없어 33초 내내 정지 상태를 재는 실패가 있었다.

남은 것: **모터 구동 시 진동은 미측정**이다. 이번 값은 손으로 민 것이라 모터 자체
진동과 실제 속도(0.408 m/s)의 노면 충격이 빠져 있다.

### 2-5. 포인트클라우드로 기울기 판정 (5분)

빈 평지에 세우고 RViz 에서 **Fixed Frame = `base_footprint`**, PointCloud2 를 띄운 뒤
**옆에서** 본다. 위에서 내려다보면 휘어짐이 안 보인다.

```
정상        ───────────────────────   바닥 점이 z=0 에 평평
기울기 오차          ╱─────            멀어질수록 위로 휜다 -> 이게 "벽" 으로 찍힌다
            ────╱
```

| 결과 | 판정 |
| --- | --- |
| 멀어질수록 위로 휜다 | **TF 기울기가 범인.** `camera_joint` 의 `rpy` 에 실제 각도를 넣는다 |
| 평평한데 costmap 은 까맣다 | 범인은 TF 가 아니라 **청소(clearing)** 쪽 |

### 2-6. 카메라 고정 후 실측

| 항목 | 재는 법 | 반영 위치 |
| --- | --- | --- |
| 지면 → 렌즈 중심 | 줄자 | `camera_z` = 실측 − 0.190 (현재 0.885, 실측 1.04 면 **0.850**) |
| 앞뒤 위치 | 줄자 | `camera_x` (현재 −0.225) |
| 기울기 | 스마트폰 수평계를 D455 윗면에 | `camera_joint` 의 `rpy="0 <라디안> 0"`, **아래로 기울이면 양수** |

**20도 이상 숙이지 말 것.** STL 실측으로 앞쪽 0.385 m 구조물이 화면 하단에 걸린다.

고정 자체가 중요하다. 마스트는 길어 진동이 끝에서 증폭되고, 그 진동은 IMU → EKF →
odom 으로도 지도를 흔든다(`5f442c0` ~ `a4aa874` 에서 IMU 융합이 네 번 뒤집혔다).

---

## 3. 점검 결과에 따른 분기

```
2-2 에서 nvblox 기여가 0 이다
  └→ nvblox 를 명시적으로 끈다. plugins 에서 nvblox_layer 제거 + nvblox_node 미기동
     자원이 YOLO 로 간다. 낮은 장애물은 초음파 연결 때 다시 판단

2-2 에서 기여가 있다
  └→ nvblox 를 유지한다. 2-4/2-5 로 암전 원인을 계속 좁힌다

2-4 에서 TF 중복 발행이 나온다
  └→ 각도를 재기 전에 이것부터 고친다. 중복이면 실측값을 넣어도 소용없다

2-5 에서 점이 휜다
  └→ 2-6 실측 후 rpy 반영. 그 뒤 nvblox/voxel 재시험
```

---

## 4. YOLO 도입

> **2026-08-24 젯슨에서 §4-1 을 실행해 끝냈다.** 카메라와 무관한 작업이므로 카메라
> 부착을 기다리지 않았다. 아래는 계획이 아니라 **실행 결과**다. 대상 컨테이너는
> `vica_rs_container`(호스트 워크스페이스 `~/workspaces/isaac_ros-dev`)다.

### 4-1. 컨테이너 준비 — 완료 (2026-08-24)

| 항목 | 값 |
| --- | --- |
| L4T / JetPack | R36.4.3 / 6.2 |
| CUDA / GPU | 12.6, sm_87 (Orin) |
| `torch` | `2.5.0a0+872d972e41.nv24.08`, **`cuda: True`** |
| `torchvision` | `0.20.1a0+3ac97aa` — **소스 직접 빌드** |
| `ultralytics` | 8.4.127 |
| venv | `/workspaces/isaac_ros-dev/yolo_env` |
| 실측 추론 | `yolo11n-seg` 640, GPU **30.4 Hz** (설계 목표 5 Hz) |

되돌릴 지점 세 개를 남겼다. 이미지 `isaac_ros_backup:before_yolo`(설치 전),
이미지 `vica_isaac_ros_realsense_2563:before_mount_fix`(마운트 정리 직전),
컨테이너 `vica_rs_container_premount`(옛 컨테이너 자체. 지우지 않았다).

**① 마운트 정리 — 완료.** `run_dev.sh` 는 젯슨에 없다. 컨테이너가 `docker run` 으로
직접 만들어져 있어서 **실행 중인 컨테이너에는 볼륨을 붙일 수 없다. 다시 만들어야 한다.**
설정 누락으로 컨테이너를 못 살리는 사고를 막으려면 옛 컨테이너에서 그대로 뽑아 쓴다.

```bash
# 옛 컨테이너에서 시작 명령을 그대로 추출한다 (직접 타이핑하지 않는다)
STARTCMD=$(docker inspect vica_rs_container --format '{{json .Config.Cmd}}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)[2])")

docker commit vica_rs_container vica_isaac_ros_realsense_2563:before_mount_fix
docker stop vica_rs_container && docker rename vica_rs_container vica_rs_container_premount

docker run -d -it --name vica_rs_container \
  --runtime nvidia --privileged --network host --ipc host \
  --user 1000:1000 --group-add 44 --group-add 111 -w /workspaces/isaac_ros-dev \
  -v /home/ji_w/workspaces/isaac_ros-dev:/workspaces/isaac_ros-dev \
  -v /home/ji_w/VICA-smarthandle/vica_ros2_ws/src:/workspaces/vica_src:ro \
  -v /dev:/dev -v /run/udev:/run/udev:ro -v /tmp/.X11-unix:/tmp/.X11-unix \
  vica_isaac_ros_realsense_2563:before_mount_fix bash -c "$STARTCMD"
```

환경변수 48개는 **전부 이미지에 구워져 있어** `-e` 로 다시 줄 필요가 없다
(`DISPLAY`, `ROS_DOMAIN_ID=7`, `RMW_IMPLEMENTATION` 포함). 이미지와 컨테이너의 Env 를
비교해 확인했고 차이가 없었다.

컨테이너 안에서 복사본을 링크로 바꾼다. **링크는 컨테이너 기준 경로로 만든다.**
호스트에서 만들면 컨테이너 안에서 끊긴다 — 옛 구성이 정확히 그 상태였다.

```bash
cd /workspaces/isaac_ros-dev
mv src/vica_nvblox_bringup src/vica_nvblox_bringup.bak      # 지우지 않는다
touch src/vica_nvblox_bringup.bak/COLCON_IGNORE             # 중복 패키지 오인 방지
ln -s /workspaces/vica_src/vica_nvblox_bringup src/vica_nvblox_bringup
rm -rf build/vica_nvblox_bringup install/vica_nvblox_bringup
colcon build --packages-select vica_nvblox_bringup          # 4.1 s
```

정리하며 치운 것이 하나 더 있다. 워크스페이스 최상위에 **이름이 공백 하나인 링크**가
`vica_nvblox_bringup` 을 가리키고 있었다(`ln -s` 실수). 참조하는 곳이 없어
`_stray_link.bak` 으로 옮겼다.

빌드 때 `listing git files failed` 가 stderr 로 나오는데 무해하다. `src` 만 마운트해
상위의 `.git` 이 안 보여서다.

**② 스냅샷 — 완료.** `docker commit vica_rs_container isaac_ros_backup:before_yolo`

**③ 설치 — 완료. 다만 문서에 적힌 `pip install ultralytics` 를 그대로 하면 안 된다.**
`torchvision` 이 없는데, 기성 휠이 **하나도 맞지 않는다.**

| 출처 | 결과 |
| --- | --- |
| PyPI `0.20.1` (manylinux2014_aarch64) | `RuntimeError: operator torchvision::nms does not exist` |
| `pypi.jetson-ai-lab.io/jp6/cu122`·`cu124` 의 `0.20.x` | **PyPI 복사본**이라 위와 동일하게 실패 |
| 같은 곳 `cu126` 네이티브 빌드(`linux_aarch64`) | `0.23.0` 이상뿐 → torch 2.6~2.9 용, 2.5.0 과 불일치 |

`macosx`·`win_amd64` 파일이 섞여 있으면 그 인덱스는 미러다. 도메인도 주의한다 —
`pypi.jetson-ai-lab.dev` 는 죽었고 **`.io` 가 살아 있다**.

그래서 소스에서 직접 빌드했다. 젯슨 8코어에서 **5분**이면 끝난다.

```bash
git clone --depth 1 --branch v0.20.1 https://github.com/pytorch/vision.git torchvision_src
cd torchvision_src
FORCE_CUDA=1 TORCH_CUDA_ARCH_LIST="8.7" MAX_JOBS=6 \
  TORCHVISION_USE_NVJPEG=0 TORCHVISION_USE_VIDEO_CODEC=0 \
  python3 setup.py bdist_wheel
pip install --no-deps dist/torchvision-0.20.1a0+*-linux_aarch64.whl
```

CUDA 가 들어갔는지는 `build/**/ops/cuda/*.o` 로 확인한다(`.cu.o` 가 아니라 `.o` 다).
휠 5.1 MB 가 정상이고, PyPI 것(14 MB)보다 작다고 실패가 아니다.

`ultralytics` 는 의존성 자동설치를 막고 본체만 넣는다. 그러면 `setuptools` 가
59.6.0 그대로 남아 `colcon` 이 깨지지 않는다 — 아래 방식으로 실제로 안 깨졌다.

```bash
pip install --no-deps ultralytics ultralytics-thop
pip install matplotlib pandas psutil py-cpuinfo pyyaml requests scipy tqdm pillow
# opencv 는 시스템 것(4.5.4)을 쓴다. 다시 깔지 않는다
```

**④ 확인 — 완료.** `nms` CPU·CUDA, `roi_align` GPU(세그멘테이션 마스크 경로),
컨테이너·호스트 `colcon build` 모두 통과했다. venv 밖 시스템 파이썬은 `setuptools`
65.7.0, `ultralytics` 미설치로 **오염되지 않았다.**

`torch` 가 없거나 `cuda.is_available()` 이 False 면 **TensorRT 직접 추론**으로 가야 하고,
세그멘테이션 후처리를 직접 구현해야 한다. 작업량이 크게 늘어난다. **이 분기는 피했다.**

### 4-2. 모델 배포

```bash
# 노트북에서 학습한 .pt 만 젯슨으로 복사한 뒤, 젯슨에서 변환한다
yolo export model=best_v3.pt format=engine half=True device=0
```

**`.engine` 은 만든 기기에만 묶인다.** 노트북 GPU 에서 만든 엔진은 젯슨에서 로드조차
안 된다. 반드시 젯슨에서 변환한다. 미리 한 번 해보는 것이 좋다.

학습 산출물 위치: `/home/msk/visuallyimpaired-dataset/models/best_v3.pt`
(yolo11s-seg, 640, 클래스 1개 `visually-impaired`, mask mAP50-95 0.82)

---

## 5. 노트북에서 병행할 수 있는 것 (Phase A)

**카메라·젯슨과 무관하다.** 셋 다 순수 함수라 pytest 로 끝난다.

| | 할 일 | 상태 |
| --- | --- | --- |
| A1 | `PersonDetection.msg` · `RequestApproach.srv` 정의 | 완료 `e45e79d` |
| A2 | goal 계산 (사람 위치 → 1.1 m 물러난 pose) | 완료 `e813bba` |
| A3 | 판정 로직 (`stable` · `approachable`) | 완료 `addb553` |
| A4 | Mission 상태 기계 (IDLE→APPROACHING→AWAITING_USER→RETURNING) | 완료 `569f06a` |
| A5 | `person_detector_node` 골격 + 웹캠 추론 | **골격 완료** (2026-08-24, 아래 참조) |

A1~A4 는 `vica_ros2_ws` 의 `feat/person-approach-phase-a` 에 있다. 2026-08-24 젯슨에서
빌드·테스트를 확인했다 — `colcon build` 3개 패키지 성공, pytest **242 passed**.
A5 는 §4-1 이 끝나 라이브러리를 갖다 쓰는 방식으로 갈 수 있다.

**2026-08-24 저녁 — A5 골격까지 완료.** 같은 날 젯슨에서 모델 배포·검증·노드까지
한 번에 갔다. `feat/person-approach-phase-a` 에 커밋됨.

| 단계 | 결과 |
| --- | --- |
| 모델 입수 | `v6-blur-640/weights/best.pt` (yolo11s-seg, 클래스 1개 `visually-impaired`, Box mAP50-95 0.94) |
| `.engine` 변환 | 젯슨에서 FP16, 9분 16초. `.pt` 와 검출 동일(변환 무손실 확인) |
| 속도 | `.pt` 28.3 Hz → **`.engine` 61.4 Hz** (2.2배, 목표 5 Hz 의 12배) |
| 거리별 검출(걷기) | 1.2 m 밖 43~57 %(conf 0.76~0.86) / **0.8 m 안 4~12 %** |
| 정지 2.1 m | 45~48 %. **놓침의 절반이 conf 0** — 문턱 조정 무효. stable 창 통과 ~50 % |
| 지팡이 유무 | **없으면 전 구간 0 %.** 모델은 흰지팡이 든 사람만 찾는다(설계 의도대로) |
| A5 노드 | `/vica/person_detection` 발행, detection_gate(A3) 연동, pytest 72 passed |

기동법 주의: `ros2 run` 은 venv 를 못 태운다. 컨테이너에서
`yolo_env 활성화 → python3 -m vica_perception.person_detector_node`.
빌드는 **컨테이너에서** `vica_interfaces vica_perception` 을 한다(심링크 패턴).

남은 것: ① 사람이 화면에 있을 때의 실발행 확인(수신 시험 2회가 빈 화면과
겹쳐 0건 — [미검증]) ② `stable 0.6·1초` 실기 검증(측정상 창 통과 ~50 % 로
방아쇠는 수 초 내 발동 예상) ③ **로봇 카메라 시점 재학습** — 놓침의 절반이
conf 0 인 근본 원인(도메인 격차) 해소. 카메라 고정 위치 확정 후
그 위치에서 데이터를 모아야 한다(권장: 1.075 m + 아래 15도, 근거는
close-person 메모리와 URDF 주석).

추가로 `scripts/vica_costmap_probe.py`(§2-2 측정 도구)도 노트북에서 만들 수 있다.

---

## 6. 미리 알아야 할 함정

| | 내용 |
| --- | --- |
| `.engine` 이식 불가 | 젯슨에서 변환해야 한다 |
| **`pip install torchvision` 맨몸 금지** | pip 이 의존성으로 PyPI 일반 torch 를 끌어와 갈아끼우고 그 순간 `cuda: True` 가 죽는다. 시험 설치조차 반드시 `--no-deps` 로 한다. 기성 휠은 전부 ABI 불일치라 **소스 빌드가 유일한 길**이다 (§4-1 ③) |
| `ultralytics` 설치 | `setuptools` 를 올려 `colcon` 을 깬다. `--no-deps` + venv 로 막았다 (§4-1 ③에 실제 명령) |
| 컨테이너 재생성 | 시스템 패키지 설치가 날아간다. `docker commit` 으로 굳힌다. **venv·소스를 마운트된 `/workspaces/isaac_ros-dev` 아래 두면 이 함정 자체가 사라진다** — 2026-08-24 재생성에서 `yolo_env` 가 그대로 살아남았다 |
| 컨테이너 안 심볼릭 링크 | 호스트 경로로 만들면 컨테이너 안에서 끊긴다. **컨테이너 기준 경로**로 만든다 (§4-1 ①) |
| `PolygonSlow` 1.10 m | 접근 거리 1.1 m 와 겹쳐 마지막 구간이 40 % 감속된다. **의도된 동작이다** |
| collision_monitor 입력 | `["scan"]` 뿐이라 라이다만 본다. 흰지팡이는 안 잡힌다 |
| goal 갱신 | `NavigateToPose` 는 preempt 되지만 **BT 가 재시작**된다. 0.5 m 임계를 지킬 것 |
| 회차 간 편차 | 같은 설정으로 정체 81.5 s vs 43.1 s (`run13`/`run15`). **편차보다 작은 차이는 판정 불가** |

---

## 7. 참조

| 문서 | 내용 |
| --- | --- |
| `devlog/2026-08-23-사람접근-구현설계.md` | 설계 정본. 계약·상태기계·값·근거 |
| `devlog/2026-08-12-능동접근-설계-TONY0043.md` | 선행 설계 13건 (일부 값은 옛 footprint 기준) |
| `devlog/2026-08-15-people-mode-와-planner-교착.md` | CPU 병목 확정, R-1~R-4 자원 확보 |
| `devlog/2026-08-12-yolo-비전도입-검토와-동적장애물-정지.md` | nvblox 세 모드 소스 분석 |
| `docs/nav2_backlog.md` | **§9 하지 말 것** — 설정 바꾸기 전에 반드시 |
| `vica_ros2_ws/src/vica_nvblox_bringup/README.md` | 컨테이너·호스트 분리 구조, 동기화 절차 |
