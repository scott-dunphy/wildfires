import streamlit as st
import requests
import json
import time
from shapely.geometry import Point, shape
from math import radians, cos, sin, sqrt, atan2
from geopy.geocoders import Nominatim
from datetime import datetime
import pandas as pd

# Haversine formula to calculate distance in miles between two points
def haversine(lat1, lon1, lat2, lon2):
    R = 3958.8  # Radius of Earth in miles
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])  # Convert to radians
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

# Find evacuation zones or closest distance
def find_evacuation_zones(lat, lon, geojson_data):
    point = Point(lon, lat)
    matching_zones = []
    closest_distance = float('inf')
    closest_zone = None
    closest_warning_distance = float('inf')
    closest_warning_zone = None

    for feature in geojson_data["features"]:
        polygon = shape(feature["geometry"])
        zone_status = feature["properties"].get("zone_status", "")
        if polygon.contains(point):
            matching_zones.append(feature["properties"])
        else:
            # Calculate distance to the closest point on the polygon
            distance = polygon.exterior.distance(point)
            if distance < closest_distance:
                closest_distance = distance
                closest_zone = feature["properties"]
            if zone_status == "Evacuation Warning" and distance < closest_warning_distance:
                closest_warning_distance = distance
                closest_warning_zone = feature["properties"]

    if closest_zone:
        closest_point = polygon.exterior.interpolate(polygon.exterior.project(point))
        closest_lat, closest_lon = closest_point.y, closest_point.x
        closest_distance = haversine(lat, lon, closest_lat, closest_lon)
    if closest_warning_zone:
        closest_point = polygon.exterior.interpolate(polygon.exterior.project(point))
        closest_lat, closest_lon = closest_point.y, closest_point.x
        closest_warning_distance = haversine(lat, lon, closest_lat, closest_lon)


    return matching_zones, closest_distance, closest_zone, closest_warning_distance, closest_warning_zone

# Geocoding function
def locate_property(address):
    geolocator = Nominatim(user_agent="fires")
    location = geolocator.geocode(address)
    time.sleep(1)
    return location

# Streamlit App
st.title("Evacuation Zone Finder")
st.write("Enter a list of addresses (one per line) to check their evacuation zone status.")

# Input addresses
address_input = st.text_area("Addresses", placeholder="Enter addresses here, one per line...")
addresses = address_input.strip().split("\n")

if st.button("Check Zones"):
    if not addresses or addresses == [""]:
        st.warning("Please enter at least one address.")
    else:
        # Fetch the GeoJSON file
        geojson_url = "https://static01.nyt.com/projects/weather/weather-bots/cal-fire-evacuations/latest.json"
        response = requests.get(geojson_url)
        geojson_data = response.json()

        results = []

        for address in addresses:
            location = locate_property(address)
            if not location:
                results.append({
                    "Address": address,
                    "Evacuation Zone": "No",
                    "Evacuation Warning": "No",
                    "Distance to Closest Evacuation Zone (miles)": "N/A",
                    "Distance to Closest Warning Zone (miles)": "N/A",
                    "Zone ID": None,
                    "Zone Status": None,
                    "Zone Status Reason": None,
                    "North Of": None,
                    "East Of": None,
                    "South Of": None,
                    "West Of": None,
                    "Acreage": None,
                    "Estimated Population": None,
                    "Last Updated (EST)": None
                })
                continue

            latitude, longitude = location.latitude, location.longitude
            matching_zones, closest_distance, closest_zone, closest_warning_distance, closest_warning_zone = find_evacuation_zones(latitude, longitude, geojson_data)

            if matching_zones:
                zone = matching_zones[0]
                last_updated = datetime.fromtimestamp(zone["last_updated"] / 1000).strftime("%Y-%m-%d %H:%M:%S")
                results.append({
                    "Address": address,
                    "Evacuation Zone": "Yes",
                    "Evacuation Warning": "Yes" if zone.get("zone_status") == "Evacuation Warning" else "No",
                    "Distance to Closest Evacuation Zone (miles)": None,
                    "Distance to Closest Warning Zone (miles)": None,
                    "Zone ID": zone.get("zone_id"),
                    "Zone Status": zone.get("zone_status"),
                    "Zone Status Reason": zone.get("zone_status_reason"),
                    "North Of": zone.get("north_of"),
                    "East Of": zone.get("east_of"),
                    "South Of": zone.get("south_of"),
                    "West Of": zone.get("west_of"),
                    "Acreage": zone.get("acreage"),
                    "Estimated Population": zone.get("est_population"),
                    "Last Updated (EST)": last_updated
                })
            else:
                results.append({
                    "Address": address,
                    "Evacuation Zone": "No",
                    "Evacuation Warning": "No",
                    "Distance to Closest Evacuation Zone (miles)": f"{closest_distance:.2f}",
                    "Distance to Closest Warning Zone (miles)": f"{closest_warning_distance:.2f}" if closest_warning_zone else "N/A",
                    "Zone ID": None,
                    "Zone Status": None,
                    "Zone Status Reason": None,
                    "North Of": None,
                    "East Of": None,
                    "South Of": None,
                    "West Of": None,
                    "Acreage": None,
                    "Estimated Population": None,
                    "Last Updated (EST)": None
                })

        # Convert results to a DataFrame
        df = pd.DataFrame(results)

        # Add a column with red dots or apply custom styles
        def add_red_dot(row):
            if row["Evacuation Zone"] == "Yes":
                return "🔴"
            return ""

        
        # Streamlit Styling with Conditional Formatting
        def highlight_evacuation_zone(val):
            if val == "Yes":
                return "color: red; font-weight: bold;"
            return ""
        
        # Apply styles
        styled_df = df.style.applymap(highlight_evacuation_zone, subset=["Evacuation Zone"])
        
        # Display with red dots and styled text
        st.write("Results:")
        st.dataframe(styled_df, use_container_width=True)
