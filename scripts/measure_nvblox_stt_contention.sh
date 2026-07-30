#!/usr/bin/env bash
#
# nvblox(depth) + 긴급어 감시 STT 동시 GPU 부하 실측
# ─────────────────────────────────────────────────────────────
# 목적: 상시로 도는 nvblox depth 파이프라인에, 준-상시(0.5초 hop)로 도는
#       긴급어 감시 STT(faster-whisper small, cuda)가 얹혔을 때
#       - GPU util(GR3D)이 포화(→100%)되는지
#       - nvblox static_map_slice 발행 Hz가 떨어지는지 (= 장애물 맵 갱신 지연)
#       - 공유 메모리(UMA) 사용량이 얼마나 늘어나는지
#       를 A/B(STT off vs on)로 비교 측정한다.
#
# ⚠️ 이 스크립트는 Jetson Orin NX 실기에서만 의미가 있다 (tegrastats 필요).
#    개발 노트북(x86_64)에서는 tegrastats가 없어 자동으로 중단된다.
#
# 전제 (측정 시작 전에 이미 떠 있어야 함):
#   - RealSense D455 (run_d455.sh)  → /camera/camera/depth/image_rect_raw 발행 중
#   - nvblox_node (Isaac ROS Docker) → /nvblox_node/static_map_slice 발행 중
#   - 이 스크립트가 긴급어 감시 STT는 직접 켜고 끈다.
#
# ⚠️ 긴급어 감시 STT에는 RMS 음량 게이트가 있어, "조용하면 STT를 건너뛴다".
#    최악 부하(매 0.5초 STT)를 재현하려면 load 구간 동안 마이크에 계속
#    소리를 넣어야 한다(계속 말하기 / 라디오·노이즈 재생). 조용하면 STT가
#    거의 안 돌아 부하가 과소평가된다. 스크립트가 해당 시점에 안내한다.
#
# 사용법:
#   ./scripts/measure_nvblox_stt_contention.sh [측정초=30]
#
set -uo pipefail

# ── 설정 (환경에 맞게 조정) ───────────────────────────────────
DUR="${1:-30}"                                   # 각 구간 측정 시간(초)
WARMUP="${WARMUP:-20}"                            # STT(whisper small) 모델 로드 대기(초)
DEPTH_TOPIC="${DEPTH_TOPIC:-/camera/camera/depth/image_rect_raw}"
SLICE_TOPIC="${SLICE_TOPIC:-/nvblox_node/static_map_slice}"
VOICE_DIR="${VOICE_DIR:-$HOME/VICA-smarthandle/vica-voice-llm}"
VENV_PY="${VENV_PY:-$VOICE_DIR/.venv/bin/python}"
OUTDIR="${OUTDIR:-$HOME/VICA-smarthandle/log/nvblox_stt_$(date +%Y%m%d_%H%M%S)}"

# ── 사전 점검 ─────────────────────────────────────────────────
die() { echo "[ERROR] $*" >&2; exit 1; }

command -v tegrastats >/dev/null 2>&1 || \
  die "tegrastats 없음 → Jetson 실기가 아니다. 이 측정은 노트북에서 불가."
command -v ros2 >/dev/null 2>&1 || \
  die "ros2 없음 → ROS 2 환경을 source 했는지 확인 (source /opt/ros/humble/setup.bash 등)."
[ -x "$VENV_PY" ] || \
  die "STT venv 파이썬 없음: $VENV_PY (VOICE_DIR/VENV_PY 환경변수로 지정 가능)."

echo "== 토픽 생존 확인 =="
ros2 topic list 2>/dev/null | grep -qxF "$DEPTH_TOPIC" \
  || echo "[WARN] $DEPTH_TOPIC 미발행? RealSense(run_d455.sh)가 떠 있는지 확인."
ros2 topic list 2>/dev/null | grep -qxF "$SLICE_TOPIC" \
  || echo "[WARN] $SLICE_TOPIC 미발행? nvblox_node가 떠 있는지 확인."

mkdir -p "$OUTDIR"
echo "결과 저장: $OUTDIR"
echo

# ── 헬퍼: 토픽 평균 Hz 측정 (DUR초 동안) ──────────────────────
measure_hz() {  # $1=초  $2=토픽  → 평균 rate 숫자만 stdout
  timeout "$1" ros2 topic hz "$2" 2>/dev/null \
    | grep -oE 'average rate: [0-9.]+' | tail -1 | grep -oE '[0-9.]+$'
}

# ── 헬퍼: tegrastats 로그에서 GPU util / RAM 요약 ─────────────
summarize_tegrastats() {  # $1=로그파일 → "gpu_avg gpu_max ram_max_used ram_total"
  awk '
    match($0, /GR3D_FREQ [0-9]+/) {
      g = substr($0, RSTART+10, RLENGTH-10) + 0; gsum += g; gn++
      if (g > gmax) gmax = g
    }
    match($0, /RAM [0-9]+\/[0-9]+MB/) {
      split(substr($0, RSTART+4, RLENGTH-6), a, "/")
      if (a[1]+0 > rmax) rmax = a[1]+0
      rtot = a[2]+0
    }
    END {
      printf "%.0f %.0f %d %d", (gn? gsum/gn : 0), gmax, rmax, rtot
    }' "$1"
}

# ── 한 구간 측정: tegrastats + 두 토픽 Hz 를 같은 창으로 동시 수집 ─
run_phase() {  # $1=라벨(baseline|load)
  local label="$1"
  local ts_log="$OUTDIR/tegrastats_${label}.log"
  echo "── [$label] ${DUR}초 측정 시작 ──"

  timeout "$DUR" tegrastats --interval 500 >"$ts_log" 2>/dev/null &
  local ts_pid=$!

  measure_hz "$DUR" "$SLICE_TOPIC" >"$OUTDIR/hz_slice_${label}.txt" &
  local h1=$!
  measure_hz "$DUR" "$DEPTH_TOPIC" >"$OUTDIR/hz_depth_${label}.txt" &
  local h2=$!

  wait "$ts_pid" "$h1" "$h2" 2>/dev/null

  local slice_hz depth_hz
  slice_hz="$(cat "$OUTDIR/hz_slice_${label}.txt" 2>/dev/null)"; slice_hz="${slice_hz:-0}"
  depth_hz="$(cat "$OUTDIR/hz_depth_${label}.txt" 2>/dev/null)"; depth_hz="${depth_hz:-0}"

  read -r g_avg g_max r_max r_tot < <(summarize_tegrastats "$ts_log")

  # 전역 변수에 저장 (구간별로 접미사 다르게)
  eval "${label}_slice=\$slice_hz"
  eval "${label}_depth=\$depth_hz"
  eval "${label}_gavg=\$g_avg"
  eval "${label}_gmax=\$g_max"
  eval "${label}_rmax=\$r_max"
  RAM_TOTAL="$r_tot"

  printf "   GPU util 평균 %s%% / 최대 %s%% | RAM 최대 %s/%s MB | slice %s Hz | depth %s Hz\n" \
    "$g_avg" "$g_max" "$r_max" "$r_tot" "$slice_hz" "$depth_hz"
  echo
}

# ── PHASE A: baseline (긴급어 STT OFF) ────────────────────────
echo "###############################################"
echo "# PHASE A: baseline  (nvblox 단독, STT OFF)"
echo "###############################################"
echo "지금 긴급어 감시 STT는 꺼져 있어야 한다. 켜져 있으면 Ctrl-C 후 끄고 다시 실행."
run_phase baseline

# ── PHASE B: load (긴급어 STT ON) ─────────────────────────────
echo "###############################################"
echo "# PHASE B: load  (nvblox + 긴급어 감시 STT ON)"
echo "###############################################"
echo "긴급어 감시 STT 실행 (VICA_EMERGENCY_STT_MODEL=small, device=cuda)..."
(
  cd "$VOICE_DIR" || exit 1
  VICA_EMERGENCY_STT_MODEL="${VICA_EMERGENCY_STT_MODEL:-small}" \
  VICA_STT_DEVICE="${VICA_STT_DEVICE:-cuda}" \
  VICA_STT_COMPUTE="${VICA_STT_COMPUTE:-float16}" \
  "$VENV_PY" -m src.emergency_monitor
) >"$OUTDIR/emergency_monitor.log" 2>&1 &
STT_PID=$!

# 프로세스가 죽으면(예: whisper 로드 실패) 정리하도록 트랩
cleanup() { kill "$STT_PID" 2>/dev/null; wait "$STT_PID" 2>/dev/null; }
trap cleanup EXIT

echo "whisper small 로드 대기 ${WARMUP}초..."
sleep "$WARMUP"
if ! kill -0 "$STT_PID" 2>/dev/null; then
  echo "[ERROR] 긴급어 감시 STT가 조기 종료됨. 로그 확인:"
  tail -n 20 "$OUTDIR/emergency_monitor.log" >&2
  die "STT 기동 실패 — GPU 로드 없이 측정 무의미."
fi

echo
echo ">>> 지금부터 ${DUR}초간 마이크에 소리를 계속 넣어라 <<<"
echo ">>> (계속 말하기 / 노이즈·라디오 재생). 조용하면 RMS 게이트가 STT를 건너뛴다."
echo
run_phase load

cleanup
trap - EXIT

# ── 비교 요약 ─────────────────────────────────────────────────
delta() { awk -v a="$1" -v b="$2" 'BEGIN{ printf "%+.1f", b-a }'; }
pct_drop() { awk -v a="$1" -v b="$2" 'BEGIN{ if(a>0) printf "%.1f", (a-b)/a*100; else printf "n/a" }'; }

echo "==============================================="
echo " 결과 요약  (측정창 ${DUR}초, RAM 총 ${RAM_TOTAL} MB)"
echo "==============================================="
printf "%-22s %12s %12s %10s\n" "지표" "baseline" "load(STT)" "변화"
printf "%-22s %12s %12s %10s\n" "GPU util 평균 %"  "$baseline_gavg" "$load_gavg" "$(delta "$baseline_gavg" "$load_gavg")"
printf "%-22s %12s %12s %10s\n" "GPU util 최대 %"  "$baseline_gmax" "$load_gmax" "$(delta "$baseline_gmax" "$load_gmax")"
printf "%-22s %12s %12s %10s\n" "RAM 최대 MB"      "$baseline_rmax" "$load_rmax" "$(delta "$baseline_rmax" "$load_rmax")"
printf "%-22s %12s %12s %9s%%\n" "nvblox slice Hz"  "$baseline_slice" "$load_slice" "-$(pct_drop "$baseline_slice" "$load_slice")"
printf "%-22s %12s %12s %9s%%\n" "depth 입력 Hz"    "$baseline_depth" "$load_depth" "-$(pct_drop "$baseline_depth" "$load_depth")"
echo
echo "판정 가이드:"
echo "  • GPU util 최대가 load에서 상시 ~100% 도달 → GPU 컴퓨트 포화 (경합 발생)."
echo "  • nvblox slice Hz 하락률이 크면(>10~20%) → 장애물 맵 갱신 지연 = 안전 영향."
echo "  • RAM 증가분이 whisper small(~0.5GB대) 이상으로 크면 UMA 여유 확인 필요."
echo "  • depth 입력 Hz까지 떨어지면 RealSense/USB·CPU 병목도 의심."
echo
echo "원자료: $OUTDIR (tegrastats_*.log / hz_*.txt / emergency_monitor.log)"
