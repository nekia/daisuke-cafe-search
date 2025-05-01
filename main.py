import os
import pandas as pd
import requests
import json
from dotenv import load_dotenv
# from urllib.parse import unquote
from pymongo import MongoClient
import csv

# Category constants
CAT_INSIDE_OK = 1
CAT_TERRACE_OK = 2

load_dotenv()

def get_place_id(location_name, cat_num, api_key):
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
                "openingHours": results[0].get('currentOpeningHours'),
                "category": cat_num,
                "alias": location_name
            }

    print(response.json())
    return None

# MongoDB接続設定

client = MongoClient(os.environ["MONGODB_ADDRESS"])
db = client.places
collection = db.place_info

# CSVファイルの読み込み
csv_file = 'New!! 犬外席OK、散歩途中テイクアウトOK飲食店.csv'
category = CAT_TERRACE_OK
df = pd.read_csv(csv_file, encoding='utf-8', quotechar='"', escapechar='\\', on_bad_lines='skip')

# Google APIキー
api_key = os.environ["GOOGLE_MAPS_API_KEY"]

# 出力用CSVファイルの設定
output_file = 'output.csv'

# 出力用CSVファイルの初期化（ヘッダーを書き込む）
with open(output_file, mode='w', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    writer.writerow(['location_name', 'comment', 'url'])

def check_location_exists(location_name):
    """Check if a location_name exists in the MongoDB collection by checking both location_name.text and alias fields"""
    # First check location_name.text
    result = collection.find_one({"location_name.text": location_name})
    if result is not None:
        return True
    
    # If not found, check alias field (if it exists)
    result = collection.find_one({"alias": location_name})
    return result is not None

# 各場所の名前について詳細情報を取得
for index, row in df.iterrows():
    # location_name = unquote(row['タイトル'])
    location_name = row['タイトル']
    comment = row['メモ']
    # 使用例
    exists = check_location_exists(location_name)
    if exists:
        print(f"{location_name}は既にデータベースに存在します")
    else:
        place_info = get_place_id(location_name, category, api_key)
        if place_info:
            print(f"Retrieved location info: {place_info}")
            # MongoDBにデータを挿入（既存IDがあれば更新、なければ挿入）
            collection.update_one(
                {"id": place_info["id"]},
                {"$set": place_info},
                upsert=True
            )
            # CSVファイルにデータを書き込む
            with open(output_file, mode='a', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow([location_name, comment, place_info['url']])
        else:
            print(f"Failed to retrieve place ID for {location_name}")

