# Working on Overbird

## Use the virtual display

Use the local virtual display when creating or changing features that affect the screen. Iterate and validate the result here before calling the work complete. Read the [preview workflow](README.md#virtual-display) for setup and limitations.

The preview executes the display lambda from `overhead.yaml`. Make layout and font changes there so the preview and firmware use the same drawing code. Do not build a separate HTML approximation of the board.

```sh
uv run --locked preview/build.py
```

Open `preview/output/index.html` to switch scenes, inspect at 1:1 scale, and export PNGs. For repeated edits, use `uv run --locked preview/build.py --watch`, then refresh the HTML after each rebuild. Stop the watcher when finished. Inline previews are snapshots and must be regenerated after edits.

## Validate changes

For display features and changes to the preview itself:

1. Run `uv run --locked preview/build.py --check` after the final edit. Fix failures; update expectations only when the requested behavior changes.
2. Inspect the generated PNGs or rendered HTML yourself. Automated checks alone do not prove the layout looks correct. Check readability, clipping, spacing, and alignment on the 800 × 480 screen.
3. Check the affected scenes, including a full board with overflow, one aircraft, long or missing data, an empty sky, and Wi-Fi/feed errors where relevant. Add a fixture in `preview/fixtures.json` for a new visible state.
4. If preview controls change, exercise scene selection, 1:1 sizing, the device frame, PNG export, and narrow-screen layout in a browser.
5. Report the checks you ran, scenes you inspected, and any remaining limitations in the handoff or PR.

When showing the result in T3 Code, pass the generated HTML to `html_preview`, inspect it, and then call `html_render`. Use the image-viewing tool to inspect generated PNGs. Keep generated artifacts in the ignored `preview/output/` directory.

## Keep the preview faithful

- New drawing calls need matching support in `preview/display_shim.h` and `preview/build.py`. Add a focused check when extending the adapter.
- New font families need a `FONT_FILES` entry and a licensed font file under `preview/fonts/`.
- Use synthetic fixtures. Do not read or embed `secrets.yaml`, credentials, or the home location in preview artifacts.
- The preview validates display output, not feed fetching/filtering, ESPHome firmware compilation, hardware behavior, e-paper refresh, or ghosting. Validate those separately when the change affects them; do not claim the preview proves them.
