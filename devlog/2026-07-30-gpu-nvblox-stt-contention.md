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

## 남은 것 (게이트)

- **실측(Jetson)**: `measure_nvblox_stt_contention.sh 30`. slice Hz 하락률 >10~20% 또는
  GPU util 상시 ~100%면 경합 실재. 노트북(x86_64)에선 tegrastats 없어 불가.
- **slice staleness 진단 구현**: health monitor 오류 로깅 패키지(`vica_system_monitor`,
  진행 중)에 편입. slice age/Hz → `/diagnostics` → aggregator → `robot_health_monitor_node`
  → `/robot/events`. 초안 §3.1 원칙대로 **즉시 정지 경로엔 넣지 않는다**. 초안 §22(승인 전
  safety 변경 금지) 준수.
- **nvblox 부하 삭감**: 실측이 경합 입증 시에만. mesh/debug rate→0 → max distance↓ → voxel↑.
  slice ≥ ~8Hz 하한 유지. 긴급어 STT(`VICA_EMERGENCY_STT_MODEL`)는 불변(안전 직결).

관련 계획: `~/.claude/plans/graceful-chasing-bee.md`
