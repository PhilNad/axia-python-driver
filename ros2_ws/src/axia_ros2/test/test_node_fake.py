"""The node end to end against the RDT emulator (no telnet), in-process."""

import threading
import time

import pytest

rclpy = pytest.importorskip("rclpy")


def test_node_publishes_the_emulated_stream():
    from geometry_msgs.msg import WrenchStamped
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.parameter import Parameter

    from axia_ros2.axia_node import QOS
    from axia_ros2.fake_sensor import FakeAxia

    fake = FakeAxia(port=0, rate=1000).start()
    rclpy.init()
    try:
        from rclpy.node import Node

        overrides = [Parameter("ip", value="127.0.0.1"), Parameter("port", value=fake.port),
                     Parameter("apply_config", value=False), Parameter("rdt_rate", value=1000),
                     Parameter("topic", value="/test_axia/wrench"), Parameter("diagnostics_topic", value="/test_axia/diag")]

        node = _make_node(overrides)
        sub = Node("listener")
        got = []
        sub.create_subscription(WrenchStamped, "/test_axia/wrench", lambda m: got.append(m), QOS)
        ex = MultiThreadedExecutor()
        ex.add_node(node)
        ex.add_node(sub)
        th = threading.Thread(target=ex.spin, daemon=True)
        th.start()
        time.sleep(3.0)
        ex.shutdown()
        node.shutdown()
        assert len(got) > 1500, len(got)
        stamps = [m.header.stamp.sec + 1e-9 * m.header.stamp.nanosec for m in got]
        assert all(b > a for a, b in zip(stamps, stamps[1:]))           # monotonic sequence stamps
        assert abs(got[-1].wrench.force.z - (-9.3)) < 0.7
        assert got[0].header.frame_id == "axia_sensor"
    finally:
        fake.stop()
        rclpy.shutdown()


def _make_node(overrides):
    from axia_ros2.axia_node import AxiaNode
    import rclpy.node

    original = rclpy.node.Node.__init__

    def patched(self, name, **kw):
        kw.setdefault("parameter_overrides", overrides)
        original(self, name, **kw)

    rclpy.node.Node.__init__ = patched
    try:
        return AxiaNode()
    finally:
        rclpy.node.Node.__init__ = original
