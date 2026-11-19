import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
import services


class SortingTests(unittest.TestCase):
    def setUp(self):
        self.stations = [
            {"id": "a", "name": "Žlutá", "address": "Zahradní", "distance": 1.2,
             "prices": {"benzín": 100, "nafta": 41, "lpg": 23}, "price_kind": "Odhad"},
            {"id": "b", "name": "Červená", "address": "Česká", "distance": 10.5,
             "prices": {"benzín": 9, "nafta": 40, "lpg": 22}, "price_kind": "Ceník Tank ONO"},
            {"id": "c", "name": "Bílá", "address": "Brněnská", "distance": .5,
             "prices": {"benzín": 39, "nafta": 42, "lpg": 24}, "price_kind": "Hlášení uživatele"},
            {"id": "unknown", "name": "Neznámá", "address": "Praha", "distance": 2, "prices": {}}
        ]

    def test_all_numeric_columns_both_directions(self):
        for field, ascending in (("benzín", ["b", "c", "a"]), ("nafta", ["b", "a", "c"]),
                                 ("lpg", ["b", "a", "c"])):
            with self.subTest(field=field):
                for descending in (False, True):
                    expected = list(reversed(ascending)) if descending else ascending
                    self.assertEqual([s["id"] for s in services.sort_stations(self.stations, field, descending)],
                                     expected + ["unknown"])
        self.assertEqual([s["id"] for s in services.sort_stations(self.stations, "distance")], ["c", "a", "unknown", "b"])
        self.assertEqual([s["id"] for s in services.sort_stations(self.stations, "distance", True)], ["b", "unknown", "a", "c"])

    def test_text_and_price_type_both_directions(self):
        for field, ascending in (("name", ["c", "b", "unknown", "a"]),
                                 ("address", ["c", "b", "unknown", "a"]),
                                 ("kind", ["b", "c", "a", "unknown"])):
            with self.subTest(field=field):
                self.assertEqual([s["id"] for s in services.sort_stations(self.stations, field)], ascending)
                descending = list(reversed(ascending[:-1])) + ["unknown"] if field == "kind" else list(reversed(ascending))
                self.assertEqual([s["id"] for s in services.sort_stations(self.stations, field, True)], descending)


class SearchTests(unittest.TestCase):
    def test_directions_contain_start_destination_and_driving_mode(self):
        from urllib.parse import urlparse, parse_qs
        station = {"lat": 50.55, "lon": 15.90}
        for origin, expected in (({"lat": 50.56, "lon": 15.91}, "50.56,15.91"),
                                 ("Trutnov, Polská 12", "Trutnov, Polská 12")):
            with self.subTest(origin=origin):
                url = services.directions_url(origin, station)
                self.assertEqual(urlparse(url).netloc, "www.google.com")
                params = parse_qs(urlparse(url).query)
                self.assertEqual(params, {"api": ["1"], "origin": [expected],
                                         "destination": ["50.55,15.9"], "travelmode": ["driving"]})
        with self.assertRaises(ValueError):
            services.directions_url("", station)

    def test_gps_address_is_not_replaced_by_wrong_provider_city(self):
        station = services.prepare_station_address({"address": "GPS 50.5648,15.9230", "city": "Červený Kostelec"})
        self.assertTrue(station["address_pending"])
        self.assertEqual(station["address"], "Upřesňuji obec…")
        self.assertEqual(station["source_address"], "GPS 50.5648,15.9230")
        self.assertFalse(services.prepare_station_address({"address": "Trutnov, Polská 12"})["address_pending"])

    def test_reverse_location_uses_town_and_marks_nearby_street(self):
        data = {"features": [{"properties": {"countrycode": "CZ", "city": "Trutnov",
                             "street": "Polská", "housenumber": "99", "district": "Horní Předměstí"}}]}
        with patch.object(services, "get_json", return_value=data):
            place = services.fetch_station_place(50.56, 15.91)
        self.assertEqual(place["city"], "Trutnov")
        self.assertEqual(place["address"], "Trutnov · Horní Předměstí · poblíž Polská")
        self.assertNotIn("99", place["address"])

    def test_address_lookup_uses_persistent_cache(self):
        import queue
        import threading
        with tempfile.TemporaryDirectory() as folder:
            app = main.FuelRadarApp.__new__(main.FuelRadarApp)
            app.store = main.FuelStore(Path(folder) / "test.db")
            app.events = queue.Queue()
            stations = [{"id": "pump", "lat": 50.56, "lon": 15.91}]
            place = {"city": "Trutnov", "address": "Trutnov · poblíž Polská"}
            with patch.object(main, "fetch_station_place", return_value=place) as reverse:
                app._address_worker(1, stations, threading.Event())
                app._address_worker(2, stations, threading.Event())
            reverse.assert_called_once()
            self.assertEqual(app.events.get_nowait(), ("address", 1, "pump", place))
            self.assertEqual(app.events.get_nowait(), ("address", 2, "pump", place))

    def test_autocomplete_keeps_distinct_places_and_exact_coordinates(self):
        def feature(country, lon, lat):
            return {"properties": {"countrycode": country, "name": "Nová Ves", "city": "Praha"},
                    "geometry": {"coordinates": [lon, lat]}}
        data = {"features": [feature("CZ", 14, 50), feature("CZ", 14, 50),
                             feature("DE", 13, 51), feature("CZ", 15, 49)]}
        with patch.object(services, "get_json", return_value=data):
            places = services.fetch_places("Nová")
        self.assertEqual(len(places), 2)
        self.assertEqual((places[0]["lat"], places[0]["lon"]), (50, 14))

    def test_radius_missing_prices_and_estimates(self):
        data = {"stations": [
            {"id": "near", "lat": 50, "lng": 14, "p": {"n95": 35, "src": "tank-ono.cz"}},
            {"id": "estimate", "lat": 50.01, "lng": 14, "p": {"naf": 39, "lpg": -1, "src": "mbenzin-avg-offset"}},
            {"id": "far", "lat": 49, "lng": 14},
            {"id": "unknown", "lat": 50.02, "lng": 14},
        ]}
        stations = services.nearby_stations(data, 50, 14, 5)
        self.assertEqual([s["id"] for s in stations], ["near", "estimate", "unknown"])
        self.assertEqual(stations[0]["price_kind"], "Ceník Tank ONO")
        self.assertEqual(stations[1]["price_kind"], "Odhad")
        self.assertNotIn("lpg", stations[1]["prices"])
        self.assertEqual(stations[2]["prices"], {})

    def test_cache_keeps_overlapping_searches_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            store = main.FuelStore(Path(folder) / "test.db")
            store.save_search("50,14/5", [{"id": "shared", "prices": {"nafta": 38}}])
            store.save_search("50,14/15", [{"id": "shared"}, {"id": "other"}])
            first, fresh = store.cached_search("50,14/5")
            self.assertTrue(fresh)
            self.assertEqual(first[0]["prices"]["nafta"], 38)
            self.assertEqual(len(first), 1)
            store.save_search("50,14/5", [])
            self.assertEqual(store.cached_search("50,14/5"), ([], True))
            self.assertEqual(len(store.cached_search("50,14/15")[0]), 2)

    def test_search_uses_selected_coordinates_without_geocoding(self):
        with tempfile.TemporaryDirectory() as folder:
            app = main.FuelRadarApp.__new__(main.FuelRadarApp)
            app.store = main.FuelStore(Path(folder) / "test.db")
            import queue
            app.events = queue.Queue()
            location = {"label": "Vybraná adresa", "lat": 50, "lon": 14}
            with patch.object(main, "fetch_places") as geocoder, \
                 patch.object(main, "fetch_price_dataset", return_value={"stations": []}):
                app._search_worker(7, "Vybraná adresa", location, 5)
            geocoder.assert_not_called()
            result = app.events.get_nowait()
            self.assertEqual(result[:4], ("results", 7, location, []))
            self.assertIsNone(result[-1])

    def test_national_week_format_does_not_crash(self):
        app = main.FuelRadarApp.__new__(main.FuelRadarApp)
        from unittest.mock import Mock
        card = Mock()
        app.average_cards = {"nafta": card}
        app.national = {"nafta": {"price": 38, "period": "2026-W47"}}
        app._render_national()
        card.hint_label.configure.assert_called_with(text="ČSÚ · týden 47/2026")

    def test_csu_distribution_can_already_contain_dataset(self):
        from unittest.mock import MagicMock
        import json
        dataset = {"href": "https://example.invalid/unneeded", "size": [3, 1, 1, 1],
                   "dimension": {
                       "CENPHM": {"category": {"index": {"0722201": 0, "0722101": 1, "0722301": 2}}},
                       "IndicatorType": {"category": {"index": {"6621T": 0}}},
                       "Uz0": {"category": {"index": {"CZ": 0}}},
                       "CASTPHM": {"category": {"index": {"2026-W47": 0}}}},
                   "value": [37, 38, 20]}
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(dataset).encode()
        with patch.object(main.urllib.request, "urlopen", return_value=response) as request:
            prices, week = main.fetch_national_averages()
        self.assertEqual(week, "2026-W47")
        self.assertEqual(prices["nafta"], 38)
        self.assertEqual(request.call_count, 1)


if __name__ == "__main__":
    unittest.main()
