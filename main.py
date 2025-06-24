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
CAT_FAV_DOG_NG = 3

load_dotenv()

def get_place_id(location_name, cat_num, api_key):
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-FieldMask": "places.displayName,places.primaryTypeDisplayName,places.googleMapsUri,places.id,places.location,places.formattedAddress",
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
            # 結果が1件の場合は自動選択
            if len(results) == 1:
                selected_place = results[0]
                print(f"✓ 1件のみ見つかりました: {selected_place.get('displayName')}")
            else:
                # 複数の結果がある場合はユーザーに選択させる
                print(f"\n「{location_name}」で{len(results)}件の候補が見つかりました:")
                print("-" * 60)
                for i, place in enumerate(results):
                    display_name = place.get('displayName', {}).get('text', 'N/A')
                    primary_type = place.get('primaryTypeDisplayName', {}).get('text', 'N/A')
                    address = place.get('formattedAddress', 'N/A')
                    print(f"{i + 1}. {display_name} ({primary_type}) - {address}")
                
                print(f"{len(results) + 1}. スキップ（この場所を飛ばす）")
                print("-" * 60)
                
                while True:
                    try:
                        choice = input(f"選択してください (1-{len(results) + 1}): ")
                        choice_num = int(choice)
                        if 1 <= choice_num <= len(results):
                            selected_place = results[choice_num - 1]
                            selected_name = selected_place.get('displayName', {}).get('text', 'N/A')
                            print(f"✓ 選択されました: {selected_name}")
                            break
                        elif choice_num == len(results) + 1:
                            print("✓ スキップします")
                            return None
                        else:
                            print(f"1から{len(results) + 1}の数字を入力してください")
                    except ValueError:
                        print("数字を入力してください")
                    except KeyboardInterrupt:
                        print("\n処理を中断します")
                        return None
            
            return {
                "id": selected_place.get('id'),
                "location_name": selected_place.get('displayName'),
                "primary_type": selected_place.get('primaryTypeDisplayName'),
                "url": selected_place.get('googleMapsUri'),
                "location": selected_place.get('location'),
                "category": cat_num,
                "alias": location_name
            }

    print(f"エラー: {response.json()}")
    return None

def get_opening_hours(place_id, api_key):
    """営業時間情報を別途取得する関数"""
    url = f"https://places.googleapis.com/v1/places/{place_id}"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-FieldMask": "currentOpeningHours",
        "X-Goog-Api-Key": api_key,
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        result = response.json()
        return result.get('currentOpeningHours')
    else:
        print(f"Failed to get opening hours for {place_id}: {response.json()}")
        return None

# MongoDB接続設定

client = MongoClient(os.environ["MONGODB_ADDRESS"])
db = client.places
collection = db.place_info

# CSVファイルの読み込み
csv_file = 'おれたちのモグモグリスト.csv'
category = CAT_FAV_DOG_NG
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
            
            # 営業時間情報を別途取得するかどうか（必要に応じてTrue/Falseを切り替え）
            get_hours = False  # 営業時間情報が必要な場合はTrueに変更
            if get_hours:
                opening_hours = get_opening_hours(place_info["id"], api_key)
                if opening_hours:
                    place_info["openingHours"] = opening_hours
                    print(f"Retrieved opening hours for {location_name}")
            
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

