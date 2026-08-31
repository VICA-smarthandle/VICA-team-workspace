#!/bin/bash
# 지도 저장 + 앱용 png 변환 + 검증을 한 번에 한다.
#
#   bash scripts/vica_map_save.sh vica_map_0813
#
# 왜 png 를 따로 만드는가 — map_saver_cli 는 .pgm 과 .yaml 만 만든다. 관리자 앱은
# VICA_Supervisor/ros2/map_list_node.py 62행이 maps/*.png 를 훑어 목록을 만들므로,
# 같은 이름의 .png 가 없으면 지도를 떠도 앱 목록에 나타나지 않는다. 손으로 convert
# 를 한 번 빠뜨리면 "지도는 저장됐는데 앱에만 안 보이는" 상태가 된다.
#
# 왜 덮어쓰기를 거부하는가 — 지도 한 장은 사람이 로봇을 끌고 다닌 시간이다.
# 이름을 재활용하다 지우면 되돌릴 방법이 없다.
#
# 왜 저장 전에 SLAM 을 먼저 보는가 — map_saver_cli 는 /map 이 없어도 timeout 까지
# 조용히 기다린 뒤 빈 손으로 끝난다. 사람이 그 대기를 "저장 중"으로 오해한다.
#
# set -u 를 쓰지 않는다. ROS 2의 setup.bash 가 미정의 변수를 참조해서
# `AMENT_TRACE_SETUP_FILES: unbound variable` 로 즉시 죽는다.

NAME=${1:-}

ok()   { printf "  \033[32mOK\033[0m   %s\n" "$1"; }
bad()  { printf "  \033[31mNG\033[0m   %s\n" "$1"; }
warn() { printf "  \033[33m--\033[0m   %s\n" "$1"; }
die()  { printf "\n\033[31m[중단]\033[0m %s\n" "$1"; exit 1; }

# 워크스페이스. 터미네이터가 띄운 칸에서는 rc 가 이미 export 해 두었다.
# 단독 실행일 때만 스크립트 위치에서 유도한다.
if [ -z "$VICA_ROS_WS" ]; then
  VICA_ROS_WS=$(cd "$(dirname "${BASH_SOURCE[0]}")/../vica_ros2_ws" 2>/dev/null && pwd)
fi
MAPS="$VICA_ROS_WS/maps"

# ---------------------------------------------------------------------------
# 1. 인자 검증
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# 2. 덮어쓰기 방지
# ---------------------------------------------------------------------------
echo "--- 1) 덮어쓰기 확인 ---"
exists=""
# 금지구역 파일도 함께 본다(2026-08-31). 지도를 지울 때 이 셋이 같이 지워지지만,
# 손으로 pgm/png/yaml 만 지운 경우에는 남는다. 그 상태로 같은 이름의 새 지도를
# 저장하면 **다른 장소의 금지구역이 새 지도에 붙는다.**
for f in "$PGM" "$PNG" "$YAML" \
         "$MAPS/$NAME"_keepout.pgm "$MAPS/$NAME"_keepout.yaml \
         "$MAPS/$NAME"_keepout.json; do
  [ -e "$f" ] && exists="$exists  $f"$'\n'
done
if [ -n "$exists" ]; then
  printf "%s" "$exists"
  die "이 이름은 이미 있습니다. 다른 이름을 쓰세요.
       덮어쓰지 않는 것은 의도한 동작입니다 — 지운 지도는 되돌릴 수 없습니다."
fi
ok "$NAME 은 새 이름이다"
echo

# ---------------------------------------------------------------------------
# 3. SLAM 기동 확인
# ---------------------------------------------------------------------------
echo "--- 2) SLAM 확인 ---"
# pgrep -x 는 comm 을 본다. 리눅스 comm 은 15자에서 잘리므로 아래 이름도 15자다.
#   cartographer_occupancy_grid_node -> cartographer_oc
#   cartographer_node                -> cartographer_no
# 실제 잘린 이름은 실기에서 확인하기 전까지 [미검증]이다. 틀렸을 때 사람이 갇히지
# 않도록 건너뛰는 길을 함께 안내한다.
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

# ---------------------------------------------------------------------------
# 4. 저장
# ---------------------------------------------------------------------------
echo "--- 3) map_saver_cli ---"
source /opt/ros/humble/setup.bash
if [ -f "$VICA_ROS_WS/install/setup.bash" ]; then
  source "$VICA_ROS_WS/install/setup.bash"
fi
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-7}
export ROS_LOCALHOST_ONLY=${ROS_LOCALHOST_ONLY:-0}
export RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}

# map_saver_cli 의 기본 제한시간은 2 초다(save_map_timeout, 초 단위 double).
# 노드가 십수 개 떠 있으면 DDS 가 /map 구독을 맺는 데만 그 시간을 넘겨
# "Failed to spin map subscription" 으로 끝난다. 지도는 멀쩡히 발행 중인데도
# 실패하므로 사람이 SLAM 쪽을 의심하게 된다. 2026-08-12 실기에서 노드 16 개가
# 뜬 상태로 정확히 2.002 초에 잘렸고, 같은 순간 /map 은 882x334 로 정상이었다.
#
# 넉넉히 잡는 쪽이 옳다. 이 값은 "저장에 걸리는 시간"이 아니라 "포기하기까지
# 기다리는 시간"이라, 정상일 때는 /map 첫 장이 도착하는 즉시 끝나므로 크게 잡아도
# 느려지지 않는다. 손해는 실패할 때 그만큼 더 기다리는 것뿐인데, 그 대가로 잃는
# 것은 사람이 로봇을 끌고 다닌 시간 전부다. 위 3) SLAM 확인을 이미 통과한 뒤라
# 여기서 오래 걸린다면 그것은 "없는 지도"가 아니라 "늦게 오는 지도"다.
TIMEOUT=${VICA_MAP_SAVE_TIMEOUT:-120}
# 파라미터 타입이 double 이다. 정수로 넘기면 타입 불일치로 거부당한다.
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

# ---------------------------------------------------------------------------
# 5. 앱용 png 변환
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# 6. 검증
# ---------------------------------------------------------------------------
echo "--- 5) 검증 ---"
for f in "$PGM" "$PNG" "$YAML"; do
  if [ -f "$f" ]; then
    ok "$(basename "$f")  $(stat -c%s "$f") bytes"
  else
    bad "$(basename "$f") 없음"
  fi
done

# pgm 과 png 의 픽셀 크기가 다르면 앱 캔버스의 좌표 변환이 어긋난다.
# 앱은 yaml 의 resolution·origin 을 png 픽셀에 적용하기 때문이다.
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

# ---------------------------------------------------------------------------
# 7. CURRENT_MAP 기록
# ---------------------------------------------------------------------------
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
