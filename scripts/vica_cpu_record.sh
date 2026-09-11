#!/usr/bin/env bash

set -u

NAME="${1:-cpu_$(date +%H%M)}"
OUT_DIR="${HOME}/vica_data/cpu"
OUT="${OUT_DIR}/${NAME}.csv"
INTERVAL="${VICA_CPU_INTERVAL:-1}"

mkdir -p "$OUT_DIR"

WATCH=(controller_serv planner_server bt_navigator amcl behavior_server \
       nvblox_node realsense2_came rviz2 ekf_node encoder_feedbac \
       rplidar_node imu_base_link_a keyboard_knob robot_health_mo code)

CORES=$(nproc)

printf 'time,load1,cpu_total_pct,mem_used_gb' > "$OUT"
for w in "${WATCH[@]}"; do printf ',%s' "$w" >> "$OUT"; done
printf '\n' >> "$OUT"

echo "기록 시작: $OUT   (코어 ${CORES}개 · ${INTERVAL}초 간격)"
echo "주행이 끝나면 Ctrl+C 를 누르세요."

summary() {
  echo
  echo "=== 요약: $OUT ==="
  python3 - "$OUT" "$CORES" <<'PY'
import csv, sys, statistics
rows=list(csv.DictReader(open(sys.argv[1])))
cores=int(sys.argv[2])
if not rows:
    print("  표본 없음"); raise SystemExit
def col(k):
    v=[float(r[k]) for r in rows if r.get(k) not in (None,'')]
    return v or [0.0]
print(f"  표본 {len(rows)}개 · 코어 {cores}개")
l=col('load1'); c=col('cpu_total_pct')
print(f"  load average  평균 {statistics.mean(l):5.2f}  최대 {max(l):5.2f}"
      f"   (코어 수 {cores} 를 넘으면 과부하)")
print(f"  전체 CPU      평균 {statistics.mean(c):5.1f}%  최대 {max(c):5.1f}%"
      f"   (상한 {cores*100}%)")
print("\n  프로세스별 CPU 점유 (평균 / 최대, 코어 1개 = 100%)")
names=[k for k in rows[0] if k not in ('time','load1','cpu_total_pct','mem_used_gb')]
data=[]
for n in names:
    v=col(n)
    if max(v)>0: data.append((statistics.mean(v), max(v), n))
for avg,mx,n in sorted(data, reverse=True):
    bar='#'*min(40,int(avg/5))
    print(f"    {n:18} {avg:6.1f} / {mx:6.1f}  {bar}")
m=col('mem_used_gb')
print(f"\n  메모리 사용   평균 {statistics.mean(m):4.1f} GB  최대 {max(m):4.1f} GB")
PY
  echo
  echo "controller 제어 주기 놓침과 대조하려면:"
  echo "  grep -c 'missed its desired rate' ~/.ros/log/controller_server_*.log"
}
trap 'summary; exit 0' INT TERM

while true; do
  TS=$(date +%H:%M:%S)
  LOAD=$(awk '{print $1}' /proc/loadavg)
  TOTAL=$(ps -eo pcpu= | awk '{s+=$1} END {printf "%.1f", s}')
  MEM=$(free -g | awk '/^Mem:/ {print $3}')

  LINE="${TS},${LOAD},${TOTAL},${MEM}"
  for w in "${WATCH[@]}"; do
    V=$(ps -eo comm=,pcpu= | awk -v n="$w" '$1==n {s+=$2} END {printf "%.1f", s}')
    LINE="${LINE},${V:-0.0}"
  done
  echo "$LINE" >> "$OUT"
  sleep "$INTERVAL"
done
