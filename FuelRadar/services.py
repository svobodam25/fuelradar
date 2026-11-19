"""Location autocomplete and station prices; no third party packages required."""
from __future__ import annotations

import json
import math
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
        result.append({"id": identity, "name": record.get("name") or record.get("brand") or "Čerpací stanice",
                       "address": record.get("address") or record.get("city") or f"GPS {slat:.5f}, {slon:.5f}",
                       "city": record.get("city", ""), "lat": slat, "lon": slon,
                       "distance": distance, "prices": prices,
                       "source": price.get("src", ""), "price_kind": price_kind(price.get("src")),
                       "updated_at": price.get("at") or dataset.get("last_updated", "")})
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
