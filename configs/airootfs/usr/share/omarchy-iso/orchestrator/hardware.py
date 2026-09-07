"""Conservative live-hardware profiles.  Input config is never authoritative."""
from pathlib import Path

SURFACE_PRO_12 = {
    "sys_vendor": "Microsoft Corporation",
    "product_family": "Surface",
    "product_name": "Surface Pro 12in 1st Ed with Snapdragon",
    "product_sku": "Surface_Pro_12in_1st_Ed_with_Snapdragon_2110",
}
_OPTIONAL_BOARD = {
    "board_vendor": "Microsoft Corporation",
    "board_name": "Surface Pro 12in 1st Ed with Snapdragon",
}

def _value(root: Path, name: str) -> str | None:
    try:
        value = (root / name).read_text().strip()
    except OSError:
        return None
    return value or None

def _dmi_root() -> Path | None:
    """Use either sysfs spelling exposed by ACPI firmware."""
    for root in (Path("/sys/class/dmi/id"), Path("/sys/devices/virtual/dmi/id")):
        if root.is_dir():
            return root
    return None


def detect_hardware_profile(root: Path | None = None) -> str | None:
    """Return Surface profile only when every required DMI fact exactly matches.

    Baseboard fields are useful corroboration but are optional because firmware
    may not expose them through sysfs on this known device.
    """
    root = root or _dmi_root()
    if root is None or any(_value(root, key) != value for key, value in SURFACE_PRO_12.items()):
        return None
    board = {key: _value(root, key) for key in _OPTIONAL_BOARD}
    if all(value is not None for value in board.values()) and board != _OPTIONAL_BOARD:
        return None
    return 'surface-pro-12'
