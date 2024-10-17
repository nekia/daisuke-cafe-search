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
        "X-Goog-FieldMask": "places.displayName,places.primaryType,places.primaryTypeDisplayName,places.shortFormattedAddress,places.googleMapsUri,places.id,places.location,places.currentOpeningHours",
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
                "location": results[0].get('location'),
                "openingHours": results[0].get('currentOpeningHours')
            }

    print(response.json())
    return None

# MongoDB接続設定
client = MongoClient("mongodb://localhost:27017/")
db = client.places
collection = db.place_info

# CSVファイルの読み込み
csv_file = 'locations_fixed.csv'
df = pd.read_csv(csv_file)

# Google APIキー
api_key = os.environ["GOOGLE_MAPS_API_KEY"]

# 各場所の名前について詳細情報を取得
for index, row in df.iterrows():
    location_name = unquote(row['タイトル'])
    place_info = get_place_id(location_name, api_key)
    if place_info:
        print(f"Retrieved location info: {place_info}")
        # MongoDBにデータを挿入（既存IDがあれば更新、なければ挿入）
        collection.update_one(
            {"id": place_info["id"]},
            {"$setOnInsert": place_info},
            upsert=True
        )
    else:
        print(f"Failed to retrieve place ID for {location_name}")