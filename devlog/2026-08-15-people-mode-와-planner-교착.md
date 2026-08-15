# nvblox human 모드 도입과 "30초 대기"의 진짜 원인 — 2026-08-15

브랜치 `vica_ros2_ws` `feat/nvblox-people-mode` · bag `run13_people_mode` 보존

---

## 0. 오늘의 결론 — 가정이 틀렸다

**"사람이 nvblox 에 남아 30초를 기다린다"가 아니었다.**

`Starting point in lethal space` 를 내는 것은 **planner** 이고, planner 는
**global costmap** 을 본다. 그리고 **global costmap 에는 nvblox 가 없다**
(`plugins: ["static_layer", "obstacle_layer", "inflation_layer"]`).

즉 그동안 nvblox 를 붙잡고 씨름한 정체의 상당 부분은 nvblox 와 무관했다.

human 모드 자체는 **설계대로 작동한다**(§1). 다만 그것이 고치는 문제와 실제로
주행을 막던 문제가 **서로 다른 것**이었다(§3).

---

## 1. human 모드는 작동한다

`mapping_type: human_with_static_tsdf` + `use_segmentation: true`.
마스크 공급자는 PeopleSemSegNet shuffleseg(TensorRT fp16, 2.4 MB).

### 1.1 마스크 품질 (실측)

```
사람 없음   597장   전경 0.00 %              오검출 0건
정지 상태   596장   검출 100 %  끊김 없음    전경 평균 2.83 %
접근 주행   838장   거리별 아래 표
```

| 거리 | 표본 | 검출률 | 마스크 아래끝 |
| --- | --- | --- | --- |
| 0.30 ~ 0.45 m | 16 | **19 %** | 539 / 544 |
| 0.45 ~ 0.60 m | 234 | **92 %** | 539 |
| 0.60 ~ 0.80 m | 45 | 67 % | 462 |
| 1.00 ~ 1.30 m | 43 | 74 % | 384 |
| 1.70 ~ 2.40 m | 81 | **100 %** | 328 |

**다리만 보여도 잡는다.** 0.45~0.60 m 에서 92 % 다. AMR 용으로 학습된 모델이라
로봇 눈높이의 잘린 사람을 아는 것으로 보인다. **0.45 m 미만이 한계**다 —
무릎 아래만 들어오면 판정 근거가 사라진다.

끊김은 **최대 0.6초**. 앞서 "3초 끊김"이라 적었던 것은 1초 간격 표본만 보고
판단한 오류였다.

카메라 기하가 이 한계를 만든다(세로 시야 64.6도, 높이 0.382 m).

```
0.36 m   0.16 ~ 0.61 m 높이만 들어온다   무릎 아래
0.50 m   0.07 ~ 0.70 m                  다리
1.00 m   0    ~ 1.01 m                  허리
3.00 m   0    ~ 2.28 m                  머리까지
```

### 1.2 static 오염 0칸

사람이 서 있던 **그 자리의 셀만** 추적했다.

```
사람이 잡힌 구간            +8.5s ~ +17.7s   (9.2초)
dynamic 가까운칸 최대       326
사람 때문에 static 에 새로 생긴 셀    0 칸
dynamic 에서 사라지는 데    0.11초
```

**정적 지도에 한 칸도 안 들어갔다.** 30.6초 감쇠를 기다릴 것 자체가 없다.

> **[정정]** 첫 측정에서 "static 이 +307칸 늘었다"고 적었는데 오류였다. 총 칸
> 수를 세는 바람에 **사람이 비키며 가려졌던 뒤쪽이 새로 보이는 것**이 섞였다.
> 지표를 "사람이 서 있던 자리"로 바꾸니 0칸이다.

---

## 2. 그런데 주행은 안 좋아졌다

목적지가 살아 있던 구간만 골라 비교했다(대기 시간 제외).

| | run12 (도입 전) | run13 (human 모드) |
| --- | --- | --- |
| 주행 시간 | 250 초 | 384 초 |
| 정체(3초 이상) | 3개 · 56초 | 3개 · 79초 |
| **정체 비율** | **22 %** | **21 %** |
| **최장 정체** | **28.2 초** | **33.1 초** |
| No valid trajectories | 226 | 579 |
| lethal space | 25 | 18 |
| Goal failed | 0 | 0 |

**정체 비율이 그대로다.** 책상에서 0.11초였는데 주행에서 안 줄었다.

### run13 유효성

- 오도메트리 건전. `amcl_pose` 616장 총이동 58.7 m 한 스텝 최대 0.19 m,
  `/odom` 20523장 최대 0.06 m. **발산 없음**
- `vica_drive_compare.py` 가 "무효 의심(이동거리 155배)"으로 표시하지만
  **오탐**이다. 로봇이 출발점 근처로 돌아오면 그 비율은 무조건 커진다
- teleop 이 켜진 채였다(사용자 확인). `/cmd_vel_req` 에 끼어든 0 명령은 3회뿐이라
  오염은 미미하다
- 세그멘테이션·nvblox 는 **주행 내내 살아 있었다.** 컨테이너는 주행 종료
  1분 53초 뒤에 내려갔다(ExitCode 129, OOMKilled false)

---

## 3. 진짜 원인 — planner 가 자기 자리를 거부한다

33.1초 정체(+454.8 ~ +487.9s)를 팠다.

### 3.1 로봇 주변이 INSCRIBED 였다

```
local costmap, 로봇 반경 0.3 m 안 최댓값
  +451.9s   99      253이상 2805칸
  +456.7s   99             3085칸   최대
  +475.9s   99             2001칸
  +483.1s   99             1079칸
  +485.5s    0              818칸   갑자기 풀림
  +487.9s    0                      정체 끝
```

99 는 OccupancyGrid 로 옮긴 **253 = INSCRIBED** 다. planner 는 253 이상이면
**footprint 모양을 보지도 않고 거부**한다.

### 3.2 그런데 그건 nvblox 가 아니다

```
local_costmap    voxel_layer(라이다) + nvblox_layer + inflation
global_costmap   static_layer + obstacle_layer(라이다) + inflation   <- nvblox 없음
```

`plugins` 에 없으면 로드되지 않는다. **planner 는 global 을 보고, 거기엔 nvblox 가
들어가지 않는다.**

global 을 직접 재니 33초 내내 로봇 0.3 m 안이 99~100 이었고, 로봇이 움직인 뒤
(+490.4s) 63 으로 떨어졌다.

### 3.3 로봇이 스스로 만든다

같은 **지점**(x=1.05, y=8.15)을 시간대별로 봤다.

```
로봇이 없을 때        65      통과 가능
로봇이 거기 있을 때   99~100  planner 거부
로봇이 떠난 뒤        65      다시 통과 가능
```

**로봇이 그 자리에 있을 때만 막힌다.** 원래 비용 65짜리 좁은 자리인데, 로봇이
들어가면 라이다가 벽을 더 가까이 보고 `obstacle_layer` 가 그것을 찍어 inflation 이
로봇 자리를 덮는다.

```
좁은 자리 진입 → 라이다가 벽을 가까이 봄 → global inflation 이 로봇을 덮음
   → planner "Starting point in lethal space" → 경로 없음 → 정지
   → 벗어나려면 움직여야 하는데 경로가 없다              <- 교착
```

**8/15 오전에 "costmap 최댓값이 100인데 왜 253이라 하나"로 남겨 둔 수수께끼가
여기서 풀린다.** 그때 본 것은 **local** 이었고 planner 는 **global** 을 본다.

---

## 4. 배선과 함정

### 4.1 slice 토픽은 안 바꾼다

`human` 모드에서는 마스크가 사람을 전경 mapper 로 보내므로 `static_map_slice` 에
사람이 애초에 안 들어간다. 나눌 필요가 없다.

`combined_map_slice` 로 옮기는 안은 **택하지 않았다** — local 만 사람을 보고
global 은 못 봐서 planner 가 사람을 뚫고 경로를 내고 DWB 가 거부하는 형태로 굳는다
(`test_both_costmaps_use_the_same_slice` 가 막는 결함이다).

### 4.2 [함정] 컬러도 리사이즈된 것을 물려야 한다

원본 컬러(640x480)를 물리면 nvblox 가 4초 만에 SIGABRT 로 죽는다.

```
image_masker.cu:258  Check failed:
  (input.rows() == mask.rows()) && (input.cols() == mask.cols())
호출 경로 NvbloxNode::processColorImage()
```

깊이 경로는 마스크 카메라 모델로 **투영해서** 자르므로 크기가 달라도 되는데,
컬러 경로는 **픽셀 대 픽셀**이라 마스크(960x544)와 같아야 한다.

대가: nvblox 의 컬러가 세그멘테이션에 매인다. 그리고 리사이즈 발행이 원본보다
느리다(4.9 vs 15.9 Hz). 컬러는 시각화용이라 주행에는 영향이 없다.

### 4.3 [함정] nvblox 는 odom 이 생긴 뒤에 띄운다

`odom` 프레임이 없으면 이렇게 반복하며 지도가 0칸으로 남는다.

```
Lookup transform failed for frame camera_link
Tried to clear map outside of radius but couldn't look up frame: camera_link
```

기동 순서: `power → can1 → safety → motor → nav2 → d455 → 세그멘테이션 → nvblox`.
`odom` 은 nav2 launch 가 include 하는 wheel_ekf 에서 나온다.

### 4.4 [함정] use_segmentation 은 깊이 단독 경로를 닫는다

`nvblox_node.cpp:258` 의 if/else 다. 마스크가 안 오면 **깊이도 통합되지 않고**
nvblox 가 조용히 멈춘다. 세그멘테이션 감시가 필요하다.

### 4.5 [함정] vica_nvblox_bringup 은 두 벌이다

```
정본(git)      VICA-smarthandle/vica_ros2_ws/src/vica_nvblox_bringup
실행용 복사본   ~/workspaces/isaac_ros-dev/src/vica_nvblox_bringup   <- nvblox 가 읽는 곳
```

컨테이너가 VICA 저장소를 마운트하지 않는다. **정본만 고치면 반영되지 않는다.**
오늘 이걸 밟아 30분을 썼다. `README.md:23` 에 이미 경고가 있다.

설치본은 `--symlink-install` 로 src 까지 링크가 이어지므로 **복사만 하면 되고
재빌드는 불필요**하다(파일 추가·삭제 시에만 필요).

**후속 과제**: `~/.bashrc` 의 `vica_rs` 함수에 마운트를 추가해 복사 자체를 없앤다.
심볼릭 링크는 안 된다 — 대상 경로가 컨테이너 안에 없다.

---

## 5. 자원

```
세그멘테이션 추론      3.27 ms/장  (trtexec, fp16, 544x960, 304 fps)
카메라 + 세그멘테이션   GPU 35~38 %   최대 67 %
RAM                   5476 -> 7443 MB   (+2 GB)
```

`trtexec` 의 3.27 ms 만 보고 "GPU 10 %" 라 추정했던 것은 **틀렸다** — 리사이즈·
텐서 변환·마스크 디코딩이 빠져 있었다. 파이프라인 전체는 그보다 훨씬 크다.

STT(5 GB 안팎)까지 동시에 띄우면 RAM 이 12 GB 를 넘길 수 있다. **GPU 보다 RAM 이
먼저 걸릴 가능성**이 있다.

---

## 6. 다음 축 — planner 교착

**어느 것도 아직 시험하지 않았다.**

- **PM-1** `global_costmap.inflation_layer.inflation_radius` 0.55 인하.
  좁은 자리에서 99 가 덜 생긴다. 대가는 벽 여유 감소
- **PM-2** global 의 `obstacle_layer`(라이다) 기여 조정. 정적 지도는 그대로 두고
  실시간 라이다만 완화
- **PM-3** planner 의 시작점 판정 완화. `SmacPlannerLattice` 가 253 을 하드 거부
  하는 지점을 확인해야 한다

**PM-1 이 가장 직접적이지만 위험도 크다.** `docs/nav2_backlog.md` 의
inflation 근거(내접 0.277 이 통과 가능성을 정하고 inflation 은 비용만 정한다)와
함께 봐야 한다.

---

## 7. 확정된 것

```
mapping_type       human_with_static_tsdf
use_segmentation   true
마스크             /camera0/segmentation/people_mask
                   /camera0/camera0/segmentation/camera_info_resized
컬러               /camera0/camera0/segmentation/image_resized  (+ camera_info)
slice              두 costmap 모두 static_map_slice  (안 바꾼다)
```

계약 시험 **210 passed / 7 skipped**.

`dev` 는 `static_tsdf` 그대로다. 이 설정은 `feat/nvblox-people-mode` 에만 있다.

---

## 8. 닫힌 것

- **"사람이 nvblox 에 남아 30초"** — human 모드로 static 오염 0칸을 확인했는데도
  주행 정체가 그대로였다. 이 가설로는 정체를 설명 못 한다
- **`combined_map_slice` 분리** — human 모드에서는 필요 없고, 하면 planner 와
  DWB 의 장애물이 갈린다
- **"trtexec 시간 = GPU 점유율"** — 전처리·후처리가 빠진 값이다
