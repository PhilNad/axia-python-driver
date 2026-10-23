"""The Axia's RDT stream (UDP 49152): requests, parsing, sequence and status bookkeeping.

Request: 8 bytes big-endian  0x1234 | command (0 stop, 1 n records, 3 continuous) | count.
Record:  36 bytes big-endian uint32 rdt_sequence, uint32 ft_sequence, uint32 status,
         int32 Fx Fy Fz Tx Ty Tz (counts; / cpf, / cpt for N and N m). Several records may be
         packed in one datagram (rdtSize).

Same protocol as AxiaDriver.udp_listener.AxiaUdpListener, without its liabilities for a
long-running node: the socket has a receive timeout (so the reader can stop), no telnet session
is opened (and leaked) to "test" the connection, the status word is checked, and missed records
are counted from rdt_sequence (ft_sequence advances at the ADC rate, so its gaps are not misses
when rdtRate < adcRate).
"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass, field

import numpy as np

HEADER = 0x1234
CMD_STOP, CMD_BLOCK, CMD_CONTINUOUS = 0, 1, 3
RECORD = struct.Struct(">IIIiiiiii")
RECORD_SIZE = RECORD.size          # 36


def request(command, count=0):
    return struct.pack(">HHI", HEADER, command & 0xFFFF, count & 0xFFFFFFFF)


def parse(data, cpf, cpt):
    """(n, 9) float array: rdt_seq, ft_seq, status, Fx, Fy, Fz [N], Tx, Ty, Tz [N m]."""
    n = len(data) // RECORD_SIZE
    if n == 0:
        return np.zeros((0, 9))
    raw = np.frombuffer(data[: n * RECORD_SIZE], dtype=">u4").reshape(n, 9).astype(np.int64)
    out = np.empty((n, 9))
    out[:, 0:3] = raw[:, 0:3]
    signed = raw[:, 3:9]
    signed = np.where(signed >= 2 ** 31, signed - 2 ** 32, signed).astype(float)
    out[:, 3:6] = signed[:, 0:3] / float(cpf)
    out[:, 6:9] = signed[:, 3:6] / float(cpt)
    return out


@dataclass
class StreamStats:
    packets: int = 0
    records: int = 0
    missed: int = 0                 # records lost, from rdt_sequence gaps
    reordered: int = 0
    status_errors: int = 0          # records with a non-zero status word
    last_status: int = 0
    timeouts: int = 0
    _last_seq: int | None = field(default=None, repr=False)

    def update(self, records):
        self.packets += 1
        self.records += len(records)
        for seq, status in zip(records[:, 0].astype(np.int64), records[:, 2].astype(np.int64)):
            if self._last_seq is not None and seq != self._last_seq:
                delta = (int(seq) - self._last_seq) % (2 ** 32)
                if delta > 2 ** 31:
                    self.reordered += 1
                    continue
                if delta > 1:
                    self.missed += delta - 1
            self._last_seq = int(seq)
            if status:
                self.status_errors += 1
                self.last_status = int(status)


class RdtStream:
    def __init__(self, ip, port=49152, cpf=1_000_000, cpt=1_000_000, records_per_packet=1,
                 timeout=0.5, rcvbuf=4 * 1024 * 1024):
        self.address = (ip, int(port))
        self.cpf, self.cpt = float(cpf), float(cpt)
        self.bufsize = max(2048, RECORD_SIZE * int(records_per_packet) + 64)
        self.timeout = timeout
        self.rcvbuf = rcvbuf
        self.sock = None
        self.stats = StreamStats()

    def open(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.rcvbuf)
        self.sock.bind(("0.0.0.0", 0))
        self.sock.settimeout(self.timeout)
        return self

    def close(self):
        if self.sock is not None:
            try:
                self.stop()
            except OSError:
                pass
            self.sock.close()
            self.sock = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()

    def send(self, payload):
        self.sock.sendto(payload, self.address)

    def start(self):
        self.send(request(CMD_CONTINUOUS, 0))

    def stop(self):
        self.send(request(CMD_STOP, 0))

    def request_block(self, n):
        self.send(request(CMD_BLOCK, n))

    def read(self):
        """Records of the next datagram ((n, 9) array), or None after `timeout` without data."""
        try:
            data, sender = self.sock.recvfrom(self.bufsize)
        except socket.timeout:
            self.stats.timeouts += 1
            return None
        if sender[0] != self.address[0]:
            return np.zeros((0, 9))
        records = parse(data, self.cpf, self.cpt)
        if len(records):
            self.stats.update(records)
        return records
