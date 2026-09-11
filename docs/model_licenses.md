# 라이선스 대장 — 모델·라이브러리

2026-08-15 작성. **상업화 판단이 필요할 때 여기부터 본다.**

지금은 **공모전 출품용**이고 상업화는 미정이다(사용자 확인). 그래서 아래 위험 표시는
"지금 막힌다"가 아니라 **"제품으로 팔 때 확인해야 한다"**는 뜻이다.

> **작성자는 변호사가 아니다.** 아래는 공개 문서와 각 패키지의 `package.xml`
> 선언을 읽은 결과다. 실제 출하 전에는 법률 검토를 받는다.

---

## 0. 규칙

- **모델 가중치 파일을 저장소에 커밋하지 않는다.** 설치 스크립트로 받게 한다.
  재배포로 해석될 여지를 없애는 가장 싼 방법이다
- 새 모델·라이브러리를 넣을 때 **이 문서에 한 줄 추가한다**
- 라이선스를 확인하지 못한 것은 **`[미확인]`으로 남긴다.** 비워 두지 않는다

---

## 1. 코드·라이브러리 — 전부 확인 완료

각 패키지의 `package.xml` `<license>` 선언을 직접 읽었다.

| 패키지 | 라이선스 | 상업적 사용 |
| --- | --- | --- |
| `nav2_bringup` | Apache-2.0 | 가능 |
| `nav2_costmap_2d` | BSD-3-Clause | 가능 |
| `cartographer_ros` | Apache-2.0 | 가능 |
| `robot_localization` | Apache-2.0 | 가능 |
| `nvblox_ros` · `nvblox_nav2` | Apache-2.0 | 가능 |
| `isaac_ros_unet` | Apache-2.0 | 가능 |
| `isaac_ros_tensor_rt` | Apache-2.0 | 가능 |
| `isaac_ros_dnn_image_encoder` | Apache-2.0 | 가능 |
| `realsense2_camera` | Apache-2.0 | 가능 |

**주행 스택 전체가 Apache-2.0 / BSD다.** 소스 공개 의무가 없고 상업적 사용에 제약이
없다. 여기는 걱정할 것이 없다.

---

## 2. 모델(가중치) — 여기가 실제 쟁점이다

코드와 모델은 라이선스가 **따로** 붙는다. `isaac_ros_unet`이 Apache-2.0이어도 그
위에서 돌리는 모델은 별개다.

### 2.1 PeopleSemSegNet shuffleseg — 현재 사용

```
자산명   optimized_deployable_shuffleseg_unet_amr_v1.0
출처     NVIDIA NGC
경로     ~/workspaces/isaac_ros-dev/isaac_ros_assets/models/peoplesemsegnet/
설치     ros2 run isaac_ros_peoplesemseg_models_install install_peoplesemsegnet_shuffleseg.sh
동의일   2026-08-15 (ISAAC_ROS_ACCEPT_EULA=1)
```

**모델 카드에 적힌 것**

| | |
| --- | --- |
| 상업적 사용 | **"ready for commercial use"** 명시 |
| 실행 제약 | TAO Toolkit · DeepStream SDK · **TensorRT** 로만 |
| 하드웨어 | **NVIDIA 하드웨어 필요** |

**VICA 에서는 두 제약이 제약이 아니다** — TensorRT 로 쓰고 Jetson Orin NX 에서 돈다.
Jetson 을 계속 쓰는 한 락인이 걸리지 않는다.

**`[미확인]` — 재배포 조건.** 모델 카드에 **약관 본문도 링크도 없다.** 설치
스크립트가 가리키는 URL 이 그 페이지인데 라이선스 항목이 비어 있다. NVIDIA 쪽
문서화 공백이다.

- 후보 약관: [NVIDIA Open Model License](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/)
  (상업적 사용·파생모델·출력물 소유 모두 허용, 재배포 시 약관 사본과 귀속 표시 필요).
  **다만 이 모델에 적용되는지 확인하지 못했다**
- [TAO FAQ](https://docs.nvidia.com/tao/tao-toolkit/latest/text/faqs.html) 는 "모델
  라이선스는 Model EULA 가 규정"이라고만 한다
- **제품 출하 전 NVIDIA 에 직접 문의한다.** 또는 모델을 제품에 담지 않고 설치 시
  내려받는 지금 방식을 유지하면 재배포 자체가 발생하지 않는다

출처: [PeopleSemSeg AMR 모델 카드](https://catalog.ngc.nvidia.com/orgs/nvidia/teams/isaac/models/optimized-peoplesemseg-amr)

### 2.2 nvblox 퀵스타트 예제 bag

```
isaac_ros_assets/isaac_ros_nvblox/quickstart/rosbag2_2024_04_04-15_44_33_0.db3   640 MB
```

NVIDIA 제공 시험용 데이터. **시험에만 쓰고 제품에 담지 않는다.** `[미확인]`이지만
배포하지 않으므로 쟁점이 아니다.

---

## 3. 검토 중인 선택지 — 도입 전에 여기를 본다

| | 라이선스 | 상업화 | 비고 |
| --- | --- | --- | --- |
| **Ultralytics YOLOv8/v11-seg** | **AGPL-3.0** | ⚠ **위험** | 아래 |
| **RT-DETR** (`isaac_ros_rtdetr`) | Apache-2.0 | 안전 | 출력이 bbox 라 마스크 변환 필요 |
| YOLOX | Apache-2.0 | 안전 | Isaac ROS 지원은 없다 |

### AGPL-3.0 이 왜 위험한가

**"배포하면 전체 소스를 공개하라"**는 조건이다. 로봇에 담아 파는 것도 배포에
해당하고, 네트워크로 서비스만 해도 걸리는 조항이 있다.

- 회피 ①: Ultralytics 상용 라이선스 구매(유료)
- 회피 ②: 가중치만 쓰고 코드는 안 쓴다 → **논쟁적.** Ultralytics 는 가중치도 AGPL
  이라는 입장이라 안전하지 않다
- **공모전 단계에서는 문제되지 않을 가능성이 크다.** 제3자 배포가 아니면 의무가
  발동하지 않는 게 보통이고, 공모전은 공개가 자연스럽다

### 그래서 순서

```
1. PeopleSemSegNet   지금. 만들 게 없고 상업적 사용이 명시돼 있다
2. RT-DETR           확장이 필요해지면. Apache-2.0 + torch 불필요
3. YOLOv8-seg        경계 정확도가 부족하다고 판명되면. 그때 라이선스 재판단
```

**설계상 갈아 끼울 수 있게 둔다.** 마스크 만드는 쪽을 "입력=이미지, 출력=
`camera_0/mask/image`"로 고정하면 nvblox 배선은 손대지 않고 공급자만 바꿀 수 있다.

---

## 4. 우리 패키지 — 선언이 빠진 것 3개

`package.xml` 을 훑었더니 셋이 비어 있다.

```
vica_nav2              TODO: License declaration
vica_nvblox_bringup    TODO: License declaration
vica_sensor_adapters   TODO: License declaration
```

나머지는 Apache-2.0(`vica_description` 만 MIT)이다. **공모전 제출물에 라이선스
미선언 패키지가 섞여 있으면 곤란하다.** 나머지와 같은 Apache-2.0 으로 맞추는 것을
권한다 — 별도 과제로 둔다.

---

## 5. 상업화 전 확인 목록

- [ ] PeopleSemSegNet 재배포 조건 — NVIDIA 문의, 또는 "설치 시 내려받기" 유지
- [ ] 사용 중인 모든 모델이 이 문서에 있는가
- [ ] `vica_nav2` · `vica_nvblox_bringup` · `vica_sensor_adapters` 라이선스 선언
- [ ] STT/TTS/LLM 모델 라이선스 — `vica-voice-llm` 저장소. **이 세션 담당 밖이라
      조사하지 않았다.** 담당자가 이 문서에 추가할 것
- [ ] 지도·목적지 등 현장에서 수집한 데이터의 취급 방침
