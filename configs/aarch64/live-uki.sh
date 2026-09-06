#!/usr/bin/env bash
# Build a live UKI with Qualcomm DTBs selected from the system SMBIOS data.
set -euo pipefail

kernel=/boot/vmlinuz-linux-aarch64
initrd=/boot/initramfs-linux-aarch64.img
uki=/boot/omarchy-live.efi
surface_uki=/boot/omarchy-surface-pro-12in-debug.efi
hwids=/usr/lib/systemd/boot/hwids/aa64
surface_dtb=/boot/dtbs/qcom/x1p42100-microsoft-sp12in.dtb
surface_hwid=/root/surface-pro-12in-hwid.json

for f in "$kernel" "$initrd"; do
  if [[ ! -s $f ]]; then
    echo "live-uki: $f is missing; customize_airootfs.sh should have produced it" >&2
    exit 1
  fi
done
if ! command -v ukify >/dev/null; then
  echo "live-uki: ukify not found; is systemd-ukify in configs/packages.aarch64?" >&2
  exit 1
fi
if [[ ! -d $hwids ]]; then
  echo "live-uki: no SMBIOS-ID database at $hwids (systemd >= 260 ships it)" >&2
  exit 1
fi
if [[ ! -s $surface_dtb || ! -s $surface_hwid ]]; then
  echo "live-uki: Surface Pro 12in fallback inputs are missing" >&2
  exit 1
fi

# systemd v261 identifies this Surface correctly but maps its CHIDs to the
# obsolete microsoft,sp12 compatible.  Use an ISO-local copy so the automatic
# UKI can match the compatible carried by the current DTS; do not patch the
# installed systemd database.
surface_hwids="$(mktemp -d)"
trap 'rm -rf "$surface_hwids"' EXIT
cp -a "$hwids/." "$surface_hwids/"
install -Dm644 "$surface_hwid" "$surface_hwids/x1p42100-microsoft-surface-pro-12in.json"

# Include supported Snapdragon generations while staying below the UKI section limit.
# EL2 variants share hardware IDs with their base DTBs and would be ambiguous.
shopt -s nullglob
dtbs=()
for dtb in /boot/dtbs/qcom/x1*.dtb /boot/dtbs/qcom/hamoa*.dtb \
           /boot/dtbs/qcom/glymur*.dtb /boot/dtbs/qcom/sc8280xp*.dtb; do
  [[ $dtb == *-el2.dtb ]] && continue
  dtbs+=("$dtb")
done
if (( ${#dtbs[@]} == 0 )); then
  echo "live-uki: no Windows-on-ARM device trees under /boot/dtbs/qcom" >&2
  exit 1
fi
# Reserve room for the UKI's non-DTB sections.
if (( ${#dtbs[@]} > 90 )); then
  echo "live-uki: ${#dtbs[@]} device trees exceed the UKI section budget; narrow the prefixes" >&2
  exit 1
fi

args=()
for dtb in "${dtbs[@]}"; do
  args+=("--devicetree-auto=$dtb")
done

echo "live-uki: wrapping $kernel and $initrd with ${#dtbs[@]} device trees"
ukify build \
  --linux="$kernel" \
  --initrd="$initrd" \
  --hwids="$surface_hwids" \
  "${args[@]}" \
  --output="$uki"

# Verify that ukify embedded every required section.
sections="$(ukify inspect "$uki")"
n_dtb="$(grep -c '^\.dtbauto:' <<<"$sections" || true)"
if ! grep -q '^\.hwids:' <<<"$sections"; then
  echo "live-uki: $uki has no .hwids section" >&2
  exit 1
fi
if (( n_dtb != ${#dtbs[@]} )); then
  echo "live-uki: $uki has $n_dtb .dtbauto sections, expected ${#dtbs[@]}" >&2
  exit 1
fi
if ! strings "$uki" | grep -qx 'microsoft,surface-pro-12in'; then
  echo "live-uki: Surface Pro 12in compatible is absent from $uki" >&2
  exit 1
fi

# GRUB cannot attach a DTB while chainloading a UKI.  This second image has a
# fixed DTB for an explicitly selected, verbose Surface-only diagnostic boot.
ukify build \
  --linux="$kernel" \
  --initrd="$initrd" \
  --devicetree="$surface_dtb" \
  --output="$surface_uki"
surface_sections="$(ukify inspect "$surface_uki")"
if ! grep -q '^\.dtb:' <<<"$surface_sections"; then
  echo "live-uki: $surface_uki has no fixed .dtb section" >&2
  exit 1
fi
echo "live-uki: $uki: $(stat -c %s "$uki") bytes, $n_dtb .dtbauto sections, .hwids present"
echo "live-uki: $surface_uki: fixed Surface Pro 12in diagnostic DTB"
