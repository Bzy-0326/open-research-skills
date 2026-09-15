"""Actual alpha and rendered outputs for the standalone-asset workflow."""

import base64
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/build-scientific-visualizations/shared/figure-core/scripts"
sys.path.insert(0, str(SCRIPTS))
from schematic_assets import inspect_bitmap, parse_svg, prepare_svg, svg_representation
from export_schematic_asset import export_asset, render_svg


SVG = b'''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="80" viewBox="0 0 100 80">
<rect id="canvas" width="100%" height="100%" fill="white"/>
<ellipse id="membrane" cx="50" cy="40" rx="32" ry="24" fill="#86afdf" opacity="0.4"/>
<circle id="white-foreground" cx="42" cy="37" r="7" fill="white"/>
<circle id="event" cx="64" cy="47" r="5" fill="#e791b3"/>
</svg>'''


def rgba_asset():
    image = Image.new("RGBA", (100, 80), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((20, 15, 80, 65), fill=(100, 150, 200, 120))
    return image


class BitmapChecksTest(unittest.TestCase):
    def test_real_transparency_and_membrane_pass(self):
        report = inspect_bitmap(rgba_asset(), requires_transparency=True, border_alpha_threshold=0)
        self.assertEqual([], report["errors"])
        self.assertGreater(report["checks"]["transparent_pixels"], 0)
        self.assertGreater(report["checks"]["partial_alpha_pixels"], 0)

    def test_rgb_checkerboard_is_not_transparency(self):
        image = Image.new("RGB", (100, 80), "white")
        draw = ImageDraw.Draw(image)
        for y in range(0, 80, 10):
            for x in range(0, 100, 10):
                if (x // 10 + y // 10) % 2:
                    draw.rectangle((x, y, x + 9, y + 9), fill="#cccccc")
        result = inspect_bitmap(image, requires_transparency=True)
        self.assertTrue(any("no alpha" in e for e in result["errors"]))
        self.assertTrue(any("fully opaque" in e for e in result["errors"]))

    def test_rgba_with_opaque_alpha_fails(self):
        report = inspect_bitmap(Image.new("RGBA", (100, 80), "white"), requires_transparency=True)
        self.assertTrue(any("fully opaque" in e for e in report["errors"]))

    def test_empty_transparent_image_is_not_a_valid_asset(self):
        result = inspect_bitmap(Image.new("RGBA", (100, 80)), requires_transparency=True)
        self.assertIn("no visible foreground pixels", result["errors"])

    def test_opaque_rgb_is_allowed_when_transparency_not_requested(self):
        report = inspect_bitmap(Image.new("RGB", (100, 80), "gray"))
        self.assertEqual([], report["errors"])

    def test_real_palette_transparency_is_supported(self):
        image = Image.new("P", (100, 80), 0)
        image.putpalette([255, 255, 255, 100, 150, 200] + [0] * 762)
        image.info["transparency"] = 0
        ImageDraw.Draw(image).rectangle((20, 20, 80, 60), fill=1)
        self.assertEqual([], inspect_bitmap(image, requires_transparency=True)["errors"])

    def test_border_check_catches_edge_pixels(self):
        image = rgba_asset()
        image.putpixel((50, 0), (0, 0, 0, 255))
        report = inspect_bitmap(image, requires_transparency=True)
        self.assertTrue(any("opaque border" in e for e in report["errors"]))

    def test_legitimate_green_is_not_a_transparency_error(self):
        image = rgba_asset()
        image.putpixel((50, 40), (0, 200, 0, 255))
        self.assertEqual([], inspect_bitmap(image, requires_transparency=True)["errors"])
        self.assertTrue(inspect_bitmap(image, requires_transparency=True, check_chroma_fringe=True)["errors"])


class SvgPreparationTest(unittest.TestCase):
    def test_remove_only_named_canvas_and_preserve_white_foreground(self):
        result, kind = prepare_svg(SVG, background="transparent", remove_background_id="canvas")
        old = ET.fromstring(SVG)
        new = ET.fromstring(result)
        self.assertEqual(old.attrib, new.attrib)
        self.assertEqual([ET.tostring(e) for e in list(old)[1:]], [ET.tostring(e) for e in new])
        self.assertEqual("native_vector", kind)
        self.assertEqual("white", new.find("{*}circle").get("fill"))

    def test_transparency_does_not_implicitly_remove_white_shapes(self):
        result, _ = prepare_svg(SVG, background="transparent")
        self.assertIsNotNone(ET.fromstring(result).find("{*}rect"))

    def test_wrong_or_non_canvas_id_is_rejected(self):
        for name in ("missing", "event", "white-foreground"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                prepare_svg(SVG, background="transparent", remove_background_id=name)

    def test_partial_canvas_and_duplicate_id_are_rejected(self):
        for content in (SVG.replace(b'width="100%"', b'width="20"'),
                        SVG.replace(b'id="event"', b'id="canvas"')):
            with self.assertRaises(ValueError):
                prepare_svg(content, background="transparent", remove_background_id="canvas")

    def test_transformed_or_styled_canvas_is_rejected(self):
        for attribute in (b'transform="translate(1 2)"', b'style="opacity:0.5"'):
            source = SVG.replace(b'id="canvas"', b'id="canvas" ' + attribute)
            with self.assertRaises(ValueError):
                prepare_svg(source, background="transparent", remove_background_id="canvas")

    def test_white_canvas_is_inserted_without_mutating_foreground(self):
        source, _ = prepare_svg(SVG, background="transparent", remove_background_id="canvas")
        result, _ = prepare_svg(source, background="white")
        a, b = ET.fromstring(source), ET.fromstring(result)
        self.assertEqual([ET.tostring(e) for e in a], [ET.tostring(e) for e in list(b)[1:]])
        self.assertEqual("#FFFFFF", list(b)[0].get("fill"))

    def test_svg_inventory_distinguishes_embedded_and_mixed(self):
        data = io.BytesIO()
        rgba_asset().save(data, format="PNG")
        encoded = base64.b64encode(data.getvalue()).decode("ascii")
        source = f'<svg xmlns="http://www.w3.org/2000/svg"><image href="data:image/png;base64,{encoded}"/></svg>'.encode()
        self.assertEqual("embedded_bitmap", svg_representation(parse_svg(source)))
        mixed = source.replace(b'</svg>', b'<path d="M0 0L1 1"/></svg>')
        self.assertEqual("mixed", svg_representation(parse_svg(mixed)))

    def test_external_resources_are_not_fetched(self):
        bad = [b'<image href="https://example.org/asset.png"/>',
               b'<use href="file:///missing.svg#shape"/>',
               b'<style>@import "https://example.org/style.css";</style>',
               b'<rect fill="url(https://example.org/fill.svg)"/>']
        for element in bad:
            with self.subTest(element=element), self.assertRaises(ValueError):
                parse_svg(b'<svg xmlns="http://www.w3.org/2000/svg">' + element + b'</svg>')

    def test_nonfinite_viewbox_fails(self):
        for value in (b'0 0 nan 80', b'0 0 0 80'):
            with self.assertRaises(ValueError):
                prepare_svg(SVG.replace(b'0 0 100 80', value), background="transparent")


class StandalonePngTest(unittest.TestCase):
    def test_export_keeps_alpha_and_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);source = root / "icon.png"
            rgba_asset().save(source)
            result = export_asset(source, root / "out", background="transparent")
            self.assertEqual("PASS", result["status"])
            with Image.open(source) as before, Image.open(root / "out/icon.png") as after:
                self.assertEqual(before.tobytes(), after.tobytes())

    def test_white_export_and_no_source_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);source = root / "icon.png";rgba_asset().save(source)
            original = source.read_bytes()
            self.assertEqual("PASS", export_asset(source, root / "out", background="white")["status"])
            with Image.open(root / "out/icon.png") as image:
                self.assertEqual("RGB", image.mode)
                self.assertEqual((255, 255, 255), image.getpixel((0, 0)))
            with self.assertRaises(ValueError):
                export_asset(source, root, background="white", overwrite=True)
            self.assertEqual(original, source.read_bytes())

    def test_invalid_export_does_not_replace_previous_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);source = root / "icon.png"
            Image.new("RGB", (100, 80), "white").save(source)
            out = root / "out";out.mkdir();target = out / "icon.png"
            target.write_bytes(b'previous accepted output')
            result = export_asset(source, out, background="transparent", overwrite=True)
            self.assertEqual("FAIL", result["status"])
            self.assertEqual(b'previous accepted output', target.read_bytes())

    def test_check_cli_fails_on_real_file_without_project_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "checker.png"
            Image.new("RGB", (100, 80), "gray").save(source)
            run = subprocess.run([sys.executable, "-B", str(SCRIPTS / "export_schematic_asset.py"),
                                  "check", str(source), "--background", "transparent"],
                                 capture_output=True, text=True, check=False)
            self.assertEqual(1, run.returncode)
            self.assertEqual("FAIL", json.loads(run.stdout)["status"])

    def test_directory_collision_is_rejected_before_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "icon.png"
            rgba_asset().save(source)
            destination = root / "out/icon.png"
            destination.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "not a file"):
                export_asset(source, root / "out", background="transparent", overwrite=True)
            self.assertTrue(destination.is_dir())

    def test_missing_input_does_not_expose_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "missing.png"
            run = subprocess.run([sys.executable, "-B", str(SCRIPTS / "export_schematic_asset.py"),
                                  "check", str(source), "--background", "transparent"],
                                 capture_output=True, text=True, check=False)
            self.assertEqual(1, run.returncode)
            self.assertNotIn(str(source), run.stdout + run.stderr)


@unittest.skipIf(sys.version_info < (3, 10), "optional maintained SVG renderer requires Python 3.10+")
class SvgExportTest(unittest.TestCase):
    def test_real_export_preserves_foreground_and_membrane_alpha(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);source = root / "icon.svg";source.write_bytes(SVG)
            result = export_asset(source, root / "out", background="transparent", remove_background_id="canvas")
            self.assertEqual("PASS", result["status"])
            with Image.open(root / "out/icon.png") as image:
                self.assertEqual((100, 80), image.size)
                self.assertEqual(0, image.getpixel((0, 0))[3])
                self.assertTrue(0 < image.getpixel((30, 40))[3] < 255)
                self.assertEqual((255, 255, 255, 255), image.getpixel((42, 37)))
                composite = Image.new("RGBA", image.size, "white")
                composite.alpha_composite(image)
            expected = Image.open(io.BytesIO(render_svg(SVG))).convert("RGBA")
            differences = [abs(a-b) for a, b in zip(composite.tobytes(), expected.tobytes())]
            self.assertLessEqual(max(differences), 2)
            self.assertEqual(SVG, source.read_bytes())

    def test_unremoved_white_canvas_fails_without_publishing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);source = root / "icon.svg";source.write_bytes(SVG)
            result = export_asset(source, root / "out", background="transparent")
            self.assertEqual("FAIL", result["status"])
            self.assertFalse((root / "out/icon.png").exists())
            self.assertFalse((root / "out/icon.svg").exists())

    def test_white_svg_and_png_are_both_opaque(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);source = root / "icon.svg"
            content, _ = prepare_svg(SVG, background="transparent", remove_background_id="canvas")
            source.write_bytes(content)
            result = export_asset(source, root / "out", background="white", width=250)
            self.assertEqual("PASS", result["status"])
            with Image.open(root / "out/icon.png") as image:
                self.assertEqual((250, 200), image.size)
                self.assertEqual((255, 255, 255), image.getpixel((0, 0)))
            again = Image.open(io.BytesIO(render_svg((root / "out/icon.svg").read_bytes())))
            self.assertEqual((255, 255, 255, 255), again.convert("RGBA").getpixel((0, 0)))


if __name__ == "__main__":
    unittest.main()
