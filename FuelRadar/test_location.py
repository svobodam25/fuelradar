import json
import subprocess
import unittest
from unittest.mock import Mock, patch

import location_windows


class WindowsLocationTests(unittest.TestCase):
    def response(self, data):
        return Mock(stdout=json.dumps(data).encode(), returncode=0)

    def test_coordinates_and_accuracy(self):
        with patch.object(location_windows.subprocess, "run", return_value=self.response(
                {"lat": 50.56, "lon": 15.91, "accuracy": 60})) as run:
            location = location_windows.detect_location()
        self.assertEqual((location["lat"], location["lon"], location["accuracy"]), (50.56, 15.91, 60))
        self.assertIn("50.56000", location["label"])
        self.assertEqual(run.call_args.kwargs["timeout"], 35)
        self.assertEqual(run.call_args.kwargs["creationflags"], subprocess.CREATE_NO_WINDOW)

    def test_permissions_unavailable_and_invalid_coordinates(self):
        for data in ({"error": "denied"}, {"error": "unavailable"}, {"lat": 200, "lon": 15},
                     {"lat": float("nan"), "lon": 15}, {}, []):
            with self.subTest(data=data), patch.object(location_windows.subprocess, "run", return_value=self.response(data)):
                with self.assertRaises(location_windows.LocationError):
                    location_windows.detect_location()

    def test_timeout_is_readable(self):
        with patch.object(location_windows.subprocess, "run", side_effect=subprocess.TimeoutExpired("powershell", 35)):
            with self.assertRaisesRegex(location_windows.LocationError, "příliš dlouho"):
                location_windows.detect_location()


if __name__ == "__main__":
    unittest.main()
