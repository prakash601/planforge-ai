import xml.etree.ElementTree as ET
from html.parser import HTMLParser

import numpy as np
import pytest
from PIL import Image
from test_measurements import exact_geometry

from planforge.measurements import measure_geometry
from planforge.rendering import render_plan


def test_plan_svg_png_and_html_repeatability(tmp_path):
    model = measure_geometry(exact_geometry())
    first = render_plan(model, tmp_path / "first")
    second = render_plan(model, tmp_path / "second")
    assert first == second
    for name in ("plan.svg", "plan.png", "index.html"):
        assert (tmp_path / "first" / name).read_bytes() == (
            tmp_path / "second" / name
        ).read_bytes()
    root = ET.parse(tmp_path / "first/plan.svg").getroot()
    text = " ".join(root.itertext())
    assert "not meters" in text
    assert "12.000" in text
    assert "2.800" in text
    assert "uncalibrated" in text
    pixels = np.array(Image.open(tmp_path / "first/plan.png"))
    assert pixels.shape == (first["height"], first["width"], 3)
    assert np.count_nonzero(np.any(pixels < 200, axis=2)) > 10_000
    assert len(first["wall_labels"]) == 4
    for element in root.findall("{http://www.w3.org/2000/svg}text"):
        assert 0 <= float(element.attrib["x"]) < first["width"]
        assert 0 <= float(element.attrib["y"]) < first["height"]


def test_hole_is_white_and_area_not_convex(tmp_path):
    model = measure_geometry(exact_geometry(holes=(((1, 1), (2, 1), (2, 2), (1, 2)),)))
    render_plan(model, tmp_path)
    root = ET.parse(tmp_path / "plan.svg").getroot()
    assert "11.000" in " ".join(root.itertext())
    polygons = root.findall("{http://www.w3.org/2000/svg}polygon")
    assert len(polygons) == 2 and polygons[1].attrib["fill"] == "white"
    image = Image.open(tmp_path / "plan.png")
    # This known fixture maps the middle of the hole to (400, 510).
    assert image.getpixel((400, 510)) == (255, 255, 255)


@pytest.mark.parametrize("partial", [True, False])
def test_partial_or_unresolved_outputs_not_fabricated(tmp_path, partial):
    geometry = exact_geometry()
    geometry["regions"] = []
    if not partial:
        geometry["orientation"] = {"status": "ambiguous"}
        geometry["walls"] = []
    model = measure_geometry(geometry)
    render_plan(model, tmp_path)
    text = " ".join(ET.parse(tmp_path / "plan.svg").getroot().itertext())
    if partial:
        assert "Partial wall support only" in text
        assert "Area [" not in text
    else:
        assert "No supported plan geometry" in text
        assert "No room boundary or dimensions invented" in text


def test_report_escapes_capture_text(tmp_path):
    geometry = exact_geometry()
    geometry["capture_id"] = "<capture&name>"
    render_plan(measure_geometry(geometry), tmp_path)
    html = (tmp_path / "index.html").read_text()
    assert "&lt;capture&amp;name&gt;" in html
    assert "<capture&name>" not in html
    HTMLParser().feed(html)
