# Overhead

An ESPHome flight board for the Seeed reTerminal E1001. The firmware configuration is in `overhead.yaml`.

## On the device

The two white buttons cycle backward and forward through **Radar**, **Spotlight**, and **Flight Cards**. The green button returns to Radar. All three views use the latest flight snapshot.

Radar puts your configured location at the center, with true north at the top. The inner ring is half the selected range. Airplane icons mark the four closest aircraft and their numbers match the sidebar. When two icons would overlap, a line connects the shifted icon to its position. Other aircraft appear as dots.

With aircraft in range, the board checks for new positions every minute while it has requests saved for faster updates. During sustained traffic it settles to about three minutes. An empty sky or a feed error uses five-minute checks. The board syncs its clock before polling so it can preserve its request budget and any active quota wait across power cycles. [adsb.lol API limits](https://www.adsb.lol/docs/open-data/api)

## Virtual display

Build an interactive, offline copy of the display without flashing the device:

```sh
uv run --locked preview/build.py
open preview/output/index.html
```

Requires [uv](https://docs.astral.sh/uv/) and a C++17 compiler. On macOS, the Xcode command line tools provide `c++`. Python dependencies are locked and installed by uv on the first run. Subsequent builds and the generated HTML work offline.

Choose a scene to see sample aircraft, missing fields, an empty sky, or connection/feed errors. Use the arrows and green Radar button to try the three views. **View at 1:1** shows individual pixels and **Save PNG** exports the selected 800 × 480 screen. The device frame is illustrative.

### Edit and preview

1. Change the `display` lambda or `font` sizes in `overhead.yaml`.
2. Run the build command again and refresh the HTML file.
3. Inspect `preview/output/radar-busy.png`, or any other view and scene's PNG, to review the result.

For repeated edits, run `uv run --locked preview/build.py --watch`. It rebuilds when the YAML, shared aircraft header, fixtures, fonts, or preview template changes. Refresh the HTML after each build. Stop the watcher with Ctrl-C.

The preview compiles and executes the **actual display lambda** from `overhead.yaml` using a small host display adapter. It shares the firmware's aircraft type from `overhead.h`. Layout coordinates, font sizes, view contents, status branches, and the range caption come from the firmware configuration.

`preview/fixtures.json` supplies sample aircraft as `[flight, type, altitude_ft, speed_kt, distance_nm, bearing_deg]` and optional status text. Use `null` for unknown altitude or speed. The preview uses these synthetic fixtures and runs offline.

For an agent working on the layout, build the preview, inspect the generated PNGs, and show `preview/output/index.html` using T3's `html_preview` followed by `html_render`. Rebuild and render again after edits; an already displayed inline preview is a snapshot.

### Fidelity and checks

The [E1001 panel](https://esphome.io/components/display/epaper_spi/) is 800 × 480 and monochrome. The preview rasterizes the bundled IBM Plex Mono and Inter fonts with FreeType's monochrome flags, integer glyph advances, and top alignment used by [ESPHome's font renderer](https://github.com/esphome/esphome/tree/dev/esphome/components/font). Firmware currently downloads Google Fonts independently, so font revisions or FreeType versions can cause small differences. The preview does not simulate e-paper refresh, ghosting, or physical contrast.

The host adapter supports `print`, `printf`, horizontal/vertical lines, circles, rectangles, and fills. New drawing APIs need matching support in `preview/display_shim.h` and `preview/build.py`. New font families need an entry in `FONT_FILES` and a licensed font file in `preview/fonts`.

```sh
uv run --locked preview/build.py --check
```

Checks cover view navigation, radar bearings and rings, sorting and truncation, overflow, empty/error states, binary pixel output, and propagation of firmware edits. Generated HTML, PNGs, and recorded drawing commands are in the ignored `preview/output/` directory.

Bundled fonts are from [Google Fonts' IBM Plex Mono directory](https://github.com/google/fonts/tree/main/ofl/ibmplexmono) and [Inter directory](https://github.com/google/fonts/tree/main/ofl/inter). Their OFL licenses are included beside the font files.
