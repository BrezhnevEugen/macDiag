"""Light DTC description helper. Generic SAE descriptions + a few MB-specific."""

MB_DTC = {
    "B1535": "Driver seat control module - communication / internal fault",
    "C1525": "ESP - hydraulic unit / pressure sensor implausible",
    "P0170": "Fuel trim malfunction (bank 1)",
    "P0300": "Random/multiple cylinder misfire detected",
    "P2004": "Intake manifold runner control stuck open (bank 1)",
    "U0100": "Lost communication with ECM/PCM",
}

PREFIX = {
    "P": "Powertrain", "C": "Chassis", "B": "Body", "U": "Network",
}


def describe(code: str) -> str:
    if code in MB_DTC:
        return MB_DTC[code]
    area = PREFIX.get(code[:1], "Unknown")
    return f"{area} fault - see model service manual for {code}"
