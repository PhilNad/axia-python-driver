import numpy as np

from axia_ros2.sequence_clock import SequenceClock


def test_stamps_follow_the_counter_not_the_jitter():
    rng = np.random.default_rng(0)
    adc, rdt = 7812.0, 1000.0
    drift = 1 + 100e-6                                # the sensor's crystal is 100 ppm off
    t_true = np.arange(0, 40, 1 / rdt)                # sample instants
    counter = np.floor(t_true * adc * drift).astype(np.int64) + 123456
    t_recv = t_true + 0.0004 + rng.uniform(0, 0.002, t_true.size)   # latency + 2 ms jitter
    clk = SequenceClock(adc)
    stamps = np.array([clk.stamp(c, t) for c, t in zip(counter, t_recv)])
    err = stamps - (t_true + 0.0004)
    steady = err[10000:]
    assert np.abs(steady - np.median(steady)).max() < 3e-4      # < 0.3 ms after 10 s
    assert abs(np.median(steady)) < 3e-4
    assert abs(clk.period * adc * drift - 1) < 1e-4


def test_counter_wrap_and_restart():
    clk = SequenceClock(1000.0)
    t = 0.0
    for c in range(2 ** 32 - 5, 2 ** 32):
        clk.stamp(c, t); t += 0.001
    s = clk.stamp(0, t)                               # wrapped: continues
    assert abs(s - t) < 0.002
    resets = clk.resets
    for k in range(200):                              # running normally ...
        clk.stamp(1000 + 10 * k, t + 0.001 * (k + 1))
    clk.stamp(3, t + 0.3)                             # ... then the counter starts over (sensor reboot)
    assert clk.resets == resets + 1
    assert abs(clk.stamp(13, t + 0.301) - (t + 0.301)) < 0.002
