#!/usr/bin/env bash
# Sourced by pixi on activation: ROS 2 middleware as on the lab's FR3 network (robots-bringup),
# the repository on PYTHONPATH (AxiaDriver), and the colcon overlay when it is built.
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_cyclonedds_cpp}"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
export RCUTILS_COLORIZED_OUTPUT=1
export RCUTILS_CONSOLE_OUTPUT_FORMAT="[{severity}] [{name}]: {message}"
_axia_root="${PIXI_PROJECT_ROOT:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
if [ -z "${CYCLONEDDS_URI:-}" ] && [ -f "${_axia_root}/config/cyclonedds.xml" ]; then
  export CYCLONEDDS_URI="file://${_axia_root}/config/cyclonedds.xml"
fi
export PYTHONPATH="${_axia_root}${PYTHONPATH:+:${PYTHONPATH}}"
export ROS_HOME="${ROS_HOME:-${_axia_root}/ros2_ws/.ros}"
export ROS_LOG_DIR="${ROS_LOG_DIR:-${ROS_HOME}/log}"
if [ -f "${_axia_root}/ros2_ws/install/local_setup.bash" ]; then
  # shellcheck source=/dev/null
  source "${_axia_root}/ros2_ws/install/local_setup.bash"
fi
unset _axia_root
