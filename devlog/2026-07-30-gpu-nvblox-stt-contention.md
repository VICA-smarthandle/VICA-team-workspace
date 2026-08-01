# 2026-07-30 GPU 경합(nvblox × STT/TTS) 모델과 health monitor 감지 공백

## 배경

Jetson Orin NX **16GB(UMA)** 에서 GPU를 여러 기능이 시분할한다. "LLM·STT·TTS가 외부
API냐"라는 물음에서 시작해 실제 구성을 코드로 확인했다.

- **LLM 목적지 해석**: 기본 **Ollama Cloud**(`vica-voice-llm/src/langchain_intent_parser.py:27`).
  로컬 GPU 미사용. 선택적 로컬 Ollama 폴백만 열려 있음.
- **STT / TTS**: **온디바이스 로컬**. STT=faster-whisper `cuda/float16`
  (`src/stt.py:56-67`), TTS=supertonic ONNX `CUDAExecutionProvider`(`src/tts.py:20`).
  외부 API 호출 없음.

## GPU 부하 3층

| 층 | 소비자 | 비고 |
|---|---|---|
| 상시 | nvblox(depth 3D 재구성) | Isaac ROS Docker, 매 프레임 |
| 준-상시 | 긴급어 감시 STT (whisper small, hop 0.5s, RMS 게이트) | 조용하면 STT 생략 |
| 버스트 | 대화 STT(medium) / TTS(supertonic) | 발화·응답 시에만 |

- GPU는 단일 자원이라 "동시 사용"은 물리 병렬이 아니라 **시분할 인터리빙**이다.
- 상호배제: 긴급어 STT는 TTS 재생 중 mute됨(`ros_emergency_node.py`↔`/vica/tts_state`).
  단 **대화 STT와 긴급어 STT는 상호배제 안 됨** → 대화 순간 nvblox+medium+small 3중 겹침.
- 두 whisper(medium+small)+supertonic이 상시 VRAM 상주 → 메모리 압박은 idle에도 상존.

## 핵심 발견 — "조용한 저하" 안전 공백

- Nav2 local costmap의 `nvblox_layer`(`vica_ros2_ws/src/vica_nav2/config/nav2_params.yaml:207-212`)에는
  LiDAR `scan`(`:235` `expected_update_rate: 0.2`)과 달리 **`expected_update_rate`/timeout이 없다.**
- → GPU 경합·포화로 `/nvblox_node/static_map_slice`(정상 ~9Hz, `docs/vica_robot_bringup_manual.md`)가
  느려지거나 멈춰도 **costmap이 감지 못 하고 오래된 3D 장애물로 주행**한다.
- `vica_safety`는 slice를 구독하지 않음 → 이 저하는 **E-stop으로 안 걸리고** 회피 실패(충돌)로만 나타난다.
- health-monitoring 초안에도 §8.5에 nvblox slice 항목 없고, §9.1 fault 표엔 GPU **OOM**만 있고
  경합 저하가 없었음 → **설계 공백**.

## 조치 (이번 커밋)

- `guideline/vica_system_health_monitoring_draft.md`
  - §8.5: `nvblox costmap slice age/Hz` 감시 항목 + 공백 설명 추가.
  - §8.7: GPU util 포화, 전력·클럭 모드 고정 여부 감지 항목 추가.
  - §9.1: `nvblox slice stale (GPU 경합/포화)` fault 행 추가(등급 팀 결정).
  - §19: "slice 저하를 STOP/DEGRADED 중 무엇으로, 임계 Hz/age는" 팀 결정 항목(11) 추가.
- `docs/vica_robot_bringup_manual.md`: §5 ⓪ "전력·클럭 모드 고정(MAXN+jetson_clocks)" 단계 +
  §2 읽기전용 점검에 `nvpmodel -q`/`jetson_clocks --show` 추가. (repo에 전력모드 스텝 전무했음)
- `scripts/measure_nvblox_stt_contention.sh`: nvblox+긴급어 STT 동시 부하 A/B 실측(이미 존재).

## 실측 결과 (2026-08-01, Jetson) — **경합 없음. 여유는 발화 중 16 %p**

위 게이트의 "실측" 항목을 수행했다. `tegrastats`는 **sudo 없이 실행된다**.
전력 모드는 `MAXN_SUPER`(최대 성능)로 매뉴얼 ⓪절 권장과 일치했다.

측정 조건: `realsense2_camera_node` + `nvblox_node`(Docker) + 음성 3노드(호스트).
**로봇 스택(Nav2·AMCL)은 미실행**이며 이들은 CPU 위주라 GPU 영향은 작을 것으로 본다.
발화는 마이크 없이 `/vica/tts_request` 토픽으로 유발했다.

| | 무발화 | 연속 발화 | 차이 |
| --- | --- | --- | --- |
| GPU 평균 | 9.8 % | 28.7 % | **+19.0 %p** |
| GPU 중앙 | 1 % | 10 % | |
| **GPU p90** | 45 % | **84 %** | +39 %p |
| GPU 최대 | 87 % | 99 % | |
| 80 % 이상인 시간 | 1.6 % | 14.0 % | |
| **nvblox slice** | 9.37 Hz | **9.45 Hz** | **+0.9 %** |

**slice Hz가 전혀 떨어지지 않았다.** 이 문서가 정한 판정 기준(하락률 >10~20%)에 한참
못 미친다. **현재 부하 조합에서 GPU 경합은 실재하지 않는다.**

GPU와 slice Hz를 같은 시간축에서 1초 구간으로 짝지어 본 결과도 같다.

```text
GPU 낮은 구간 40.6 %  ->  slice 9.57 Hz
GPU 높은 구간 70.5 %  ->  slice 9.43 Hz      차이 -1.5 %
```

### 측정 함정 세 가지 (같은 실수를 반복하지 않기 위해 남긴다)

**① 데스크톱 앱이 GPU를 22 %p 먹는다.** 같은 상시 부하를 세 번 쟀는데 값이 달랐다.

```text
56.0 %  <- firefox + VS Code 켜져 있었음
34.0 %  <- 앱은 닫혔으나 음성 모델 적재가 진행 중
 9.8 %  <- 전부 안정된 뒤. 이 값이 맞다
```

**측정 전에 브라우저·에디터를 반드시 닫는다.**

**② 평균만 보면 안 된다.** 무발화 상태에서도 중앙 1 %인데 p90은 45 %, 최대 87 %다.
nvblox는 주기적으로 크게 튄다. **여유 판정은 p90으로 한다.**

**③ TTS는 요청과 재생 시점이 다르다.** 한 문장 재생에 12.6초가 걸리는데 7초마다 넣으면
큐가 밀린다. 처음에 "요청 직후 3초"를 발화 구간으로 잡아 **GPU가 발화 중에 더 낮다는
엉뚱한 결과(-7.8 %p)**가 나왔다. 시각 정렬 대신 **40초 구간 두 개를 통째로 비교**해야 한다.

### VSLAM·YOLO 추가 가능 여부 — 정량 기준

VSLAM과 YOLO는 상시 동작하므로 두 상태 모두에 얹힌다. 먼저 터지는 쪽은 발화 중이다.

```text
추가 부하를 X라 하면
   무발화  p90 = 45 + X
   발화 중 p90 = 84 + X      <- 이쪽이 먼저 포화

발화 중 p90을 95 % 아래로 유지하려면   X < 11 %p
```

**추가할 수 있는 GPU 예산은 약 11 %p다.** VSLAM(640x360x30 스테레오 + IMU 융합)과
YOLO가 이 예산을 나눠 쓰기는 어렵다. **둘 중 하나를 골라야 할 가능성이 높다.**

UMA 메모리는 제약이 아니다 — 6.9 GB 사용 / **8.8 GB 여유**. GPU 온도도 50 °C대로 여유 있다.

### 아직 재지 못한 것

- **STT 버스트** — 마이크 모듈이 분리되어 있어 측정 불가. 연결되면 같은 방식으로 잰다.
  긴급어 감시는 상시 동작이므로 이 값이 상시 부하에 더해진다.
- **VSLAM 자체 비용** — emitter·스트림 설정(§아래)이 선행되어야 측정 가능.
- **로봇 스택(Nav2·AMCL) 영향** — CPU 위주라 작을 것으로 보나 미확인.

### VSLAM을 켜려면 먼저 풀어야 할 설정 충돌

GPU와 별개로 **IR 프로젝터가 상호 배타**다.

| | VSLAM | nvblox |
| --- | --- | --- |
| infra1/2 | 켬 | 끔 |
| depth/color | 끔 | 켬 |
| **IR 프로젝터** | **꺼야 함** (무늬가 가짜 특징점) | **켜야 함** (depth 정확도) |

`depth_module.emitter_on_off: true`로 프레임마다 번갈아 켜면 공존할 수 있으나
**depth 유효 프레임이 절반(30 -> 15 fps)**이 된다 `[미검증]`.

## 결정 (2026-08-01, 사용자)

측정 결과를 보고 **채택 순서를 다음과 같이 정했다.**

1. **YOLO를 먼저 채택한다.** 객체 인식은 VSLAM이 필요 없다 — YOLO는 이미지 한 장으로
   동작하고, 검출 결과를 3D 위치로 올릴 때 필요한 카메라 pose는 **TF(EKF + AMCL)**에서
   온다. VSLAM은 그 대안 중 하나일 뿐이며 이미 AMCL이 그 역할을 한다.
2. **전부 실행한 상태에서 GPU를 다시 잰다.** 로봇 스택 + 음성 + YOLO까지 올린 실측치가
   나와야 남은 예산을 알 수 있다.
3. **여유가 남으면 VSLAM을 추가한다.** 남지 않으면 VSLAM은 보류한다.
4. **단, 현재 EKF가 드리프트 없이 안정적이지 못하다고 실측되면 VSLAM을 채택한다.**
   그때는 VSLAM이 "있으면 좋은 것"이 아니라 위치추정의 필수 구성이 된다.
5. **장기적으로 GPU 여유가 확인되면 둘 다 채택한다.** 배타적 선택이 아니라 예산 문제다.

### 4번 판정 완료 (2026-08-01 실주행) — **EKF는 안정적이다. VSLAM 불필요.**

바닥에서 직진 2 m·4 m와 제자리 360도 회전을 실측했다. **VSLAM 없이** encoder + 자이로
EKF만으로 주행했고, 실제 거리·각도는 줄자와 바닥 표시로 쟀다.

| 시험 | 실측 | encoder | EKF |
| --- | --- | --- | --- |
| 직진 2 m | 2.02 m | 2.0086 m (**−0.56 %**) | 2.0286 m (**+0.43 %**) |
| 직진 4 m | 4.05 m | 4.0138 m (**−0.89 %**) | 4.0880 m (**+0.94 %**) |
| 제자리 360도 | 365° | 362.72° (**−0.62 %**) | 365.15° (**+0.04 %**) |

**직진·회전 모두 ±1 % 이내다.** 0625 보고서의 VSLAM(4 m −19.1 %, 측면 78 cm,
yaw −7.6°)과 비교하면 **20~30배 정확하다.**

자이로가 한 바퀴에 0.15° 오차인 것이 특히 좋다. 오늘 편향을 제거한(161 → 4.7 °/h) 효과다.
단 **"365도"는 눈으로 판단한 값이라 ±2~3° 오차가 있다.** 그 범위에서는 encoder(−2.28°)도
자이로(+0.15°)도 맞다고 볼 수 있다.

#### 방법

`/cmd_vel_req`로만 발행해 Safety를 거쳤다. encoder가 목표에 도달하면 정지하고, 그 시점의
EKF 값을 함께 남긴 뒤 사람이 줄자로 쟀다. 순항 속도는 직진 0.15 m/s, 회전 0.30 rad/s로
Nav2 상한(0.26 m/s, 0.4 rad/s)보다 낮춰 제동 여유를 뒀다.

**측정 스크립트는 시작 전에 Safety 연결과 E-stop 해제를 확인하고, 아니면 주행하지 않는다.**
앞선 세션에서 Safety가 DDS 그래프에서 이탈했는데 그것을 모른 채 "바퀴가 한 번도 안 돌았는데
값만 나온" 일이 있었기 때문이다.

#### teleop 74도 divergence — 미끄러짐으로 본다

2 m 시험 출발 시점에 encoder yaw −3.10°, EKF yaw −77.22°로 **74도** 벌어져 있었다.
그런데 통제된 360도 회전에서는 **2.43도**만 벌어졌다. 30배 차이다.

차이는 조작 방식이다. teleop은 빠르고 급하고 양방향인 반면 시험은 느리고 부드럽고 한
방향이었다. **차동 구동 로봇이 제자리에서 급회전하면 바퀴가 옆으로 끌리는데 encoder는
그것을 모른다.**

**Nav2는 시험처럼 부드럽게 주행하므로 정상 운영에서는 문제가 되지 않는다.** 다만 미끄러짐이
생기면 odometry가 틀어지고 되돌릴 수단이 없다는 것은 사실이며, **그것이 AMCL이 필요한
이유다. VSLAM이 아니라 AMCL이 그 역할을 한다.**

#### `wheel_base_m` 보정은 하지 않는다

계산상 `0.37 x (362.72 / 365) = 0.3677 m`로 **2.3 mm 차이**다. 눈 측정 오차 안에 있어
근거가 부족하다. 확정하려면 **5바퀴(1800도) 연속 회전**으로 오차를 5배 키워 재야 한다.

#### 결론

**결정 4번의 조건("EKF가 안정적이지 못하면 VSLAM 채택")은 성립하지 않는다.**
1~3번대로 YOLO를 먼저 채택하고, 전부 실행한 뒤 GPU 여유가 남으면 VSLAM을 검토한다.

## 남은 것 (게이트)

- ~~**실측(Jetson)**~~ → **위에서 완료(2026-08-01). 경합 없음.**
- **slice staleness 진단 구현**: health monitor 오류 로깅 패키지(`vica_system_monitor`,
  진행 중)에 편입. slice age/Hz → `/diagnostics` → aggregator → `robot_health_monitor_node`
  → `/robot/events`. 초안 §3.1 원칙대로 **즉시 정지 경로엔 넣지 않는다**. 초안 §22(승인 전
  safety 변경 금지) 준수.
- **nvblox 부하 삭감**: 실측이 경합 입증 시에만. mesh/debug rate→0 → max distance↓ → voxel↑.
  slice ≥ ~8Hz 하한 유지. 긴급어 STT(`VICA_EMERGENCY_STT_MODEL`)는 불변(안전 직결).

관련 계획: `~/.claude/plans/graceful-chasing-bee.md`
