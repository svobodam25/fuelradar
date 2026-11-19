"""Location autocomplete and station prices; no third party packages required."""
from __future__ import annotations

import json
import math
import re
import threading
import time
import urllib.parse
import urllib.request
import unicodedata

PHOTON_URL = "https://photon.komoot.io/api/"
PRICES_URL = "https://www.benzinmapa.cz/data/map_data.json"
HEADERS = {"User-Agent": "FuelRadar/1.1 (desktop fuel station finder)",
           "Accept": "application/json"}
_price_lock = threading.Lock()
_price_cache = None
_price_time = 0.0
_reverse_lock = threading.Lock()
_reverse_time = 0.0


def prepare_station_address(station):
    """Migrate old cached GPS strings as well as newly downloaded records."""
    station = dict(station)
    raw = station.get("source_address", station.get("address", "")) or ""
    station["source_address"] = raw
    if "address_pending" not in station:
        coordinates_only = bool(re.match(r"^\s*(?:GPS\s*)?[+-]?\d+[.,]\d+\s*[,; ]\s*[+-]?\d+[.,]\d+\s*$", raw, re.I))
        station["address_pending"] = not raw.strip() or coordinates_only
    if station["address_pending"]:
        # The provider's 'city' can be a wrong town or a region; don't guess.
        station["address"] = "Upřesňuji obec…"
    return station


def fetch_station_place(lat, lon):
    """Describe a station's surroundings, without claiming a nearby house is its address."""
    global _reverse_time
    params = urllib.parse.urlencode({"lat": lat, "lon": lon, "limit": 3, "radius": 1, "lang": "default"})
    with _reverse_lock:
        delay = 1 - (time.monotonic() - _reverse_time)
        if delay > 0:
            time.sleep(delay)
        try:
            data = get_json("https://photon.komoot.io/reverse?" + params, timeout=8)
        finally:
            _reverse_time = time.monotonic()
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        if props.get("countrycode", "").upper() != "CZ":
            continue
        city = props.get("city") or (props.get("name") if props.get("type") in ("city", "locality") else None)
        if not city:
            continue
        district = props.get("district")
        parts = [city]
        if district and district != city:
            parts.append(district)
        street = props.get("street") or (props.get("name") if props.get("type") == "street" else None)
        if street:
            parts.append("poblíž " + street)
        return {"city": city, "address": " · ".join(parts)}
    raise ValueError("Obec se nepodařilo dohledat.")


def get_json(url, timeout=15):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_places(query: str) -> list[dict]:
    if len(query.strip()) < 2:
        return []
    params = urllib.parse.urlencode({"q": query.strip(), "limit": 6,
                                     "lang": "default", "countrycode": "CZ"})
    data = get_json(PHOTON_URL + "?" + params)
    places, seen = [], set()
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        if props.get("countrycode", "").upper() != "CZ":
            continue
        lon, lat = feature["geometry"]["coordinates"][:2]
        street = " ".join(str(props[k]) for k in ("street", "housenumber") if props.get(k))
        parts = []
        for part in (props.get("name"), street, props.get("city"),
                     props.get("district"), props.get("county"), props.get("state")):
            if part and part not in parts:
                parts.append(part)
        label = ", ".join(parts)
        key = (label, lat, lon)
        if label and key not in seen:
            seen.add(key)
            places.append({"label": label, "lat": float(lat), "lon": float(lon)})
    return places


def distance_km(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    value = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(lon2-lon1)/2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, value))))


def price_kind(source):
    if source == "tank-ono.cz":
        return "Ceník Tank ONO"
    if source == "uzivatel":
        return "Hlášení uživatele"
    return "Odhad"


def directions_url(origin, station):
    """Google Maps accepts coordinates or a typed address as the starting point."""
    if isinstance(origin, dict):
        origin = f"{origin['lat']},{origin['lon']}"
    if not str(origin or "").strip():
        raise ValueError("Zadej výchozí polohu pro trasu.")
    params = {"api": 1, "origin": origin,
              "destination": f"{station['lat']},{station['lon']}", "travelmode": "driving"}
    return "https://www.google.com/maps/dir/?" + urllib.parse.urlencode(params)


def sort_stations(stations, column="distance", descending=False):
    """Sort raw values, with missing values last in either direction."""
    def text_key(value):
        return "".join(c for c in unicodedata.normalize("NFKD", str(value).casefold())
                       if not unicodedata.combining(c))

    def value(station):
        if column in ("benzín", "nafta", "lpg"):
            return station.get("prices", {}).get(column)
        if column == "kind":
            return text_key(station.get("price_kind", "Odhad")) if station.get("prices") else None
        if column == "distance":
            return station.get("distance")
        return text_key(station.get(column, "")) or None

    known, missing = [], []
    # Deterministic ties, independent of the order of the previous sort.
    baseline = sorted(stations, key=lambda s: (s.get("distance", float("inf")),
                                               text_key(s.get("name", "")), s["id"]))
    for station in baseline:
        (missing if value(station) is None else known).append(station)
    return sorted(known, key=value, reverse=descending) + missing


def nearby_stations(dataset, lat, lon, radius=15):
    """Keep the provider's price provenance; never present estimates as reports."""
    result = []
    seen = set()
    for record in dataset["stations"]:
        try:
            slat, slon = float(record["lat"]), float(record["lng"])
            distance = distance_km(lat, lon, slat, slon)
            identity = str(record["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if distance > radius or identity in seen:
            continue
        seen.add(identity)
        price = record.get("p") or {}
        prices = {}
        for fuel, field in (("benzín", "n95"), ("nafta", "naf"), ("lpg", "lpg")):
            value = price.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0:
                prices[fuel] = float(value)
        result.append(prepare_station_address({"id": identity, "name": record.get("name") or record.get("brand") or "Čerpací stanice",
                       "address": record.get("address") or "",
                       "city": record.get("city", ""), "lat": slat, "lon": slon,
                       "distance": distance, "prices": prices,
                       "source": price.get("src", ""), "price_kind": price_kind(price.get("src")),
                       "updated_at": price.get("at") or dataset.get("last_updated", "")}))
    return sorted(result, key=lambda s: s["distance"])


def fetch_price_dataset():
    global _price_cache, _price_time
    with _price_lock:
        if _price_cache is not None and time.monotonic() - _price_time < 900:
            return _price_cache
        dataset = get_json(PRICES_URL, timeout=25)
        if not isinstance(dataset, dict) or not isinstance(dataset.get("stations"), list) or not dataset["stations"]:
            raise ValueError("Zdroj cen vrátil neplatný nebo prázdný seznam stanic.")
        _price_cache, _price_time = dataset, time.monotonic()
        return dataset
