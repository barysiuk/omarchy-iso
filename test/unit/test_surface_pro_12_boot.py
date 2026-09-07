"""Regression checks for the Surface Pro 12in live-media DTB fallback."""

import hashlib
import json
import importlib.util
from pathlib import Path
import re
import struct
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "aarch64"
SURFACE_DTB = CONFIG / "surface-pro-12in.dtb"
SURFACE_COMPATIBLE = "microsoft,surface-pro-12in"
VERIFY = CONFIG / "verify-surface-uki.py"
spec = importlib.util.spec_from_file_location("verify_surface_uki", VERIFY)
verify_surface_uki = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify_surface_uki)


class SurfacePro12BootTest(unittest.TestCase):
    def test_vendored_dtb_is_the_reviewed_surface_payload(self):
        self.assertEqual(
            hashlib.sha256(SURFACE_DTB.read_bytes()).hexdigest(),
            "d7ed4b073c7344cb0bb2c3f7d00655df60b473588a5c0364af54537dc2c672c7",
        )
        payload = SURFACE_DTB.read_bytes()
        self.assertIn(SURFACE_COMPATIBLE.encode(), payload)
        self.assertIn(b"Surface Pro 12in 1st Edition", payload)

    def test_surface_hwid_and_dtb_compatible_agree(self):
        hwid = json.loads((CONFIG / "surface-pro-12in-hwid.json").read_text())
        self.assertEqual(hwid["type"], "devicetree")
        self.assertEqual(hwid["compatible"], SURFACE_COMPATIBLE)
        self.assertIn("10cb324b-df3c-5081-bc7d-b5cc6795eeef", hwid["hwids"])
        self.assertGreaterEqual(len(hwid["hwids"]), 13)

    def test_build_stages_fallback_only_when_kernel_lacks_it(self):
        customize = (CONFIG / "customize_airootfs.sh").read_text()
        self.assertIn("surface_dtb=/boot/dtbs/qcom/x1p42100-microsoft-sp12in.dtb", customize)
        self.assertIn("if [[ ! -e $surface_dtb ]]; then", customize)
        self.assertIn("install -Dm644 /root/surface-pro-12in.dtb", customize)
        build = (ROOT / "builder" / "build-iso.sh").read_text()
        self.assertIn("/configs/aarch64/surface-pro-12in.dtb", build)
        self.assertIn("/configs/aarch64/surface-pro-12in-hwid.json", build)

    def test_automatic_and_forced_surface_ukis_are_built(self):
        uki = (CONFIG / "live-uki.sh").read_text()
        self.assertIn("--hwids=\"$surface_hwids\"", uki)
        self.assertIn("--devicetree-auto=$dtb", uki)
        self.assertIn("surface_uki=/boot/omarchy-surface-pro-12in-debug.efi", uki)
        self.assertIn("--devicetree=\"$surface_dtb\"", uki)
        self.assertIn("verify-surface-uki.py --diagnostic", uki)
        self.assertNotIn('strings "$uki"', uki)
        grub = (ROOT / "configs" / "grub" / "grub.cfg").read_text()
        self.assertIn("omarchy-surface-pro-12in-debug.efi", grub)
        self.assertIn("console=tty0 loglevel=7 plymouth.enable=0 panic=30", grub)

    def test_existing_generic_automatic_selection_remains(self):
        uki = (CONFIG / "live-uki.sh").read_text()
        self.assertIn("/boot/dtbs/qcom/x1*.dtb", uki)
        self.assertIn("/boot/dtbs/qcom/hamoa*.dtb", uki)
        self.assertIn("[[ $dtb == *-el2.dtb ]] && continue", uki)
        self.assertIn("ukify build", uki)
        grub = (ROOT / "configs" / "grub" / "grub.cfg").read_text()
        self.assertIn("default=archlinux-uki", grub)
        self.assertIn("omarchy-live.efi", grub)

    def test_arm_menu_exposes_diagnostic_without_changing_x86_default(self):
        grub = (ROOT / "configs" / "grub" / "grub.cfg").read_text()
        arm = re.search(
            r"if \[ \"\$\{grub_cpu\}\" == 'arm64' \]; then(?P<body>.*?)^fi$",
            grub,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(arm)
        self.assertIn("default=archlinux-uki", arm["body"])
        self.assertIn("timeout=10", arm["body"])
        self.assertIn("timeout_style=menu", arm["body"])
        # The top-level defaults continue to apply to every non-arm64 boot.
        before_arm = grub[: arm.start()]
        self.assertIn("default=archlinux", before_arm)
        self.assertIn("timeout=0", before_arm)
        self.assertIn("timeout_style=hidden", before_arm)

    def test_binary_hwid_validation_distinguishes_the_obsolete_mapping(self):
        chid = next(iter(verify_surface_uki.CHIDS))

        def hwids(compatible):
            table_size = 56  # one device plus the terminating null device
            strings = b"Surface\0" + compatible.encode() + b"\0"
            return (
                struct.pack("<I", 0x1000001C)
                + chid
                + struct.pack("<II", table_size, table_size + len(b"Surface\0"))
                + b"\0" * 28
                + strings
            )

        self.assertEqual(
            verify_surface_uki.hwid_mappings(hwids(SURFACE_COMPATIBLE))[chid],
            SURFACE_COMPATIBLE.encode(),
        )
        self.assertNotEqual(
            verify_surface_uki.hwid_mappings(hwids("microsoft,sp12"))[chid],
            SURFACE_COMPATIBLE.encode(),
        )

    def test_uki_validator_checks_hwid_mapping_and_dtb_payload_separately(self):
        table_size = 28 * (len(verify_surface_uki.CHIDS) + 1)
        hwids = b"".join(
            struct.pack("<I", 0x1000001C)
            + chid
            + struct.pack("<II", table_size, table_size + len(b"Surface\0"))
            for chid in verify_surface_uki.CHIDS
        ) + b"\0" * 28 + b"Surface\0microsoft,surface-pro-12in\0"

        def pe(sections):
            header = bytearray(512)
            header[:2] = b"MZ"
            struct.pack_into("<I", header, 0x3C, 0x80)
            header[0x80:0x84] = b"PE\0\0"
            struct.pack_into("<H", header, 0x86, len(sections))
            struct.pack_into("<H", header, 0x94, 0xE0)
            data = b""
            for number, (section_name, payload) in enumerate(sections):
                offset = 0x98 + 0xE0 + number * 40
                header[offset : offset + 8] = section_name.ljust(8, b"\0")
                struct.pack_into("<I", header, offset + 16, len(payload))
                struct.pack_into("<I", header, offset + 20, 512 + len(data))
                data += payload
            return bytes(header) + data

        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "uki.efi"
            image.write_bytes(pe(((b".hwids", hwids),)))
            with self.assertRaisesRegex(ValueError, "DTB-auto"):
                verify_surface_uki.verify(image)
            image.write_bytes(pe(((b".hwids", hwids), (b".dtbauto", SURFACE_DTB.read_bytes()))))
            verify_surface_uki.verify(image)


if __name__ == "__main__":
    unittest.main()
