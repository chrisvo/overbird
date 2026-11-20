# Overhead

An ESPHome flight board for the Seeed reTerminal E1001. The firmware configuration is in `overhead.yaml`.

## Virtual display

Build an interactive, offline copy of the display without flashing the device:

```sh
uv run --locked preview/build.py
open preview/output/index.html
```

Requires [uv](https://docs.astral.sh/uv/) and a C++17 compiler. On macOS, the Xcode command line tools provide `c++`. Python dependencies are locked and installed by uv on the first run. Subsequent builds and the generated HTML work offline.

Choose a scene to see sample aircraft, missing fields, an empty sky, or connection/feed errors. Use **View at 1:1** to inspect individual pixels and **Save PNG** to export the 800 × 480 screen. The device frame is illustrative.

### Edit and preview

1. Change the `display` lambda or `font` sizes in `overhead.yaml`.
2. Run the build command again and refresh the HTML file.
3. Inspect `preview/output/busy.png`, or any other scene's PNG, to review the result.

For repeated edits, run `uv run --locked preview/build.py --watch`. It rebuilds when the YAML, fixtures, fonts, or preview template changes. Refresh the HTML after each build. Stop the watcher with Ctrl-C.

The preview compiles and executes the **actual display lambda** from `overhead.yaml` using a small host display adapter. It also reuses the feed's `snprintf` format. Layout coordinates, font sizes, row limits, status branches, and the range caption come from the firmware configuration. There is no separate HTML copy of the board layout to keep in sync.

`preview/fixtures.json` supplies sample aircraft as `[flight, type, altitude, speed, distance]` and optional status text. These are display fixtures; the preview does not call the feed or simulate aircraft filtering. It does not read `secrets.yaml` or contact the hardware.

For an agent working on the layout, build the preview, inspect the generated PNGs, and show `preview/output/index.html` using T3's `html_preview` followed by `html_render`. Rebuild and render again after edits; an already displayed inline preview is a snapshot.

### Fidelity and checks

The [E1001 panel](https://esphome.io/components/display/epaper_spi/) is 800 × 480 and monochrome. The preview rasterizes the bundled IBM Plex Mono and Inter fonts with FreeType's monochrome flags, integer glyph advances, and top alignment used by [ESPHome's font renderer](https://github.com/esphome/esphome/tree/dev/esphome/components/font). Firmware currently downloads Google Fonts independently, so font revisions or FreeType versions can cause small differences. The preview does not simulate e-paper refresh, ghosting, or physical contrast.

The host adapter supports the current `print`, `printf`, horizontal/vertical lines, rectangles, and fills. New drawing APIs need matching support in `preview/display_shim.h` and `preview/build.py`; unsupported C++ calls fail at build time. New font families need an entry in `FONT_FILES` and a licensed font file in `preview/fonts`. Rotation and custom glyph sets are not supported.

```sh
uv run --locked preview/build.py --check
```

Checks cover row sorting and truncation, overflow, empty/error states, binary pixel output, and propagation of firmware edits. Generated HTML, PNGs, and recorded drawing commands are in the ignored `preview/output/` directory.

Bundled fonts are from [Google Fonts' IBM Plex Mono directory](https://github.com/google/fonts/tree/main/ofl/ibmplexmono) and [Inter directory](https://github.com/google/fonts/tree/main/ofl/inter). Their OFL licenses are included beside the font files.
