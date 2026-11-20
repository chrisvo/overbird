from pathlib import Path
import tempfile
import unittest

from PIL import Image

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

    def test_firmware_edits_change_preview_without_editing_renderer(self):
        source = (ROOT / "overhead.yaml").read_text()
        source = source.replace('ink, "Overhead"', 'ink, "Flight test"').replace('radius_nm: "10"', 'radius_nm: "25"').replace('size: 60', 'size: 42')
        config_path = self.output / "edited.yaml"
        config_path.write_text(source)
        states = build(config_path=config_path, output=self.output / "edited")
        text = [command["text"] for command in states[0]["commands"] if command["kind"] == "text"]
        self.assertIn("Flight test", text)
        self.assertIn("Within 25 NM", text)
        self.assertNotEqual(states[0]["image"], self.states["busy"]["image"])

    def test_sample_rows_sort_and_status_takes_precedence(self):
        config, drawing = read_config(ROOT / "overhead.yaml")
        aircraft = [["FAR", "B738", "10000", "200", 9.0], ["NEAR", "C172", "1000", "100", 1.0]]
        commands = record_commands(config, drawing, [{"aircraft": aircraft}, {"aircraft": aircraft, "status": "Waiting for Wi-Fi"}])
        rows = [command["text"] for command in commands[0] if command["kind"] == "text"]
        self.assertLess(next(i for i, value in enumerate(rows) if value.startswith("NEAR")), next(i for i, value in enumerate(rows) if value.startswith("FAR")))
        errors = [command["text"] for command in commands[1] if command["kind"] == "text"]
        self.assertIn("Waiting for Wi-Fi", errors)
        self.assertFalse(any(value.startswith(("NEAR", "FAR")) for value in errors))
