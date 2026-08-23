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

기록: `hz = ______`, `width x height = ______`

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

기록: `켠 상태 ______ 칸`, `끈 상태 ______ 칸`

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

기록: `frame 중복 유/무`, `depth frame_id = ______`, `tf2_echo z = ______`

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

## 4. 카메라가 정리되면 — YOLO 도입

### 4-1. 컨테이너 준비 (순서 고정)

```bash
# ① 마운트 정리 — 수동 cp -r 를 없앤다
find ~ -name "run_dev.sh" 2>/dev/null
grep -n -E '\-v |DOCKER_ARGS|VOLUME' <찾은경로>/run_dev.sh | head -20
#    볼륨 추가:  -v /home/msk/VICA-smarthandle/vica_ros2_ws/src:/workspaces/vica_src:ro
#    기존 복사본은 지우지 말고 .bak 으로 옮긴 뒤 심볼릭 링크로 대체
#    install/build 를 지우고 재빌드해야 옛 경로를 안 붙잡는다

# ② 스냅샷 — 되돌릴 지점을 만든다 (1분, 하루를 아낀다)
docker ps
docker commit <컨테이너이름> isaac_ros_backup:before_yolo

# ③ 설치 — 시스템 오염을 막는다
python3 -m venv --system-site-packages ~/yolo_env
source ~/yolo_env/bin/activate
pip install ultralytics

# ④ 즉시 확인 — 깨졌는지 지금 안다
deactivate
colcon build --packages-select vica_nvblox_bringup
python3 -c "import numpy, cv2; print(numpy.__version__, cv2.__version__)"
python3 -c "import torch; print(torch.__version__, torch.cuda.is_available())"
python3 -c "import tensorrt; print(tensorrt.__version__)"
```

`setuptools` 가 올라가 `colcon` 이 깨지면 `pip install "setuptools<80"` 로 되돌린다
(`train_kit/README.md` 에 기록된 함정).

`torch` 가 없거나 `cuda.is_available()` 이 False 면 **TensorRT 직접 추론**으로 가야 하고,
세그멘테이션 후처리를 직접 구현해야 한다. 작업량이 크게 늘어난다.

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

| | 할 일 |
| --- | --- |
| A1 | `PersonDetection.msg` · `RequestApproach.srv` 정의 |
| A2 | goal 계산 (사람 위치 → 1.1 m 물러난 pose) |
| A3 | 판정 로직 (`stable` · `approachable`) |
| A4 | Mission 상태 기계 (IDLE→APPROACHING→AWAITING_USER→RETURNING) |
| A5 | `person_detector_node` 골격 + 웹캠 추론 |

추가로 `scripts/vica_costmap_probe.py`(§2-2 측정 도구)도 노트북에서 만들 수 있다.

---

## 6. 미리 알아야 할 함정

| | 내용 |
| --- | --- |
| `.engine` 이식 불가 | 젯슨에서 변환해야 한다 |
| `ultralytics` 설치 | `setuptools` 를 올려 `colcon` 을 깬다. venv + 스냅샷으로 방어 |
| 컨테이너 재생성 | 시스템 패키지 설치가 날아간다. `docker commit` 으로 굳히거나 스크립트로 남긴다 |
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
