# Standalone scientific emblems and schematic assets

Use this local workflow when the deliverable is an individual pictogram, model emblem,
or a set of reusable schematic assets for the author's own layout. It is not a new
final-figure mode, a branding service, or permission to alter measured evidence.

## Decide what the object must communicate

| Role | Main job | Detail that does not belong by default |
|---|---|---|
| Method schematic | Explain source-established transformations and relationships | Unsupported mechanisms or decorative branches |
| Model emblem | Give one research object or capability a recognizable identity | Every layer, head, loss, or benchmark result |
| Category pictogram | Make a method or task family easy to recognize at small size | Model-specific implementation details |
| Reusable asset | Supply a clean object for later assembly | Page labels, panel letters, connectors, selection handles, or decorative containers |

For an emblem, identify the research object, the model's defining idea, and one visual
relationship that joins them. Do not alternate between an anatomy illustration, an
architecture diagram, and an arbitrary geometric mark while calling all three the
same brief. Judge the silhouette and recognizability at its intended insertion size.
Node counts and decorative links are illustrative unless the source establishes them.

Inspect supplied references, but distinguish what each governs: object content,
composition, colour, or rendering finish. Borrow visual reasoning, not a reference
paper's biological claims or its artwork. Confirm redistribution rights before
including any third-party asset in a shared package.

New conceptual designs follow the applicable [concept-generation route](image-concept-to-vector.md).
Respect a request limited to PNG/SVG or another narrower format. A small change to an
existing native asset, or an export-only task, does not need a new generated concept.

## Lock the small delivery brief

Use existing notes or an asset inventory; no extra project schema is required. Record:

- stable asset ID and the source/accepted version;
- what is included in the object and what the author will add during layout;
- requested formats, dimensions or insertion size, and background (`transparent` or `white`);
- whether text, a wordmark, a surrounding badge, or a frame is requested;
- required structural strokes and surfaces, including any intentionally white or translucent parts;
- the asset's schematic/decorative role and any source or permission constraints.

An annotation rectangle is a selection aid, not a literal crop instruction. Inspect
inside it for incidental text, arrows and backgrounds. Likewise, **circular composition
does not request a circular badge**. Keep inherent geometry such as a globe's latitude
lines or a magnifier handle; omit an added container unless it is requested.

For an asset set, keep the ID-to-file mapping stable, preserve accepted variants and
export the requested subset without changing unrelated assets. Keep labels on a preview
sheet separate from text-free deliverables. State if individual silhouettes have been
redrawn rather than extracted from a supplied image.

## Export without damaging the foreground

Prefer an existing native scene. To remove its page background, remove only the
explicitly identified canvas object and rerender. Do not delete all white pixels or all
white SVG shapes: they may be highlights, a pale membrane, or part of the symbol.
Preserve foreground opacity; transparency does not mean making every object opaque.
When authoring an SVG for both backgrounds, keep the page canvas as a separate
root-level rectangle with a stable ID, so later exports can remove it precisely.

The standalone helper accepts a PNG or a self-contained SVG:

```bash
SKILL_DIR="$PWD/skills/build-scientific-visualizations"

# SVG rendering is an optional Python 3.10+ dependency, separate from bitmap checks.
python3 -m pip install -r "$SKILL_DIR/requirements-assets.txt"

python3 "$SKILL_DIR/shared/figure-core/scripts/export_schematic_asset.py" export \
  "$SKILL_DIR/examples/standalone-schematic-asset/asset.svg" \
  --output-dir outputs/icons --background transparent \
  --remove-background-id canvas --width-px 1000

# Check the delivered file, independently of any figure project or earlier preview.
python3 "$SKILL_DIR/shared/figure-core/scripts/export_schematic_asset.py" check \
  outputs/icons/asset.png --background transparent
```

PNG export/check uses Pillow and works on Python 3.9+. SVG rasterization additionally
requires Python 3.10+, CairoSVG 2.9.1 or later, and the system Cairo library. On Debian/
Ubuntu the latter is `libcairo2`; use the platform's Cairo installation elsewhere.
Missing dependencies produce `FAIL`, not a successful unverified export. The helper
does not fall back to an older SVG renderer on Python 3.9.

The SVG helper requires a finite positive `viewBox` and rejects declarations/entities,
external resources, scripts and `foreignObject`; embed PNG/JPEG resources first if
authorized. Removal is conservative: the named background must be an unstyled,
untransformed, root-level full-canvas rectangle behind the foreground. Complex CSS,
groups or masks need editing in their native authoring tool, followed by the same
output check. Do not work around a refusal by deleting arbitrary shapes.

`--background transparent` never guesses which painted shapes are backgrounds. Without
an explicit removal ID, an opaque SVG canvas fails the rendered transparency check.
Opaque PNG/checkerboard sources also fail; this helper does not synthesize a cutout.
`--background white` adds/composites a white canvas behind the existing foreground.
It does not erase an already painted coloured background.

The exporter writes PNG and prepared SVG for SVG input, or PNG for PNG input. It checks
rendered alpha before publishing outputs, refuses to replace the source, and refuses
existing destinations unless `--overwrite` is supplied. No failed validation should
be described as a newly exported successful asset; an older output may still exist.

## Check the exact files being handed over

For a requested transparent asset, inspect effective alpha, transparent outer margins,
and non-empty foreground. RGB and fully opaque RGBA files do not become transparent
because a checkerboard is visible. Palette PNG transparency is valid when actually
encoded. Semi-transparent membranes and antialiased edges are expected, not defects.

Alpha checks are necessary, not proof that the cutout is visually correct. A painted
checkerboard inside an opaque rectangle can survive if someone adds transparent
padding around it. Inspect the actual image on light and dark backgrounds for remaining
patterns, missing white foreground, fringes, and clipped edges. For a background-only
change, compare a recomposition on the previous background with the accepted source;
allow small renderer rounding differences, not changed object geometry.

Report SVG representation accurately:

- `native_vector`: no embedded image element found;
- `mixed`: raster content and vector objects are both present;
- `embedded_bitmap`: an image container, not a component-editable vector drawing.

This is a conservative inventory, not a proof that an image is visible, scientifically
correct, or editable in PowerPoint. Do not reject a valid mixed scientific figure
merely because it contains an image; check whether its declared representation is true.

Deliver the requested files and a small ID/file index when helpful. Do not insert a
technical report, preview background, or internal authoring notes into the icon itself.
When an asset becomes part of a paper figure, apply the normal source-data contract,
semantic checks, final-size inspection and audience-specific packaging to that figure.
