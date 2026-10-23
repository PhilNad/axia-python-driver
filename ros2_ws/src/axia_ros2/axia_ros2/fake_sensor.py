"""An Axia RDT emulator on UDP, for trying the node and the tools without the sensor.

    python -m axia_ros2.fake_sensor [--port 49152] [--rate 1000] [--adc-rate 7812] [--drop 0.001]

Answers RDT requests like the sensor (continuous / n records / stop) to whoever sent them,
with a constant wrench plus noise, a slow sinusoid on Fz, optional dropped records and an
optional non-zero status word. Point the node at it with ip:=127.0.0.1 apply_config:=false.
"""

from __future__ import annotations

import argparse
import socket
import struct
import threading
import time

import numpy as np

from .rdt import CMD_BLOCK, CMD_CONTINUOUS, CMD_STOP, HEADER, RECORD


class FakeAxia:
    def __init__(self, host="127.0.0.1", port=49152, rate=1000.0, adc_rate=7812.0, cpf=1e6, cpt=1e6,
                 wrench=(0.5, -0.3, -9.3, 0.02, -0.01, 0.001), noise=(0.03, 0.002), drop=0.0, status=0,
                 records_per_packet=1, seed=0):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((host, port))
        self.sock.settimeout(0.1)
        self.port = self.sock.getsockname()[1]
        self.rate, self.adc_rate = float(rate), float(adc_rate)
        self.cpf, self.cpt = cpf, cpt
        self.wrench = np.asarray(wrench, float)
        self.noise = noise
        self.drop = drop
        self.status = status
        self.k = int(records_per_packet)
        self.rng = np.random.default_rng(seed)
        self.client = None
        self.remaining = 0          # 0 = stopped, -1 = continuous
        self.rdt_seq = 0
        self.sent = 0
        self.dropped = 0
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._threads = [threading.Thread(target=self._commands, daemon=True),
                         threading.Thread(target=self._stream, daemon=True)]

    def start(self):
        for th in self._threads:
            th.start()
        return self

    def stop(self):
        self._stop.set()
        for th in self._threads:
            th.join(timeout=2)
        self.sock.close()

    def _record(self, t):
        w = self.wrench.copy()
        w[2] += 0.5 * np.sin(2 * np.pi * 0.2 * t)
        w[:3] += self.rng.normal(0, self.noise[0], 3)
        w[3:] += self.rng.normal(0, self.noise[1], 3)
        counts = np.concatenate([np.round(w[:3] * self.cpf), np.round(w[3:] * self.cpt)]).astype(np.int64)
        ft_seq = int(t * self.adc_rate) & 0xFFFFFFFF
        return RECORD.pack(self.rdt_seq & 0xFFFFFFFF, ft_seq, self.status, *[int(c) for c in counts])

    def _commands(self):
        while not self._stop.is_set():
            try:
                data, addr = self.sock.recvfrom(64)
            except socket.timeout:
                continue
            except OSError:
                return
            if len(data) < 8:
                continue
            header, cmd, count = struct.unpack(">HHI", data[:8])
            if header != HEADER:
                continue
            with self._lock:
                self.client = addr
                if cmd == CMD_STOP:
                    self.remaining = 0
                elif cmd == CMD_CONTINUOUS:
                    self.remaining = -1 if count == 0 else count
                elif cmd == CMD_BLOCK:
                    self.remaining = max(1, count)

    def _stream(self):
        period = self.k / self.rate
        t0 = time.monotonic()
        next_t = t0
        while not self._stop.is_set():
            with self._lock:
                active, client = self.remaining != 0 and self.client is not None, self.client
            if not active:
                time.sleep(0.001)
                next_t = time.monotonic()
                continue
            delay = next_t - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            packet = b""
            for _ in range(self.k):
                rec = self._record(next_t - t0)
                self.rdt_seq += 1
                if self.drop and self.rng.random() < self.drop:
                    self.dropped += 1
                    continue
                packet += rec
            if packet:
                try:
                    self.sock.sendto(packet, client)
                except OSError:
                    return
                self.sent += len(packet) // RECORD.size
            next_t += period
            with self._lock:
                if self.remaining > 0:
                    self.remaining = max(0, self.remaining - self.k)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=49152)
    ap.add_argument("--rate", type=float, default=1000.0)
    ap.add_argument("--adc-rate", type=float, default=7812.0)
    ap.add_argument("--drop", type=float, default=0.0, help="probability of dropping a record")
    ap.add_argument("--status", type=lambda s: int(s, 0), default=0, help="status word to report")
    args = ap.parse_args(argv)
    fake = FakeAxia(args.host, args.port, args.rate, args.adc_rate, drop=args.drop, status=args.status).start()
    print(f"fake Axia on {args.host}:{fake.port} at {args.rate:g} Hz (Ctrl-C to stop)")
    try:
        while True:
            time.sleep(5)
            print(f"sent {fake.sent} records, dropped {fake.dropped}")
    except KeyboardInterrupt:
        fake.stop()


if __name__ == "__main__":
    main()
