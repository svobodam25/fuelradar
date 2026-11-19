"""Fuel Radar — desktop fuel-station finder for Windows (Python standard library)."""

from __future__ import annotations

import json
import os
import queue
import sqlite3
import threading
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from services import (fetch_places, fetch_price_dataset, nearby_stations, sort_stations,
                      prepare_station_address, fetch_station_place, directions_url)
from ui import FuelRadarUI, BG, SORT_LABELS, HEADINGS
from location_windows import detect_location


APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "fuel_radar.db"
CSU_DATASET_URL = "https://data.csu.gov.cz/opendata/sady/CENPHMT/distribuce/json"
NATIONAL_REFRESH_MS = 24 * 60 * 60 * 1000
STATION_CACHE_TTL = timedelta(minutes=15)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="minutes")


def fmt_price(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}".replace(".", ",") + " Kč/l"


class FuelStore:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS stations (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, address TEXT NOT NULL,
                    city TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS geocodes (
                    city_key TEXT PRIMARY KEY, lat REAL NOT NULL, lon REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS station_refreshes (
                    city_key TEXT PRIMARY KEY, refreshed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS national_prices (
                    fuel TEXT PRIMARY KEY, price REAL NOT NULL, period TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS search_results (
                    search_key TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS station_addresses (
                    coordinate_key TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at TEXT NOT NULL
                );
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def cached_search(self, key):
        with self.connect() as db:
            row = db.execute("SELECT payload,fetched_at FROM search_results WHERE search_key=?", (key,)).fetchone()
        if not row:
            return [], False
        try:
            age = datetime.now().astimezone() - datetime.fromisoformat(row["fetched_at"])
            return json.loads(row["payload"]), timedelta(0) <= age < STATION_CACHE_TTL
        except (ValueError, TypeError):
            return [], False

    def save_search(self, key, stations):
        with self.connect() as db:
            db.execute("INSERT INTO search_results VALUES(?,?,?) ON CONFLICT(search_key) "
                       "DO UPDATE SET payload=excluded.payload,fetched_at=excluded.fetched_at",
                       (key, json.dumps(stations, ensure_ascii=False), now_iso()))

    def last_city(self) -> str:
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key='last_city'").fetchone()
            return row["value"] if row else ""

    def cached_address(self, key):
        with self.connect() as db:
            row = db.execute("SELECT payload,fetched_at FROM station_addresses WHERE coordinate_key=?", (key,)).fetchone()
        if row:
            try:
                age = datetime.now().astimezone() - datetime.fromisoformat(row["fetched_at"])
                if timedelta(0) <= age < timedelta(days=30):
                    return json.loads(row["payload"])
            except (ValueError, TypeError):
                pass
        return None

    def save_address(self, key, place):
        with self.connect() as db:
            db.execute("INSERT INTO station_addresses VALUES(?,?,?) ON CONFLICT(coordinate_key) "
                       "DO UPDATE SET payload=excluded.payload,fetched_at=excluded.fetched_at",
                       (key, json.dumps(place, ensure_ascii=False), now_iso()))

    def remember_city(self, city: str) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO settings VALUES('last_city', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (city,))

    def geocode(self, city: str) -> tuple[float, float] | None:
        with self.connect() as db:
            row = db.execute("SELECT lat,lon FROM geocodes WHERE city_key=?", (city.strip().casefold(),)).fetchone()
        return (row["lat"], row["lon"]) if row else None

    def save_geocode(self, city: str, lat: float, lon: float) -> None:
        with self.connect() as db:
            db.execute("""INSERT INTO geocodes(city_key,lat,lon) VALUES(?,?,?)
                ON CONFLICT(city_key) DO UPDATE SET lat=excluded.lat,lon=excluded.lon""",
                (city.strip().casefold(), lat, lon))

    def save_national_prices(self, prices: dict[str, float], period: str) -> None:
        with self.connect() as db:
            db.executemany("""INSERT INTO national_prices(fuel,price,period,fetched_at) VALUES(?,?,?,?)
                ON CONFLICT(fuel) DO UPDATE SET price=excluded.price,period=excluded.period,fetched_at=excluded.fetched_at""",
                [(fuel, price, period, now_iso()) for fuel, price in prices.items()])

    def national_prices(self) -> dict:
        with self.connect() as db:
            rows = db.execute("SELECT fuel,price,period FROM national_prices").fetchall()
        return {row["fuel"]: {"price": row["price"], "period": row["period"]} for row in rows}


def fetch_national_averages() -> tuple[dict[str, float], str]:
    """Fetch the latest national weekly fuel averages published by the Czech Statistical Office."""
    headers = {"User-Agent": "FuelRadar/1.0 (desktop fuel station finder)"}
    req = urllib.request.Request(CSU_DATASET_URL, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as response:
        distribution = json.loads(response.read().decode("utf-8"))
    if "value" in distribution and "dimension" in distribution:
        dataset = distribution
    else:
        req = urllib.request.Request(distribution["href"], headers=headers)
        with urllib.request.urlopen(req, timeout=25) as response:
            dataset = json.loads(response.read().decode("utf-8"))

    dimensions = dataset["dimension"]
    fuel_dimension = dimensions["CENPHM"]["category"]["index"]
    indicator_dimension = dimensions["IndicatorType"]["category"]["index"]
    geo_dimension = dimensions["Uz0"]["category"]["index"]
    time_dimension = dimensions["CASTPHM"]["category"]["index"]
    time_count = dataset["size"][3]
    fuel_codes = {"benzín": "0722201", "nafta": "0722101", "lpg": "0722301"}
    values = dataset["value"]
    results, period = {}, ""
    for candidate, period_index in sorted(time_dimension.items(), key=lambda item: item[1], reverse=True):
        current = {}
        for fuel, fuel_code in fuel_codes.items():
            flat_index = (((fuel_dimension[fuel_code] * len(indicator_dimension)
                            + indicator_dimension["6621T"]) * len(geo_dimension)
                           + geo_dimension["CZ"]) * time_count + period_index)
            value = values.get(str(flat_index)) if isinstance(values, dict) else values[flat_index]
            if value is not None:
                current[fuel] = float(value)
        if len(current) == len(fuel_codes):
            period, results = candidate, current
            break
    if not period:
        raise ValueError("ČSÚ zatím nemá zveřejněné ceny pro všechny druhy paliv.")
    return results, period


class FuelRadarApp(FuelRadarUI, tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Fuel Radar")
        self.geometry("1380x920")
        self.minsize(1120, 780)
        self.configure(bg=BG)
        self.store = FuelStore()
        self.city = self.store.last_city()
        self.stations: list[dict] = []
        self.selected: dict | None = None
        self.events: queue.Queue = queue.Queue()
        self._search_id = 0
        self._suggest_id = 0
        self._suggest_after = None
        self._suggest_busy = False
        self._suggest_pending = None
        self._setting_location = False
        self._location_request = 0
        self._locating = False
        self.location = None
        self.suggestions = []
        self._address_cancel = threading.Event()
        self._configure_styles()
        self._build_ui()
        self.national = self.store.national_prices()
        self._render_national()
        self._refresh_national()
        if self.city:
            self.city_var.set(self.city)
            startup_request = self._search_id
            self.after(350, lambda: self.search() if self._search_id == startup_request and not self._locating else None)
        self.after(100, self._poll_events)

    def destroy(self):
        self._address_cancel.set()
        # Cancel callbacks before their Tcl commands disappear on window close.
        for callback in self.tk.call("after", "info"):
            self.after_cancel(callback)
        super().destroy()

    def _hide_suggestions(self):
        self.suggestion_box.pack_forget()
        self.suggestion_hint.pack_forget()
        return "break"

    def _location_changed(self, *_args):
        if self._setting_location:
            return
        self._cancel_locating()
        self._address_cancel.set()
        self.location = None
        self._update_navigation_state()
        self._search_id += 1
        self.search_button.configure(text="Hledat stanice")
        self._suggest_id += 1
        if self._suggest_after:
            self.after_cancel(self._suggest_after)
            self._suggest_after = None
        self._suggest_pending = None
        self._hide_suggestions()
        query = self.city_var.get().strip()
        if len(query) >= 2:
            self._suggest_after = self.after(450, lambda: self._request_suggestions(self._suggest_id, query))

    def _request_suggestions(self, generation, query):
        self._suggest_after = None
        self.suggestion_hint.configure(text="Hledám návrhy polohy…")
        self.suggestion_hint.pack(after=self.search_panel, fill="x", pady=(0, 8))
        if self._suggest_busy:
            self._suggest_pending = (generation, query)
            return
        self._suggest_busy = True
        def worker():
            try:
                self.events.put(("suggestions", generation, query, fetch_places(query), None))
            except Exception as exc:
                self.events.put(("suggestions", generation, query, [], str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _focus_suggestions(self, _event=None):
        if self.suggestion_box.winfo_ismapped() and self.suggestions:
            self.suggestion_box.focus_set()
            self.suggestion_box.selection_clear(0, "end")
            self.suggestion_box.selection_set(0)
            self.suggestion_box.activate(0)
        return "break"

    def _choose_suggestion(self, _event=None):
        selection = self.suggestion_box.curselection()
        if not selection or selection[0] >= len(self.suggestions):
            return "break"
        self.location = self.suggestions[selection[0]]
        self._setting_location = True
        self.city_var.set(self.location["label"])
        self._setting_location = False
        self.city_entry.focus_set()
        self.search()
        return "break"

    def _location_enter(self, _event=None):
        if self.suggestion_box.winfo_ismapped() and self.suggestion_box.curselection():
            return self._choose_suggestion()
        self.search()
        return "break"

    def _cancel_locating(self):
        if self._locating:
            self._location_request += 1
            self._locating = False
            self.location_button.configure(state="normal", text="◎ Použít moji polohu")

    def use_my_location(self):
        if self._locating:
            return
        self._locating = True
        self._update_navigation_state()
        self._address_cancel.set()
        self._location_request += 1
        request_id = self._location_request
        self._search_id += 1
        self._suggest_id += 1
        self._suggest_pending = None
        if self._suggest_after:
            self.after_cancel(self._suggest_after)
            self._suggest_after = None
        self._hide_suggestions()
        self.search_button.configure(text="Hledat stanice")
        self.location_button.configure(state="disabled", text="Zjišťuji polohu…")
        self.status_var.set("Zjišťuji polohu zařízení přes Windows…")
        threading.Thread(target=self._location_worker, args=(request_id,), daemon=True).start()

    def _location_worker(self, request_id):
        try:
            self.events.put(("position", request_id, detect_location(), None))
        except Exception as exc:
            self.events.put(("position", request_id, None, str(exc)))

    def open_location_settings(self):
        try:
            os.startfile("ms-settings:privacy-location")
        except (OSError, AttributeError):
            messagebox.showinfo("Nastavení polohy", "Otevři Nastavení Windows → Soukromí a zabezpečení → Poloha.")

    def search(self):
        city = self.city_var.get().strip()
        if not city:
            self.status_var.set("Zadej město nebo adresu.")
            self.city_entry.focus_set()
            return
        self._cancel_locating()
        self._address_cancel.set()
        self._suggest_id += 1
        self._suggest_pending = None
        if self._suggest_after:
            self.after_cancel(self._suggest_after)
            self._suggest_after = None
        self._hide_suggestions()
        self._search_id += 1
        request_id = self._search_id
        self.city = city
        self.store.remember_city(city)
        radius = int(self.radius_var.get())
        location = dict(self.location) if self.location else None
        self.stations = []
        self._render()
        self.empty.configure(text="Načítám stanice a ceny v okolí…")
        self.status_var.set("Vyhledávám stanice a ceny…")
        self.search_button.configure(text="Vyhledávám…")
        threading.Thread(target=self._search_worker, args=(request_id, city, location, radius), daemon=True).start()

    def _search_worker(self, request_id, city, location, radius):
        cached = []
        try:
            if not location:
                coordinates = self.store.geocode(city)
                if coordinates:
                    location = {"label": city, "lat": coordinates[0], "lon": coordinates[1]}
                else:
                    places = fetch_places(city)
                    if not places:
                        raise ValueError(f"Polohu „{city}“ se nepodařilo najít. Zkus přesnější adresu.")
                    location = places[0]
            self.store.save_geocode(location["label"], location["lat"], location["lon"])
            key = f"{location['lat']:.7f},{location['lon']:.7f}/{radius}"
            cached, fresh = self.store.cached_search(key)
            if fresh:
                self.events.put(("results", request_id, location, cached, True, None))
                return
            stations = nearby_stations(fetch_price_dataset(), location["lat"], location["lon"], radius)
            self.store.save_search(key, stations)
            self.events.put(("results", request_id, location, stations, False, None))
        except Exception as exc:
            self.events.put(("results", request_id, location, cached, bool(cached), str(exc)))

    def _national_worker(self):
        try:
            prices, period = fetch_national_averages()
            self.store.save_national_prices(prices, period)
            self.events.put(("national", prices, period, None))
        except Exception as exc:
            self.events.put(("national", None, None, str(exc)))

    def _start_address_lookup(self, request_id):
        self._address_cancel.set()
        self._address_cancel = threading.Event()
        pending = [dict(s) for s in self.stations if s.get("address_pending")]
        if pending:
            threading.Thread(target=self._address_worker,
                             args=(request_id, pending, self._address_cancel), daemon=True).start()

    def _address_worker(self, request_id, stations, cancelled):
        failures = 0
        for station in stations:
            if cancelled.is_set():
                return
            key = f"{station['lat']:.7f},{station['lon']:.7f}"
            place = None
            try:
                place = self.store.cached_address(key)
                if place is None and failures < 3:
                    place = fetch_station_place(station["lat"], station["lon"])
                    self.store.save_address(key, place)
                    failures = 0
            except Exception:
                failures += 1
            self.events.put(("address", request_id, station["id"], place))

    def _refresh_national(self):
        threading.Thread(target=self._national_worker, daemon=True).start()
        self.after(NATIONAL_REFRESH_MS, self._refresh_national)

    def _render_national(self):
        for fuel, card in getattr(self, "average_cards", {}).items():
            record = self.national.get(fuel)
            if not record:
                card.configure(text="—")
                continue
            card.configure(text=fmt_price(record["price"]))
            year, week = record["period"].split("-W")
            card.hint_label.configure(text=f"ČSÚ · týden {int(week)}/{year}")

    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "address":
                    _, request_id, station_id, place = event
                    if request_id != self._search_id:
                        continue
                    station = next((s for s in self.stations if s["id"] == station_id), None)
                    if station is not None:
                        if place:
                            station.update(place)
                        else:
                            station["address"] = "Obec nezjištěna · otevři mapu"
                        station["address_pending"] = False
                        y, x = self.tree.yview()[0], self.tree.xview()[0]
                        self._render()
                        self.tree.yview_moveto(y)
                        self.tree.xview_moveto(x)
                elif event[0] == "position":
                    _, request_id, location, error = event
                    if request_id != self._location_request or not self._locating:
                        continue
                    self._locating = False
                    self._update_navigation_state()
                    self.location_button.configure(state="normal", text="◎ Použít moji polohu")
                    if error:
                        self.status_var.set("Polohu se nepodařilo zjistit · zkontroluj Nastavení polohy")
                        messagebox.showwarning("Poloha není dostupná", error)
                    else:
                        self.location = location
                        self._setting_location = True
                        self.city_var.set(location["label"])
                        self._setting_location = False
                        self.search()
                elif event[0] == "suggestions":
                    _, generation, query, places, error = event
                    self._suggest_busy = False
                    if generation == self._suggest_id and query == self.city_var.get().strip():
                        self.suggestions = places
                        self.suggestion_box.delete(0, "end")
                        for place in places:
                            self.suggestion_box.insert("end", place["label"])
                        if places:
                            self.suggestion_hint.pack_forget()
                            self.suggestion_box.configure(height=min(6, len(places)))
                            self.suggestion_box.pack(after=self.search_panel, fill="x", pady=(0, 12))
                        else:
                            self.suggestion_hint.configure(text="Našeptávač je nedostupný. Zkus hledání znovu." if error
                                                           else "Žádné návrhy. Zkus přesnější název nebo adresu.")
                    if self._suggest_pending:
                        pending = self._suggest_pending
                        self._suggest_pending = None
                        if pending[0] == self._suggest_id:
                            self._request_suggestions(*pending)
                elif event[0] == "national":
                    _, prices, period, error = event
                    if prices:
                        self.national = {fuel: {"price": value, "period": period} for fuel, value in prices.items()}
                        self._render_national()
                    elif error and not self.national:
                        for card in self.average_cards.values():
                            card.hint_label.configure(text="ČSÚ je nedostupný")
                elif event[0] == "results":
                    _, request_id, location, stations, cached, error = event
                    if request_id != self._search_id:
                        continue
                    self.stations = [prepare_station_address(s) for s in stations]
                    if location:
                        self.location = location
                        self.city = location["label"]
                        self._setting_location = True
                        self.city_var.set(self.city)
                        self._setting_location = False
                        self.store.remember_city(self.city)
                    self._render()
                    self._start_address_lookup(request_id)
                    self.search_button.configure(text="Hledat stanice")
                    if error:
                        self.status_var.set("Online hledání selhalo · uložené výsledky" if cached else "Hledání se nezdařilo")
                        self.empty.configure(text="Stanice se nepodařilo načíst. Zkontroluj připojení a zkus to znovu.")
                        messagebox.showwarning("Vyhledávání se nezdařilo", str(error) +
                                               ("\nZobrazuji dříve uložené výsledky; ceny mohou být zastaralé." if cached else ""))
                    else:
                        estimated = sum(bool(s["prices"]) and s["price_kind"] == "Odhad" for s in stations)
                        prefix = "Uložené výsledky" if cached else "Načteno"
                        self.status_var.set(f"{prefix}: {len(stations)} stanic · {estimated} s odhadem ceny")
                        if location and location.get("accuracy") is not None:
                            self.status_var.set(self.status_var.get() + f" · přesnost polohy ±{location['accuracy']:.0f} m")
        except queue.Empty:
            pass
        finally:
            self.after(100, self._poll_events)

    def _sort_selected(self, *_args):
        self.sort_column = SORT_LABELS.get(self.sort_var.get(), "distance")
        self.sort_descending = False
        self._render()

    def _sort_by(self, column):
        if self.sort_column == column:
            self.sort_descending = not self.sort_descending
        else:
            label = next(label for label, key in SORT_LABELS.items() if key == column)
            self.sort_var.set(label)
            return
        self._render()

    def _toggle_sort_direction(self):
        self.sort_descending = not self.sort_descending
        self._render()

    def _update_sort_headers(self):
        for column, label in HEADINGS.items():
            arrow = ("  ↓" if self.sort_descending else "  ↑") if column == self.sort_column else ""
            self.tree.heading(column, text=label + arrow)
        self.direction_button.configure(text="↓ Sestupně" if self.sort_descending else "↑ Vzestupně")

    def _reset_filters(self):
        self.type_var.set("Všechny typy cen")
        self.sort_var.set("Vzdálenost")
        self.city_entry.focus_set()

    def _table_double_click(self, event):
        if self.tree.identify_region(event.x, event.y) in ("cell", "tree"):
            self._select_station()
            self.navigate()

    def _render(self):
        selection = self.tree.selection()
        selected_id = selection[0] if selection else None
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.empty.place_forget()
        kind_filter = self.type_var.get()
        visible = [s for s in self.stations if kind_filter == "Všechny typy cen" or
                   (s.get("price_kind", "Odhad") if s.get("prices") else "Cena neznámá") == kind_filter]
        ordered = sort_stations(visible, self.sort_column, self.sort_descending)
        self._update_sort_headers()
        for index, station in enumerate(ordered):
            prices = station.get("prices", {})
            formatted = [("≈ " if station["price_kind"] == "Odhad" and prices.get(f) is not None else "") +
                         fmt_price(prices.get(f)) for f in ("benzín", "nafta", "lpg")]
            self.tree.insert("", "end", iid=station["id"], values=(station["name"], station["address"],
                             f"{station['distance']:.1f}", *formatted,
                             station["price_kind"] if prices else "Cena neznámá"),
                             tags=("odd" if index % 2 else "even",))
        self.station_count.configure(text=str(len(self.stations)))
        self.result_count_var.set(f"{len(visible)} z {len(self.stations)} stanic" if self.stations else "Zatím žádné výsledky")
        if selected_id and self.tree.exists(selected_id):
            self.tree.selection_set(selected_id)
            self.tree.focus(selected_id)
        self._select_station()
        if not visible:
            self.empty.configure(text="Tomuto filtru neodpovídá žádná stanice.\nZkus jiný typ ceny." if self.stations else
                                 "V tomto okruhu nejsou ve zdroji žádné stanice.\nZkus větší okruh." if self.city else
                                 "Tvoje další zastávka začíná tady.\n\nZadej město nebo adresu do vyhledávání.")
            self.empty.place(relx=.5, rely=.5, anchor="center")

    def _select_station(self, _event=None):
        selected = self.tree.selection()
        self.selected = next((s for s in self.stations if selected and s["id"] == selected[0]), None)
        self._update_navigation_state()
        if not self.selected:
            self.map_button.configure(state="disabled")
            self.detail_var.set("Vyber stanici pro detail ceny.  ≈ odhad   ·   — cena není uvedena")
            return
        self.map_button.configure(state="normal")
        stamp = self.selected.get("updated_at", "")
        try:
            stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone().strftime("%d. %m. %Y %H:%M")
        except ValueError:
            stamp = "datum neuvedeno"
        self.detail_var.set(f"{self.selected['name']} · {self.selected['address']} · {self.selected['price_kind']} · "
                            f"{self.selected.get('source') or 'zdroj neuveden'}\n"
                            f"BenzinMapa.cz · záznam {stamp} · cenu ověř před tankováním")

    def _update_navigation_state(self):
        # During construction the input and buttons have not yet been created.
        if "navigate_button" not in self.__dict__:
            return
        enabled = self.selected is not None and bool(self.city_var.get().strip()) and not self._locating
        self.navigate_button.configure(state="normal" if enabled else "disabled")

    def navigate(self):
        if not self.selected:
            self.status_var.set("Nejdřív vyber stanici, ke které chceš jet.")
            return
        if self._locating:
            self.status_var.set("Počkej na zjištění výchozí polohy.")
            return
        origin = self.location or self.city_var.get().strip()
        if not origin:
            self.status_var.set("Zadej nahoře, odkud vyrážíš, nebo klikni na Použít moji polohu.")
            self.city_entry.focus_set()
            return
        try:
            opened = webbrowser.open(directions_url(origin, self.selected))
        except (OSError, webbrowser.Error):
            opened = False
        if opened:
            self.status_var.set(f"Trasa autem k {self.selected['name']} otevřena v Google Mapách.")
        else:
            messagebox.showwarning("Trasu nelze otevřít", "Nepodařilo se otevřít prohlížeč s trasou. Zkontroluj výchozí prohlížeč Windows.")

    def open_map(self):
        if self.selected:
            lat, lon = self.selected["lat"], self.selected["lon"]
            url = "https://www.openstreetmap.org/?" + urllib.parse.urlencode({"mlat": lat, "mlon": lon, "zoom": 16})
            webbrowser.open(url)


if __name__ == "__main__":
    FuelRadarApp().mainloop()
