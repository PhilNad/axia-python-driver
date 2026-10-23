"""axia_node: the ATI Axia80 as a ROS 2 node.

    ros2 launch axia_ros2 axia.launch.py [rdt_rate:=1000] [ip:=192.168.3.101] [record_csv:=/tmp/a.csv]

At start-up (telnet, port 23, main thread, RAM only): set adcRate / rdtRate / filTc / calib if
they differ from the parameters, disable the sensor-side bias, read back cpf/cpt and status.
Then the RDT stream (UDP 49152) is read in its own thread and every record is published.

Publishes
  /axia/wrench       geometry_msgs/WrenchStamped  raw sensor values (N, N m) in the sensor's own
                     frame and sign, minus the software zero if one was set with ~/zero.
                     header.stamp from the sample counter (SequenceClock), frame_id axia_sensor.
                     QoS best effort, depth 50.
  /axia/diagnostics  diagnostic_msgs/DiagnosticArray, 1 Hz: rate, missed records, status word,
                     timeouts, clock, zero, sensor settings.
Services ~/start, ~/stop (stream), ~/zero (software zero = mean of the last second),
~/clear_zero (std_srvs/Trigger), ~/set_recording (std_srvs/SetBool: CSV on/off).
Do not zero during an estimation run: the estimator estimates the bias itself.
"""

from __future__ import annotations

import csv
import threading
import time
from collections import deque

import numpy as np
import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from geometry_msgs.msg import WrenchStamped
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_srvs.srv import SetBool, Trigger

from .paths import default_sensor_yaml
from .rdt import RdtStream
from .sequence_clock import SequenceClock

QOS = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=50, reliability=ReliabilityPolicy.BEST_EFFORT)


class AxiaNode(Node):
    def __init__(self):
        super().__init__("axia")
        p = self.declare_parameter
        p("config_yaml", default_sensor_yaml())
        p("ip", "")
        p("port", 0)
        p("adc_rate", 7812)
        p("rdt_rate", 1000)
        p("filter_index", -1)        # -1: leave the sensor's setting
        p("calibration", -1)         # -1: leave the sensor's setting
        p("apply_config", True)
        p("disable_bias", True)
        p("require_telnet", True)
        p("frame_id", "axia_sensor")
        p("topic", "/axia/wrench")
        p("diagnostics_topic", "/axia/diagnostics")
        p("stamp_mode", "sequence")  # sequence | receive
        p("clock_counter", "ft_sequence")
        p("publish_every", 1)
        p("record_csv", "")
        g = lambda name: self.get_parameter(name).value  # noqa: E731

        from AxiaDriver.configuration import AxiaConfiguration

        cfg = AxiaConfiguration()
        cfg.load_from_yaml(g("config_yaml"))
        self.ip = g("ip") or cfg.ip_address
        port = int(g("port") or cfg.udp_port or 49152)
        cpf, cpt = cfg.counts_per_force, cfg.counts_per_torque
        records_per_packet = int(cfg.udp_records_per_packet or 1)
        self.sensor_info = {"serial": cfg.current_config_serial_num, "part": cfg.current_config_part_num,
                            "source": "yaml"}
        adc_rate, rdt_rate = int(g("adc_rate")), int(g("rdt_rate"))
        if g("apply_config"):
            try:
                from .telnet_session import apply_runtime_config, read_configuration, telnet_session

                with telnet_session(self.ip) as com:
                    changes = apply_runtime_config(
                        com, adc_rate=adc_rate, rdt_rate=rdt_rate,
                        filter_index=None if g("filter_index") < 0 else int(g("filter_index")),
                        calibration=None if g("calibration") < 0 else int(g("calibration")),
                        disable_bias=bool(g("disable_bias")))
                    live = read_configuration(com)
                cpf, cpt = live.counts_per_force, live.counts_per_torque
                adc_rate, rdt_rate = int(live.adc_rate), int(live.udp_transmit_rate)
                records_per_packet = int(live.udp_records_per_packet or 1)
                self.sensor_info = {"serial": live.current_config_serial_num, "part": live.current_config_part_num,
                                    "firmware": live.firmware_version, "good_status": live.is_good_status,
                                    "calib": live.calibration_number, "filTc": live.filter_intensity,
                                    "changes": str(changes), "source": "telnet"}
                self.get_logger().info(f"sensor {self.sensor_info['serial']} ({self.sensor_info['part']}): "
                                       f"adc {adc_rate} Hz, rdt {rdt_rate} Hz, filTc {live.filter_intensity}, "
                                       f"calib {live.calibration_number}, status {'GOOD' if live.is_good_status else 'BAD'}"
                                       f"{'; changed (RAM only) ' + str(changes) if changes else ''}")
            except Exception as e:
                if g("require_telnet"):
                    raise RuntimeError(f"telnet configuration of {self.ip} failed: {e} "
                                       f"(apply_config:=false to stream with the stored settings)") from e
                self.get_logger().warn(f"telnet configuration failed ({e}); streaming with the stored settings")
        self.adc_rate, self.rdt_rate = adc_rate, rdt_rate
        counter = g("clock_counter")
        self.counter_col = 1 if counter == "ft_sequence" else 0
        self.clock = SequenceClock(adc_rate if counter == "ft_sequence" else rdt_rate)
        self.stamp_mode = g("stamp_mode")
        self.frame_id = g("frame_id")
        self.every = max(1, int(g("publish_every")))
        self.stream = RdtStream(self.ip, port, cpf, cpt, records_per_packet).open()
        self.pub = self.create_publisher(WrenchStamped, g("topic"), QOS)
        self.pub_diag = self.create_publisher(DiagnosticArray, g("diagnostics_topic"), 10)
        self.zero = np.zeros(6)
        self.recent = deque(maxlen=max(10, rdt_rate))
        self.arrivals = deque()
        self.lock = threading.Lock()
        self.csv = None
        if g("record_csv"):
            self._open_csv(g("record_csv"))
        self.create_service(Trigger, "~/start", self._srv_start)
        self.create_service(Trigger, "~/stop", self._srv_stop)
        self.create_service(Trigger, "~/zero", self._srv_zero)
        self.create_service(Trigger, "~/clear_zero", self._srv_clear_zero)
        self.create_service(SetBool, "~/set_recording", self._srv_recording)
        self.create_timer(1.0, self._diagnostics)
        self._running = True
        self.published = 0
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self.stream.start()
        self._thread.start()
        self.get_logger().info(f"streaming {self.ip}:{port} -> {g('topic')} ({self.stamp_mode} stamps)")

    # -- streaming ----------------------------------------------------------------------------
    def _reader(self):
        k = 0
        msg = WrenchStamped()
        msg.header.frame_id = self.frame_id
        while self._running:
            records = self.stream.read()
            if records is None or not len(records):
                continue
            t_recv = time.time()
            with self.lock:
                self.arrivals.append((time.monotonic(), len(records)))
            for rec in records:
                if self.stamp_mode == "sequence":
                    t = self.clock.stamp(rec[self.counter_col], t_recv)
                else:
                    t = t_recv
                w = rec[3:9] - self.zero
                self.recent.append(rec[3:9])
                if self.csv is not None:
                    self.csv[1].writerow([f"{t:.6f}", f"{t_recv:.6f}", int(rec[0]), int(rec[1]), int(rec[2])]
                                         + [f"{v:.6f}" for v in rec[3:9]])
                k += 1
                if k % self.every:
                    continue
                sec = int(t)
                msg.header.stamp.sec, msg.header.stamp.nanosec = sec, int((t - sec) * 1e9)
                (msg.wrench.force.x, msg.wrench.force.y, msg.wrench.force.z,
                 msg.wrench.torque.x, msg.wrench.torque.y, msg.wrench.torque.z) = (float(v) for v in w)
                self.pub.publish(msg)
                self.published += 1

    def _rate(self):
        now = time.monotonic()
        with self.lock:
            while self.arrivals and self.arrivals[0][0] < now - 1.0:
                self.arrivals.popleft()
            return float(sum(n for _, n in self.arrivals))

    def _diagnostics(self):
        s = self.stream.stats
        rate = self._rate()
        st = DiagnosticStatus(name="axia", hardware_id=str(self.sensor_info.get("serial")))
        if rate < 0.9 * self.rdt_rate:
            st.level, st.message = DiagnosticStatus.ERROR, f"rate {rate:.0f} Hz < {self.rdt_rate} Hz"
        elif s.status_errors:
            st.level, st.message = DiagnosticStatus.ERROR, f"status word 0x{s.last_status:08X}"
        elif s.missed:
            st.level, st.message = DiagnosticStatus.WARN, f"{s.missed} records missed"
        else:
            st.level, st.message = DiagnosticStatus.OK, "streaming"
        values = {"rate_hz": f"{rate:.1f}", "rdt_rate": str(self.rdt_rate), "adc_rate": str(self.adc_rate),
                  "records": str(s.records), "missed": str(s.missed), "reordered": str(s.reordered),
                  "status_errors": str(s.status_errors), "last_status": f"0x{s.last_status:08X}",
                  "timeouts": str(s.timeouts), "published": str(self.published),
                  "clock_period_us": f"{1e6 * self.clock.period:.4f}", "clock_resets": str(self.clock.resets),
                  "zero": str(np.round(self.zero, 4).tolist()), "recording": str(self.csv is not None),
                  **{f"sensor_{k}": str(v) for k, v in self.sensor_info.items()}}
        if len(self.recent) > 10:
            sd = np.std(np.asarray(self.recent), axis=0)
            values["std_last_s"] = str(np.round(sd, 5).tolist())
        st.values = [KeyValue(key=k, value=v) for k, v in values.items()]
        arr = DiagnosticArray()
        arr.header.stamp = self.get_clock().now().to_msg()
        arr.status = [st]
        self.pub_diag.publish(arr)

    # -- services -----------------------------------------------------------------------------
    def _srv_start(self, req, res):
        self.stream.start()
        res.success, res.message = True, "stream started"
        return res

    def _srv_stop(self, req, res):
        self.stream.stop()
        res.success, res.message = True, "stream stopped"
        return res

    def _srv_zero(self, req, res):
        if len(self.recent) < 10:
            res.success, res.message = False, "not enough recent samples"
            return res
        self.zero = np.mean(np.asarray(self.recent), axis=0)
        res.success, res.message = True, f"zero {np.round(self.zero, 4).tolist()}"
        self.get_logger().warn(f"software zero set: {res.message}")
        return res

    def _srv_clear_zero(self, req, res):
        self.zero = np.zeros(6)
        res.success, res.message = True, "zero cleared"
        return res

    def _open_csv(self, path):
        f = open(path, "w", newline="")
        w = csv.writer(f)
        w.writerow(["t_stamp", "t_recv", "rdt_seq", "ft_seq", "status", "Fx", "Fy", "Fz", "Tx", "Ty", "Tz"])
        self.csv = (f, w)
        self.get_logger().info(f"recording raw records to {path}")

    def _srv_recording(self, req, res):
        if req.data and self.csv is None:
            path = time.strftime("/tmp/axia_%Y%m%d-%H%M%S.csv")
            self._open_csv(path)
            res.message = path
        elif not req.data and self.csv is not None:
            self.csv[0].close()
            self.csv = None
            res.message = "stopped"
        res.success = True
        return res

    def shutdown(self):
        self._running = False
        self._thread.join(timeout=2)
        self.stream.close()
        if self.csv is not None:
            self.csv[0].close()


def main(args=None):
    rclpy.init(args=args)
    node = AxiaNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
