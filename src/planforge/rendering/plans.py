"""Render the validated candidate model as matching SVG, PNG and HTML artifacts."""

import xml.etree.ElementTree as ET
from html import escape
from itertools import pairwise
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shapely import Polygon
from shapely.ops import polylabel

from planforge.measurements import validate_model


class Drawing:
    def __init__(self, width, height):
        self.root = ET.Element(
            "svg",
            {
                "xmlns": "http://www.w3.org/2000/svg",
                "viewBox": f"0 0 {width} {height}",
                "width": str(width),
                "height": str(height),
                "role": "img",
            },
        )
        ET.SubElement(
            self.root, "title"
        ).text = "Candidate plan; physical scale unverified"
        self.image = Image.new("RGB", (width, height), "white")
        self.draw = ImageDraw.Draw(self.image)

    def line(self, points, color="#26383d", width=3, dashed=False):
        coords = np.asarray(points, float)
        attributes = {
            "points": " ".join(f"{x:.3f},{y:.3f}" for x, y in coords),
            "fill": "none",
            "stroke": color,
            "stroke-width": str(width),
        }
        if dashed:
            attributes["stroke-dasharray"] = "9 6"
            for a, b in pairwise(coords):
                length = np.linalg.norm(b - a)
                for start in np.arange(0, length, 15):
                    segment = [
                        a + (b - a) * start / length,
                        a + (b - a) * min(start + 9, length) / length,
                    ]
                    self.draw.line([tuple(p) for p in segment], fill=color, width=width)
        else:
            self.draw.line([tuple(p) for p in coords], fill=color, width=width)
        ET.SubElement(self.root, "polyline", attributes)

    def polygon(self, points, color):
        ET.SubElement(
            self.root,
            "polygon",
            {"points": " ".join(f"{x:.3f},{y:.3f}" for x, y in points), "fill": color},
        )
        self.draw.polygon([tuple(point) for point in points], fill=color)

    def text(
        self, xy, text, size=20, color="#26383d", max_width=None, background=False
    ):
        font = ImageFont.load_default(size=size)
        if max_width:
            while self.draw.textlength(text, font=font) > max_width and size > 8:
                size -= 1
                font = ImageFont.load_default(size=size)
            if self.draw.textlength(text, font=font) > max_width:
                while (
                    text and self.draw.textlength(text + "...", font=font) > max_width
                ):
                    text = text[:-1]
                text += "..."
        x, y = xy
        width = self.draw.textlength(text, font=font)
        if background:
            self.draw.rectangle(
                (x - 4, y - 3, x + width + 4, y + size + 4), fill="white"
            )
            ET.SubElement(
                self.root,
                "rect",
                {
                    "x": str(x - 4),
                    "y": str(y - 3),
                    "width": str(width + 8),
                    "height": str(size + 7),
                    "fill": "white",
                },
            )
        ET.SubElement(
            self.root,
            "text",
            {
                "x": str(x),
                "y": str(y + size),
                "fill": color,
                "font-family": "sans-serif",
                "font-size": str(size),
            },
        ).text = text
        self.draw.text((x, y), text, font=font, fill=color)
        return (x - 4, y - 3, x + width + 4, y + size + 7)


def render_plan(model, output):
    """No north arrow or metric scale bar: neither convention is verified."""
    validate_model(model)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    measurements = {item["id"]: item for item in model["measurements"]}
    region_walls = [
        wall for wall in model["walls"] if wall["kind"] == "region_boundary"
    ]
    displayed = region_walls or model["walls"]
    wall_labels = {
        wall["id"]: f"W{index + 1:02}" for index, wall in enumerate(displayed)
    }
    room_labels = {
        room["id"]: f"R{index + 1:02}" for index, room in enumerate(model["rooms"])
    }
    opening_labels = {
        opening["id"]: f"O{index + 1:02}"
        for index, opening in enumerate(model["openings"])
    }
    visible_openings = [
        opening
        for opening in model["openings"]
        if set(opening.get("support_wall_ids", [opening["wall_id"]])) & set(wall_labels)
    ]
    height = max(
        1000,
        420
        + 32 * len(displayed)
        + 160 * len(model["rooms"])
        + 76 * len(model["openings"]),
    )
    drawing = Drawing(1600, height)
    drawing.text((50, 30), "PlanForge AI", 34)
    drawing.text((50, 80), model["capture_id"], 22, max_width=1450)
    drawing.text(
        (50, 117),
        "CANDIDATE PLAN  |  Scale unverified  |  Pose units, not meters",
        20,
        "#a12f32",
    )
    drawing.line([(1000, 165), (1000, height - 100)], "#d7dedf", 1)
    labels = []
    if displayed:
        coordinates = np.concatenate(
            [np.asarray(wall["endpoints_local"]) for wall in displayed]
        )
        low, high = coordinates.min(axis=0), coordinates.max(axis=0)
        span = np.maximum(high - low, 1e-6)
        scale = min(800 / span[0], 600 / span[1])
        center = (low + high) / 2

        def project(points):
            value = (np.asarray(points) - center) * scale
            return value * np.array([1, -1]) + [500, 510]

        for room in model["rooms"]:
            drawing.polygon(project(room["polygon_local"]), "#e4f1ee")
            for hole in room["holes_local"]:
                drawing.polygon(project(hole), "white")
        for wall in displayed:
            endpoints = project(wall["endpoints_local"])
            drawing.line(
                endpoints,
                "#17655e" if region_walls else "#6c777b",
                5,
                dashed=not region_walls,
            )
            midpoint = endpoints.mean(axis=0)
            direction = endpoints[1] - endpoints[0]
            normal = np.array([-direction[1], direction[0]]) / np.linalg.norm(direction)
            label = wall_labels[wall["id"]]
            for distance in (16, -32, 40, -56, 64, -80, 88, -104):
                x, y = midpoint + normal * distance - [18, 9]
                box = (x - 4, y - 3, x + 45, y + 27)
                if (
                    45 <= x <= 910
                    and 170 <= y <= 820
                    and not any(
                        box[0] < old[2]
                        and box[2] > old[0]
                        and box[1] < old[3]
                        and box[3] > old[1]
                        for old in labels
                    )
                ):
                    drawing.line([midpoint, [x + 18, y + 9]], "#aab4b5", 1)
                    labels.append(drawing.text((x, y), label, 18, background=True))
                    break
        for room in model["rooms"]:
            polygon = Polygon(room["polygon_local"], room["holes_local"])
            position = polylabel(polygon, tolerance=max(span) * 1e-4)
            x, y = project([position.x, position.y])
            labels.append(
                drawing.text(
                    (x - 20, y - 10),
                    room_labels[room["id"]],
                    22,
                    "#17655e",
                    background=True,
                )
            )
        for opening in visible_openings:
            endpoints = project(opening["endpoints_local"])
            drawing.line(endpoints, "#a12f32", 7, dashed=True)
            midpoint = endpoints.mean(axis=0)
            direction = endpoints[1] - endpoints[0]
            normal = np.array([-direction[1], direction[0]]) / np.linalg.norm(direction)
            for displacement in (24, -36, 54, -66, 84, -96):
                x, y = midpoint + normal * displacement - [18, 9]
                box = (x - 4, y - 3, x + 45, y + 27)
                if (
                    45 <= x <= 910
                    and 170 <= y <= 820
                    and not any(
                        box[0] < old[2]
                        and box[2] > old[0]
                        and box[1] < old[3]
                        and box[3] > old[1]
                        for old in labels
                    )
                ):
                    labels.append(
                        drawing.text(
                            (x, y),
                            opening_labels[opening["id"]],
                            18,
                            "#a12f32",
                            background=True,
                        )
                    )
                    break
        drawing.text(
            (50, 855),
            "Supported candidate boundaries"
            if region_walls
            else "Partial wall support only; no closed floor area",
            20,
        )
        if region_walls:
            drawing.text(
                (50, 888),
                "Other observed runs omitted from this region view. Not a whole-property footprint.",
                17,
                max_width=900,
            )
    else:
        drawing.text((80, 370), "No supported plan geometry", 30)
        drawing.text((80, 422), "Orientation unresolved or ambiguous", 22, "#a12f32")
        drawing.text((80, 463), "No room boundary or dimensions invented", 20)
    drawing.text((1030, 173), "Wall lengths [pose units]", 24)
    drawing.text(
        (1030, 213), "ID        Value         Conditional sensitivity", 17, "#6c777b"
    )
    rows = []
    y = 250
    for wall in displayed:
        item = measurements[wall["measurement_ids"][0]]
        lo, hi = item["uncertainty"]["conditional_interval"]
        label = wall_labels[wall["id"]]
        drawing.text((1030, y), label, 19)
        drawing.text((1120, y), f"{item['value']:.3f}", 19, max_width=110)
        drawing.text((1250, y), f"[{lo:.3f}, {hi:.3f}]", 18, max_width=290)
        rows.append(
            (label, "Wall length", f"{item['value']:.3f}", f"[{lo:.3f}, {hi:.3f}]")
        )
        y += 32
    for room in model["rooms"]:
        y += 20
        drawing.text((1030, y), f"{room_labels[room['id']]}  Candidate region", 22)
        for reference in room["measurement_ids"]:
            item = measurements[reference]
            label = (
                "Area [pose units^2]"
                if item["kind"] == "floor_area"
                else "Ceiling [pose units]"
            )
            value = "Unavailable" if item["value"] is None else f"{item['value']:.3f}"
            interval = item["uncertainty"]["conditional_interval"]
            sensitivity = (
                "Not observed / ambiguous"
                if interval is None
                else f"[{interval[0]:.3f}, {interval[1]:.3f}]"
            )
            y += 30
            drawing.text((1030, y), f"{label}: {value}", 18, max_width=510)
            y += 24
            drawing.text((1030, y), sensitivity, 16, "#6c777b", max_width=510)
            rows.append((room_labels[room["id"]], label, value, sensitivity))
    if model["openings"]:
        y += 35
        drawing.text((1030, y), "Opening candidates [pose units]", 22, "#a12f32")
        for opening in model["openings"]:
            item = measurements[opening["measurement_ids"][0]]
            lo, hi = item["uncertainty"]["conditional_interval"]
            y += 32
            label = opening_labels[opening["id"]]
            drawing.text(
                (1030, y),
                f"{label}  {opening['kind']} candidate: {item['value']:.3f}",
                18,
                max_width=510,
            )
            y += 24
            drawing.text(
                (1030, y),
                f"[{lo:.3f}, {hi:.3f}]  Geometry only; class unverified",
                16,
                max_width=510,
            )
            rows.append(
                (
                    label,
                    f"{opening['kind']} candidate width [pose units]",
                    f"{item['value']:.3f}",
                    f"[{lo:.3f}, {hi:.3f}]",
                )
            )
    drawing.text(
        (50, height - 60),
        "Sensitivity ranges are uncalibrated, not confidence intervals. Physical uncertainty is unknown; drift is uncorrected.",
        19,
        max_width=1490,
    )
    ET.ElementTree(drawing.root).write(
        output / "plan.svg", encoding="utf-8", xml_declaration=True
    )
    drawing.image.save(output / "plan.png")
    table = "".join(
        "<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    flags = "".join(
        f"<li>{escape(flag.replace('_', ' '))}</li>" for flag in model["flags"]
    )
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PlanForge AI - {escape(model["capture_id"])}</title><style>
*{{box-sizing:border-box}}body{{margin:0;color:#26383d;background:#fff;font:16px system-ui,sans-serif}}main{{max-width:1600px;margin:auto;padding:24px}}h1{{font-size:28px;margin:0 0 8px}}h2{{font-size:20px}}p,li{{line-height:1.5;overflow-wrap:anywhere}}.warning{{color:#a12f32}}nav{{display:flex;gap:24px;flex-wrap:wrap;margin:20px 0}}a{{color:#17655e}}img{{display:block;width:100%;height:auto}}table{{border-collapse:collapse;width:100%;max-width:900px}}td:first-child,td:nth-child(3),th:nth-child(3),td:last-child{{white-space:nowrap}}td,th{{text-align:left;border-bottom:1px solid #d7dedf;padding:12px 8px;overflow-wrap:anywhere}}th{{font-size:14px}}@media(max-width:600px){{main{{padding:16px}}td,th{{padding:10px 4px;font-size:13px}}h1{{font-size:24px}}}}
</style></head><body><main><h1>PlanForge AI</h1><p>{escape(model["capture_id"])}</p>
<p class="warning">Candidate geometry. Scale unverified; pose units are not meters. Sensitivity ranges are uncalibrated, not confidence intervals.</p>
<nav><a href="plan.svg">Open SVG</a><a href="plan.png" download>Download PNG</a><a href="measurements.json">Measurements JSON</a><a href="run.json">Run record</a></nav>
<a href="plan.svg"><img src="plan.png" alt="Candidate dimensioned plan; unverified scale" width="1600" height="{height}"></a>
<h2>Dimensions</h2><table><thead><tr><th>ID</th><th>Measurement</th><th>Value</th><th>Conditional sensitivity</th></tr></thead><tbody>{table}</tbody></table>
<h2>Evidence limits</h2><ul>{flags}</ul></main></body></html>'''
    (output / "index.html").write_text(html, encoding="utf-8")
    return {
        "svg": "plan.svg",
        "png": "plan.png",
        "report": "index.html",
        "width": 1600,
        "height": height,
        "displayed_wall_ids": [wall["id"] for wall in displayed],
        "wall_labels": wall_labels,
        "room_labels": room_labels,
        "opening_labels": opening_labels,
        "displayed_opening_ids": [opening["id"] for opening in visible_openings],
    }
