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

    def test_busy_sky_limits_rows_and_reports_overflow(self):
        text = self.texts("busy")
        self.assertEqual(sum(value.startswith(("SWA", "UAL", "N172", "DAL", "ASA", "FDX")) for value in text), 6)
        self.assertFalse(any(value.startswith("AAL902") for value in text))
        self.assertIn("+2 more", text)
        self.assertIn("SWA1482    B738      12400     312     1.2", text)

    def test_empty_and_failure_states(self):
        expected = {"empty": "No aircraft in range", "wifi": "Waiting for Wi-Fi", "unavailable": "Flight feed unavailable", "quota": "Feed quota reached", "invalid": "Invalid flight data"}
        for state, message in expected.items():
            with self.subTest(state=state):
                text = self.texts(state)
                self.assertIn(message, text)
                self.assertFalse(any(value.startswith("FLIGHT") for value in text))
                self.assertIn("adsb.lol  /  3 min updates", text)

    def test_native_format_truncates_long_labels_and_preserves_missing_data(self):
        text = self.texts("edge")
        self.assertTrue(any(value.startswith("LONGCALLSI TYPE12") and "-" in value for value in text))
        self.assertTrue(any(value.endswith("10.0") for value in text))

    def test_all_images_have_panel_dimensions_and_binary_pixels(self):
        for state in self.states.values():
            with self.subTest(state=state["id"]):
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
            'it.printf(32, 100, id(detail_font), Color::BLACK, "Within %s NM", "${radius_nm}");'
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
        aircraft = [["FAR", "B738", "10000", "200", 9.0], ["NEAR", "C172", "1000", "100", 1.0]]
        commands = record_commands(config, drawing, [{"aircraft": aircraft}, {"aircraft": aircraft, "status": "Waiting for Wi-Fi"}])
        rows = [command["text"] for command in commands[0] if command["kind"] == "text"]
        self.assertLess(next(i for i, value in enumerate(rows) if value.startswith("NEAR")), next(i for i, value in enumerate(rows) if value.startswith("FAR")))
        errors = [command["text"] for command in commands[1] if command["kind"] == "text"]
        self.assertIn("Waiting for Wi-Fi", errors)
        self.assertFalse(any(value.startswith(("NEAR", "FAR")) for value in errors))
