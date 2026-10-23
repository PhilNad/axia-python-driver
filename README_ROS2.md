# Axia80 on ROS 2 (Jazzy) through pixi

`ros2_ws/src/axia_ros2` publishes the Axia80 on ROS 2. It is built on `AxiaDriver`, whose
modules are unchanged; the ROS 1 publisher stays as it was. Everything runs from this
repository's pixi workspace (conda-forge + robostack-jazzy). The ROS settings match the lab's
FR3 network: CycloneDDS, `ROS_DOMAIN_ID=42`, unicast discovery (`config/cyclonedds.xml`).

```bash
pixi install && pixi run build && pixi run test     # 7 tests against an RDT emulator, no sensor
pixi run axia-config show                           # telnet: settings, firmware, status
pixi run axia-node                                  # -> /axia/wrench, /axia/diagnostics
pixi run axia-record --seconds 30 --rdt 7812        # raw CSV without ROS, prints the noise
pixi run fake-sensor                                # emulator; then: pixi run axia-node ip:=127.0.0.1 apply_config:=false
```

## What the node does

1. **Configures the sensor at start-up** over telnet (port 23):
   - sets `adcRate` 7812, `rdtRate` 1000, `filTc` 0 and `calib` 0 if they differ;
   - disables the sensor-side bias;
   - reads back `cpf`/`cpt` and the status.

   All of this is in RAM only: `AxiaCommunication.write_configuration()` would `saveall`
   to NVM, so the node never calls it. The command `axia-config set ... --save` persists
   explicitly.
2. **Reads the RDT stream** (UDP 49152) in its own thread. The socket has a receive timeout,
   no telnet session is left open, the status word is checked, and missed records are counted
   from `rdt_sequence`.
3. **Stamps every record from the sensor's sample counter.** It uses `ft_sequence` at the ADC
   rate, with the crystal drift fitted, on the lower envelope of the arrival times
   (`sequence_clock.py`). The stamps are regular and carry no network jitter.
4. **Publishes** `/axia/wrench` (`geometry_msgs/WrenchStamped`, best effort, frame
   `axia_sensor`). The values are raw: the sensor's own sign and axes, in N and N m. The
   estimator applies its configured sign and frame.
5. **Reports** `/axia/diagnostics` at 1 Hz: rate, missed records, status word, timeouts, the
   clock, and the last second's standard deviations.

Services: `/axia/start`, `/axia/stop`, `/axia/zero` and `/axia/clear_zero` (software zero; do
not zero during estimation runs), and `/axia/set_recording` (CSV).

Parameters live in `ros2_ws/src/axia_ros2/config/joe.yaml`; the launch arguments are `ip`,
`rdt_rate`, `apply_config`, `require_telnet`, `record_csv` and `stamp_mode`. The sensor itself
is described by `Axia_Joe_Config.yaml`: FT45616, SI-150-8, 192.168.3.101.

## Network

The sensor is 192.168.3.101 on Joe's switch. duolith needs an address on that subnet, for
example `sudo ip addr add 192.168.3.1/24 dev br0`.

The step-by-step test with the robot and the payload estimator is in
`~/auto_ft_debiasing/ros2_ws/README.md`.

## Notes on the original driver

These were found while wrapping it; the new code avoids them, and `AxiaDriver` is unchanged:

- `setup.py` requires `rospy`, so the package is imported from the repository (`PYTHONPATH`,
  set by the pixi activation) instead of being pip-installed.
- `AxiaUdpListener` has three problems: its `recv` has no timeout, `stop_listening_thread()`
  does not join, and `connect()` opens a telnet session it never closes.
- `asyncio.get_event_loop()` in `AxiaCommunication` needs a current loop on Python 3.12;
  `telnet_session.py` provides one.
- `data_management._detect_missed_records` diffs `ft_sequence`, which advances at the ADC
  rate. That is not a miss when `rdtRate < adcRate`.
