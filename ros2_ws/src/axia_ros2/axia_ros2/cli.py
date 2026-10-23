"""Axia tools without ROS.

    python -m axia_ros2.cli config show                       # settings, firmware, status (telnet)
    python -m axia_ros2.cli config set --rdt 1000 [--adc 7812 --filter 0 --calib 0] [--save]
    python -m axia_ros2.cli record --seconds 30 --out /tmp/axia.csv [--rdt 7812]

`record` prints the per-axis standard deviation of the recording: standing still, those are
the numbers for covSigmaw (their squares) in the estimator's joe_axia_payload.yaml.
Settings are changed in RAM only unless --save (which writes the sensor's NVM).
"""

from __future__ import annotations

import argparse
import csv
import sys
import time

import numpy as np

from .paths import default_sensor_yaml


def _sensor(args):
    from AxiaDriver.configuration import AxiaConfiguration

    cfg = AxiaConfiguration()
    cfg.load_from_yaml(args.yaml)
    return cfg, args.ip or cfg.ip_address


def cmd_config(args):
    from .telnet_session import apply_runtime_config, read_configuration, telnet_session

    _, ip = _sensor(args)
    with telnet_session(ip) as com:
        if args.action == "set":
            changes = apply_runtime_config(com, adc_rate=args.adc, rdt_rate=args.rdt, filter_index=args.filter,
                                           calibration=args.calib, disable_bias=True, save=args.save)
            print(f"changed: {changes or 'nothing'}{' (SAVED to NVM)' if args.save else ' (RAM only)'}")
        live = read_configuration(com)
        ok, bad = com.get_status()
    s = live._settings_dict
    print(f"{ip}: {live.product_name} {live.current_config_serial_num} ({live.current_config_part_num}), "
          f"firmware {live.firmware_version}, calibrated {s.get('calTime')}")
    print(f"  adcRate {s.get('adcRate')} Hz, rdtRate {s.get('rdtRate')} Hz, rdtSize {s.get('rdtSize')}, "
          f"filTc {s.get('filTc')} (cutoff {live.filter_cutoff_frequency}), calib {s.get('calib')}, "
          f"cpf {s.get('cpf')}, cpt {s.get('cpt')}")
    print(f"  status {'GOOD' if ok else 'BAD'}" + ("" if ok else ":\n    " + "\n    ".join(bad)))
    return 0 if ok else 1


def cmd_record(args):
    from .rdt import RdtStream
    from .sequence_clock import SequenceClock

    cfg, ip = _sensor(args)
    adc = int(cfg.adc_rate or 7812)
    if args.rdt:
        from .telnet_session import apply_runtime_config, read_configuration, telnet_session

        with telnet_session(ip) as com:
            apply_runtime_config(com, rdt_rate=args.rdt)
            live = read_configuration(com)
        adc = int(live.adc_rate)
    clock = SequenceClock(adc)
    rows = []
    with RdtStream(ip, int(cfg.udp_port or 49152), cfg.counts_per_force, cfg.counts_per_torque,
                   int(cfg.udp_records_per_packet or 1)) as s:
        s.start()
        t0 = time.time()
        while time.time() - t0 < args.seconds:
            r = s.read()
            if r is None:
                continue
            t_recv = time.time()
            for rec in r:
                rows.append([clock.stamp(rec[1], t_recv), t_recv, *rec])
        stats = s.stats
    if not rows:
        print(f"no data from {ip} in {args.seconds} s")
        return 1
    a = np.asarray(rows)
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_stamp", "t_recv", "rdt_seq", "ft_seq", "status", "Fx", "Fy", "Fz", "Tx", "Ty", "Tz"])
        for r in a:
            w.writerow([f"{r[0]:.6f}", f"{r[1]:.6f}", int(r[2]), int(r[3]), int(r[4])] + [f"{v:.6f}" for v in r[5:11]])
    dur = a[-1, 0] - a[0, 0]
    sd = a[:, 5:11].std(axis=0)
    print(f"{len(a)} records in {dur:.2f} s ({len(a) / max(dur, 1e-9):.1f} Hz), missed {stats.missed}, "
          f"status errors {stats.status_errors}, timeouts {stats.timeouts} -> {args.out}")
    print(f"  mean  F {np.round(a[:, 5:8].mean(0), 4).tolist()} N, T {np.round(a[:, 8:11].mean(0), 5).tolist()} N m")
    print(f"  std   F {np.round(sd[:3], 4).tolist()} N, T {np.round(sd[3:], 5).tolist()} N m")
    print(f"  covSigmaw (variances) {np.round(sd ** 2, 8).tolist()}")
    return 0 if stats.missed == 0 and stats.status_errors == 0 else 2


def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--yaml", default=default_sensor_yaml(), help="sensor YAML (ip, cpf/cpt)")
    common.add_argument("--ip", default=None, help="sensor IP (default: the YAML's)")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    c = sub.add_parser("config", parents=[common])
    c.add_argument("action", choices=["show", "set"], nargs="?", default="show")
    c.add_argument("--adc", type=int)
    c.add_argument("--rdt", type=int)
    c.add_argument("--filter", type=int)
    c.add_argument("--calib", type=int)
    c.add_argument("--save", action="store_true", help="write the sensor's non-volatile memory")
    r = sub.add_parser("record", parents=[common])
    r.add_argument("--seconds", type=float, default=30.0)
    r.add_argument("--out", default=time.strftime("/tmp/axia_%Y%m%d-%H%M%S.csv"))
    r.add_argument("--rdt", type=int, default=None, help="set the RDT rate first (RAM only)")
    args = ap.parse_args(argv)
    return cmd_config(args) if args.command == "config" else cmd_record(args)


if __name__ == "__main__":
    sys.exit(main())
