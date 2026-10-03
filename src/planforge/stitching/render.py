"""Render the candidate property model as SVG, PNG and HTML artifacts."""

import xml.etree.ElementTree as ET
from html import escape
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shapely import Polygon

from .model import validate_property


def _font(size):
    return ImageFont.load_default(size=size)


def render_property(prop, output):
    prop = validate_property(prop)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)

    rooms = prop["rooms"]
    walls = prop["walls"]
    openings = prop.get("openings", [])

    room_labels = {r["id"]: f"R{i+1:02}" for i, r in enumerate(rooms)}
    # Short capture tags for display.
    caps = sorted({r.get("capture_id", "?") for r in rooms} | {w.get("capture_id", "?") for w in walls})
    cap_tag = {c: c[:8] for c in caps}

    points = []
    for r in rooms:
        points.extend(r["polygon_property"])
        for h in r.get("holes_property", []):
            points.extend(h)
    for w in walls:
        points.extend(w.get("endpoints_property", []))
    for o in openings:
        points.extend(o.get("endpoints_property", []))

    height = max(1000, 420 + 32 * len(walls) + 60 * len(rooms) + 40 * len(openings))
    width = 1600
    root = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg",
                              "viewBox": f"0 0 {width} {height}",
                              "width": str(width), "height": str(height), "role": "img"})
    ET.SubElement(root, "title").text = "Candidate property plan; scale and alignment unverified"
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    def text(xy, s, size=20, color="#26383d", max_width=None):
        font = _font(size)
        if max_width:
            while draw.textlength(s, font=font) > max_width and size > 8:
                size -= 1
                font = _font(size)
        x, y = xy
        ET.SubElement(root, "text", {"x": str(x), "y": str(y + size),
                                     "fill": color, "font-family": "sans-serif",
                                     "font-size": str(size)}).text = s
        draw.text((x, y), s, font=font, fill=color)

    def line(points, color="#26383d", w=3, dashed=False):
        coords = np.asarray(points, float)
        attrs = {"points": " ".join(f"{x:.3f},{y:.3f}" for x, y in coords),
                 "fill": "none", "stroke": color, "stroke-width": str(w)}
        if dashed:
            attrs["stroke-dasharray"] = "9 6"
        ET.SubElement(root, "polyline", attrs)
        draw.line([tuple(p) for p in coords], fill=color, width=w)

    def polygon(points, color):
        ET.SubElement(root, "polygon",
                      {"points": " ".join(f"{x:.3f},{y:.3f}" for x, y in points), "fill": color})
        draw.polygon([tuple(p) for p in points], fill=color)

    text((50, 30), "PlanForge AI  |  Candidate property plan", 28)
    text((50, 80), prop["property_id"], 20, max_width=1450)
    text((50, 117), "ASSUMED SINGLE PROPERTY  |  Scale and inter-capture alignment unverified  |  Pose units, not meters",
         18, "#a12f32")
    # Divider between map and tables.
    line([(1000, 165), (1000, height - 100)], "#d7dedf", 1)

    if points:
        coords = np.asarray(points, float)
        low, high = coords.min(axis=0), coords.max(axis=0)
        span = np.maximum(high - low, 1e-6)
        scale = min(800 / span[0], 600 / span[1])
        center = (low + high) / 2

        def project(pts):
            v = (np.asarray(pts, float) - center) * scale
            return (v * np.array([1, -1]) + [500, 510]).tolist()

        palette = ["#e4f1ee", "#e8eef7", "#f1ece4", "#ece4f1"]
        cap_color = {c: palette[i % len(palette)] for i, c in enumerate(caps)}
        for r in rooms:
            polygon(project(r["polygon_property"]), cap_color.get(r.get("capture_id"), "#e4f1ee"))
            for h in r.get("holes_property", []):
                polygon(project(h), "white")
        for w in walls:
            line(project(w["endpoints_property"]),
                 "#17655e" if w.get("kind") == "region_boundary" else "#6c777b",
                 5, dashed=(w.get("kind") != "region_boundary"))
        for o in openings:
            line(project(o["endpoints_property"]), "#a12f32", 7, dashed=True)
        # Room labels at polygon centroids.
        for r in rooms:
            try:
                poly = Polygon(r["polygon_property"])
                c = [poly.centroid.x, poly.centroid.y]
            except Exception:
                c = np.asarray(r["polygon_property"]).mean(axis=0).tolist()
            x, y = project([c])[0]
            label = f"{room_labels[r['id']]} ({cap_tag.get(r.get('capture_id'), '?')})"
            text((x - 40, y - 10), label, 18, "#17655e")
    else:
        text((80, 370), "No supported property geometry", 30)
        text((80, 422), "No closed regions in any input capture", 22, "#a12f32")
        text((80, 463), "Observed wall runs are listed; no footprint invented", 20)

    # Right-hand tables.
    y = 173
    text((1030, y), "Rooms", 24)
    y += 37
    if rooms:
        for r in rooms:
            text((1030, y), f"{room_labels[r['id']]}  {cap_tag.get(r.get('capture_id'), '?')}  {r['id'][:13]}", 17, max_width=510)
            y += 30
    else:
        text((1030, y), "No closed candidate rooms", 18)
        y += 30
    y += 15
    text((1030, y), f"Walls ({len(walls)} runs)", 22)
    y += 34
    for w in walls[:30]:
        text((1030, y), f"{cap_tag.get(w.get('capture_id'), '?')}  {w.get('kind', '')}  {w['id'][:20]}", 15, max_width=510)
        y += 26
    if len(walls) > 30:
        text((1030, y), f"... and {len(walls) - 30} more (see property.json)", 15)
        y += 26
    y += 12
    edges = prop["room_graph"]["edges"]
    overlaps = prop.get("overlaps", [])
    text((1030, y), f"Adjacency edges: {len(edges)}", 20)
    y += 30
    if edges:
        for e in edges:
            text((1030, y), f"{e['room_a'][:13]} -- {e['room_b'][:13]}", 15, max_width=510)
            y += 26
    else:
        text((1030, y), "Rooms unconnected; no shared openings", 16, "#a12f32", max_width=510)
        y += 26
    text((1030, y), f"Overlaps: {len(overlaps)}", 20)
    y += 30
    for o in overlaps[:8]:
        text((1030, y), f"{o['room_a'][:10]} x {o['room_b'][:10]}  {o['overlap_area_pose2']:.3f}", 15, max_width=510)
        y += 26

    text((50, height - 60), "Candidate stitching. Identity or manual 2D transforms only; no measured alignment, drift correction, or physical accuracy.",
         18, max_width=1490)

    ET.ElementTree(root).write(output / "property.svg", encoding="utf-8", xml_declaration=True)
    image.save(output / "property.png")

    rows = "".join(
        f"<tr><td>{escape(room_labels[r['id']])}</td><td>{escape(str(r.get('capture_id','')))}</td><td>{escape(r['id'])}</td></tr>"
        for r in rooms
    )
    flags = "".join(f"<li>{escape(f.replace('_', ' '))}</li>" for f in prop["flags"])
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PlanForge AI - {escape(prop["property_id"])}</title><style>
*{{box-sizing:border-box}}body{{margin:0;color:#26383d;background:#fff;font:16px system-ui,sans-serif}}main{{max-width:1600px;margin:auto;padding:24px}}h1{{font-size:28px;margin:0 0 8px}}p,li{{line-height:1.5;overflow-wrap:anywhere}}.warning{{color:#a12f32}}nav{{display:flex;gap:24px;flex-wrap:wrap;margin:20px 0}}a{{color:#17655e}}img{{display:block;width:100%;height:auto}}table{{border-collapse:collapse;width:100%;max-width:900px}}td,th{{text-align:left;border-bottom:1px solid #d7dedf;padding:12px 8px;overflow-wrap:anywhere}}@media(max-width:600px){{main{{padding:16px}}}}
</style></head><body><main><h1>PlanForge AI | Candidate property</h1><p>{escape(prop["property_id"])}</p>
<p class="warning">Assumed single property per user instruction, not evidence. Scale and inter-capture alignment unverified; pose units are not meters.</p>
<nav><a href="property.svg">Open SVG</a><a href="property.png" download>Download PNG</a><a href="property.json">Property JSON</a><a href="run.json">Run record</a></nav>
<a href="property.svg"><img src="property.png" alt="Candidate stitched property plan; alignment unverified" width="1600" height="{height}"></a>
<h2>Rooms</h2><table><thead><tr><th>ID</th><th>Capture</th><th>Stable room ID</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Evidence limits</h2><ul>{flags}</ul></main></body></html>'''
    (output / "index.html").write_text(html, encoding="utf-8")
    return {"svg": "property.svg", "png": "property.png", "report": "index.html",
            "width": width, "height": height, "room_labels": room_labels}
