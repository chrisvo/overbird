from pathlib import Path
import tempfile
import unittest

from PIL import Image
import yaml

from build import ROOT, build, read_config, record_commands


class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temp.name)
        cls.states = {state["id"]: state for state in build(output=cls.output)}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def texts(self, state):
        return [command["text"] for command in self.states[state]["commands"] if command["kind"] == "text"]

    def test_busy_sky_shows_nearest_first_and_reports_overflow(self):
        cards = self.texts("cards-busy")
        expected = ["SWA1482", "N172SP", "DAL281", "UAL934", "ASA617", "AAL902"]
        self.assertEqual([value for value in cards if value in expected], expected)
        self.assertNotIn("FDX502", cards)
        self.assertIn("+2 more", cards)
        self.assertIn("12,400", cards)
        for view in ("radar", "spotlight"):
            text = self.texts(f"{view}-busy")
            self.assertIn("+4 more", text)
            self.assertTrue(set(expected[:4]).issubset(text))

    def test_all_views_rank_by_ground_distance_and_altitude(self):
        expected = ["N172SP", "DAL281", "UAL934", "N204AB"]
        for view in ("radar", "spotlight", "cards"):
            with self.subTest(view=view):
                text = self.texts(f"{view}-altitude")
                self.assertEqual([value for value in text if value in expected], expected)

    def test_empty_and_failure_states(self):
        expected = {
            "empty": "No aircraft in range",
            "wifi": "Waiting for Wi-Fi",
            "clock": "Waiting for flight data",
            "unavailable": "Flight feed unavailable",
            "receiver-stale": "Flight feed stale",
            "quota": "Feed quota reached",
            "invalid": "Invalid flight data",
        }
        for scene, message in expected.items():
            for view in ("radar", "spotlight", "cards"):
                with self.subTest(scene=scene, view=view):
                    text = self.texts(f"{view}-{scene}")
                    self.assertIn(message, text)
                    self.assertNotIn("CLOSEST AIRCRAFT", text)

    def test_live_radar_shows_snapshot_time_and_keeps_stale_tracks(self):
        self.assertIn("UPDATED 14:32:10 UTC", self.texts("radar-empty"))
        self.assertIn("STALE", self.texts("radar-stale"))
        self.assertIn("14:32:10 UTC · NO NEW DATA", self.texts("radar-stale"))
        self.assertIn("SWA1482", self.texts("radar-stale"))
        commands = self.states["radar-stale"]["commands"]
        self.assertIn({"kind": "circle", "color": "white", "x": 194, "y": 278, "w": 3, "h": 3}, commands)
        self.assertIn("14:32:10 UTC · INVALID FEED DATA", self.texts("radar-invalid-retained"))
        self.assertIn("SWA1482", self.texts("radar-invalid-retained"))

    def test_native_format_truncates_long_labels_and_preserves_missing_data(self):
        for view in ("radar", "spotlight", "cards"):
            text = self.texts(f"{view}-edge")
            self.assertIn("LONGCALLSI", text)
            self.assertIn("TYPE12", text)
            self.assertGreaterEqual(text.count("-"), 2)
            self.assertIn("10.0 NM", text)

    def test_flight_identifiers_and_recognized_airline_names_show_in_each_view(self):
        for view in ("radar", "spotlight", "cards"):
            with self.subTest(view=view):
                text = self.texts(f"{view}-busy")
                self.assertIn("SWA1482", text)
                self.assertIn("Southwest", text)
                self.assertIn("United", text)
                self.assertIn("Delta", text)
                self.assertIn("N172SP", self.texts(f"{view}-single"))
                self.assertNotIn("Southwest", self.texts(f"{view}-single"))
        spotlight = self.texts("spotlight-busy")
        self.assertIn("B789", spotlight)
        self.assertIn("A321", spotlight)

    def test_aircraft_names_show_with_identifiers_and_type_codes(self):
        for view in ("radar", "spotlight", "cards"):
            with self.subTest(view=view):
                text = self.texts(f"{view}-aircraft-names")
                for label in ("N79VZ", "Cirrus SR20", "SR20", "Southwest", "Boeing 737-800"):
                    self.assertIn(label, text)
                self.assertIn("Cessna 172 Skyhawk", self.texts(f"{view}-single"))
        self.assertIn("Airbus Helicopt...", self.texts("spotlight-aircraft-names"))
        self.assertIn("Airbus Helicopters H135", self.texts("cards-aircraft-names"))
        self.assertIn("GLF6", self.texts("cards-aircraft-names"))

    def test_all_images_have_panel_dimensions_and_binary_pixels(self):
        for state in self.states.values():
            with self.subTest(state=state["id"]):
                text = self.texts(state["id"])
                self.assertIn("Overbird", text)
                self.assertNotIn("adsb.lol", text)
                with Image.open(self.output / f'{state["id"]}.png') as image:
                    self.assertEqual(image.size, (800, 480))
                    self.assertEqual(image.mode, "1")
                    self.assertEqual({value for _, value in image.getcolors()}, {0, 255})
                self.assertEqual(state["warnings"], [])

    def build_controlled_layout(self, name, title="Preview title", size=40, radius="10"):
        config, _ = read_config(ROOT / "overhead.yaml")
        display = next(item for item in config["display"] if item["id"] == "board_display")
        display["lambda"] = (
            f'it.print(32, 17, id(title_font), Color::BLACK, "{title}");\n'
            'it.printf(32, 100, id(label_font), Color::BLACK, "Within %s NM", "${radius_nm}");'
        )
        next(item for item in config["font"] if item["id"] == "title_font")["size"] = size
        config["substitutions"]["radius_nm"] = radius
        config_path = self.output / f"{name}.yaml"
        config_path.write_text(yaml.safe_dump(config))
        return build(config_path=config_path, output=self.output / name)[0]

    def test_text_and_substitution_edits_reach_preview(self):
        before = self.build_controlled_layout("text-before")
        after = self.build_controlled_layout("text-after", title="Flight test", radius="25")
        self.assertEqual([command["text"] for command in before["commands"]], ["Preview title", "Within 10 NM"])
        self.assertEqual([command["text"] for command in after["commands"]], ["Flight test", "Within 25 NM"])
        self.assertNotEqual(before["image"], after["image"])

    def test_font_size_alone_changes_preview(self):
        before = self.build_controlled_layout("font-before", size=40)
        after = self.build_controlled_layout("font-after", size=20)
        self.assertEqual(before["commands"], after["commands"])
        self.assertNotEqual(before["image"], after["image"])

    def test_sample_rows_sort_and_status_takes_precedence(self):
        config, drawing = read_config(ROOT / "overhead.yaml")
        aircraft = [["FAR", "B738", 10000, 200, 9.0, 90], ["NEAR", "C172", 1000, 100, 1.0, 270]]
        commands = record_commands(config, drawing, [{"aircraft": aircraft}, {"aircraft": aircraft, "status": "Waiting for Wi-Fi"}])
        rows = [command["text"] for command in commands[0] if command["kind"] == "text"]
        self.assertLess(next(i for i, value in enumerate(rows) if value.startswith("NEAR")), next(i for i, value in enumerate(rows) if value.startswith("FAR")))
        errors = [command["text"] for command in commands[1] if command["kind"] == "text"]
        self.assertIn("Waiting for Wi-Fi", errors)
        self.assertFalse(any(value.startswith(("NEAR", "FAR")) for value in errors))

    def test_radar_places_cardinal_contacts_and_rasterizes_rings(self):
        state = self.states["radar-compass"]
        markers = {
            command["text"]: (command["x"], command["y"])
            for command in state["commands"]
            if command["kind"] == "text" and command["text"].isdigit() and command["x"] < 462
        }
        self.assertEqual(markers, {"1": (263, 233), "2": (327, 265), "3": (263, 361), "4": (135, 265)})
        with Image.open(self.output / "radar-compass.png") as image:
            self.assertEqual(image.getpixel((245, 137)), 255)  # Outer ring at due north.
            self.assertEqual(image.getpixel((245, 136)), 0)
            self.assertEqual(image.getpixel((245, 221)), 255)  # Nose.
            self.assertEqual(image.getpixel((234, 233)), 255)  # Wingtip.
            self.assertEqual(image.getpixel((239, 238)), 255)  # Engine.
            self.assertEqual(image.getpixel((241, 238)), 0)    # Gap between engine and fuselage.
            self.assertEqual(image.getpixel((239, 244)), 255)  # Tailplane.

    def test_radar_uses_ground_track_instead_of_the_bearing_from_home(self):
        with Image.open(self.output / "radar-compass.png") as image:
            # Aircraft 2 is east of home at (309, 265) and traveling south.
            self.assertEqual(image.getpixel((309, 277)), 255)  # South-facing nose.
            self.assertEqual(image.getpixel((311, 277)), 0)
            self.assertEqual(image.getpixel((311, 253)), 255)  # Tail on the north side.
            self.assertEqual(image.getpixel((495, 298)), 0)    # Upright silhouette in the sidebar.
            self.assertEqual(image.getpixel((497, 298)), 255)
            self.assertEqual(image.getpixel((497, 322)), 0)

    def test_aircraft_icons_distinguish_rotorcraft_prop_planes_jets_and_unknown_types(self):
        with Image.open(self.output / "cards-aircraft-icons.png") as image:
            icons = [image.crop((x - 11, y - 12, x + 12, y + 13)).tobytes()
                     for y in (121, 275) for x in (148, 400, 652)]
            self.assertEqual(icons[0], icons[3])  # Model and emitter category identify the same rotor icon.
            self.assertEqual(icons[1], icons[4])  # Piston and turboprop use the straight-wing icon.
            self.assertEqual(len(set(icons)), 4)
            self.assertEqual(image.getpixel((141, 113)), 255)  # Rotor tip.
            self.assertEqual(image.getpixel((390, 119)), 255)  # Straight wingtip.
            self.assertEqual(image.getpixel((646, 126)), 255)  # Jet engine.
            self.assertEqual(image.getpixel((648, 126)), 0)    # Gap beside the engine.
        with Image.open(self.output / "spotlight-aircraft-icons.png") as image:
            self.assertEqual(image.getpixel((393, 227)), 255)  # Rotor tip on the featured aircraft.
            self.assertEqual(image.getpixel((390, 245)), 0)
        with Image.open(self.output / "radar-aircraft-icons.png") as image:
            self.assertEqual(image.getpixel((255, 255)), 255)  # East-facing rotorcraft nose.
            self.assertEqual(image.getpixel((245, 244)), 0)
            self.assertEqual(image.getpixel((245, 315)), 255)  # The second rotorcraft has no ground track.
            self.assertEqual(image.getpixel((245, 319)), 0)
            self.assertEqual(image.getpixel((488, 380)), 0)    # It still has a rotor in the sidebar.

    def test_radar_separates_crowded_markers_and_keeps_east_visible(self):
        commands = self.states["radar-crowded"]["commands"]
        markers = {
            command["text"]: (command["x"], command["y"])
            for command in commands
            if command["kind"] == "text" and command["text"].isdigit() and command["x"] < 462
        }
        self.assertEqual(markers, {"1": (253, 265), "2": (237, 265), "3": (307, 236), "4": (391, 265)})
        with Image.open(self.output / "radar-crowded.png") as image:
            self.assertEqual(image.getpixel((271, 255)), 255)  # Unshifted prop plane nose.
            self.assertEqual(image.getpixel((289, 224)), 255)  # Shifted nose.
            self.assertTrue(all(image.getpixel((289, y)) == 255 for y in range(250, 266)))
            self.assertEqual(image.getpixel((288, 265)), 255)  # Position dot extends off the line.
            self.assertGreater(image.crop((406, 254, 416, 276)).getbbox()[2], 0)  # East label.

    def test_radar_keeps_all_four_numbered_aircraft_in_the_east_sector(self):
        commands = self.states["radar-east-traffic"]["commands"]
        markers = {
            command["text"]: (command["x"], command["y"])
            for command in commands
            if command["kind"] == "text" and command["text"].isdigit() and command["x"] < 462
        }
        self.assertEqual(set(markers), {"1", "2", "3", "4"})
        with Image.open(self.output / "radar-east-traffic.png") as image:
            self.assertEqual(image.getpixel((354, 259)), 255)  # Fourth aircraft's actual position.
            self.assertGreater(image.crop((406, 254, 416, 276)).getbbox()[2], 0)  # East label.

    def test_radar_keeps_a_numbered_callout_when_positions_coincide(self):
        markers = {
            command["text"]: (command["x"], command["y"])
            for command in self.states["radar-coincident"]["commands"]
            if command["kind"] == "text" and command["text"].isdigit() and command["x"] < 462
        }
        self.assertEqual(set(markers), {"1", "2", "3", "4"})
        self.assertIn((453, 144), markers.values())
        with Image.open(self.output / "radar-coincident.png") as image:
            self.assertEqual(image.getpixel((245, 138)), 255)  # Shared position dot.

    def test_firmware_button_actions_wrap_and_return_to_radar(self):
        config, drawing = read_config(ROOT / "overhead.yaml")
        presses = {button["id"]: button["on_press"][0]["lambda"] for button in config["binary_sensor"]}
        for button, view, active_tab in (
            ("left_button", "radar", "FLIGHT CARDS"),
            ("right_button", "cards", "RADAR"),
            ("right_button", "radar", "SPOTLIGHT"),
            ("green_button", "spotlight", "RADAR"),
            ("green_button", "cards", "RADAR"),
        ):
            with self.subTest(button=button, view=view):
                commands, = record_commands(config, presses[button] + "\n" + drawing, [{"view": view}])
                tabs = [item["text"] for item in commands if item["kind"] == "text" and item["color"] == "white" and item["y"] == 449]
                self.assertEqual(tabs, [active_tab])

    def test_great_circle_position_uses_true_north_and_crosses_dateline(self):
        config, _ = read_config(ROOT / "overhead.yaml")
        drawing = """
        const auto north = overhead::relative_position(37.0, -122.0, 37.05, -122.0);
        const auto east = overhead::relative_position(0.0, 179.95, 0.0, -179.95);
        for (const auto &position : {north, east}) {
          it.printf(28, 50, id(label_font), Color::BLACK, "%.3f NM at %.0f deg",
                    position.distance_nm, position.bearing_radians / overhead::RADIANS_PER_DEGREE);
        }
        """
        commands, = record_commands(config, drawing, [{}])
        self.assertEqual([command["text"] for command in commands], ["3.002 NM at 0 deg", "6.004 NM at 90 deg"])

    def test_receiver_polling_runs_every_ten_seconds_and_backs_off(self):
        config, _ = read_config(ROOT / "overhead.yaml")
        drawing = """
        overhead::PollSchedule poll;
        if (!poll.record_attempt(0) || poll.record_attempt(9999) || !poll.record_attempt(10000)) return;
        poll.back_off(10250);
        if (poll.ready(40249) || !poll.record_attempt(40250)) return;
        poll.back_off(40500, true);
        if (poll.ready(340499) || !poll.record_attempt(340500)) return;

        it.print(0, 0, id(label_font), Color::BLACK, "Cadence and backoff verified");
        """
        commands, = record_commands(config, drawing, [{}])
        self.assertEqual([command["text"] for command in commands], ["Cadence and backoff verified"])

    def test_receiver_retry_after_survives_reboot(self):
        config, _ = read_config(ROOT / "overhead.yaml")
        drawing = """
        overhead::PollSchedule poll;
        const auto reboot = [&]() {
          const auto *bytes = reinterpret_cast<const unsigned char *>(&poll);
          const std::vector<unsigned char> saved(bytes, bytes + sizeof(poll));
          poll = {};
          std::copy(saved.begin(), saved.end(), reinterpret_cast<unsigned char *>(&poll));
        };
        if (!poll.record_attempt(0)) return;
        poll.rate_limited(250, "1800");
        reboot();
        if (!poll.waiting_for_quota(1800249) || poll.ready(1800249) || !poll.record_attempt(1800250)) return;
        poll.rate_limited(1800500, "invalid");
        if (poll.ready(1860499) || !poll.ready(1860500)) return;
        it.print(0, 20, id(label_font), Color::BLACK, "Retry respected after reboot");
        """
        commands, = record_commands(config, drawing, [{}])
        self.assertEqual([command["text"] for command in commands], ["Retry respected after reboot"])

    def test_radar_keeps_trail_samples_spaced_during_ten_second_updates(self):
        config, _ = read_config(ROOT / "overhead.yaml")
        drawing = """
        overhead::FlightSnapshot snapshot;
        for (int step = 0; step < 6; ++step) {
          overhead::FlightSnapshot next;
          next.received_at_ms = step * 10000;
          next.flights.push_back({{double(step), 0}, "ABC123", "-", {}, {}, {}, {}, "abc123"});
          next.carry_history(snapshot);
          snapshot = std::move(next);
        }
        const auto &trail = snapshot.flights.front().history;
        if (trail[0] && trail[1]) {
          it.printf(28, 50, id(label_font), Color::BLACK, "Previous positions %.1f and %.1f NM",
                    trail[0]->distance_nm, trail[1]->distance_nm);
        }
        """
        commands, = record_commands(config, drawing, [{}])
        self.assertEqual([command["text"] for command in commands], ["Previous positions 3.0 and 0.0 NM"])
