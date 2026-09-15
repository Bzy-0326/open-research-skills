#!/usr/bin/env python3
"""Export or check one standalone schematic asset, without a figure project."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import re
import tempfile

from PIL import Image, UnidentifiedImageError

from schematic_assets import inspect_bitmap, parse_svg, prepare_svg, svg_representation


def render_svg(content: bytes, width: int = None) -> bytes:
    # Keep bitmap export/check usable on Python 3.9. The optional maintained SVG
    # renderer has its own documented Python 3.10+ runtime requirement.
    try:
        import cairosvg
    except (ImportError, OSError) as exc:
        raise ValueError("SVG rendering needs Python 3.10+, CairoSVG >=2.9.1 and Cairo; see requirements-assets.txt") from exc
    version = tuple(int(v) for v in re.findall(r"\d+", cairosvg.__version__)[:3])
    if version < (2, 9, 1):
        raise ValueError("SVG rendering requires CairoSVG >=2.9.1")
    parse_svg(content)
    try:
        return cairosvg.svg2png(bytestring=content, output_width=width)
    except Exception as exc:
        # Backend messages may contain private paths from the source document.
        raise ValueError(f"SVG rendering failed ({type(exc).__name__})") from exc


def check_file(source: Path, *, background: str) -> dict:
    representation = None
    if source.suffix.lower() == ".svg":
        content = source.read_bytes()
        representation = svg_representation(parse_svg(content))
        image_source = io.BytesIO(render_svg(content))
    else:
        image_source = source
    with Image.open(image_source) as image:
        report = inspect_bitmap(image, requires_transparency=background == "transparent", border_alpha_threshold=0)
        if background == "white" and image.convert("RGBA").getchannel("A").getextrema() != (255, 255):
            report["errors"].append("white-background output contains transparent pixels")
    if representation:
        report["checks"]["svg_representation"] = representation
    report["status"] = "FAIL" if report["errors"] else "PASS"
    return report


def export_asset(source: Path, output_dir: Path, *, background: str,
                 remove_background_id: str = None, width: int = None,
                 overwrite: bool = False) -> dict:
    is_svg = source.suffix.lower() == ".svg"
    if not is_svg and source.suffix.lower() != ".png":
        raise ValueError("export supports SVG or PNG inputs")
    if remove_background_id and not is_svg:
        raise ValueError("background IDs apply only to SVG; raster backgrounds are not removed automatically")
    if width is not None and not 1 <= width <= 10000:
        raise ValueError("width must be between 1 and 10000 pixels")
    outputs = [output_dir / (source.stem + ".png")]
    if is_svg:
        outputs.append(output_dir / (source.stem + ".svg"))
    for path in outputs:
        if path.resolve() == source.resolve():
            raise ValueError("output would replace the source; choose another directory")
        if path.exists() and not path.is_file():
            raise ValueError("output destination is not a file; choose another directory")
        if path.exists() and not overwrite:
            raise ValueError("output already exists; choose another directory or use --overwrite")
    payloads = {}
    representation = None
    if is_svg:
        content, representation = prepare_svg(source.read_bytes(), background=background,
                                               remove_background_id=remove_background_id)
        payloads[outputs[1].name] = content
        image_source = io.BytesIO(render_svg(content, width))
    else:
        image_source = source
    with Image.open(image_source) as image:
        # Check the input before a conversion could hide an opaque raster failure.
        if not is_svg and background == "transparent":
            input_check = inspect_bitmap(image, requires_transparency=True, border_alpha_threshold=0)
            if input_check["errors"]:
                return {"status": "FAIL", **input_check}
        rgba = image.convert("RGBA")
    if width and not is_svg:
        height = max(1, round(rgba.height * width / rgba.width))
        if height > 10000:
            raise ValueError("resized height exceeds 10000 pixels")
        rgba = rgba.resize((width, height), Image.Resampling.LANCZOS)
    if background == "white":
        white = Image.new("RGBA", rgba.size, "white")
        white.alpha_composite(rgba)
        rendered = white.convert("RGB")
    else:
        rendered = rgba
    report = inspect_bitmap(rendered, requires_transparency=background == "transparent", border_alpha_threshold=0)
    report["checks"].update(background=background, svg_representation=representation)
    if report["errors"]:
        return {"status": "FAIL", **report}
    buffer = io.BytesIO()
    rendered.save(buffer, format="PNG")
    payloads[outputs[0].name] = buffer.getvalue()
    # Validate the encoded PNG too, not just its in-memory predecessor.
    with Image.open(io.BytesIO(payloads[outputs[0].name])) as encoded:
        final_check = inspect_bitmap(encoded, requires_transparency=background == "transparent", border_alpha_threshold=0)
    if final_check["errors"]:
        return {"status": "FAIL", **final_check}
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".asset-export-", dir=output_dir) as tmp:
        staging = Path(tmp)
        for filename, payload in payloads.items():
            (staging / filename).write_bytes(payload)
        for filename in payloads:
            (staging / filename).replace(output_dir / filename)
    return {"status": "PASS", **report, "output_files": list(payloads)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "export"))
    parser.add_argument("source", type=Path)
    parser.add_argument("--background", choices=("transparent", "white"), required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--remove-background-id")
    parser.add_argument("--width-px", type=int)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.action == "export" and args.output_dir is None:
        parser.error("export requires --output-dir")
    if args.action == "check" and (args.output_dir or args.remove_background_id or args.width_px is not None or args.overwrite):
        parser.error("check accepts only source and --background")
    try:
        if args.action == "check":
            report = check_file(args.source, background=args.background)
        else:
            report = export_asset(args.source, args.output_dir, background=args.background,
                                  remove_background_id=args.remove_background_id,
                                  width=args.width_px, overwrite=args.overwrite)
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else f"cannot read or write asset ({type(exc).__name__})"
        report = {"status": "FAIL", "errors": [message], "warnings": []}
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
