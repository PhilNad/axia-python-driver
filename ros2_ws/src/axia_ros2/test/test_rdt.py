import time

import numpy as np

from axia_ros2.fake_sensor import FakeAxia
from axia_ros2.rdt import RECORD, RdtStream, StreamStats, parse, request


def test_request_bytes_match_the_original_driver():
    from AxiaDriver.udp_listener import AxiaUdpListener

    for cmd, count in ((0, 0), (1, 5), (3, 0)):
        assert request(cmd, count) == AxiaUdpListener._rdt_request(None, cmd, count)


def test_parse_scales_and_signs_several_records():
    recs = [(7, 100, 0, -1_500_000, 2_000_000, -9_810_000, 12_345, -6_789, 1), (8, 108, 0x40, 1, 2, 3, 4, 5, 6)]
    data = b"".join(RECORD.pack(*r) for r in recs)
    out = parse(data, 1e6, 1e6)
    assert out.shape == (2, 9)
    assert np.allclose(out[0], [7, 100, 0, -1.5, 2.0, -9.81, 0.012345, -0.006789, 1e-6])
    assert out[1, 2] == 0x40


def test_stats_count_missed_records_and_status():
    s = StreamStats()
    rows = np.zeros((5, 9))
    rows[:, 0] = [1, 2, 5, 6, 7]                     # 3 and 4 lost
    rows[3, 2] = 0x20
    s.update(rows)
    assert s.missed == 2 and s.status_errors == 1 and s.last_status == 0x20
    wrap = np.zeros((2, 9))
    wrap[:, 0] = [2 ** 32 - 1, 0]                    # counter wrap is not a gap
    s2 = StreamStats()
    s2.update(wrap)
    assert s2.missed == 0


def test_stream_against_the_emulator_counts_its_drops():
    fake = FakeAxia(port=0, rate=1000, drop=0.005, seed=3).start()
    try:
        with RdtStream("127.0.0.1", fake.port, timeout=0.2) as s:
            s.start()
            t0, n = time.monotonic(), 0
            while time.monotonic() - t0 < 2.0:
                r = s.read()
                if r is not None:
                    n += len(r)
            s.stop()
            time.sleep(0.05)
            stats = s.stats
    finally:
        fake.stop()
    assert 1700 < n < 2100
    assert fake.dropped > 0 and abs(stats.missed - fake.dropped) <= 1   # a drop after the last read is unseen
