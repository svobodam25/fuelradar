"""Desktop smoke tests with deterministic network responses and a temporary DB."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class DesktopTests(unittest.TestCase):
    def test_fuel_selection_price_order_visibility_and_saved_preference(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(main, "FuelStore", side_effect=lambda: store), \
             patch.object(main.FuelRadarApp, "_refresh_national"):
            store = STORE_TYPE(Path(folder) / "test.db")
            app = main.FuelRadarApp()
            try:
                app.stations = [
                    {"id": "near", "name": "Blízká", "address": "Trutnov", "distance": 1,
                     "prices": {"benzín": 40, "nafta": 35, "lpg": 27}, "price_kind": "Odhad"},
                    {"id": "cheap", "name": "Levnější", "address": "Trutnov", "distance": 10,
                     "prices": {"benzín": 38, "nafta": 45, "lpg": 25}, "price_kind": "Odhad"},
                    {"id": "unknown", "name": "Neznámá", "address": "Trutnov", "distance": .1,
                     "prices": {}, "price_kind": "Odhad"}]
                app._render()
                app.update()
                self.assertEqual(app.tree.get_children(), ("cheap", "near", "unknown"))
                self.assertIn("benzín", app.tree["displaycolumns"])
                self.assertNotIn("nafta", app.tree["displaycolumns"])
                self.assertNotIn("lpg", app.tree["displaycolumns"])
                self.assertFalse(app.average_cards["nafta"].panel.winfo_ismapped())
                app.fuel_var.set("Nafta (Diesel)")
                self.assertEqual(store.preferred_fuel(), "nafta")
                self.assertEqual(app.tree.get_children(), ("near", "cheap", "unknown"))
                self.assertIn("nafta", app.tree["displaycolumns"])
                self.assertNotIn("benzín", app.tree["displaycolumns"])
                app.other_fuels_button.invoke()
                app.update()
                self.assertTrue(app.average_cards["benzín"].panel.winfo_ismapped())
                self.assertIn("lpg", app.tree["displaycolumns"])
                app.sort_var.set("LPG")
                self.assertEqual(app.tree.get_children()[0], "cheap")
                app.other_fuels_button.invoke()
                self.assertEqual(app.sort_column, "nafta")
                self.assertEqual(app.tree.get_children()[0], "near")
                app.fuel_var.set("LPG")
                self.assertEqual(app.tree.get_children(), ("cheap", "near", "unknown"))
                app._toggle_sort_direction()
                app._reset_filters()
                self.assertFalse(app.sort_descending)
                self.assertEqual(app.sort_column, "lpg")
            finally:
                app.destroy()

    def test_city_is_resolved_in_background_and_old_gps_cache_is_upgraded(self):
        import threading
        release = threading.Event()
        place = {"city": "Trutnov", "address": "Trutnov · poblíž Polská"}
        def reverse(*_args):
            release.wait(3)
            return place
        data = {"stations": [{"id": "pump", "name": "ORLEN", "lat": 50.56, "lng": 15.91,
                              "address": "GPS 50.5600,15.9100", "city": "Červený Kostelec", "p": {"n95": 38}}]}
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(main, "FuelStore", side_effect=lambda: store), \
             patch.object(main.FuelRadarApp, "_refresh_national"), \
             patch.object(main, "fetch_places", return_value=[{"label": "Trutnov", "lat": 50.56, "lon": 15.91}]), \
             patch.object(main, "fetch_price_dataset", return_value=data), \
             patch.object(main, "fetch_station_place", side_effect=reverse) as lookup:
            store = STORE_TYPE(Path(folder) / "test.db")
            app = main.FuelRadarApp()
            try:
                app.city_var.set("Trutnov")
                app.search()
                self.pump_until(app, lambda: bool(app.tree.get_children()))
                self.assertNotIn("GPS", app.tree.set("pump", "address"))
                self.assertNotIn("Červený Kostelec", app.tree.set("pump", "address"))
                app.tree.selection_set("pump")
                release.set()
                self.pump_until(app, lambda: app.tree.set("pump", "address") == place["address"])
                self.assertEqual(app.tree.selection(), ("pump",))
                self.assertIn(place["address"], app.detail_var.get())
                app.search()
                self.pump_until(app, lambda: bool(app.tree.get_children()) and app.tree.set("pump", "address") == place["address"])
                lookup.assert_called_once()
            finally:
                release.set()
                app.destroy()

    def test_device_location_search_failure_and_stale_position(self):
        position = {"label": "Moje poloha · 50.56000, 15.91000", "lat": 50.56, "lon": 15.91, "accuracy": 75}
        data = {"stations": [{"id": "near", "name": "Stanice", "address": "Trutnov", "lat": 50.56, "lng": 15.91,
                              "p": {"n95": 38, "src": "tank-ono.cz"}}]}
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(main, "FuelStore", side_effect=lambda: store), \
             patch.object(main.FuelRadarApp, "_refresh_national"), \
             patch.object(main, "fetch_places") as geocoder, \
             patch.object(main, "fetch_price_dataset", return_value=data), \
             patch.object(main, "detect_location", return_value=position) as detector, \
             patch.object(main.webbrowser, "open", return_value=True) as browser, \
             patch.object(main.messagebox, "showwarning") as warning:
            store = STORE_TYPE(Path(folder) / "test.db")
            app = main.FuelRadarApp()
            errors = []
            app.report_callback_exception = lambda *args: errors.append(args)
            try:
                app.update()
                app.location_button.invoke()
                self.pump_until(app, lambda: len(app.tree.get_children()) == 1)
                self.assertEqual(app.location, position)
                self.assertEqual(app.city_var.get(), position["label"])
                self.assertIn("±75 m", app.status_var.get())
                geocoder.assert_not_called()
                app.tree.selection_set("near")
                app._select_station()
                self.assertEqual(app.navigate_button.cget("state"), "normal")
                app.navigate_button.invoke()
                from urllib.parse import urlparse, parse_qs
                params = parse_qs(urlparse(browser.call_args.args[0]).query)
                self.assertEqual(params["origin"], ["50.56,15.91"])
                self.assertEqual(params["destination"], ["50.56,15.91"])
                self.assertEqual(params["travelmode"], ["driving"])
                app.city_var.set("Praha, Václavské náměstí 1")
                app.navigate_button.invoke()
                params = parse_qs(urlparse(browser.call_args.args[0]).query)
                self.assertEqual(params["origin"], ["Praha, Václavské náměstí 1"])
                app.city_var.set("")
                self.assertEqual(app.navigate_button.cget("state"), "disabled")
                browser.reset_mock()
                app.navigate()
                browser.assert_not_called()
                detector.side_effect = RuntimeError("Přístup k poloze je zakázaný.")
                app.location_button.invoke()
                self.pump_until(app, lambda: warning.called)
                self.assertEqual(app.location_button.cget("state"), "normal")
                self.assertEqual(len(app.tree.get_children()), 1)
                app._locating = True
                app._location_request += 1
                obsolete = app._location_request
                app.city_var.set("Brno")
                app.events.put(("position", obsolete, position, None))
                self.pump_until(app, lambda: app.events.empty())
                self.assertEqual(app.city_var.get(), "Brno")
                self.assertIsNone(app.location)
                self.assertFalse(errors, errors)
            finally:
                app.destroy()

    def test_typing_selection_prices_sort_and_stale_results(self):
        place = {"label": "Trutnov, okres Trutnov", "lat": 50.56, "lon": 15.91}
        data = {"last_updated": "2026-11-19T05:00:00Z", "stations": [
            {"id": "one", "name": "První", "address": "Trutnov", "lat": 50.56, "lng": 15.91,
             "p": {"n95": 38.2, "src": "tank-ono.cz"}},
            {"id": "two", "name": "Druhá", "address": "Trutnov", "lat": 50.57, "lng": 15.91,
             "p": {"n95": 37.1, "src": "mbenzin-avg-offset"}},
        ]}
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(main, "FuelStore", side_effect=lambda: store), \
             patch.object(main.FuelRadarApp, "_refresh_national"), \
             patch.object(main, "fetch_places", return_value=[place]), \
             patch.object(main, "fetch_price_dataset", return_value=data):
            store = STORE_TYPE(Path(folder) / "test.db")
            app = main.FuelRadarApp()
            errors = []
            app.report_callback_exception = lambda *args: errors.append(args)
            try:
                app.update()
                app.city_var.set("Trut")
                self.pump_until(app, lambda: app.suggestion_box.size() == 1)
                app._focus_suggestions()
                app._choose_suggestion()
                self.pump_until(app, lambda: len(app.tree.get_children()) == 2)
                self.assertEqual(app.location, place)
                self.assertIn("38,20", str(app.tree.item("one", "values")))
                self.assertIn("≈", str(app.tree.item("two", "values")))
                app.sort_var.set("Benzín")
                self.assertEqual(app.tree.get_children()[0], "two")
                # Trigger the actual Tk heading command through a mouse click.
                app.update()
                self.click_heading(app, "benzín")
                self.assertEqual(app.tree.get_children()[0], "one")
                self.assertIn("↓", app.tree.heading("benzín", "text"))
                app.direction_button.invoke()
                self.assertEqual(app.tree.get_children()[0], "two")
                app.sort_var.set("Typ ceny")
                self.assertEqual(app.tree.get_children()[0], "one")
                self.click_heading(app, "kind")
                self.assertEqual(app.tree.get_children()[0], "two")
                app.tree.selection_set("two")
                app._select_station()
                self.assertIn("Odhad", app.detail_var.get())
                app.sort_var.set("Stanice")
                self.assertEqual(app.tree.selection(), ("two",))
                self.assertEqual(app.map_button.cget("state"), "normal")
                app.type_var.set("Ceník Tank ONO")
                self.assertEqual(app.tree.get_children(), ("one",))
                self.assertEqual(app.map_button.cget("state"), "disabled")
                app.type_var.set("Hlášení uživatele")
                self.assertEqual(app.tree.get_children(), ())
                app._reset_filters()
                self.assertEqual(len(app.tree.get_children()), 2)
                stale_id = app._search_id
                app.city_var.set("Praha")
                app.events.put(("results", stale_id, place, [], False, None))
                self.pump_until(app, lambda: app.events.empty())
                self.assertEqual(app.city_var.get(), "Praha")
                self.assertFalse(errors, errors)
                app.geometry("1120x780")
                app.update()
                self.assertTrue(app.map_button.winfo_ismapped())
                self.assertTrue(app.navigate_button.winfo_ismapped())
                self.assertTrue(app.detail_label.winfo_ismapped())
                self.assertGreater(app.tree.winfo_height(), 100)
                self.assertLessEqual(app.map_button.winfo_rooty() + app.map_button.winfo_height(),
                                     app.winfo_rooty() + app.winfo_height())
            finally:
                app.destroy()

    @staticmethod
    def click_heading(app, column):
        app.update()
        # Scroll the target heading into view even at the smallest window size.
        columns = app.tree["displaycolumns"]
        offset = sum(app.tree.column(c, "width") for c in columns[:columns.index(column)])
        total = sum(app.tree.column(c, "width") for c in columns)
        app.tree.xview_moveto(offset / total)
        app.update()
        left = app.tree.xview()[0] * total
        x = int(offset - left + app.tree.column(column, "width") / 2)
        app.tree.event_generate("<Button-1>", x=x, y=15)
        app.tree.event_generate("<ButtonRelease-1>", x=x, y=15)
        app.update()

    @staticmethod
    def pump_until(app, condition):
        deadline = time.monotonic() + 4
        while not condition() and time.monotonic() < deadline:
            app.update()
            time.sleep(.01)
        if not condition():
            raise AssertionError("Timed out waiting for desktop update")


STORE_TYPE = main.FuelStore

if __name__ == "__main__":
    unittest.main()
