#!/usr/bin/env python3
"""Verify the binary HWID and DTB payloads required by the Surface live UKI."""

import argparse
import hashlib
import struct
import sys
import uuid
from pathlib import Path


COMPATIBLE = b"microsoft,surface-pro-12in\0"
DTB_SHA256 = "d7ed4b073c7344cb0bb2c3f7d00655df60b473588a5c0364af54537dc2c672c7"
REQUIRED_INSTALLED_ARGS = ("initramfs_async=0", "clk_ignore_unused", "pd_ignore_unused", "arm64.nopauth")
FORBIDDEN_INSTALLED_ARGS = ("archiso", "systemd.tpm2_wait=0", "modprobe.blacklist=qcom_q6v5_pas", "debug")
CHIDS = {
    uuid.UUID(value).bytes_le
    for value in (
        "38f75a5d-c3fc-5306-bb2e-bbb516e1ea91",
        "57ba7c1d-8e88-59a9-82c9-044e765788e7",
        "10cb324b-df3c-5081-bc7d-b5cc6795eeef",
        "7c967d92-123c-5bfc-9fe8-430e6bba5ecb",
        "277a48e4-924d-5ab0-81b9-d29c2ff47ad5",
        "0a3f15dc-fcde-5159-baf8-1b55f5e1ae57",
        "d17ea34a-39dc-5a14-8046-f47f082b4065",
        "94996ddd-cdc3-5617-a625-3052726c4654",
        "ef716fc4-b1b0-595c-b66e-1e3df6a0dc1d",
        "b3930262-2a19-5f3f-adf0-b34629632fbb",
        "2cdac0d6-d408-54ab-bf1e-a124b6c5425b",
        "abbf3314-7dde-5966-980c-a1be8cf163b8",
        "587dab3d-0f40-5962-b043-6fc86e41cba2",
    )
}


def sections(image):
    pe = struct.unpack_from("<I", image, 0x3C)[0]
    if image[pe : pe + 4] != b"PE\0\0":
        raise ValueError("not a PE image")
    count = struct.unpack_from("<H", image, pe + 6)[0]
    optional_size = struct.unpack_from("<H", image, pe + 20)[0]
    table = pe + 24 + optional_size
    return [
        (image[offset : offset + 8].rstrip(b"\0"), image[
            struct.unpack_from("<I", image, offset + 20)[0] :
            struct.unpack_from("<I", image, offset + 20)[0] + struct.unpack_from("<I", image, offset + 16)[0]
        ])
        for offset in range(table, table + count * 40, 40)
    ]


def hwid_mappings(payload):
    mappings = {}
    offset = 0
    while True:
        descriptor = struct.unpack_from("<I", payload, offset)[0]
        if descriptor == 0:
            return mappings
        if descriptor != 0x1000001C:
            raise ValueError("invalid HWID descriptor")
        chid = payload[offset + 4 : offset + 20]
        compatible_offset = struct.unpack_from("<I", payload, offset + 24)[0]
        end = payload.index(b"\0", compatible_offset)
        mappings[chid] = payload[compatible_offset:end]
        offset += 28


def is_surface_dtb(payload):
    return payload.startswith(b"\xd0\r\xfe\xed") and COMPATIBLE in payload[:struct.unpack_from(">I", payload, 4)[0]]


def exact_surface_dtb(payload):
    if not payload.startswith(b"\xd0\r\xfe\xed"):
        return False
    size = struct.unpack_from(">I", payload, 4)[0]
    tree = payload[:size]
    return size <= len(payload) and COMPATIBLE in tree and hashlib.sha256(tree).hexdigest() == DTB_SHA256


def verify(path, diagnostic=False, installed=False):
    by_name = {}
    for name, payload in sections(Path(path).read_bytes()):
        by_name.setdefault(name, []).append(payload)
    if installed:
        dtbs = by_name.get(b".dtb", [])
        if len(dtbs) != 1 or not exact_surface_dtb(dtbs[0]):
            raise ValueError("installed UKI lacks exactly one exact fixed Surface DTB")
        if b".dtbauto" in by_name or b".hwids" in by_name:
            raise ValueError("installed UKI must not use DTB-auto/HWID selection")
        cmdlines = by_name.get(b".cmdline", [])
        if len(cmdlines) != 1:
            raise ValueError("installed UKI lacks exactly one .cmdline section")
        cmdline = cmdlines[0].split(b"\0", 1)[0].decode(errors="replace").split()
        missing = [arg for arg in REQUIRED_INSTALLED_ARGS if arg not in cmdline]
        forbidden = [arg for arg in FORBIDDEN_INSTALLED_ARGS if arg in cmdline]
        if missing or forbidden:
            raise ValueError(f"installed cmdline missing={missing} forbidden={forbidden}")
        return
    if diagnostic:
        dtbs = by_name.get(b".dtb", [])
        if len(dtbs) != 1 or not is_surface_dtb(dtbs[0]):
            raise ValueError("diagnostic UKI lacks the fixed Surface DTB")
        return
    hwids = by_name.get(b".hwids", [])
    if len(hwids) != 1:
        raise ValueError("automatic UKI lacks exactly one HWID section")
    mappings = hwid_mappings(hwids[0])
    if any(mappings.get(chid) != COMPATIBLE[:-1] for chid in CHIDS):
        raise ValueError("automatic UKI HWIDs do not map every Surface CHID to its DTB")
    if not any(is_surface_dtb(payload) for payload in by_name.get(b".dtbauto", [])):
        raise ValueError("automatic UKI lacks a Surface DTB-auto payload")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("uki", type=Path)
    parser.add_argument("--diagnostic", action="store_true")
    parser.add_argument("--installed", action="store_true")
    args = parser.parse_args()
    try:
        verify(args.uki, args.diagnostic, args.installed)
    except (IndexError, OSError, ValueError, struct.error) as error:
        sys.exit(f"verify-surface-uki: {error}")


if __name__ == "__main__":
    main()
