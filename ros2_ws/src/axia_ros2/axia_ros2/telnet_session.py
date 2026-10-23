"""The Axia's telnet console (port 23), safely: one session, its own event loop, RAM-only writes.

AxiaDriver.communication.AxiaCommunication calls asyncio.get_event_loop() for every read and
write, which on Python >= 3.12 only works when the calling thread has a current loop; this
context manager gives it one and closes everything afterwards. AxiaCommunication's
write_configuration() ends with `saveall` (NVM): it is never called here. Runtime settings go
to RAM with the individual setters, so a power cycle restores the sensor's stored setup;
persist explicitly with save=True.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging


@contextlib.contextmanager
def telnet_session(ip, timeout=5.0):
    from AxiaDriver.communication import AxiaCommunication

    previous = None
    try:
        previous = asyncio.get_event_loop_policy().get_event_loop()
    except RuntimeError:
        previous = None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    com = AxiaCommunication(ip)
    try:
        com.connect(timeout=timeout)
        yield com
    finally:
        try:
            com.disconnect()
        except Exception:  # the connection may already be gone
            pass
        loop.close()
        asyncio.set_event_loop(previous if previous is not None and not previous.is_closed() else None)


def read_configuration(com):
    """AxiaConfiguration of the sensor's current settings (+ firmware, status)."""
    return com.read_configuration()


def apply_runtime_config(com, adc_rate=None, rdt_rate=None, filter_index=None, calibration=None,
                         disable_bias=True, save=False):
    """Change what differs from the sensor's current settings (RAM only unless save).

    Returns {setting: (old, new)} for every value that changed.
    """
    current = com.get_settings()
    changes = {}

    def differs(key, value):
        return value is not None and str(current.get(key)) != str(value)

    # the RDT rate may not exceed the ADC rate: lower the RDT rate first when reducing the ADC
    if differs("adcRate", adc_rate):
        if rdt_rate is not None and int(rdt_rate) <= int(current.get("rdtRate", 0)):
            changes["rdtRate"] = com.set_udp_transmit_rate(int(rdt_rate))
        changes["adcRate"] = com.set_adc_sample_rate(int(adc_rate))
    if differs("rdtRate", rdt_rate) and "rdtRate" not in changes:
        changes["rdtRate"] = com.set_udp_transmit_rate(int(rdt_rate))
    if differs("filTc", filter_index):
        changes["filTc"] = com.set_low_pass_filter(int(filter_index))
    if differs("calib", calibration):
        changes["calib"] = com.set_calibration(int(calibration))
    if disable_bias:
        com.disable_bias()
    if save:
        com.write_settings_to_memory()
        logging.warning("Axia settings SAVED to non-volatile memory")
    return changes
