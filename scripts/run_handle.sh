#!/bin/bash
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
