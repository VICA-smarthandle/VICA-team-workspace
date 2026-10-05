# 라이선스 대장 — 모델·라이브러리

2026-08-15 작성 · **2026-09-19 전면 갱신**(음성·앱 스택 추가, Ultralytics 현황 정정,
미선언 패키지 목록 교체). **상업화 판단이 필요할 때 여기부터 본다.**

지금은 **공모전 출품용**이고 상업화는 미정이다(사용자 확인). 그래서 아래 위험 표시는
"지금 막힌다"가 아니라 **"제품으로 팔 때 확인해야 한다"**는 뜻이다.

> **작성자는 변호사가 아니다.** 아래는 공개 문서, 각 패키지의 `package.xml` 선언,
> 설치된 패키지 메타데이터를 읽은 결과다. 실제 출하 전에는 법률 검토를 받는다.

---

## 0. 규칙

- **모델 가중치 파일을 저장소에 커밋하지 않는다.** 설치 스크립트로 받게 한다.
  재배포로 해석될 여지를 없애는 가장 싼 방법이다
- 새 모델·라이브러리를 넣을 때 **이 문서에 한 줄 추가한다**
- 라이선스를 확인하지 못한 것은 **`[미확인]`으로 남긴다.** 비워 두지 않는다
- **"검토 중"으로 적은 것이 코드에 들어왔는지 주기적으로 확인한다.** 2026-08-15 판이
  Ultralytics 를 "검토 중인 선택지"로 적어 둔 사이에 실제 도입됐고, 문서가 한 달 넘게
  현실과 어긋나 있었다(3.2절)

---

## 1. 한 장 요약

| 층 | 라이선스 | 대당 비용 | 쟁점 |
| --- | --- | --- | --- |
| 주행 스택 (`vica_ros2_ws`) | Apache-2.0 / BSD / MIT | 0원 | 없음 |
| 음성 스택 (`vica-voice-llm`) | MIT / Apache-2.0 | 0원 | 모델 가중치 일부 `[미확인]` |
| 관리자 앱 (`VICA_Supervisor`) | BSD-3 / MIT | 0원 | 없음 |
| 인지 모델 — NVIDIA PeopleSemSegNet | 상업적 사용 명시 | 0원 | 재배포 조건 `[미확인]` |
| **인지 모델 — Ultralytics YOLO** | **AGPL-3.0** | 고정비 | ⚠ **대응 필요** (3.2절) |
| 클라우드 LLM | 서비스 약관 | 운영비 | 대수 증가 시 단가 미실측 (5절) |

**로열티(팔 때마다 떼어 주는 돈)는 Ultralytics 한 곳을 빼면 없다.** 그 한 곳도
대수와 무관한 고정비이고, 대체 경로가 있다(4절).

---

## 2. 코드·라이브러리

### 2.1 주행 (`vica_ros2_ws`)

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
| `rplidar_ros` | BSD | 가능 |
| `ydlidar_ros2_driver` | MIT | 가능 |

**주행 스택 전체가 Apache-2.0 / BSD / MIT다.** 소스 공개 의무가 없고 상업적 사용에
제약이 없다. 여기는 걱정할 것이 없다.

우리 패키지는 `vica_description` 등 일부 MIT, 나머지는 Apache-2.0이다. 선언이 빠진
것은 6절.

### 2.2 음성 (`vica-voice-llm`) — 2026-09-19 추가

2026-08-15 판이 "담당 밖이라 조사하지 않았다"고 남겨 둔 칸이다. 설치된 패키지
메타데이터(`pip show`)를 직접 읽었다.

| 패키지 | 역할 | 라이선스 |
| --- | --- | --- |
| `faster-whisper` | STT | MIT |
| `ctranslate2` | STT 추론 엔진 | MIT |
| `supertonic` | TTS (Supertone) | MIT |
| `openwakeword` | 웨이크워드 | Apache-2.0 |
| `langchain` · `langgraph` | LLM 배선 | MIT |
| `ollama` (클라이언트) | LLM 호출 | MIT |
| `onnxruntime` | 추론 | MIT |
| `sounddevice` · `soundfile` | 오디오 입출력 | MIT |

**음성 스택 코드도 전부 MIT / Apache-2.0이다.** 쟁점은 코드가 아니라 가중치이며
3.3절에 따로 적는다.

### 2.3 관리자 앱 (`VICA_Supervisor`) — 2026-09-19 추가

Flutter·Dart SDK 가 BSD-3-Clause이고, `pubspec.yaml` 의 의존 패키지 6개
(`provider`, `web_socket_channel`, `shared_preferences`, `uuid`, `intl`,
`another_telephony`)는 모두 BSD·MIT 계열이다. 쟁점 없음.

---

## 3. 모델(가중치) — 여기가 실제 쟁점이다

코드와 모델은 라이선스가 **따로** 붙는다. `isaac_ros_unet`이 Apache-2.0이어도 그
위에서 돌리는 모델은 별개다.

### 3.1 PeopleSemSegNet shuffleseg — 사용 중

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

### 3.2 Ultralytics YOLO — ⚠ 사용 중 (2026-09-19 정정)

**2026-08-15 판은 이것을 "검토 중인 선택지"로 적었다. 실제로는 도입되어 돌고 있다.**

```
사용처   vica_ros2_ws/src/vica_perception/vica_perception/person_detector_node.py:321
         from ultralytics import YOLO
엔진     VICA_YOLO_ENGINE (기본값 .../models/v6-blur-640/weights/best.engine)
역할     사람 인지 → /vica/person_detection → 미션 매니저 접근 요청
실행 위치 isaac_ros-dev 컨테이너 (런치 파일이 아니라 별도 실행)
```

가중치도 우리가 **Ultralytics 로 학습한 자체 모델**이라 프레임워크와 같은 조건이
따라붙는다고 보는 것이 안전하다.

**AGPL-3.0 이 왜 위험한가**

**"배포하면 전체 소스를 공개하라"**는 조건이다. 로봇에 담아 파는 것도 배포에
해당하고, 네트워크로 서비스만 해도 걸리는 조항이 있다.

- 회피 ①: Ultralytics 상용 라이선스 구매(유료). 공개가는 없고 협의이며,
  공개된 사례는 **연 $5,000 수준**이다. 대수와 무관한 고정비라 500대로 나누면
  대당 연 1.4만 원이다
- 회피 ②: 가중치만 쓰고 코드는 안 쓴다 → **논쟁적.** Ultralytics 는 가중치도 AGPL
  이라는 입장이라 안전하지 않다
- 회피 ③: Apache-2.0 대체 모델로 전환 → 0원. 4절
- **공모전 단계에서는 문제되지 않을 가능성이 크다.** 제3자 배포가 아니면 의무가
  발동하지 않는 게 보통이고, 공모전은 공개가 자연스럽다

출처: [Ultralytics License](https://www.ultralytics.com/license) ·
[Enterprise 가격 논의](https://github.com/orgs/ultralytics/discussions/7440)

### 3.3 음성 모델 가중치 — 2026-09-19 추가

| 모델 | 용도 | 출처 | 라이선스 |
| --- | --- | --- | --- |
| Whisper `medium` (CTranslate2 변환본) | STT 기본값 (`VICA_STT_MODEL`) | Hugging Face | MIT (원본 OpenAI Whisper MIT) |
| `supertonic-3` | TTS | HF `Supertone/supertonic-3` (리비전 고정) | **`[미확인]`** — 패키지는 MIT지만 가중치 약관을 확인하지 못했다 |
| `vica_bikaya_v1.onnx` · `vica_modelb_v2.onnx` | 웨이크워드 | **자체 학습** (`vica-voice-llm/models/`) | 우리 자산 |
| Gemma 계열 (`gemma4:cloud` / `gemma4:e2b`) | LLM | Ollama | [Gemma Terms of Use](https://ai.google.dev/gemma/terms) — 상업적 사용 가능하나 **금지사용정책이 하위 사용자까지 따라붙고** 구글이 약관을 일방 변경할 수 있다 |

**확인할 것 둘**

1. `Supertone/supertonic-3` 저장소의 모델 카드에서 가중치 약관을 읽는다
2. openWakeWord 로 학습한 자체 모델은 우리 것이지만, 학습 파이프라인이 쓰는
   특징 추출기(멜스펙트로그램·임베딩 모델)의 출처 약관은 확인하지 않았다 `[미확인]`

### 3.4 nvblox 퀵스타트 예제 bag

```
isaac_ros_assets/isaac_ros_nvblox/quickstart/rosbag2_2024_04_04-15_44_33_0.db3   640 MB
```

NVIDIA 제공 시험용 데이터. **시험에만 쓰고 제품에 담지 않는다.** `[미확인]`이지만
배포하지 않으므로 쟁점이 아니다.

---

## 4. 대안 — Ultralytics 를 벗어나는 길

| | 라이선스 | 상업화 | 비고 |
| --- | --- | --- | --- |
| **RT-DETR** (`isaac_ros_rtdetr`) | Apache-2.0 | 안전 | 출력이 bbox 라 마스크 변환 필요 |
| YOLOX | Apache-2.0 | 안전 | Isaac ROS 지원은 없다 |

**설계상 갈아 끼울 수 있게 둔다.** 마스크 만드는 쪽을 "입력=이미지, 출력=
`camera_0/mask/image`"로 고정하면 nvblox 배선은 손대지 않고 공급자만 바꿀 수 있다.
사람 인지 쪽도 `/vica/person_detection` 메시지 형식을 유지하면 검출기만 교체된다.

전환 판단 시점은 **제3자에게 로봇을 인도하기 전**이다. 그때까지는 현행 유지로 둔다.

---

## 5. 유료 항목 — 라이선스가 아니라 운영비

로열티와 구분한다. 아래는 **쓴 만큼 내는 서비스 요금**이다.

| 항목 | 현재 설정 | 비용 | 성격 |
| --- | --- | --- | --- |
| LLM (목적지 해석) | Ollama Cloud `gemma4:cloud` | Free / Pro $20·월 / Max $100·월 | 계정 구독 |
| LLM 폴백 | 로컬 `gemma4:e2b` | 0원 | 온디바이스 |
| LLM (선택) | OpenAI `VICA_LLM_PROVIDER=openai` | 종량 | 사용량 비례 |
| STT | faster-whisper, 온디바이스 | 0원 | — |
| TTS | supertonic, 온디바이스 | 0원 | — |
| CLOVA Voice | 고정 멘트를 미리 wav 로 구워 캐시 | 사실상 1회성 | 운영 중 호출 0 |

**STT·TTS 가 로봇 안에서 돌아 대화마다 나가는 통신비가 0이다.** 망이 끊겨도 말을
알아듣고 말한다.

**주의 두 가지**

- IR 원가표에서 "클라우드 + LLM·STT·TTS API 연 24만 원"으로 잡은 항목은 실제로는
  **LLM 요금뿐**이다. Ollama Cloud Pro 기준이면 연 33.6만 원이라 24만은 낙관적이다
- Ollama Cloud 는 **계정 구독**이라 로봇 대수에 비례하지 않는다. 대수가 늘면
  요금제 상향이나 종량제로 옮겨야 하는데 **대당 단가는 실측이 없다** `[미확인]`

---

## 6. 우리 패키지 — 선언이 빠진 것 2개

`package.xml` 을 다시 훑었다. 2026-08-15 판이 지적한 `vica_nav2` ·
`vica_nvblox_bringup` · `vica_sensor_adapters` 는 **모두 Apache-2.0 으로 채워졌다.**
지금 비어 있는 것은 다른 둘이다.

```
mdrobot_can_control    TODO: License declaration
encoder_feedback       TODO: License declaration
```

**공모전 제출물에 라이선스 미선언 패키지가 섞여 있으면 곤란하다.** 나머지와 같은
Apache-2.0 으로 맞추는 것을 권한다 — 별도 과제로 둔다.

---

## 7. 상업화 전 확인 목록

- [ ] **Ultralytics 대응 결정** — 상용 라이선스 구매 vs RT-DETR 전환 (3.2절·4절)
- [ ] PeopleSemSegNet 재배포 조건 — NVIDIA 문의, 또는 "설치 시 내려받기" 유지
- [ ] `Supertone/supertonic-3` 가중치 약관 확인 (3.3절)
- [ ] openWakeWord 학습 파이프라인의 특징 추출기 출처 약관 확인 (3.3절)
- [ ] Gemma 금지사용정책을 하위 사용자(시설)에게 전달할 방법 마련
- [ ] 클라우드 LLM 의 **대당** 단가 실측 (5절)
- [ ] `mdrobot_can_control` · `encoder_feedback` 라이선스 선언 (6절)
- [ ] 사용 중인 모든 모델이 이 문서에 있는가
- [ ] 지도·목적지 등 현장에서 수집한 데이터의 취급 방침
