#!/bin/bash

NAME=${1:-}

ok()   { printf "  \033[32mOK\033[0m   %s\n" "$1"; }
bad()  { printf "  \033[31mNG\033[0m   %s\n" "$1"; }
warn() { printf "  \033[33m--\033[0m   %s\n" "$1"; }
die()  { printf "\n\033[31m[중단]\033[0m %s\n" "$1"; exit 1; }

if [ -z "$VICA_ROS_WS" ]; then
  VICA_ROS_WS=$(cd "$(dirname "${BASH_SOURCE[0]}")/../vica_ros2_ws" 2>/dev/null && pwd)
fi
MAPS="$VICA_ROS_WS/maps"

if [ -z "$NAME" ]; then
  cat <<'USAGE'
사용법: vica_map_save.sh <지도이름>

  vica_map_save.sh vica_map_0813

지도 이름에는 영문·숫자·밑줄·붙임표만 씁니다. 확장자와 경로는 붙이지 않습니다.
세 파일(.pgm .png .yaml)이 그 이름으로 maps/ 에 생깁니다.
USAGE
  exit 1
fi

if [[ ! "$NAME" =~ ^[A-Za-z0-9_-]+$ ]]; then
  die "지도 이름에 쓸 수 없는 문자가 있습니다: '$NAME'
       영문·숫자·밑줄(_)·붙임표(-) 만 씁니다. 확장자와 경로는 붙이지 않습니다.
       ROS 의 map yaml 과 앱의 HTTP 경로가 이 이름을 그대로 쓰기 때문입니다."
fi

if [ ! -d "$MAPS" ]; then
  die "maps 디렉터리가 없습니다: $MAPS
       VICA_ROS_WS 가 맞는지 확인하세요 (현재: $VICA_ROS_WS)"
fi

PGM="$MAPS/$NAME.pgm"
PNG="$MAPS/$NAME.png"
YAML="$MAPS/$NAME.yaml"

echo "=== 지도 저장: $NAME ==="
echo "    위치: $MAPS"
echo

echo "--- 1) 덮어쓰기 확인 ---"
exists=""
for f in "$PGM" "$PNG" "$YAML"; do
  [ -e "$f" ] && exists="$exists  $f"$'\n'
done
if [ -n "$exists" ]; then
  printf "%s" "$exists"
  die "이 이름은 이미 있습니다. 다른 이름을 쓰세요.
       덮어쓰지 않는 것은 의도한 동작입니다 — 지운 지도는 되돌릴 수 없습니다."
fi
ok "$NAME 은 새 이름이다"
echo

echo "--- 2) SLAM 확인 ---"
grid_pid=$(pgrep -x cartographer_oc 2>/dev/null | head -1)
node_pid=$(pgrep -x cartographer_no 2>/dev/null | head -1)

[ -n "$node_pid" ] && ok "cartographer_node (pid $node_pid)" \
                   || warn "cartographer_node 를 못 찾았다"
[ -n "$grid_pid" ] && ok "occupancy_grid_node (pid $grid_pid) — /map 발행자" \
                   || warn "occupancy_grid_node 를 못 찾았다"

if [ -z "$grid_pid" ] && [ -z "$node_pid" ] && [ -z "$VICA_SKIP_SLAM_CHECK" ]; then
  die "SLAM 이 떠 있지 않습니다. slam 칸을 먼저 실행하세요.
       이대로 저장하면 map_saver_cli 가 timeout 까지 기다린 뒤 빈 손으로 끝납니다.

       프로세스 이름이 달라서 못 찾은 것일 수도 있습니다. 확인:
         ps -eo comm= | grep -i carto
       이름이 맞는데도 못 찾으면 이 검사를 건너뜁니다:
         VICA_SKIP_SLAM_CHECK=1 bash scripts/vica_map_save.sh $NAME"
fi
[ -n "$VICA_SKIP_SLAM_CHECK" ] && warn "VICA_SKIP_SLAM_CHECK — SLAM 검사를 건너뛴다"
echo

echo "--- 3) map_saver_cli ---"
source /opt/ros/humble/setup.bash
if [ -f "$VICA_ROS_WS/install/setup.bash" ]; then
  source "$VICA_ROS_WS/install/setup.bash"
fi
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-7}
export ROS_LOCALHOST_ONLY=${ROS_LOCALHOST_ONLY:-0}
export RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}

TIMEOUT=${VICA_MAP_SAVE_TIMEOUT:-120}
case "$TIMEOUT" in *.*) ;; *) TIMEOUT="$TIMEOUT.0" ;; esac

ros2 run nav2_map_server map_saver_cli -f "$MAPS/$NAME" \
  --ros-args -p save_map_timeout:="$TIMEOUT"
rc=$?
if [ $rc -ne 0 ]; then
  die "map_saver_cli 가 실패했습니다 (종료 코드 $rc). 위 출력을 보세요.
       'Failed to spin map subscription' 이면 제한시간이 모자란 것입니다.
       ${TIMEOUT}초를 기다리고도 /map 이 안 왔다는 뜻이라 이때는 시간보다 배선을
       먼저 의심합니다. SLAM 을 끄지 말고 다른 칸에서 확인하세요:
         ros2 topic hz /map          발행자가 실제로 있는지
       발행이 되는데도 실패하면 더 길게 다시 합니다:
         VICA_MAP_SAVE_TIMEOUT=300 bash scripts/vica_map_save.sh $NAME"
fi
[ -f "$PGM" ] || die "map_saver_cli 는 끝났는데 $PGM 이 없습니다.
       /map 을 못 받았을 때 이렇게 됩니다. SLAM 이 실제로 지도를 내고 있는지 보세요."
ok "pgm·yaml 저장 완료"
echo

echo "--- 4) 앱용 png 변환 ---"
if ! command -v convert >/dev/null 2>&1; then
  bad "convert(ImageMagick) 가 없습니다"
  die "pgm 과 yaml 은 남았습니다. png 만 따로 만드세요:
         convert $PGM $PNG
       또는  sudo apt install -y imagemagick"
fi
convert "$PGM" "$PNG"
if [ $? -ne 0 ] || [ ! -f "$PNG" ]; then
  die "png 변환에 실패했습니다. pgm 과 yaml 은 남아 있으므로 아래로 다시 하세요:
         convert $PGM $PNG"
fi
ok "png 생성 완료 — 앱이 읽는 것은 이 파일이다"
echo

echo "--- 5) 검증 ---"
for f in "$PGM" "$PNG" "$YAML"; do
  if [ -f "$f" ]; then
    ok "$(basename "$f")  $(stat -c%s "$f") bytes"
  else
    bad "$(basename "$f") 없음"
  fi
done

python3 - "$PGM" "$PNG" <<'PY' 2>/dev/null || warn "Pillow 가 없어 픽셀 크기는 확인하지 못했다"
import sys
from PIL import Image
a = Image.open(sys.argv[1]).size
b = Image.open(sys.argv[2]).size
if a == b:
    print(f"  \033[32mOK\033[0m   픽셀 크기 일치 {a[0]}x{a[1]}")
else:
    print(f"  \033[31mNG\033[0m   픽셀 크기 불일치 pgm {a} vs png {b}")
    print("       앱 캔버스의 좌표가 어긋납니다. png 를 다시 만드세요.")
PY

grep -E '^(resolution|origin):' "$YAML" 2>/dev/null | sed 's/^/       /'
echo

echo "--- 6) 현재 지도 갱신 ---"
if printf '%s\n' "$NAME" > "$MAPS/CURRENT_MAP" 2>/dev/null; then
  ok "maps/CURRENT_MAP -> $NAME"
else
  warn "CURRENT_MAP 을 쓰지 못했다. 지도 자체는 남아 있으므로 저장은 성공이다."
fi
echo

printf "\033[32m=== 완료: %s ===\033[0m\n" "$NAME"
cat <<EOF

앱이 보게 될 경로:  /maps/$NAME.png
확인:               cat $MAPS/CURRENT_MAP
되돌리기:           export VICA_MAP_ID=<옛 이름>   (터미널을 띄우기 전에)

앱 목록에 안 보이면 앱에서 지도 목록 동기화를 한 번 하세요.
EOF
