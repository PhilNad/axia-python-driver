"""axia_watch: a readable view of /axia/wrench (the topic itself runs at 1 kHz).

    pixi run axia-watch [--rate 5] [--topic /axia/wrench]

Prints, a few times per second, the mean force and torque over the last interval and their
change since the start (the first second is the baseline). Press on the gripper and watch
which component moves: pushing it toward the robot along the tool axis changes Fz.
"""

from __future__ import annotations

import argparse
import sys
import time

import numpy as np


def main(argv=None):
    import rclpy
    from geometry_msgs.msg import WrenchStamped
    from rclpy.node import Node
    from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--topic", default="/axia/wrench")
    ap.add_argument("--rate", type=float, default=5.0, help="lines per second")
    args, ros_args = ap.parse_known_args(argv)

    rclpy.init(args=ros_args)
    node = Node("axia_watch")
    buf = []
    state = {"baseline": None, "base_buf": [], "t0": time.monotonic()}

    def on_msg(m):
        f, t = m.wrench.force, m.wrench.torque
        buf.append((f.x, f.y, f.z, t.x, t.y, t.z))

    def tick():
        if not buf:
            print(f"waiting for {args.topic} ...", flush=True)
            return
        w = np.asarray(buf)
        buf.clear()
        mean = w.mean(axis=0)
        if state["baseline"] is None:
            state["base_buf"].append(mean)
            if time.monotonic() - state["t0"] >= 1.0:
                state["baseline"] = np.mean(state["base_buf"], axis=0)
                print("baseline taken: now press on the gripper", flush=True)
            return
        d = mean - state["baseline"]
        print(f"F [{mean[0]:8.3f} {mean[1]:8.3f} {mean[2]:8.3f}] N  dF [{d[0]:+7.3f} {d[1]:+7.3f} {d[2]:+7.3f}] N   "
              f"T [{mean[3]:7.4f} {mean[4]:7.4f} {mean[5]:7.4f}] Nm  dT [{d[3]:+7.4f} {d[4]:+7.4f} {d[5]:+7.4f}] Nm   "
              f"({len(w)} samples)", flush=True)

    qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=200, reliability=ReliabilityPolicy.BEST_EFFORT)
    node.create_subscription(WrenchStamped, args.topic, on_msg, qos)
    node.create_timer(1.0 / args.rate, tick)
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
