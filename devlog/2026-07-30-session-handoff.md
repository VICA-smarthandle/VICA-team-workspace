# 세션 핸드오프 — 2026-07-30 (GPU 경합 / health monitor)

> **이 파일 용도**: 다른 Claude Code 세션/에이전트에 이 경로 하나를 넘겨 맥락을 이어받게 하는 핸드오프 문서다.
> 새 세션은 이 파일 + 저장소 코드 + `~/.claude/.../memory/MEMORY.md`(자동 로드)만으로 이어서 작업할 수 있다.
> 이어받는 세션에게: 먼저 `CLAUDE.md`, `AGENTS.md`, `GOVERNANCE.md`를 읽고, 아래 "남은 작업"부터 확인할 것.

---

## 0. 한 줄 요약

Jetson Orin NX에서 **nvblox(depth)와 STT/TTS가 GPU를 시분할할 때의 경합**을 분석 →
"조용한 저하(nvblox slice staleness 감지 공백)"를 발견 → health-monitoring 초안에 감지 항목을
추가하고, 전력모드 고정 절차와 실측 스크립트를 정리해 **커밋·푸시 완료**. 실측(Jetson)과
진단 구현(사용자가 진행 중인 health monitor 패키지)은 게이트로 남음.

## 1. 환경 / 장비 (중요)

- **현재 장비 = 개발 노트북 (x86_64 Ubuntu)**. Jetson 아님. `tegrastats`·`nvpmodel` 없음.
- 장비가 **두 대**다: 개발 노트북 + Jetson Orin NX **16GB**(JetPack 6.x). 센서·주행·GPU 실측은
  **Jetson에서만** 가능. 작업 전 `uname -m`으로 장비부터 확인할 것.
- 워크스페이스 = 4개 독립 git 저장소 (최상위 + 제품 3개).

## 2. 현재 git 상태 (이 세션 종료 시점)

| 저장소 | branch | 원격 대비 | 비고 |
|---|---|---|---|
| VICA-smarthandle(최상위) | `dev` | 동기화(0/0) | 이 세션 커밋 `046ae10` **푸시 완료** |
| vica_ros2_ws | `feat/user-guidance` | 동기화(0/0) | 변경 없음 |
| vica-voice-llm | `dev` | 동기화(0/0) | 변경 없음 |
| VICA_Supervisor | `dev` | 동기화(0/0) | 변경 없음 |

- 세션 초기에 최상위(4커밋)·vica-voice-llm(2커밋)이 origin보다 뒤처져 있어 **fast-forward pull** 했음.
  그때 들어온 코드 변경은 `vica-voice-llm/src/stt.py`의 `_preload_cuda_ctranslate2()`
  (Jetson CUDA용 libctranslate2 사전 적재, `.venv/ct2lib/libctranslate2.so.4` 있을 때만, 없으면 CPU 폴백).
- 이 세션이 만든 커밋: **`046ae10` `docs(health-monitor): nvblox slice GPU 경합 감지와 실측 스크립트 추가`** (4파일 +270줄).

## 3. 대화 타임라인 (전체)

1. hook 오류(`No module named 'hookify'`) 화면 → 이후 다른 질문으로 전환(미해결로 남김).
2. CLI 이미지 첨부 방법 안내(스크린샷→`Ctrl+V`, 드래그, 경로 입력).
3. 4개 저장소 git 상태 확인 → 뒤처진 2곳 pull.
4. `stt.py` 변경 내용 리뷰(CUDA ctranslate2 preload).
5. "STT를 GPU로 돌리는 장점?" → 지연 + **CPU 오프로딩**(실시간 제어 스택 보호).
6. "LLM·depth 둘 다 GPU 스펙상 가능?" → 코드 확인 결과 **LLM은 Ollama Cloud(로컬 GPU 미사용)**,
   STT/TTS만 로컬 GPU. 진짜 쟁점은 nvblox(상시) vs STT(준상시) 경합.
7. "STT/TTS도 GPU를 버스트/비동기로?" → 버스트(대화 STT·TTS) vs 준상시(긴급어 STT) 구분,
   비동기여도 GPU는 단일 자원이라 **시분할 인터리빙**.
8. "경합해도 안 깨지는 조합 필요?" → **플랜 모드**로 조사 → 승인 → A·D 실행 → 커밋·푸시.
9. 세션 핸드오프 방법 질문 → 이 문서 작성.

## 4. 핵심 기술 내용 (이어받는 세션이 알아야 할 것)

### 4.1 GPU 부하 3층 (Jetson)
- **상시**: nvblox (depth 3D 재구성, Isaac ROS Docker).
- **준-상시**: 긴급어 감시 STT (whisper `small`, hop 0.5s, RMS 음량 게이트 — 조용하면 STT 생략).
- **버스트**: 대화 STT (`medium`), TTS (supertonic ONNX).
- LLM = Ollama Cloud(네트워크). 로컬 GPU 경합에 안 낌.
- 상호배제: 긴급어 STT는 TTS 재생 중 mute(`/vica/tts_state`). **대화 STT ↔ 긴급어 STT는 상호배제 안 됨**
  → 대화 순간 nvblox+medium+small 3중 겹침. 두 whisper+supertonic은 상시 VRAM 상주.

### 4.2 핵심 발견 — "조용한 저하" 안전 공백
- `vica_ros2_ws/src/vica_nav2/config/nav2_params.yaml:207-212`의 `nvblox_layer`에는
  LiDAR `scan`(`:235` `expected_update_rate: 0.2`)과 달리 **timeout이 없다.**
- → GPU 경합으로 `/nvblox_node/static_map_slice`(정상 ~9Hz)가 느려지거나 멈춰도 costmap이 감지 못 하고
  **오래된 3D 장애물로 주행**. `vica_safety`는 slice 미구독 → **E-stop으로도 안 걸림**. 회피 실패(충돌)로만 발현.

## 5. 승인된 플랜과 게이트 상태

플랜 파일: `~/.claude/plans/graceful-chasing-bee.md` (전체 내용은 거기 참조)

| 항목 | 내용 | 상태 |
|---|---|---|
| **A. 문서화** | health 초안 §8.5/§8.7/§9.1/§19에 nvblox slice 감지 항목 + devlog | ✅ **완료**(커밋됨) |
| **D. 전력모드 고정** | bringup에 MAXN+jetson_clocks ⓪ 단계 | ✅ **완료**(커밋됨) |
| **B. 경합 실측** | `scripts/measure_nvblox_stt_contention.sh 30` (Jetson) | ⏸ **게이트** — Jetson 필요, 노트북 불가 |
| **C. slice staleness 진단 구현** | health monitor 패키지에 slice age/Hz 진단 편입 | ⏸ **게이트** — 사용자가 패키지 개발 초안 완성 후 착수 |
| **E. nvblox 부하 삭감** | B가 경합 입증 시에만 (mesh/debug→0 → max dist↓ → voxel↑, slice≥~8Hz 하한) | ⏸ **조건부** |

## 6. 사용자가 진행 중인 작업 (핸드오프 핵심)

- 사용자가 **health monitor 오류 로깅 패키지(`vica_system_monitor` / `robot_health_monitor_node`)**의
  **개발 초안을 직접 완성 중**이다.
- 합의된 순서: 사용자가 개발 초안 완성 → 사용자가 알려줌 → **그때 Claude가 테스트 코드/방법을 작성**.
- Claude가 짤 테스트(대기 중):
  - 단위 테스트: slice age/Hz 주입식으로 `health_logic` 판정 검증 (마이크·nvblox 없이).
  - fault-injection 방법: slice 강제 지연/중단 주입 → `/robot/events`에 `NVBLOX_SLICE_STALE`가 WARN/DEGRADED로 뜨는지 (초안 §18.1 스타일).
- **원칙(초안 §2·§3.1·§22)**: slice 진단을 **즉시 정지 경로에 직접 연결 금지**. 정지 등급은 팀 결정(초안 §19-11).
  age 계산은 monotonic clock 기준(초안 §8.1, [[safety-steady-clock-contract]] 원칙).

## 7. 남은 작업 (다음 세션이 할 일 후보)

1. **[대기]** 사용자가 health monitor 개발 초안 완성 알림 → 완성 코드를 읽고 거기 맞춰 테스트 작성.
2. **[Jetson]** `measure_nvblox_stt_contention.sh`로 경합 실측 → 임계 Hz/age를 실측 근거로 확정.
3. **[Jetson, 별건]** Smart Handle: yaw 측정과 Phase 5 ([[smart-handle-guidance-resume]]).
4. **[선택]** 세션 초기 hook 오류(`No module named 'hookify'`) — 미해결. 필요 시 hookify import 경로 진단.

## 8. 산출물 인덱스 (경로)

- 플랜: `~/.claude/plans/graceful-chasing-bee.md`
- 이 세션 devlog(기술 상세): `devlog/2026-07-30-gpu-nvblox-stt-contention.md`
- 실측 스크립트: `scripts/measure_nvblox_stt_contention.sh` (Jetson 전용)
- 편집된 설계 초안: `guideline/vica_system_health_monitoring_draft.md` (§8.5/§8.7/§9.1/§19)
- 편집된 bringup: `docs/vica_robot_bringup_manual.md` (§2, §5 ⓪)
- 커밋: `046ae10` (최상위 저장소, dev, 푸시됨)
- 관련 코드 근거: `vica_ros2_ws/src/vica_nav2/config/nav2_params.yaml`,
  `vica-voice-llm/src/{stt.py,emergency_monitor.py,tts.py,langchain_intent_parser.py}`

## 9. 세션을 그대로 이어받는 방법 (파일 아닌 대화 자체 재개)

이 파일과 별개로, **이 대화 세션 자체**를 재개하려면:
- 같은 디렉토리에서 가장 최근 세션: `claude --continue` (`-c`)
- 세션 선택기: `claude --resume` (`-r`), 또는 ID로 `claude --resume <session-id>`
- transcript 위치: `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl` (JSONL). 다른 기기로 옮기려면
  이 파일을 복사 후 **동일 cwd**에서 `--resume`.
- 평문 내보내기: 대화 중 `/export [파일명]`.
- 클라우드↔로컬: `claude --cloud "..."` / `claude --teleport <id>`.

새 세션에 "맥락만" 넘기려면 → **이 핸드오프 파일 경로를 새 세션에 주면 됨.**
