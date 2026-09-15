# Standalone transparent asset example

This original synthetic icon has a white canvas, a translucent ellipse and an
intentionally white foreground circle. It is a rendering example, not biological data.

From the repository root, with Python 3.10+ and the system Cairo library installed:

```bash
SKILL_DIR="$PWD/skills/build-scientific-visualizations"
python3 -m pip install -r "$SKILL_DIR/requirements-assets.txt"

python3 "$SKILL_DIR/shared/figure-core/scripts/export_schematic_asset.py" export \
  "$SKILL_DIR/examples/standalone-schematic-asset/asset.svg" \
  --output-dir outputs/asset-transparent --background transparent \
  --remove-background-id canvas --width-px 1000

python3 "$SKILL_DIR/shared/figure-core/scripts/export_schematic_asset.py" check \
  outputs/asset-transparent/asset.png --background transparent

python3 "$SKILL_DIR/shared/figure-core/scripts/export_schematic_asset.py" export \
  "$SKILL_DIR/examples/standalone-schematic-asset/asset.svg" \
  --output-dir outputs/asset-white --background white --width-px 1000
```

The transparent directory contains SVG and PNG with clear outer margins. The ellipse
retains intermediate alpha and the white foreground circle remains opaque. Compositing
the transparent PNG on white should match the white export within renderer rounding.
Inspect it on dark as well as light backgrounds; do not remove all white pixels.

Omit `--remove-background-id canvas` from the first command and the rendered white
canvas fails transparency validation. No failed candidate is published. Use a fresh
destination or `--overwrite` to replace a previous export; the original input cannot
be overwritten by this command. Bitmap-only checks need only Pillow and Python 3.9+.
