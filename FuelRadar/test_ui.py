"""Desktop smoke tests with deterministic network responses and a temporary DB."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class DesktopTests(unittest.TestCase):
    def test_typing_selection_prices_sort_and_stale_results(self):
        place = {"label": "Trutnov, okres Trutnov", "lat": 50.56, "lon": 15.91}
        data = {"last_updated": "2026-11-19T05:00:00Z", "stations": [
            {"id": "one", "name": "První", "lat": 50.56, "lng": 15.91,
             "p": {"n95": 38.2, "src": "tank-ono.cz"}},
            {"id": "two", "name": "Druhá", "lat": 50.57, "lng": 15.91,
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
        columns = app.tree["columns"]
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
