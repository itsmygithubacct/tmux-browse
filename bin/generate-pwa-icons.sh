#!/usr/bin/env bash
# Regenerate the PWA icons (192px + 512px PNGs) from static/favicon.svg.
#
# Run this whenever favicon.svg changes. Requires ImageMagick's
# `convert` (Debian/Ubuntu: `apt install imagemagick`; macOS:
# `brew install imagemagick`). Output is byte-deterministic given the
# same input SVG, so re-running on an unchanged source produces the
# same PNGs and Git sees no diff.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SVG="$REPO/static/favicon.svg"
OUT_192="$REPO/static/pwa-192.png"
OUT_512="$REPO/static/pwa-512.png"

if [ ! -f "$SVG" ]; then
    echo "error: $SVG not found" >&2
    exit 1
fi

if ! command -v convert >/dev/null 2>&1; then
    echo "error: ImageMagick 'convert' not on \$PATH" >&2
    echo "  install with: bin/install-prereqs.sh --dev" >&2
    exit 1
fi

# ImageMagick on Debian/Ubuntu uses rsvg-convert as the SVG decoding
# delegate; without it, 'convert' fails opaquely on .svg input.
if ! command -v rsvg-convert >/dev/null 2>&1; then
    echo "error: rsvg-convert not on \$PATH (ImageMagick needs it for SVG)" >&2
    echo "  install with: bin/install-prereqs.sh --dev" >&2
    exit 1
fi

# The favicon SVG has a CSS animation that 'convert' renders at t=0;
# we want the cursor visible for the static icon, so the captured frame
# (with the rect at full opacity) is the right one.
convert -background none -resize 192x192 "$SVG" "$OUT_192"
convert -background none -resize 512x512 "$SVG" "$OUT_512"

echo "wrote: $OUT_192 ($(stat -c%s "$OUT_192") bytes)"
echo "wrote: $OUT_512 ($(stat -c%s "$OUT_512") bytes)"
