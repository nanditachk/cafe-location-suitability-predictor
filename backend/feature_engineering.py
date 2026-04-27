import requests
from geopy.distance import geodesic

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def count_places(lat, lon, amenity, radius=500):

    query = f"""
    [out:json];
    (
      node["amenity"="{amenity}"](around:{radius},{lat},{lon});
    );
    out;
    """

    try:
        response = requests.get(
            OVERPASS_URL,
            params={"data": query},
            timeout=25
        )

        if response.status_code != 200:
            return 0

        data = response.json()

        return len(data.get("elements", []))

    except Exception as e:
        print("Overpass error:", e)
        return 0


def competition_features(lat, lon):

    return {
        "cafe_count_500m": count_places(lat, lon, "cafe"),
        "restaurant_count_500m": count_places(lat, lon, "restaurant"),
        "bakery_count_500m": count_places(lat, lon, "bakery")
    }


def demand_features(lat, lon):

    return {
        "office_count": count_places(lat, lon, "office"),
        "school_count": count_places(lat, lon, "school"),
        "college_count": count_places(lat, lon, "college"),
        "bus_stop_count": count_places(lat, lon, "bus_station")
    }


def metro_distance(lat, lon):

    query = f"""
    [out:json];
    node["railway"="station"](around:5000,{lat},{lon});
    out;
    """

    try:
        response = requests.get(
            OVERPASS_URL,
            params={"data": query},
            timeout=25
        )

        if response.status_code != 200:
            return 5

        data = response.json()

        if not data.get("elements"):
            return 5

        distances = []

        for el in data["elements"]:
            station = (el["lat"], el["lon"])
            distances.append(
                geodesic((lat, lon), station).km
            )

        return min(distances)

    except Exception as e:
        print("Metro query error:", e)
        return 5


def build_feature_vector(lat, lon):

    features = {}

    # Competition
    features.update(competition_features(lat, lon))

    # Demand
    features.update(demand_features(lat, lon))

    # Placeholder values for now
    features["premium_chain_count_500m"] = 0
    features["mall_count"] = 0

    features["population_density"] = 8000
    features["built_up_density"] = 0.6
    features["night_light_intensity"] = 35
    features["commercial_building_ratio"] = 0.5

    features["road_density"] = 8
    features["distance_to_main_road"] = 50
    features["distance_to_junction"] = 30

    # Metro
    features["metro_distance"] = metro_distance(lat, lon)

    return features