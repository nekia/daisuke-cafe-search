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
        "X-Goog-FieldMask": "places.displayName,places.primaryTypeDisplayName,places.googleMapsUri,places.id,places.location,places.formattedAddress,places.businessStatus",
        "X-Goog-Api-Key": api_key,
    }
    payload = {
        "textQuery": location_name,
        "languageCode": "ja",
        "maxResultCount": 20  # Places APIの最大値
    }
    
    all_results = []
    page_token = None
    
    # 最大100件まで取得（5ページ分）
    max_results = 100
    page_count = 0
    max_pages = 5  # 最大5ページまで取得
    
    while len(all_results) < max_results and page_count < max_pages:
        if page_token:
            payload["pageToken"] = page_token
        
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        if response.status_code == 200:
            result_data = response.json()
            results = result_data.get('places', [])
            all_results.extend(results)
            page_count += 1
            
            print(f"✓ ページ{page_count}: {len(results)}件取得（累計: {len(all_results)}件）")
            
            # 次のページがあるかチェック
            next_page_token = result_data.get('nextPageToken')
            
            if not next_page_token:
                print("これ以上の結果はありません")
                break
            else:
                page_token = next_page_token
        else:
            print(f"エラー: {response.json()}")
            return None
    
    if all_results:
        print(f"\n「{location_name}」で{len(all_results)}件の候補が見つかりました:")
        print("-" * 100)
        
        # 結果を表示（ページング対応）
        page_size = 20
        current_page = 0
        total_pages = (len(all_results) + page_size - 1) // page_size
        
        while True:
            start_idx = current_page * page_size
            end_idx = min(start_idx + page_size, len(all_results))
            current_results = all_results[start_idx:end_idx]
            
            print(f"\n--- ページ {current_page + 1}/{total_pages} ---")
            for i, place in enumerate(current_results):
                global_idx = start_idx + i
                display_name = place.get('displayName', {}).get('text', 'N/A')
                primary_type = place.get('primaryTypeDisplayName', {}).get('text', 'N/A')
                address = place.get('formattedAddress', 'N/A')
                business_status = place.get('businessStatus', 'N/A')
                
                # 住所をインデントでそろえる
                name_type = f"{display_name} ({primary_type})"
                print(f"{global_idx + 1:2d}. {name_type}")
                print(f"    {address} [状態: {business_status}]")
            
            # ナビゲーションオプションを表示
            print("-" * 100)
            if current_page > 0:
                print(f"p. 前のページ")
            if current_page < total_pages - 1:
                print(f"n. 次のページ")
            print(f"s. スキップ（この場所を飛ばす）")
            
            choice = input(f"選択してください (1-{len(all_results)}, p/n/s): ").strip().lower()
            
            if choice == 'p' and current_page > 0:
                current_page -= 1
                continue
            elif choice == 'n' and current_page < total_pages - 1:
                current_page += 1
                continue
            elif choice == 's':
                print("✓ スキップします")
                return None
            else:
                try:
                    choice_num = int(choice)
                    if 1 <= choice_num <= len(all_results):
                        selected_place = all_results[choice_num - 1]
                        selected_name = selected_place.get('displayName', {}).get('text', 'N/A')
                        print(f"✓ 選択されました: {selected_name}")
                        break
                    else:
                        print(f"1から{len(all_results)}の数字を入力してください")
                        continue
                except ValueError:
                    print("有効な選択肢を入力してください")
                    continue
                except KeyboardInterrupt:
                    print("\n処理を中断します")
                    return None
        
        # businessStatusをチェック
        business_status = selected_place.get('businessStatus')
        if business_status == 'CLOSED_PERMANENTLY':
            print(f"⚠️  {selected_place.get('displayName', {}).get('text', 'N/A')} は永久閉店のため登録しません")
            return None
        
        return {
            "id": selected_place.get('id'),
            "location_name": selected_place.get('displayName'),
            "primary_type": selected_place.get('primaryTypeDisplayName'),
            "url": selected_place.get('googleMapsUri'),
            "location": selected_place.get('location'),
            "category": cat_num,
            "alias": location_name,
            "businessStatus": business_status
        }

    print(f"エラー: 結果が見つかりませんでした")
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
csv_files = [
    ('犬店内（インナーテラス含む）OK飲食店.csv', CAT_INSIDE_OK),
    ('New!! 犬外席OK、散歩途中テイクアウトOK飲食店.csv', CAT_TERRACE_OK),
    ('おれたちのモグモグリスト.csv', CAT_FAV_DOG_NG)
]

# Google APIキー
api_key = os.environ["GOOGLE_MAPS_API_KEY"]

# 出力用CSVファイルの設定
output_file = 'output.csv'

# 出力用CSVファイルの初期化（ヘッダーを書き込む）
with open(output_file, mode='w', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    writer.writerow(['location_name', 'comment', 'url', 'category'])

def check_location_exists(location_name):
    """Check if a location_name exists in the MongoDB collection by checking both location_name.text and alias fields"""
    # First check location_name.text
    result = collection.find_one({"location_name.text": location_name})
    if result is not None:
        return True
    
    # If not found, check alias field (if it exists)
    result = collection.find_one({"alias": location_name})
    return result is not None

# 各CSVファイルを処理
for csv_file, category in csv_files:
    print(f"\n=== 処理中: {csv_file} (カテゴリ: {category}) ===")
    
    try:
        df = pd.read_csv(csv_file, encoding='utf-8', quotechar='"', escapechar='\\', on_bad_lines='skip')
        print(f"CSVファイル読み込み完了: {len(df)}件のデータ")
    except FileNotFoundError:
        print(f"エラー: {csv_file} が見つかりません。スキップします。")
        continue
    except Exception as e:
        print(f"エラー: {csv_file} の読み込みに失敗しました: {e}")
        continue

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
                    writer.writerow([location_name, comment, place_info['url'], category])
            else:
                print(f"Failed to retrieve place ID for {location_name}")

print("\n=== 全CSVファイルの処理が完了しました ===")

