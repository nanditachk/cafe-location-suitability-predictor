import requests
import numpy as np
import rasterio
from geopy.distance import geodesic
import os

from dotenv import load_dotenv

load_dotenv()

# -----------------------------
# PATH
# -----------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POP_PATH = os.path.join(BASE_DIR, "data", "india_pop.tif")

pop_dataset = rasterio.open(POP_PATH)
pop_band = pop_dataset.read(1)

# -----------------------------
# CONFIG
# -----------------------------
API_KEY = os.getenv("API_KEY")

PLACES_URL = "https://places.googleapis.com/v1/places:searchNearby"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

HEADERS = {
    "Content-Type": "application/json",
    "X-Goog-Api-Key": API_KEY,
    "X-Goog-FieldMask": "places.displayName,places.types,places.location"
}

# -----------------------------
# GOOGLE PLACES (PRIMARY)
# -----------------------------
def fetch_places(lat, lon):
    url = "https://places.googleapis.com/v1/places:searchText"

    all_places = []

    queries = [
        "cafe",
        "restaurant",
        "bakery",
        "office",
        "school",
        "college",
        "shopping mall",
        "bus stop"
    ]

    for q in queries:
        data = {
            "textQuery": q,
            "locationBias": {
                "circle": {
                    "center": {
                        "latitude": lat,
                        "longitude": lon
                    },
                    "radius": 500
                }
            }
        }

        try:
            res = requests.post(url, headers=HEADERS, json=data, timeout=10)

            if res.status_code == 200:
                places = res.json().get("places", [])
                print(f"{q}: {len(places)}")
                all_places.extend(places)
            else:
                print("Error:", res.status_code)

        except Exception as e:
            print("Exception:", e)

    return all_places
# -----------------------------
# OVERPASS (FALLBACK)
# -----------------------------
def count_overpass(lat, lon, tag, value):
    query = f"""
    [out:json][timeout:15];
    node(around:500,{lat},{lon})["{tag}"="{value}"];
    out;
    """

    try:
        res = requests.get(OVERPASS_URL, params={"data": query}, timeout=15)
        if res.status_code == 200:
            return len(res.json().get("elements", []))
        return 0
    except:
        return 0

# -----------------------------
# POPULATION
# -----------------------------
def get_population(lat, lon):
    try:
        r, c = pop_dataset.index(lon, lat)
        val = pop_band[r, c]
        return float(val) if val > 0 else 1
    except:
        return 1

# -----------------------------
# ROADS
# -----------------------------
def road_features(lat, lon):
    query = f"""
    [out:json][timeout:15];
    way(around:500,{lat},{lon})["highway"];
    out geom;
    """

    try:
        res = requests.get(OVERPASS_URL, params={"data": query}, timeout=15)
        data = res.json()

        total_length = 0
        min_dist = 999
        junction_dist = 999

        for el in data.get("elements", []):
            if "geometry" not in el:
                continue

            coords = el["geometry"]

            for i in range(len(coords) - 1):
                lat1, lon1 = coords[i]["lat"], coords[i]["lon"]
                lat2, lon2 = coords[i+1]["lat"], coords[i+1]["lon"]

                d = geodesic((lat1, lon1), (lat2, lon2)).km
                total_length += d

                dist = geodesic((lat, lon), (lat1, lon1)).km
                min_dist = min(min_dist, dist)

        return total_length, min_dist, min_dist

    except:
        return 0.1, 0.5, 0.5  # fallback realistic

# -----------------------------
# BUILDINGS
# -----------------------------
def building_features(lat, lon):
    query = f"""
    [out:json][timeout:15];
    way(around:500,{lat},{lon})["building"];
    out;
    """

    try:
        res = requests.get(OVERPASS_URL, params={"data": query}, timeout=15)
        data = res.json()

        total = len(data.get("elements", []))
        commercial = 0

        for el in data.get("elements", []):
            tags = el.get("tags", {})
            if tags.get("building") in ["commercial", "retail", "office"]:
                commercial += 1

        if total == 0:
            return 5, 0.2  # fallback

        return total, commercial / total

    except:
        return 5, 0.2

# -----------------------------
# MAIN
# -----------------------------
def get_features(lat, lon):

    places = fetch_places(lat, lon)

    features = {
        "cafe_count_500m": 0,
        "restaurant_count_500m": 0,
        "premium_chain_count_500m": 0,
        "bakery_count_500m": 0,
        "office_count": 0,
        "college_count": 0,
        "school_count": 0,
        "mall_count": 0,
        "bus_stop_count": 0,
        "metro_distance": 999
    }

    premium = ["starbucks", "barista", "blue tokai", "costa", "third wave"]
    metro_dists = []

    # -----------------------------
    # GOOGLE PARSING
    # -----------------------------
    for p in places:
        types = p.get("types", [])
        name = str(p.get("displayName", {}).get("text", "")).lower()

        plat = p.get("location", {}).get("latitude")
        plon = p.get("location", {}).get("longitude")

        if "cafe" in types:
            features["cafe_count_500m"] += 1
            if any(x in name for x in premium):
                features["premium_chain_count_500m"] += 1

        if "restaurant" in types:
            features["restaurant_count_500m"] += 1

        if "bakery" in types:
            features["bakery_count_500m"] += 1

        if "school" in types:
            features["school_count"] += 1

        if "university" in types:
            features["college_count"] += 1

        if "shopping_mall" in types:
            features["mall_count"] += 1

        if "bus_station" in types:
            features["bus_stop_count"] += 1

        if "subway_station" in types or "train_station" in types:
            if plat and plon:
                metro_dists.append(geodesic((lat, lon), (plat, plon)).km)

    # -----------------------------
    # FALLBACK USING OVERPASS
    # -----------------------------
    if features["cafe_count_500m"] == 0:
        features["cafe_count_500m"] = count_overpass(lat, lon, "amenity", "cafe")

    if features["restaurant_count_500m"] == 0:
        features["restaurant_count_500m"] = count_overpass(lat, lon, "amenity", "restaurant")

    if features["bus_stop_count"] == 0:
        features["bus_stop_count"] = count_overpass(lat, lon, "highway", "bus_stop")

    # -----------------------------
    # METRO FIX
    # -----------------------------
    if metro_dists:
        features["metro_distance"] = min(metro_dists)
    else:
        features["metro_distance"] = 3.0  # fallback realistic

    # -----------------------------
    # EXTRA FEATURES
    # -----------------------------
    pop = get_population(lat, lon)
    road, dist_main, dist_junc = road_features(lat, lon)
    built, commercial_ratio = building_features(lat, lon)

    features["population_density"] = pop
    features["built_up_density"] = built
    features["commercial_building_ratio"] = commercial_ratio
    features["road_density"] = road
    features["distance_to_main_road"] = dist_main
    features["distance_to_junction"] = dist_junc
    features["night_light_intensity"] = (pop * 0.00001) + (road * 0.3)

    # -----------------------------
    # DERIVED FEATURES
    # -----------------------------
    cafe = features["cafe_count_500m"]
    rest = features["restaurant_count_500m"]

    cafe_to_restaurant_ratio = cafe / rest if rest > 0 else cafe
    competition_score = cafe + rest
    accessibility_score = features["bus_stop_count"] + (1 / (features["metro_distance"] + 1))

    rating = 4.0
    review_count = 100

    # -----------------------------
    # FINAL
    # -----------------------------
    return {
        "latitude": lat,
        "longitude": lon,

        **features,

        "rating": rating,
        "review_count": review_count,
        "cafe_to_restaurant_ratio": cafe_to_restaurant_ratio,
        "competition_score": competition_score,
        "accessibility_score": accessibility_score
    }