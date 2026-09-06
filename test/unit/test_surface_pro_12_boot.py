"""Regression checks for the Surface Pro 12in live-media DTB fallback."""

import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "aarch64"
SURFACE_DTB = CONFIG / "surface-pro-12in.dtb"
SURFACE_COMPATIBLE = "microsoft,surface-pro-12in"


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
        self.assertIn("fixed .dtb section", uki)
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


if __name__ == "__main__":
    unittest.main()
