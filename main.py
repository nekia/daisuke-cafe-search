import os
import pandas as pd
import requests
import json
from dotenv import load_dotenv
from urllib.parse import unquote
from pymongo import MongoClient

load_dotenv()

def get_place_id(location_name, api_key):
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-FieldMask": "places.displayName,places.primaryType,places.primaryTypeDisplayName,places.shortFormattedAddress,places.googleMapsUri,places.id,places.location",
        "X-Goog-Api-Key": api_key,
    }
    payload = {
        "textQuery": location_name,
        "languageCode": "ja",
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    if response.status_code == 200:
        results = response.json().get('places')
        if results:
            return {
                "id": results[0].get('id'),
                "address": results[0].get('shortFormattedAddress'),
                "location_name": results[0].get('displayName'),
                "primary_type": results[0].get('primaryTypeDisplayName'),
                "url": results[0].get('googleMapsUri'),
                "location": results[0].get('location')
            }

    print(response.json())
    return None

# MongoDB接続設定
client = MongoClient("mongodb://localhost:27017/")
db = client.places
collection = db.place_info

# CSVファイルの読み込み
csv_file = 'locations_mini.csv'
df = pd.read_csv(csv_file)

# Google APIキー
api_key = os.environ["GOOGLE_MAPS_API_KEY"]

# 各場所の名前について詳細情報を取得
for index, row in df.iterrows():
    location_name = unquote(row['location_name'])
    place_info = get_place_id(location_name, api_key)
    if place_info:
        print(f"Retrieved location info: {place_info}")
        # MongoDBにデータを挿入
        collection.insert_one(place_info)
    else:
        print(f"Failed to retrieve place ID for {location_name}")



# def get_place_id(location_name, api_key):
#     url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={location_name}&key={api_key}"
#     response = requests.get(url)
#     if response.status_code == 200:
#         results = response.json().get('results')
#         if results:
#             return results[0].get('place_id')
#     return None

# def get_place_details(place_id, api_key):
#     url = f"https://places.googleapis.com/v1/places/{place_id}"
#     headers = {
#         "Content-Type": "application/json",
#         "X-Goog-FieldMask": "places.displayName,places.primaryTypeDisplayName,places.id",
#         "X-Goog-Api-Key": api_key,
#     }

#     response = requests.get(url, headers=headers, data=json.dumps(payload))
#     if response.status_code == 200:
#         results = response.json().get('places')
#         if results:
#             return results[0].get('id')

#     print(response.json())
#     return None

#     response = requests.get(url)
#     if response.status_code == 200:
#         print(response.json())
#         return response.json()
#     return None
