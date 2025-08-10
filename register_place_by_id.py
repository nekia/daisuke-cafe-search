import os
import sys
import requests
import json
from dotenv import load_dotenv
from pymongo import MongoClient

# Category constants
CAT_INSIDE_OK = 1
CAT_TERRACE_OK = 2
CAT_FAV_DOG_NG = 3

load_dotenv()

# 以下からPlace IDを取得する
# https://developers.google.com/maps/documentation/javascript/examples/places-placeid-finder

def get_place_details(place_id, api_key):
    """Google Places API からPlace IDの詳細情報を取得する"""
    
    url = f"https://places.googleapis.com/v1/places/{place_id}?languageCode=ja"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-FieldMask": "displayName,primaryTypeDisplayName,googleMapsUri,id,location,formattedAddress,businessStatus,currentOpeningHours",
        "X-Goog-Api-Key": api_key,
    }

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"エラー: {response.json()}")
        return None

    return response.json()

def register_place_to_mongodb(place_data, category, alias=None):
    """MongoDBに場所情報を登録する"""
    
    # MongoDB接続設定
    client = MongoClient(os.environ["MONGODB_ADDRESS"])
    db = client.places
    collection = db.place_info

    # 登録用データの作成
    place_info = {
        "id": place_data.get('id'),
        "location_name": place_data.get('displayName'),
        "primary_type": place_data.get('primaryTypeDisplayName'),
        "url": place_data.get('googleMapsUri'),
        "location": place_data.get('location'),
        "category": category,
        "businessStatus": place_data.get('businessStatus'),
        "currentOpeningHours": place_data.get('currentOpeningHours')
    }

    # aliasが指定されている場合は追加
    if alias:
        place_info["alias"] = alias

    # businessStatusをチェック
    business_status = place_data.get('businessStatus')
    if business_status == 'CLOSED_PERMANENTLY':
        print(f"⚠️  {place_data.get('displayName', {}).get('text', 'N/A')} は永久閉店のため登録しません")
        return False

    # MongoDBにデータを挿入（既存IDがあれば更新、なければ挿入）
    result = collection.update_one(
        {"id": place_info["id"]},
        {"$set": place_info},
        upsert=True
    )

    if result.upserted_id:
        print(f"✓ 新しい場所を登録しました: {place_data.get('displayName', {}).get('text', 'N/A')}")
    else:
        print(f"✓ 既存の場所を更新しました: {place_data.get('displayName', {}).get('text', 'N/A')}")

    return True

def main():
    """メイン処理"""
    
    if len(sys.argv) < 3:
        print("使用方法: python register_place_by_id.py <place_id> <category> [alias]")
        print("category: 1=店内OK, 2=テラスOK, 3=犬NG")
        print("例: python register_place_by_id.py ChIJN1t_tDeuEmsRUsoyG83frY4 1")
        sys.exit(1)

    place_id = sys.argv[1]
    category = int(sys.argv[2])
    alias = sys.argv[3] if len(sys.argv) > 3 else None

    # カテゴリの妥当性チェック
    if category not in [CAT_INSIDE_OK, CAT_TERRACE_OK, CAT_FAV_DOG_NG]:
        print("エラー: カテゴリは1, 2, 3のいずれかを指定してください")
        print("1=店内OK, 2=テラスOK, 3=犬NG")
        sys.exit(1)

    # Google APIキー
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("エラー: GOOGLE_MAPS_API_KEY環境変数が設定されていません")
        sys.exit(1)

    print(f"Place ID: {place_id}")
    print(f"カテゴリ: {category}")
    if alias:
        print(f"エイリアス: {alias}")
    print("-" * 50)

    # Place IDから詳細情報を取得
    place_data = get_place_details(place_id, api_key)
    if not place_data:
        print("場所の詳細情報を取得できませんでした")
        sys.exit(1)

    # 取得した情報を表示
    display_name = place_data.get('displayName', {}).get('text', 'N/A')
    primary_type = place_data.get('primaryTypeDisplayName', {}).get('text', 'N/A')
    address = place_data.get('formattedAddress', 'N/A')
    business_status = place_data.get('businessStatus', 'N/A')

    print(f"場所名: {display_name}")
    print(f"タイプ: {primary_type}")
    print(f"住所: {address}")
    print(f"営業状態: {business_status}")

    # MongoDBに登録
    success = register_place_to_mongodb(place_data, category, alias)
    
    if success:
        print("✓ 登録が完了しました")
    else:
        print("✗ 登録に失敗しました")
        sys.exit(1)

if __name__ == "__main__":
    main() 