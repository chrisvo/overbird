# /// script
# requires-python = ">=3.11"
# dependencies = ["PyYAML>=6,<7", "Pillow>=11,<13", "freetype-py>=2.5,<3"]
# ///
"""Run the firmware display lambda on the host and render an offline preview."""

import argparse
import base64
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

import freetype
from PIL import Image, ImageDraw
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SIZE = (800, 480)
FONT_FILES = {
    "gfonts://IBM Plex Mono": ("IBMPlexMono-Regular.ttf", None),
    "gfonts://Inter": ("Inter.ttf", 400),
    "gfonts://Inter@700": ("Inter.ttf", 700),
}


class ConfigLoader(yaml.SafeLoader):
    pass


# Secrets are deliberately unresolved. No credentials or home location are read.
ConfigLoader.add_constructor("!secret", lambda loader, node: None)
ConfigLoader.add_constructor("!lambda", lambda loader, node: loader.construct_scalar(node))


def read_config(path):
    config = yaml.load(path.read_text(), Loader=ConfigLoader)
    displays = [item for item in config["display"] if item["id"] == "board_display"]
    if len(displays) != 1 or displays[0]["model"] != "Seeed-reTerminal-E1001":
        raise ValueError("The preview requires a Seeed-reTerminal-E1001 board_display.")
    if displays[0].get("rotation", 0) != 0:
        raise ValueError("Add rotation support to the preview before changing display rotation.")
    return config, displays[0]["lambda"]


def record_commands(config, drawing, fixtures):
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, (dict, list)):
            for child in value.values() if isinstance(value, dict) else value:
                yield from strings(child)

    def substitute(match):
        value = config.get("substitutions", {}).get(match[1])
        if value is None:
            raise ValueError(f"Preview cannot resolve substitution {match[1]!r}.")
        return str(value)

    drawing = re.sub(r"\$\{(\w+)\}", substitute, drawing)
    # Reuse the live feed's snprintf format for sample rows too.
    fetch = next(script for script in config["script"] if script["id"] == "fetch_aircraft")
    row_format = re.search(r'snprintf\(row, sizeof\(row\), ("(?:\\.|[^"\\])*"),', '\n'.join(strings(fetch)))
    if not row_format:
        raise ValueError("Cannot find the aircraft row format. Update the fixture adapter.")
    declarations = []
    for item in config["font"]:
        name = item["id"]
        if not re.fullmatch(r"[A-Za-z_]\w*", name):
            raise ValueError(f"Invalid font ID: {name}")
        declarations.append(f'Font {name}_value{{"{name}"}}; Font *{name} = &{name}_value;')
    source = '\n'.join([
        '#include "display_shim.h"',
        '#define id(name) name',
        *declarations,
        'std::vector<std::pair<double, std::string>> aircraft_rows;',
        'std::string board_status;',
        'void draw(Display &it) {', drawing, '}',
        'int main() {',
    ])
    for fixture in fixtures:
        source += '\naircraft_rows.clear();\n'
        source += f'board_status = {json.dumps(fixture.get("status", ""))};\n'
        for flight, kind, altitude, speed, distance in fixture.get("aircraft", []):
            args = ', '.join(json.dumps(str(value)) for value in (flight, kind, altitude, speed))
            source += (
                '{ char row[64]; '
                f'snprintf(row, sizeof(row), {row_format[1]}, {args}, {float(distance)!r}); '
                f'aircraft_rows.emplace_back({float(distance)!r}, row); }}\n'
            )
        source += 'std::sort(aircraft_rows.begin(), aircraft_rows.end());\n'
        source += '{ Display it; std::cout << "["; draw(it); std::cout << "]\\n"; }\n'
    source += '}\n'
    with tempfile.TemporaryDirectory(prefix="overbird-preview-") as temp:
        cpp = Path(temp) / "display.cpp"
        executable = Path(temp) / "display"
        cpp.write_text(source)
        subprocess.run([os.environ.get("CXX", "c++"), "-std=c++17", "-Wall", "-Wextra", "-I", str(HERE), str(cpp), "-o", str(executable)], check=True)
        output = subprocess.check_output([str(executable)], text=True)
    return [json.loads(line) for line in output.splitlines()]


class BitmapFont:
    """Use ESPHome's FreeType mono flags, glyph advances, and top offsets."""

    def __init__(self, config):
        if config.get("bpp", 1) != 1 or "extras" in config or "glyphs" in config:
            raise ValueError("The preview currently supports default 1-bit font glyphs only.")
        font_file, weight = FONT_FILES[config["file"]]
        self.face = freetype.Face(str(HERE / "fonts" / font_file))
        if weight is not None:
            axes = self.face.get_variation_info().axes
            self.face.set_var_design_coords([weight if axis.tag == "wght" else axis.default for axis in axes])
        self.face.set_pixel_sizes(config["size"], 0)
        self.baseline = (self.face.size.ascender + 63) // 64
        self.height = (self.face.size.height + 63) // 64
        self.cache = {}

    def glyph(self, char):
        if char not in self.cache:
            if not self.face.get_char_index(ord(char)):
                raise ValueError(f"Font has no glyph for {char!r}")
            self.face.load_char(char, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_MONO)
            slot = self.face.glyph
            bitmap = slot.bitmap
            mask = Image.new("L", (bitmap.width, bitmap.rows))
            buffer = bitmap.buffer
            mask.putdata([
                255 if buffer[y * bitmap.pitch + x // 8] & (0x80 >> (x % 8)) else 0
                for y in range(bitmap.rows) for x in range(bitmap.width)
            ])
            self.cache[char] = (mask, slot.bitmap_left, self.baseline - slot.bitmap_top, (slot.metrics.horiAdvance + 63) // 64)
        return self.cache[char]

    def draw(self, image, command):
        glyphs = [self.glyph(char) for char in command["text"]]
        advance = sum(glyph[3] for glyph in glyphs)
        x, y = command["x"], command["y"]
        align = command["align"]
        if align.endswith("RIGHT"):
            x -= advance
        elif align in ("TOP_CENTER", "CENTER"):
            x -= advance // 2
        if align.startswith("BASELINE"):
            y -= self.baseline
        elif align.startswith("BOTTOM"):
            y -= self.height
        elif align == "CENTER":
            y -= self.height // 2
        clipped = False
        for mask, left, top, width in glyphs:
            bounds = mask.getbbox()
            if bounds:
                x1, y1, x2, y2 = bounds
                clipped |= x + left + x1 < 0 or y + top + y1 < 0 or x + left + x2 > SIZE[0] or y + top + y2 > SIZE[1]
                image.paste(command["color"], (x + left, y + top), mask)
            x += width
        return clipped


def render(commands, fonts):
    image = Image.new("RGB", SIZE, "white")
    pen = ImageDraw.Draw(image)
    warnings = []
    for command in commands:
        if command["kind"] == "text":
            if fonts[command["font"]].draw(image, command):
                warnings.append(f'Text extends beyond the display: {command["text"].strip()}')
        else:
            x, y, w, h = (command[key] for key in ("x", "y", "w", "h"))
            if w <= 0 or h <= 0:
                continue
            box = (x, y, x + w - 1, y + h - 1)
            pen.rectangle(box, outline=command["color"], fill=command["color"] if command["kind"] == "fill" else None)
    return image.convert("1"), warnings


def build(config_path=ROOT / "overhead.yaml", output=HERE / "output", fixtures_path=HERE / "fixtures.json"):
    config, drawing = read_config(config_path)
    fixtures = json.loads(fixtures_path.read_text())
    ids = [fixture["id"] for fixture in fixtures]
    if not fixtures or len(set(ids)) != len(ids) or any(not re.fullmatch(r"[a-z0-9-]+", name) for name in ids):
        raise ValueError("Fixtures need unique, nonempty lowercase IDs using letters, numbers, or hyphens.")
    commands = record_commands(config, drawing, fixtures)
    fonts = {item["id"]: BitmapFont(item) for item in config["font"]}
    output.mkdir(parents=True, exist_ok=True)
    states = []
    for fixture, operations in zip(fixtures, commands, strict=True):
        image, warnings = render(operations, fonts)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        png = buffer.getvalue()
        (output / f'{fixture["id"]}.png').write_bytes(png)
        states.append({
            "id": fixture["id"], "label": fixture["label"], "description": fixture["description"],
            "image": "data:image/png;base64," + base64.b64encode(png).decode(),
            "warnings": warnings, "commands": operations,
        })
    records = [{key: value for key, value in state.items() if key != "image"} for state in states]
    (output / "commands.json").write_text(json.dumps(records, indent=2) + '\n')
    payload = json.dumps({"states": [{key: value for key, value in state.items() if key != "commands"} for state in states]})
    html = (HERE / "template.html").read_text().replace("__PREVIEW_DATA__", payload.replace("<", "\\u003c"))
    (output / "index.html").write_text(html)
    print(f"Built {len(states)} states: {output / 'index.html'}", flush=True)
    for state in states:
        for warning in state["warnings"]:
            print(f'{state["id"]}: {warning}', flush=True)
    return states


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "overhead.yaml")
    parser.add_argument("--output", type=Path, default=HERE / "output")
    parser.add_argument("--fixtures", type=Path, default=HERE / "fixtures.json")
    parser.add_argument("--watch", action="store_true", help="Rebuild on save; refresh the HTML file to see changes.")
    parser.add_argument("--check", action="store_true", help="Run preview regression checks after building.")
    args = parser.parse_args()
    build(args.config, args.output, args.fixtures)
    if args.check:
        import unittest
        suite = unittest.defaultTestLoader.discover(str(HERE), pattern="test_*.py")
        if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
            raise SystemExit(1)
    if not args.watch:
        return
    watched = [args.config, args.fixtures, HERE / "display_shim.h", HERE / "template.html", *sorted((HERE / "fonts").glob("*.ttf"))]
    previous = [path.stat().st_mtime_ns for path in watched]
    print("Watching layout, fixtures, and fonts. Refresh the HTML after each rebuild. Ctrl-C stops.", flush=True)
    while True:
        time.sleep(0.4)
        current = [path.stat().st_mtime_ns for path in watched]
        if current != previous:
            previous = current
            try:
                build(args.config, args.output, args.fixtures)
            except Exception as error:
                print(f"Build failed; keeping the last preview. {error}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
