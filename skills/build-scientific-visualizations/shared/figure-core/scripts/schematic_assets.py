"""Shared checks and conservative SVG preparation for standalone assets."""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET

from PIL import Image


SVG_NS = "http://www.w3.org/2000/svg"
META_TAGS = {"defs", "title", "desc", "metadata"}
LENGTH = re.compile(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(?:px)?$")
URL = re.compile(r"url\(\s*['\"]?([^)'\"\s]+)", re.IGNORECASE)
RASTER_DATA = re.compile(r"data:image/(?:png|jpeg);base64,[A-Za-z0-9+/=\s]+$", re.IGNORECASE)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def inspect_bitmap(image: Image.Image, *, requires_transparency: bool = False,
                   border_alpha_threshold: int = 20, min_long_edge: int = 0,
                   check_chroma_fringe: bool = False) -> dict:
    """Inspect effective alpha; converting RGB to RGBA does not create transparency.

    No-alpha checks apply only when requested. Palette PNGs with tRNS are valid
    transparent images too. The fringe diagnostic is opt-in, not a ban on green art.
    """
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    histogram = alpha.histogram()
    has_alpha = "A" in image.getbands() or "transparency" in image.info
    w, h = rgba.size
    borders = [alpha.crop(box) for box in
               ((0, 0, w, 1), (0, h - 1, w, h), (0, 0, 1, h), (w - 1, 0, w, h))]
    opaque_border = sum(sum(edge.histogram()[border_alpha_threshold + 1:]) for edge in borders)
    visible = sum(histogram[21:])
    visible_ratio = visible / (w * h)
    green = 0
    if check_chroma_fringe:
        getter = getattr(rgba, "get_flattened_data", None)
        pixels = getter() if getter else rgba.getdata()
        green = sum(a > 20 and g > 150 and r < 100 and b < 100 for r, g, b, a in pixels)
    errors = []
    warnings = []
    if requires_transparency:
        if not has_alpha:
            errors.append("no alpha channel or palette transparency")
        if opaque_border:
            errors.append(f"{opaque_border} opaque border pixels")
        if histogram[255] == w * h:
            errors.append("fully opaque image does not satisfy transparent output")
        if alpha.getbbox() is None:
            errors.append("no visible foreground pixels")
        if green:
            errors.append(f"{green} possible chroma fringe pixels")
    if max(w, h) < min_long_edge:
        errors.append(f"long edge below {min_long_edge} px")
    if visible_ratio < 0.01:
        warnings.append("very low visible-content ratio")
    return {
        "errors": errors, "warnings": warnings,
        "checks": {
            "size": (w, h), "mode": image.mode, "has_alpha": has_alpha,
            "bbox": alpha.getbbox(), "visible_ratio": round(visible_ratio, 4),
            "requires_transparency": requires_transparency,
            "opaque_border": opaque_border if requires_transparency else None,
            "green_fringe": green if requires_transparency and check_chroma_fringe else None,
            "transparent_pixels": histogram[0],
            "partial_alpha_pixels": sum(histogram[1:255]),
            "opaque_pixels": histogram[255],
        },
    }


def parse_svg(content: bytes) -> ET.Element:
    """Accept a self-contained static SVG; never fetch a linked resource."""
    if len(content) > 10 * 1024 * 1024:
        raise ValueError("SVG exceeds the 10 MiB input limit")
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)", content, re.IGNORECASE):
        raise ValueError("SVG declarations and entities are not supported")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError("invalid SVG XML") from exc
    if root.tag != f"{{{SVG_NS}}}svg":
        raise ValueError("input must have an SVG root in the SVG namespace")
    for element in root.iter():
        tag = local_name(element.tag)
        if tag in {"script", "foreignObject"}:
            raise ValueError(f"unsupported SVG element: {tag}")
        for key, value in element.attrib.items():
            if local_name(key) == "base":
                raise ValueError("SVG base URLs are not supported")
            if local_name(key) == "href" and not (
                value.startswith("#") or RASTER_DATA.fullmatch(value)
            ):
                raise ValueError("SVG references must be local fragments or embedded PNG/JPEG")
        texts = list(element.attrib.values())
        if tag == "style":
            texts.append(element.text or "")
        for text in texts:
            if re.search(r"@import", text, re.IGNORECASE):
                raise ValueError("SVG CSS imports are not supported")
            if any(not value.startswith("#") for value in URL.findall(text)):
                raise ValueError("SVG CSS URLs must be local fragments")
    return root


def svg_representation(root: ET.Element) -> str:
    """Conservative inventory, not a claim of native PowerPoint editability."""
    tags = {local_name(e.tag) for e in root.iter()}
    if not tags.intersection({"image", "feImage"}):
        return "native_vector"
    vector_tags = {"path", "rect", "circle", "ellipse", "polygon", "polyline", "line", "text", "use"}
    return "mixed" if tags.intersection(vector_tags) else "embedded_bitmap"


def view_box(root: ET.Element) -> tuple:
    try:
        values = tuple(float(v) for v in re.split(r"[\s,]+", root.get("viewBox", "").strip()))
    except ValueError as exc:
        raise ValueError("SVG needs a finite, positive viewBox") from exc
    if len(values) != 4 or not all(math.isfinite(v) for v in values) or min(values[2:]) <= 0:
        raise ValueError("SVG needs a finite, positive viewBox")
    return values


def _length(value: str, extent: float) -> float:
    if value == "100%":
        return extent
    match = LENGTH.fullmatch(value)
    if not match:
        raise ValueError("canvas rectangle needs numeric/px lengths or 100% extents")
    result = float(match.group(1))
    if not math.isfinite(result):
        raise ValueError("canvas rectangle has non-finite geometry")
    return result


def prepare_svg(content: bytes, *, background: str,
                remove_background_id: str = None) -> tuple:
    """Remove only an explicitly named, untransformed full-canvas rectangle.

    No colour-keying or implicit white-shape deletion. Foreground XML, viewBox,
    transforms, gradients and opacity are retained; serialization may change prefixes.
    """
    if background not in {"transparent", "white"}:
        raise ValueError("background must be transparent or white")
    root = parse_svg(content)
    x, y, w, h = view_box(root)
    if remove_background_id:
        matches = [e for e in root.iter() if e.get("id") == remove_background_id]
        if len(matches) != 1:
            raise ValueError("background ID must identify exactly one element")
        target = matches[0]
        drawables = [e for e in root if local_name(e.tag) not in META_TAGS]
        if (not drawables or target is not drawables[0]
                or target.tag != f"{{{SVG_NS}}}rect" or root.get("transform")
                or any(key in target.attrib for key in ("transform", "clip-path", "mask", "filter", "style", "class"))
                or list(target)):
            raise ValueError("background must be the first root-level, unstyled canvas rectangle")
        geometry = (_length(target.get("x", "0"), w), _length(target.get("y", "0"), h),
                    _length(target.get("width", "0"), w), _length(target.get("height", "0"), h))
        if not all(math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
                   for a, b in zip(geometry, (x, y, w, h))):
            raise ValueError("background rectangle must match the full viewBox")
        root.remove(target)
    if background == "white":
        canvas = ET.Element(f"{{{SVG_NS}}}rect", {
            "x": str(x), "y": str(y), "width": str(w), "height": str(h), "fill": "#FFFFFF",
        })
        position = next((i for i, e in enumerate(root) if local_name(e.tag) not in META_TAGS), len(root))
        root.insert(position, canvas)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), svg_representation(root)
