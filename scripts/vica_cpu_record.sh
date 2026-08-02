#!/usr/bin/env bash
# 주행 중 CPU·부하를 1초 간격으로 기록한다.
#
# 왜 필요한가: 2026-08-02 주행에서 controller_server 가 20 Hz 제어 주기를
# 838회 놓쳤고(RViz·VS Code 종료 후에도 345회), 그 지연이 "직진 중 좌우 흔들림"과
# 충돌로 이어졌다. 어느 프로세스가 CPU 를 가져갔는지 사후에 알 방법이 없어
# 매번 추정만 했다. 이 스크립트가 그 공백을 메운다.
#
# 사용법
#   scripts/vica_cpu_record.sh                 # 기본 이름(cpu_HHMM)으로 기록 시작
#   scripts/vica_cpu_record.sh run1530         # 이름 지정
#   Ctrl+C 로 중단하면 요약을 출력한다
#
# ros2 CLI 를 쓰지 않는다. DDS 그래프 조회는 느리고 오탐이 있다(2026-08-01).
# 프로세스 테이블만 읽는다.

set -u

NAME="${1:-cpu_$(date +%H%M)}"
OUT_DIR="${HOME}/vica_data/cpu"
OUT="${OUT_DIR}/${NAME}.csv"
INTERVAL="${VICA_CPU_INTERVAL:-1}"

mkdir -p "$OUT_DIR"

# 감시할 프로세스. comm 이름 기준(15자 제한이 있어 잘린 이름을 그대로 쓴다).
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
  # 전체 CPU: ps 의 %CPU 합(코어 수 x 100 이 상한)
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
