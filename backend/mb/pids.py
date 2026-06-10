"""Standard OBD-II mode 01 PIDs with decoders, plus a few MB DIDs."""

# pid: (label, unit, decoder(bytes)->float|str)
LIVE_PIDS = {
    0x05: ("Coolant temp", "°C", lambda d: d[0] - 40),
    0x0C: ("Engine RPM", "rpm", lambda d: ((d[0] << 8) | d[1]) / 4),
    0x0D: ("Vehicle speed", "km/h", lambda d: d[0]),
    0x0F: ("Intake air temp", "°C", lambda d: d[0] - 40),
    0x10: ("MAF rate", "g/s", lambda d: ((d[0] << 8) | d[1]) / 100),
    0x11: ("Throttle position", "%", lambda d: round(d[0] * 100 / 255, 1)),
    0x2F: ("Fuel level", "%", lambda d: round(d[0] * 100 / 255, 1)),
    0x42: ("Module voltage", "V", lambda d: round(((d[0] << 8) | d[1]) / 1000, 2)),
    0x5C: ("Oil temp", "°C", lambda d: d[0] - 40),
}

# Dashboard default selection (works on most MB ME/CDI engine ECUs)
DEFAULT_DASHBOARD = [0x0C, 0x0D, 0x05, 0x11, 0x2F, 0x42]

# Useful identifiers (UDS ReadDataByIdentifier)
DIDS = {
    0xF190: "VIN",
    0xF187: "MB part number",
    0xF195: "Software version",
    0xF18C: "ECU serial number",
}


def decode_pid(pid: int, data: bytes) -> dict:
    label, unit, fn = LIVE_PIDS.get(pid, (f"PID 0x{pid:02X}", "", lambda d: d.hex()))
    try:
        value = fn(data)
    except Exception:
        value = data.hex()
    return {"pid": pid, "label": label, "unit": unit, "value": value}
