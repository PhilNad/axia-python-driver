"""The Axia80 node.  ros2 launch axia_ros2 axia.launch.py [ip:=...] [rdt_rate:=1000] [apply_config:=false]"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _node(context):
    params = [os.path.join(get_package_share_directory("axia_ros2"), "config", "joe.yaml")]
    overrides = {}
    for name in ("ip", "config_yaml", "record_csv", "stamp_mode"):
        v = LaunchConfiguration(name).perform(context)
        if v:
            overrides[name] = v
    for name in ("rdt_rate", "port"):
        v = LaunchConfiguration(name).perform(context)
        if v:
            overrides[name] = int(v)
    for name in ("apply_config", "require_telnet"):
        v = LaunchConfiguration(name).perform(context)
        if v:
            overrides[name] = v.lower() in ("1", "true", "yes")
    return [Node(package="axia_ros2", executable="axia_node", name="axia", output="screen",
                 sigterm_timeout="10", parameters=params + [overrides])]


def generate_launch_description():
    args = [DeclareLaunchArgument(n, default_value="") for n in
            ("ip", "config_yaml", "record_csv", "stamp_mode", "rdt_rate", "port", "apply_config", "require_telnet")]
    return LaunchDescription(args + [OpaqueFunction(function=_node)])
