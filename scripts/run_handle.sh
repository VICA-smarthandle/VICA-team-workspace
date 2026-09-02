#!/bin/bash
# 스마트핸들(안내+초음파) 노드를 "메인 워크스페이스 빌드"로 확실하게 띄운다.
#
#   bash ~/VICA-smarthandle/scripts/run_handle.sh
#
# env -i 로 환경을 백지에서 다시 쌓는다 — 칸(pane)에 다른 worktree overlay 가
# 어떤 순서로 소싱돼 있어도 영향을 받지 않는다 (2026-09-02, wt-turnguide
# overlay 잔재가 ↑ 재시작마다 옛 빌드를 잡던 문제의 최종 처방).
exec env -i HOME="$HOME" USER="$USER" TERM="${TERM:-xterm}" LANG="${LANG:-C.UTF-8}" \
    PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    bash --noprofile --norc -c '
source /opt/ros/humble/setup.bash
source /home/ji_w/VICA-smarthandle/vica_ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=7
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
echo "[run_handle] 사용할 빌드: $(ros2 pkg prefix vica_user_guidance)"
exec ros2 launch vica_user_guidance user_guidance.launch.py
'
