"""Fuel Radar — desktop fuel-station finder for Windows (Python standard library)."""

from __future__ import annotations

import json
import queue
import sqlite3
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk


APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "fuel_radar.db"
BG = "#0b1017"
PANEL = "#121a24"
PANEL_ALT = "#172330"
LINE = "#263443"
TEXT = "#f0f5fa"
MUTED = "#8d9bab"
GREEN = "#79e0ad"
AMBER = "#ffc875"
BLUE = "#70b7ff"
CSU_DATASET_URL = "https://data.csu.gov.cz/opendata/sady/CENPHMT/distribuce/json"
NATIONAL_REFRESH_MS = 24 * 60 * 60 * 1000
STATION_CACHE_TTL = timedelta(minutes=15)
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://ovp.dresel.systems/api/interpreter",
)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="minutes")


def fmt_price(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}".replace(".", ",") + " Kč/l"


def osm_address(tags: dict, fallback: str) -> str:
    full_address = (tags.get("addr:full") or "").strip()
    if full_address:
        return full_address
    street = tags.get("addr:street")
    street_address = " ".join(part for part in (street, tags.get("addr:housenumber")) if part)
    locality = tags.get("addr:city") or tags.get("addr:place") or fallback
    pieces = [street_address, tags.get("addr:postcode"), locality]
    return ", ".join(part for part in pieces if part) or "Adresa není v mapě uvedena"


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
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def last_city(self) -> str:
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key='last_city'").fetchone()
            return row["value"] if row else ""

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

    def replace_stations(self, city: str, stations: list[dict]) -> None:
        with self.connect() as db:
            db.executemany("""INSERT INTO stations(id,name,address,city,lat,lon,updated_at)
                VALUES(:id,:name,:address,:city,:lat,:lon,:updated_at)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,address=excluded.address,
                city=excluded.city,lat=excluded.lat,lon=excluded.lon,updated_at=excluded.updated_at""",
                stations)
            db.execute("""INSERT INTO station_refreshes(city_key,refreshed_at) VALUES(?,?)
                ON CONFLICT(city_key) DO UPDATE SET refreshed_at=excluded.refreshed_at""",
                (city.strip().casefold(), now_iso()))

    def station_cache_is_fresh(self, city: str) -> bool:
        with self.connect() as db:
            row = db.execute("SELECT refreshed_at FROM station_refreshes WHERE city_key=?",
                             (city.strip().casefold(),)).fetchone()
        if not row:
            return False
        try:
            return datetime.now().astimezone() - datetime.fromisoformat(row["refreshed_at"]) < STATION_CACHE_TTL
        except ValueError:
            return False

    def stations_for_city(self, city: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("""SELECT id,name,address,city,lat,lon FROM stations
                ORDER BY name COLLATE NOCASE""").fetchall()
        city_key = city.strip().casefold()
        return [dict(row) for row in rows if row["city"].strip().casefold() == city_key]

    def save_national_prices(self, prices: dict[str, float], period: str) -> None:
        with self.connect() as db:
            db.executemany("""INSERT INTO national_prices(fuel,price,period,fetched_at) VALUES(?,?,?,?)
                ON CONFLICT(fuel) DO UPDATE SET price=excluded.price,period=excluded.period,fetched_at=excluded.fetched_at""",
                [(fuel, price, period, now_iso()) for fuel, price in prices.items()])

    def national_prices(self) -> dict:
        with self.connect() as db:
            rows = db.execute("SELECT fuel,price,period FROM national_prices").fetchall()
        return {row["fuel"]: {"price": row["price"], "period": row["period"]} for row in rows}


def fetch_stations(city: str, store: FuelStore | None = None) -> tuple[str, list[dict]]:
    """Resolve a Czech city and fetch fuel stations from OpenStreetMap via Overpass."""
    headers = {"User-Agent": "FuelRadar/1.0 (desktop fuel station finder)"}
    coordinates = store.geocode(city) if store else None
    if coordinates:
        lat, lon = coordinates
    else:
        params = urllib.parse.urlencode({"q": city, "format": "jsonv2", "limit": 1, "countrycodes": "cz"})
        req = urllib.request.Request(f"https://nominatim.openstreetmap.org/search?{params}", headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            found = json.loads(response.read().decode("utf-8"))
        if not found:
            raise ValueError(f"Město „{city}“ se nepodařilo najít. Zkus zadat přesnější název.")
        lat, lon = float(found[0]["lat"]), float(found[0]["lon"])
        if store:
            store.save_geocode(city, lat, lon)
    display_city = city.strip()
    query = f'[out:json][timeout:16];(nwr["amenity"="fuel"](around:15000,{lat},{lon});nwr["shop"="fuel"](around:15000,{lat},{lon}););out center tags;'
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    elements = None
    endpoint_errors = []
    for index, endpoint in enumerate(OVERPASS_ENDPOINTS):
        req = urllib.request.Request(endpoint, data=data,
                                     headers={**headers, "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=18 if index == 0 else 12) as response:
                elements = json.loads(response.read().decode("utf-8")).get("elements", [])
            break
        except Exception as exc:
            endpoint_errors.append(f"{endpoint}: {exc}")
    if elements is None:
        raise ConnectionError("Nedostupné jsou oba servery OpenStreetMap. " + " | ".join(endpoint_errors))
    stamp = now_iso()
    stations = []
    for element in elements:
        tags = element.get("tags", {})
        point = element.get("center", element)
        if "lat" not in point or "lon" not in point:
            continue
        station_name = tags.get("name") or tags.get("name:cs") or tags.get("brand") or tags.get("operator")
        station_name = station_name or (f"Čerpací stanice · {tags['addr:street']}" if tags.get("addr:street") else "Čerpací stanice")
        address = osm_address(tags, display_city)
        identity = f"{element['type']}/{element['id']}"
        stations.append({
            "id": identity, "name": station_name, "address": address, "city": display_city,
            "lat": float(point["lat"]), "lon": float(point["lon"]), "updated_at": stamp,
        })
    return display_city, stations


def fetch_national_averages() -> tuple[dict[str, float], str]:
    """Fetch the latest national weekly fuel averages published by the Czech Statistical Office."""
    headers = {"User-Agent": "FuelRadar/1.0 (desktop fuel station finder)"}
    req = urllib.request.Request(CSU_DATASET_URL, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as response:
        distribution = json.loads(response.read().decode("utf-8"))
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


class FuelRadarApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Fuel Radar")
        self.geometry("1260x820")
        self.minsize(1020, 680)
        self.configure(bg=BG)
        self.store = FuelStore()
        self.city = self.store.last_city()
        self.stations: list[dict] = []
        self.selected: dict | None = None
        self.events: queue.Queue = queue.Queue()
        self._configure_styles()
        self._build_ui()
        self.national = self.store.national_prices()
        self._render_national()
        self._refresh_national()
        if self.city:
            self.city_var.set(self.city)
            self._load_cached()
            self.after(350, self.search)
        self.after(100, self._poll_events)

    def _configure_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                        rowheight=48, borderwidth=0, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background=PANEL_ALT, foreground=MUTED,
                        borderwidth=0, relief="flat", font=("Segoe UI", 9, "bold"), padding=(10, 12))
        style.map("Treeview", background=[("selected", "#244b41")], foreground=[("selected", TEXT)])
        style.configure("Fuel.TCombobox", fieldbackground=PANEL, background=PANEL_ALT,
                        foreground=TEXT, arrowcolor=GREEN, padding=9)

    def _build_ui(self):
        sidebar = tk.Frame(self, bg="#0e151e", width=230)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        logo = tk.Frame(sidebar, bg="#0e151e")
        logo.pack(fill="x", padx=22, pady=(27, 35))
        tk.Label(logo, text="◉", fg=GREEN, bg="#0e151e", font=("Segoe UI", 24, "bold")).pack(side="left")
        tk.Label(logo, text="FUEL\nRADAR", fg=TEXT, bg="#0e151e", justify="left",
                 font=("Segoe UI", 12, "bold")).pack(side="left", padx=(10, 0))
        tk.Label(sidebar, text="PŘEHLED", bg="#1a322d", fg=GREEN, anchor="w",
                 padx=18, pady=12, font=("Segoe UI", 10, "bold")).pack(fill="x", padx=13)
        tk.Label(sidebar, text="\nPALIVA", bg="#0e151e", fg="#627181", anchor="w",
                 padx=24, font=("Segoe UI", 8, "bold")).pack(fill="x", pady=(24, 8))
        for label, glyph in (("Benzín Natural 95", "●"), ("Nafta / Diesel", "●"), ("LPG", "●")):
            row = tk.Frame(sidebar, bg="#0e151e")
            row.pack(fill="x", padx=24, pady=8)
            tk.Label(row, text=glyph, fg=GREEN if label.startswith("Benzín") else BLUE if label.startswith("Nafta") else AMBER,
                     bg="#0e151e", font=("Segoe UI", 10)).pack(side="left")
            tk.Label(row, text=label, fg="#b3bfcb", bg="#0e151e", font=("Segoe UI", 9)).pack(side="left", padx=10)
        tk.Frame(sidebar, bg=LINE, height=1).pack(fill="x", padx=20, pady=(28, 20))
        tk.Label(sidebar, text="DATA O STANICÍCH", bg="#0e151e", fg="#627181", anchor="w",
                 padx=24, font=("Segoe UI", 8, "bold")).pack(fill="x", pady=(0, 9))
        tk.Label(sidebar, text="OpenStreetMap", bg="#0e151e", fg=MUTED, anchor="w",
                 padx=24, font=("Segoe UI", 9)).pack(fill="x")
        tk.Label(sidebar, text="Týdenní průměry: ČSÚ", bg="#0e151e", fg=MUTED,
                 anchor="w", padx=24, font=("Segoe UI", 9)).pack(fill="x", pady=(7, 0))
        tk.Label(sidebar, text="Uložené ceny najdeš i\npo opětovném spuštění.",
                 bg="#0e151e", fg="#718092", justify="left", padx=24,
                 font=("Segoe UI", 9)).pack(side="bottom", anchor="w", pady=22)

        content = tk.Frame(self, bg=BG)
        content.pack(side="left", fill="both", expand=True, padx=30, pady=24)
        top = tk.Frame(content, bg=BG)
        top.pack(fill="x")
        tk.Label(top, text="Najdi výhodné tankování", bg=BG, fg=TEXT,
                 font=("Segoe UI", 23, "bold")).pack(side="left")
        self.status_var = tk.StringVar(value="Připraveno k hledání")
        tk.Label(top, textvariable=self.status_var, bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="right", pady=10)
        tk.Label(content, text="Stanice v okolí · cenové karty ukazují týdenní průměr ČSÚ za celé Česko",
                 bg=BG, fg=MUTED,
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(3, 21))

        search = tk.Frame(content, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        search.pack(fill="x", pady=(0, 18))
        tk.Label(search, text="⌕", bg=PANEL, fg=GREEN, font=("Segoe UI", 21)).pack(side="left", padx=(15, 8))
        self.city_var = tk.StringVar()
        self.city_entry = tk.Entry(search, textvariable=self.city_var, bg=PANEL, fg=TEXT,
                                   insertbackground=TEXT, relief="flat", font=("Segoe UI", 11))
        self.city_entry.pack(side="left", fill="x", expand=True, ipady=16)
        self.city_entry.insert(0, "")
        self.city_entry.bind("<Return>", lambda _e: self.search())
        self.search_button = tk.Button(search, text="Hledat stanice", command=self.search, bg=GREEN,
                                       fg="#102018", activebackground="#9af0c4", relief="flat",
                                       padx=20, pady=11, cursor="hand2", font=("Segoe UI", 10, "bold"))
        self.search_button.pack(side="right", padx=8, pady=8)

        cards = tk.Frame(content, bg=BG)
        cards.pack(fill="x", pady=(0, 19))
        self.station_count = self._stat_card(cards, "STANICE V OKOLÍ", "—", "OpenStreetMap")
        self.average_cards = {
            "benzín": self._stat_card(cards, "PRŮMĚR ČR · BENZÍN", "—", "ČSÚ · týdenní cena"),
            "nafta": self._stat_card(cards, "PRŮMĚR ČR · NAFTA", "—", "ČSÚ · týdenní cena"),
            "lpg": self._stat_card(cards, "PRŮMĚR ČR · LPG", "—", "ČSÚ · týdenní cena"),
        }

        toolbar = tk.Frame(content, bg=BG)
        toolbar.pack(fill="x", pady=(0, 9))
        tk.Label(toolbar, text="Stanice v okolí", bg=BG, fg=TEXT,
                 font=("Segoe UI", 14, "bold")).pack(side="left")
        table_frame = tk.Frame(content, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        table_frame.pack(fill="both", expand=True)
        columns = ("name", "address")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headings = {"name": "ČERPACÍ STANICE", "address": "ZNÁMÁ ADRESA"}
        widths = {"name": 300, "address": 450}
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], minwidth=180, anchor="w")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._select_station)
        self.tree.bind("<Double-1>", lambda _e: self.open_map())
        self.empty = tk.Label(table_frame, text="Zadej město a stiskni Hledat stanice.",
                              bg=PANEL, fg=MUTED, font=("Segoe UI", 11), justify="center")
        self.empty.place(relx=.5, rely=.5, anchor="center")

        bottom = tk.Frame(content, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        bottom.pack(fill="x", pady=(13, 0))
        self.detail_var = tk.StringVar(value="Vyber stanici ze seznamu pro zobrazení detailu.")
        tk.Label(bottom, textvariable=self.detail_var, bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9), anchor="w").pack(side="left", padx=14, pady=14, fill="x", expand=True)
        self.map_button = tk.Button(bottom, text="Otevřít mapu ↗", command=self.open_map, state="disabled",
                                    bg=PANEL_ALT, fg=TEXT, activebackground="#273646", relief="flat",
                                    padx=15, pady=9, cursor="hand2", font=("Segoe UI", 9))
        self.map_button.pack(side="right", padx=5, pady=8)

    def _stat_card(self, parent, title, value, hint):
        card = tk.Frame(parent, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        card.pack(side="left", fill="x", expand=True, padx=(0, 10))
        tk.Label(card, text=title, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=15, pady=(12, 3))
        label = tk.Label(card, text=value, bg=PANEL, fg=TEXT, font=("Segoe UI", 19, "bold"))
        label.pack(anchor="w", padx=15)
        hint_label = tk.Label(card, text=hint, bg=PANEL, fg="#68798a", font=("Segoe UI", 8))
        hint_label.pack(anchor="w", padx=15, pady=(0, 12))
        label.hint_label = hint_label
        return label

    def _load_cached(self):
        if not self.city:
            return
        self.stations = self.store.stations_for_city(self.city)
        self._render()

    def search(self):
        city = self.city_var.get().strip()
        if not city:
            messagebox.showinfo("Zadej město", "Napiš název města, například Praha, Brno nebo Trutnov.")
            self.city_entry.focus_set()
            return
        self.city = city
        self.store.remember_city(city)
        self.stations = self.store.stations_for_city(city)
        self._render()
        if self.store.station_cache_is_fresh(city):
            self.status_var.set(f"Načteno z cache · {len(self.stations)} stanic")
            return
        self.status_var.set(f"Vyhledávám stanice poblíž: {city}…")
        self.search_button.configure(state="disabled", text="Vyhledávám…")
        threading.Thread(target=self._search_worker, args=(city,), daemon=True).start()

    def _search_worker(self, city):
        try:
            resolved, stations = fetch_stations(city, self.store)
            self.store.replace_stations(resolved, stations)
            self.events.put(("success", city, resolved, len(stations), None))
        except Exception as exc:
            self.events.put(("error", city, str(exc)))

    def _national_worker(self):
        try:
            prices, period = fetch_national_averages()
            self.store.save_national_prices(prices, period)
            self.events.put(("national", prices, period, None))
        except Exception as exc:
            self.events.put(("national", None, None, str(exc)))

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
            week, year = record["period"].split("-W")
            card.hint_label.configure(text=f"ČSÚ · týden {int(week)}/{year}")

    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "national":
                    _, prices, period, error = event
                    if prices:
                        self.national = {fuel: {"price": value, "period": period} for fuel, value in prices.items()}
                        self._render_national()
                    elif error and not self.national:
                        self.status_var.set("ČSÚ nedostupný · ceny se načtou při příštím spuštění")
                elif event[0] == "success":
                    _, requested, resolved, count, _ = event
                    if requested == self.city:
                        self.city = resolved
                        self.city_var.set(resolved)
                        self.stations = self.store.stations_for_city(resolved)
                        self._render()
                        self.status_var.set(f"Načteno {count} stanic · OpenStreetMap")
                elif event[0] == "error":
                    _, requested, error = event
                    if requested == self.city:
                        self.stations = self.store.stations_for_city(requested)
                        self._render()
                        cached_count = len(self.stations)
                        self.status_var.set(f"Stanice nešlo obnovit · zobrazeno uložených: {cached_count}")
                        messagebox.showwarning(
                            "Stanice se nepodařilo načíst",
                            f"Online vyhledávání selhalo.\n\n{error}\n\n"
                            f"Zobrazuji uložené stanice ({cached_count}), pokud jsou k dispozici. "
                            "Zkontroluj připojení k internetu a zkus hledání znovu.",
                        )
                if event[0] != "national":
                    self.search_button.configure(state="normal", text="Hledat stanice")
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def _render(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.empty.place_forget()
        for station in self.stations:
            if station["name"].strip() and station["address"].strip():
                self.tree.insert("", "end", iid=station["id"], values=(station["name"], station["address"]))
        self.station_count.configure(text=str(len(self.stations)))
        if not self.tree.get_children():
            self.empty.configure(text="Zadej město a stiskni Hledat stanice." if not self.stations else "V okolí nebyly nalezeny žádné stanice.")
            self.empty.place(relx=.5, rely=.5, anchor="center")

    def _select_station(self, _event=None):
        selected = self.tree.selection()
        self.selected = next((s for s in self.stations if selected and s["id"] == selected[0]), None)
        if not self.selected:
            self.map_button.configure(state="disabled")
            return
        self.map_button.configure(state="normal")
        self.detail_var.set(f"{self.selected['name']}  ·  {self.selected['address']}")

    def open_map(self):
        if self.selected:
            lat, lon = self.selected["lat"], self.selected["lon"]
            url = "https://www.openstreetmap.org/?" + urllib.parse.urlencode({"mlat": lat, "mlon": lon, "zoom": 16})
            webbrowser.open(url)


if __name__ == "__main__":
    FuelRadarApp().mainloop()
