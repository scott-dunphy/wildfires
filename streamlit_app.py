import streamlit as st
import requests
import json
import time
from shapely.geometry import Point, shape
from math import radians, cos, sin, sqrt, atan2
from geopy.geocoders import Nominatim
from datetime import datetime
import pandas as pd
from shapely.ops import transform
import pyproj
import googlemaps
from collections import namedtuple

Location = namedtuple("Location", ["latitude", "longitude"])

def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in miles using the haversine formula"""
    R = 3958.8  # Radius of Earth in miles
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

def meters_to_miles(meters):
    """Convert meters to miles"""
    return meters * 0.000621371

def find_evacuation_zones(lat, lon, geojson_data):
    point = Point(lon, lat)
    matching_zones = []
    closest_distance = float('inf')
    closest_zone = None
    closest_warning_distance = float('inf')
    closest_warning_zone = None

    # Create a local projection centered on the point of interest
    local_azimuthal_projection = pyproj.Proj(
        proj='aeqd',  # Azimuthal Equidistant projection
        lat_0=lat,
        lon_0=lon,
        datum='WGS84'
    )
    wgs84 = pyproj.Proj('EPSG:4326')
    project = pyproj.Transformer.from_proj(wgs84, local_azimuthal_projection, always_xy=True).transform

    # Project the point
    point_projected = transform(project, point)

    for feature in geojson_data["features"]:
        try:
            polygon = shape(feature["geometry"])
            zone_status = feature["properties"].get("zone_status", "")
            
            # Project the polygon
            polygon_projected = transform(project, polygon)
            
            if polygon.contains(point):
                matching_zones.append(feature["properties"])
            else:
                # Calculate distance using haversine for more stability
                boundary_points = list(polygon.exterior.coords)
                min_distance = float('inf')
                
                for boundary_point in boundary_points:
                    dist = haversine(lat, lon, boundary_point[1], boundary_point[0])
                    min_distance = min(min_distance, dist)
                
                if min_distance < closest_distance:
                    closest_distance = min_distance
                    closest_zone = feature["properties"]
                if zone_status == "Evacuation Warning" and min_distance < closest_warning_distance:
                    closest_warning_distance = min_distance
                    closest_warning_zone = feature["properties"]

        except (ValueError, AttributeError) as e:
            # Skip invalid geometries
            continue

    return matching_zones, closest_distance, closest_zone, closest_warning_distance, closest_warning_zone

# Geocoding function
def locate_property(address):
    api_key = st.secrets["GOOGLE_MAPS_API_KEY"]
    if not api_key:
        print("Error: GOOGLE_MAPS_API_KEY environment variable not set.")
        return None

    gmaps = googlemaps.Client(key=api_key)

    try:
        geocode_result = gmaps.geocode(address)
        if geocode_result:
            location = geocode_result[0]['geometry']['location']
            latitude = location['lat']
            longitude = location['lng']
            return Location(latitude=latitude, longitude=longitude)
        else:
            print(f"Geocoding failed for address: {address}, no results found")
            return None
    except googlemaps.exceptions.ApiError as e:
        print(f"Geocoding error for address: {address}. API Error: {e}")
        return None

# Streamlit App
st.title("SoCal Wildfire Evacuation/Warning Zone Finder")
st.write("Enter up to 10 addresses (one per line) to check their evacuation zone status.")

# Input addresses
address_input = st.text_area("Addresses", placeholder="Enter addresses here, one per line...")
addresses = address_input.strip().split("\n")

if st.button("Check Zones"):
    if not addresses or addresses == [""]:
        st.warning("Please enter at least one address.")
    elif len(addresses) > 10:
       st.warning("Please enter a maximum of 10 addresses.")
    else:
        # Fetch the GeoJSON file
        geojson_url = "https://static01.nyt.com/projects/weather/weather-bots/cal-fire-evacuations/latest.json"
        response = requests.get(geojson_url)
        geojson_data = response.json()

        results = []

        for address in addresses[:10]:
            location = locate_property(address)
            if not location:
                results.append({
                    "Address": address,
                    "Evacuation Zone": "Not Available",
                    "Evacuation Warning": "Not Available",
                    "Distance to Closest Evacuation Zone (miles)": "N/A",
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
                last_updated = datetime.fromtimestamp(zone["last_updated"] / 1000).strftime("%Y-%m-%d %H:%M:%S") if zone.get("last_updated") else None
                results.append({
                    "Address": address,
                    "Evacuation Zone": "Yes" if zone.get("zone_status") == "Evacuation Order" else "No",
                    "Evacuation Warning": "Yes" if zone.get("zone_status") == "Evacuation Warning" else "No",
                    "Distance to Closest Evacuation Zone (miles)": None,
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
        
        # Streamlit Styling with Conditional Formatting
        def highlight_evacuation_zone(val):
            if val == "Yes":
                return "color: red; font-weight: bold;"
            return ""
        
        def highlight_evacuation_warning(val):
            if val == "Yes":
                return "color: red; font-weight: bold;"
            return ""

        # Apply styles
        styled_df = df.style.applymap(highlight_evacuation_zone, subset=["Evacuation Zone"])
        styled_df = styled_df.applymap(highlight_evacuation_warning, subset=["Evacuation Warning"])

        # Display with styled text
        st.write("Results:")
        st.dataframe(styled_df, use_container_width=True)

st.write("Evacuation Zone Source: NY Times")
st.write("Geocoding Source: OpenStreetMap")
