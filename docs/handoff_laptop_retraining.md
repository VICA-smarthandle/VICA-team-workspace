# 인수인계 — 로봇 시점 재학습 (노트북 작업 지침서)

작성일: 2026-08-25 (젯슨 세션)
대상: **노트북에서 이 작업을 이어받는 Claude / 작업자**
목표: 로봇 카메라 시점 데이터로 YOLO 세그멘테이션 모델을 fine-tune 하여
**근접(1.2 m 안) 검출률을 끌어올린다.** 최종 산출물은 `best.pt` 하나다.

---

## 0. 왜 하는가 — 30초 배경

VICA(실내 안내 로봇)가 **흰지팡이를 든 시각장애인**을 감지해 다가가는 기능은
실기 검증까지 끝났다. 남은 병목은 검출률이다:

- 현재 모델 `v6-blur-640` (yolo11s-seg): 학습 지표는 mAP50 0.98로 훌륭하지만
  **로봇 카메라(지면 1.05 m) 시점에서는** 정지 인물 기준 프레임 검출 45~48 %,
  놓침의 절반이 conf 0 (문턱 조정 무효 = 도메인 격차)
- 특히 **0.8 m 안 근접에서 4~12 %** — 지팡이가 화면 밖으로 나가는 구간
- 해법: 로봇 시점 데이터를 학습에 섞는다. 그 데이터가 이 지침의 대상이다

## 1. 받은 데이터 — `robot_view_dataset.zip` (107 MB)

```
robot_view_dataset/
├─ data.yaml              # nc=1, names=['visually-impaired']
├─ CAPTURE_INFO.md        # 촬영 조건 (카메라 지면 1.05 m 수평 · 4인 교대 · 2 Hz)
└─ train/
   ├─ images/  1,336장   # person1~4 접두어, 640x480
   └─ labels/    799개   # YOLO-seg 폴리곤, class 0
```

- **라벨 있는 799장** = 현재 모델(conf 0.10, 후하게)의 **사전 라벨** — 보정 전제.
  틀린 라벨 삭제가 놓친 라벨 그리기보다 싸도록 일부러 낮은 conf 로 그렸다
- **라벨 없는 537장** = 현재 모델의 **미검출 장면 + 음성 예제** 혼합.
  ★ 이 중 "지팡이 든 사람인데 못 잡은 것"이 이번 재학습의 알짜다
- 각 회차 구성: 근접 0.5~1.5 m(40 s) → 2~4 m 정지(60 s) → 5 m 왕복(40 s)
  → **지팡이 없이(30 s)** → 퇴장(10 s)

## 2. 작업 순서

### ① Roboflow 업로드·보정

기존 `visually_impaired` 프로젝트(Instance Segmentation, 클래스 1개)에 ZIP 드래그.
- 799장은 폴리곤이 얹힌 채 들어온다 → **틀린 것 삭제 위주로 훑기**
- 537장 분류:

| 장면 | 처리 |
| --- | --- |
| 지팡이 든 사람 (못 잡힌 것) | **폴리곤 라벨** ← 핵심 노동 |
| 지팡이 없는 사람 | **Mark Null** (negative — 일반 보행자 무시 학습) |
| 빈 배경 | **Mark Null** |

- **함정**: Unannotated 로 방치하면 버전 생성 때 **버려진다**. negative 는 반드시
  Mark Null 로 확정해야 빈 라벨로 포함된다 (Ultralytics 는 빈 라벨 = 배경 예제)
- 전부 볼 필요 없다. 연속 프레임은 비슷하니 건너뛰고, **미검출 위주 200~300장**만
  보정해도 1차 효과가 난다. negative 비율은 전체의 10~20 %면 충분

### ② 데이터셋 합치기·버전 생성

기존 학습 데이터(`visually_impaired-4` 계열)와 **합쳐서** 새 버전을 만든다 —
로봇 시점만으로 학습하면 기존 성능을 잃는다(catastrophic forgetting).
train/valid 분할 시 **로봇 시점 이미지가 valid 에도 일부 들어가게** 할 것 —
그래야 도메인 개선이 지표로 보인다.

### ③ 학습 — v6 레시피 그대로

기존 성공 레시피 (`runs/v6-blur-640/args.yaml` 참조):

```
task=segment  model=yolo11s-seg.pt  imgsz=640  epochs=80  batch=16
(+ v6 의 blur 증강 설정 그대로 — args.yaml 에서 복사)
```

- 베이스는 `yolo11s-seg.pt` (v6 와 동일 조건 재학습). 시간을 아끼려면
  `runs/v6-blur-640/weights/best.pt` 에서 이어 학습(fine-tune)해도 되나,
  그 경우 lr 을 낮추고(예: lr0 0.001) epochs 30~40 으로
- 학습 산출물 폴더 이름 제안: `v7-robotview-640`

### ④ 판정 기준

- mAP 는 참고일 뿐이다. **진짜 판정은 젯슨 실측** — 기준선:
  정지 2.1 m 프레임 검출 45~48 % / 근접(<0.8 m) 4~12 % / conf-0 프레임 50 %.
  이 숫자들이 오르는지가 성패다 (재측정은 젯슨 쪽 도구·담당이 이미 있음)
- valid 의 로봇 시점 부분 지표가 별도로 보이면 기록해 둘 것

### ⑤ 인계물 — 이것만 돌려주면 된다

```bash
# best.pt 를 젯슨으로 (같은 Wi-Fi):
scp runs/v7-robotview-640/weights/best.pt \
    ji_w@192.168.50.244:/home/ji_w/workspaces/isaac_ros-dev/models/v7-robotview/
# (Tailscale 이면 ji_w@100.110.180.95)
```

가능하면 `args.yaml` 과 `results.csv` 도 함께 — 기록용.

## 3. 하지 말 것 / 함정

- **`.engine` 을 노트북에서 만들지 말 것.** TensorRT 엔진은 만든 기기에 묶인다 —
  젯슨에서 로드조차 안 된다. 변환은 젯슨 담당이 한다 (검증된 파이프라인 있음)
- 클래스를 늘리거나 이름을 바꾸지 말 것 — `visually-impaired` 단일 클래스(id 0)
  가 계약이다. 로봇 쪽 노드가 이 전제로 돈다
- 지팡이 없는 사람을 라벨하지 말 것 — "일반 보행자 무시"가 이 모델의 정체성이다
- 젯슨 쪽 저장소·코드는 건드릴 필요 없다. 이 작업의 산출물은 `best.pt` 하나다

## 4. 참조 (모두 GitHub 에 push 됨)

- 전체 맥락: `devlog/2026-08-25-사람접근-완주와-음성인수인계.md`
- 젯슨 환경·실측: `docs/handoff_jetson_camera_and_yolo.md`
- 기존 학습 위치(노트북): `/home/msk/visuallyimpaired-dataset/runs/v6-blur-640/`
  (args.yaml = 레시피 정본, results.csv = 기준 성능)
