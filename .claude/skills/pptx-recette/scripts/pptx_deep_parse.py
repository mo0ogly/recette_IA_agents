#!/usr/bin/env python3
"""
Deep-parse a PPTX via python-pptx (no libreoffice needed).
Emits one line per slide with shape/text/chart/image stats, plus a summary
line with aggregate verdict. stdout is consumed by pptx_visual_recette.sh.

Exit 0 = all slides look healthy
Exit 1 = at least one empty/suspicious slide
Exit 2 = file cannot be opened / parse error
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
except ImportError:
    print("PYERR python-pptx not installed", file=sys.stderr)
    sys.exit(2)


def slide_stats(slide) -> dict:
    shapes = list(slide.shapes)
    n_shapes = len(shapes)
    n_text_runs = 0
    text_chars = 0
    n_charts = 0
    n_images = 0
    n_tables = 0
    charts_empty = 0

    for shp in shapes:
        if shp.has_text_frame:
            for p in shp.text_frame.paragraphs:
                for r in p.runs:
                    if r.text:
                        n_text_runs += 1
                        text_chars += len(r.text)
        if shp.has_chart:
            n_charts += 1
            try:
                chart = shp.chart
                has_data = False
                for plot in chart.plots:
                    for s in plot.series:
                        # Bubble charts expose bubble_sizes; regular charts have values.
                        for attr in ("values", "bubble_sizes"):
                            try:
                                arr = list(getattr(s, attr, []) or [])
                                if arr:
                                    has_data = True
                                    break
                            except Exception:
                                pass
                        if has_data:
                            break
                    if has_data:
                        break
                if not has_data:
                    charts_empty += 1
            except Exception:
                charts_empty += 1
        try:
            if shp.shape_type == MSO_SHAPE_TYPE.PICTURE:
                n_images += 1
        except (NotImplementedError, AttributeError):
            pass
        try:
            if shp.has_table:
                n_tables += 1
        except (NotImplementedError, AttributeError):
            pass

    return {
        "shapes": n_shapes,
        "text_runs": n_text_runs,
        "text_chars": text_chars,
        "charts": n_charts,
        "charts_empty": charts_empty,
        "images": n_images,
        "tables": n_tables,
    }


def main(pptx_path: str) -> int:
    p = Path(pptx_path)
    if not p.is_file():
        print(f"PYERR file not found: {pptx_path}", file=sys.stderr)
        return 2
    try:
        pres = Presentation(str(p))
    except Exception as exc:
        print(f"PYERR cannot open: {exc}", file=sys.stderr)
        return 2

    slides = list(pres.slides)
    suspicious = 0
    empty_charts_total = 0
    slides_no_content = 0

    print(f"SLIDES {len(slides)}")
    for idx, slide in enumerate(slides, start=1):
        s = slide_stats(slide)
        # A slide is "sparse" if it has <= 1 shape and no text run and no chart/image/table.
        no_content = (
            s["text_runs"] == 0
            and s["charts"] == 0
            and s["images"] == 0
            and s["tables"] == 0
        )
        if no_content:
            slides_no_content += 1
            suspicious += 1
        empty_charts_total += s["charts_empty"]
        if s["charts_empty"] > 0:
            suspicious += 1
        print(
            f"SLIDE {idx} shapes={s['shapes']} text_runs={s['text_runs']} "
            f"text_chars={s['text_chars']} charts={s['charts']} "
            f"charts_empty={s['charts_empty']} images={s['images']} "
            f"tables={s['tables']} no_content={int(no_content)}"
        )

    print(
        f"SUMMARY slides={len(slides)} suspicious={suspicious} "
        f"slides_no_content={slides_no_content} empty_charts={empty_charts_total}"
    )
    return 1 if suspicious > 0 else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: pptx_deep_parse.py <file.pptx>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
