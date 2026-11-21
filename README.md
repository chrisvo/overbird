# Overbird

An ESPHome flight board for the Seeed reTerminal E1001. The firmware configuration is in `overhead.yaml`.

## On the device

The two white buttons cycle backward and forward through **Radar**, **Spotlight**, and **Flight Cards**. The green button returns to Radar. All three views use the latest flight snapshot.

The board ranks aircraft by estimated straight-line distance, using ground distance and reported altitude as height above the observer. It uses geometric altitude when barometric altitude is unavailable. When altitude is missing or below zero, the board ranks the aircraft by ground distance alone. The map and displayed distances use ground distance.

Radar puts your configured location at the center, with true north at the top. The inner ring is half the selected range. The four closest aircraft are numbered and their map icons point along the reported ground track. A ring on the map indicates a numbered aircraft with unknown track. When icons would overlap, a line connects a shifted icon to its position. Other aircraft appear as dots. Dotted trails connect up to two previous reported positions for the numbered aircraft.

The board uses a swept-wing icon for jets, a straight-wing icon for non-jet airplanes, and a rotor icon for helicopters and other rotorcraft. It uses a small arrow when the aircraft class is unknown. The receiver can supply a model designator or report the rotorcraft emitter category directly. [FAA aircraft designators](https://www.faa.gov/documentLibrary/media/Order/FAA_Order_JO_7360.1K_Aircraft_Type_Designators.pdf) · [readsb feed fields](https://github.com/wiedehopf/readsb/blob/dev/README-json.md)

The views show an airline name beside the callsign when the board recognizes its three-letter designator. Aircraft with unrecognized callsigns or only a registration still show their identifier. [ICAO airline designators](https://www.icao.int/operational-safety/Designators-and-indicators)

The footer shows the time of the last successful update in UTC, including seconds. If the feed stops updating or Wi-Fi goes offline, the board labels the last snapshot stale and retains it for up to five minutes after that update.

Set `receiver_url` in `secrets.yaml` to the LAN address of your dump1090 or readsb `aircraft.json` endpoint. The board requests a snapshot every 10 seconds, even when the sky is empty, and filters aircraft to the configured radius on the device. It backs off when the receiver returns an error. [dump1090 JSON format](https://github.com/flightaware/dump1090/blob/master/README-json.md)

The board syncs its clock before polling so it can detect expired receiver snapshots. For a LAN without internet access, set the `time_servers` list in `overhead.yaml` to reachable LAN NTP servers. The receiver needs an accurate clock too. [ESPHome SNTP configuration](https://esphome.io/components/time/sntp/)

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

`preview/fixtures.json` supplies sample aircraft as `[flight, type, altitude_ft, speed_kt, distance_nm, bearing_deg, track_deg, history, emitter_category]`. Track, history, and emitter category are optional. History contains distance and bearing pairs, most recent first. A scene can set status text and `updated_at` to show a retained snapshot. Use `null` for unknown altitude, speed, or track. The preview uses synthetic fixtures and runs offline.

For an agent working on the layout, build the preview, inspect the generated PNGs, and show `preview/output/index.html` using T3's `html_preview` followed by `html_render`. Rebuild and render again after edits; an already displayed inline preview is a snapshot.

### Fidelity and checks

The [E1001 panel](https://esphome.io/components/display/epaper_spi/) is 800 × 480 and monochrome. The preview rasterizes the bundled IBM Plex Mono and Inter fonts with FreeType's monochrome flags, integer glyph advances, and top alignment used by [ESPHome's font renderer](https://github.com/esphome/esphome/tree/dev/esphome/components/font). Firmware currently downloads Google Fonts independently, so font revisions or FreeType versions can cause small differences. The preview does not simulate e-paper refresh, ghosting, or physical contrast.

The host adapter supports `print`, `printf`, horizontal/vertical lines, circles, rectangles, and fills. New drawing APIs need matching support in `preview/display_shim.h` and `preview/build.py`. New font families need an entry in `FONT_FILES` and a licensed font file in `preview/fonts`.

```sh
uv run --locked preview/build.py --check
```

Checks cover view navigation, radar bearings and rings, sorting and truncation, overflow, empty/error states, binary pixel output, and propagation of firmware edits. Generated HTML, PNGs, and recorded drawing commands are in the ignored `preview/output/` directory.

Bundled fonts are from [Google Fonts' IBM Plex Mono directory](https://github.com/google/fonts/tree/main/ofl/ibmplexmono) and [Inter directory](https://github.com/google/fonts/tree/main/ofl/inter). Their OFL licenses are included beside the font files.
