import os
import re
import pandas as pd
import requests
import json
import time
import argparse
from dotenv import load_dotenv
# from urllib.parse import unquote
from pymongo import MongoClient
import csv
from enterprise_refresh_utils import bucket_for_place_id, get_bucket_count, utc_now

# Category constants
CAT_INSIDE_OK = 1
CAT_TERRACE_OK = 2
CAT_FAV_DOG_NG = 3

SEARCH_FIELD_MASK = (
    "places.displayName,places.primaryType,places.primaryTypeDisplayName,"
    "places.googleMapsUri,places.id,places.location,places.formattedAddress,"
    "places.businessStatus"
)
DETAIL_FIELD_MASK = (
    "id,displayName,primaryType,primaryTypeDisplayName,googleMapsUri,"
    "location,formattedAddress,businessStatus"
)
JAPAN_LOCATION_RESTRICTION = {
    "rectangle": {
        "low": {"latitude": 24.25, "longitude": 122.93},
        "high": {"latitude": 45.52, "longitude": 153.99},
    }
}
NON_OPERATIONAL_STATUSES = frozenset({"CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"})
AUTOCOMPLETE_FIELD_MASK = "suggestions.placePrediction.placeId,suggestions.placePrediction.text"

load_dotenv()


def extract_cid_from_feature_id(feature_id):
    """Maps URL の 0x...:0x... 形式から CID（十進数）を取り出す。"""
    if not feature_id:
        return None
    parts = feature_id.split(":")
    if len(parts) != 2:
        return None
    try:
        return int(parts[1], 16)
    except ValueError:
        return None


def parse_google_maps_url_hint(maps_url):
    """CSV の Google Maps URL から照合用ヒントを取り出す。"""
    if maps_url is None or pd.isna(maps_url):
        return None
    url = str(maps_url).strip()
    if not url or "google.com/maps" not in url:
        return None

    feature_match = re.search(r"1s(0x[a-f0-9]+:0x[a-f0-9]+)", url, re.I)
    if feature_match:
        feature_id = feature_match.group(1)
        return {
            "feature_id": feature_id,
            "cid": extract_cid_from_feature_id(feature_id),
            "url": url,
        }

    place_id_match = re.search(r"(ChIJ[\w-]+)", url)
    if place_id_match:
        return {"place_id": place_id_match.group(1), "url": url}

    cid_match = re.search(r"[?&]cid=(\d+)", url)
    if cid_match:
        return {"cid": int(cid_match.group(1)), "url": url}

    return {"url": url}


def cid_to_storage_value(cid):
    """MongoDB の 8-byte int 制限を避けるため CID は文字列で保存する。"""
    if cid is None:
        return None
    return str(cid)


def place_matches_cid(place, cid):
    if not cid:
        return False
    return f"cid={cid}" in (place.get("googleMapsUri") or "")


def place_matches_url_hint(place, url_hint):
    if not url_hint:
        return False
    if url_hint.get("cid") and place_matches_cid(place, url_hint["cid"]):
        return True
    if url_hint.get("place_id") and url_hint["place_id"] in (place.get("googleMapsUri") or ""):
        return True
    feature_id = url_hint.get("feature_id")
    if feature_id and feature_id.lower() in (place.get("googleMapsUri") or "").lower():
        return True
    return place.get("id") == url_hint.get("place_id")


def sort_places(places, url_hint=None):
    def score(place):
        value = 0
        if url_hint and place_matches_url_hint(place, url_hint):
            value += 100
        if place.get("primaryType"):
            value += 10
        address = place.get("formattedAddress") or ""
        if "日本" in address or "Japan" in address:
            value += 5
        return value

    return sorted(places, key=score, reverse=True)


def search_places(text_query, api_key, *, location_restriction=None):
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-FieldMask": SEARCH_FIELD_MASK,
        "X-Goog-Api-Key": api_key,
    }
    payload = {
        "textQuery": text_query,
        "languageCode": "ja",
        "regionCode": "JP",
        "maxResultCount": 20,
    }
    if location_restriction:
        payload["locationRestriction"] = location_restriction
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    if response.status_code != 200:
        print(f"エラー: {response.json()}")
        return []
    return response.json().get("places", [])


def get_place_by_id(place_id, api_key):
    url = f"https://places.googleapis.com/v1/places/{place_id}?languageCode=ja"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-FieldMask": DETAIL_FIELD_MASK,
        "X-Goog-Api-Key": api_key,
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"エラー: {response.json()}")
        return None
    return response.json()


def lookup_place_by_autocomplete(location_name, api_key, url_hint):
    """Text Search に出ない店を Autocomplete + Place Details で CID 照合する。"""
    if not url_hint or not url_hint.get("cid"):
        return None

    headers = {
        "Content-Type": "application/json",
        "X-Goog-FieldMask": AUTOCOMPLETE_FIELD_MASK,
        "X-Goog-Api-Key": api_key,
    }
    queries = [location_name]
    if "軽井沢" not in location_name:
        queries.append(f"{location_name} 軽井沢")

    seen_place_ids = set()
    for query in queries:
        response = requests.post(
            "https://places.googleapis.com/v1/places:autocomplete",
            headers=headers,
            data=json.dumps({
                "input": query,
                "languageCode": "ja",
                "includedRegionCodes": ["JP"],
            }),
        )
        if response.status_code != 200:
            continue
        for suggestion in response.json().get("suggestions", []):
            place_id = suggestion.get("placePrediction", {}).get("placeId")
            if not place_id or place_id in seen_place_ids:
                continue
            seen_place_ids.add(place_id)
            place = get_place_by_id(place_id, api_key)
            if place and place_matches_cid(place, url_hint["cid"]):
                return place
    return None


def build_stub_place_from_csv(location_name, cat_num, maps_url, url_hint):
    """API で解決できないが CSV URL がある店を最小情報で登録する。"""
    cid = url_hint.get("cid") if url_hint else None
    if not maps_url or not cid:
        return None

    cid_text = cid_to_storage_value(cid)
    return {
        "id": f"import-cid:{cid_text}",
        "location_name": {"text": location_name, "languageCode": "ja"},
        "primary_type": None,
        "primary_type_api": None,
        "url": maps_url,
        "location": None,
        "formattedAddress": None,
        "category": cat_num,
        "alias": location_name,
        "businessStatus": "CLOSED_TEMPORARILY",
        "mapsCid": cid_text,
        "importMeta": {
            "source": "csv_maps_url",
            "apiUnresolved": True,
        },
    }


def try_register_stub_from_csv(location_name, cat_num, maps_url, url_hint):
    stub = build_stub_place_from_csv(location_name, cat_num, maps_url, url_hint)
    if not stub:
        return None, None
    print(
        f"⚠️  「{location_name}」は Places API の検索結果に出ませんでした。"
        "CSVのURLをもとに臨時休業扱いで登録します。"
    )
    return stub, None


def resolve_place_from_maps_url(maps_url, location_name, api_key):
    """CSV の Maps URL から店舗候補を特定する。"""
    url_hint = parse_google_maps_url_hint(maps_url)
    if not url_hint:
        return None, url_hint

    if url_hint.get("place_id"):
        place = get_place_by_id(url_hint["place_id"], api_key)
        return place, url_hint

    if url_hint.get("cid"):
        for restriction in (JAPAN_LOCATION_RESTRICTION, None):
            places = search_places(
                location_name,
                api_key,
                location_restriction=restriction,
            )
            matched = [place for place in places if place_matches_cid(place, url_hint["cid"])]
            if len(matched) == 1:
                return matched[0], url_hint

        autocomplete_place = lookup_place_by_autocomplete(location_name, api_key, url_hint)
        if autocomplete_place:
            return autocomplete_place, url_hint

    return None, url_hint


def merge_places(*place_lists):
    merged = []
    seen_ids = set()
    for places in place_lists:
        for place in places:
            place_id = place.get("id")
            if place_id and place_id in seen_ids:
                continue
            if place_id:
                seen_ids.add(place_id)
            merged.append(place)
    return merged


def pick_auto_selected(places, url_hint=None):
    if url_hint:
        matched = [place for place in places if place_matches_url_hint(place, url_hint)]
        if len(matched) == 1:
            return matched[0]
        if url_hint.get("cid"):
            return None

    if len(places) == 1 and places[0].get("primaryType"):
        return places[0]

    return None


def print_place_option(index, place):
    display_name = (place.get("displayName") or {}).get("text", "N/A")
    primary_type = (place.get("primaryTypeDisplayName") or {}).get("text", "N/A")
    address = place.get("formattedAddress", "N/A")
    business_status = place.get("businessStatus", "N/A")
    print(f"{index:2d}. {display_name} ({primary_type})")
    print(f"    {address} [状態: {business_status}]")


def prompt_place_selection(location_name, places):
    print(f"\n--- {location_name} の検索結果 ---")
    for i, place in enumerate(places, start=1):
        print_place_option(i, place)

    print("-" * 100)
    print("s. スキップ（この場所を飛ばす）")
    print("q. キャンセル")

    while True:
        choice = input(f"選択してください (1-{len(places)}, s/q): ").strip().lower()

        if choice == "s":
            print("✓ スキップします")
            return None, "user_skipped"
        if choice == "q":
            print("✓ キャンセルしました")
            return None, None

        try:
            choice_num = int(choice)
            if 1 <= choice_num <= len(places):
                selected_place = places[choice_num - 1]
                selected_name = (selected_place.get("displayName") or {}).get("text", "N/A")
                print(f"✓ 選択されました: {selected_name}")
                return selected_place, None
            print(f"1から{len(places)}の数字を入力してください")
        except ValueError:
            print("有効な選択肢を入力してください")
        except KeyboardInterrupt:
            print("\n処理を中断します")
            return None, None


def build_place_info(selected_place, location_name, cat_num, url_hint=None):
    place_info = {
        "id": selected_place.get("id"),
        "location_name": selected_place.get("displayName"),
        "primary_type": selected_place.get("primaryTypeDisplayName"),
        "primary_type_api": selected_place.get("primaryType"),
        "url": selected_place.get("googleMapsUri"),
        "location": selected_place.get("location"),
        "formattedAddress": selected_place.get("formattedAddress"),
        "category": cat_num,
        "alias": location_name,
        "businessStatus": selected_place.get("businessStatus"),
    }
    if url_hint and url_hint.get("cid"):
        place_info["mapsCid"] = cid_to_storage_value(url_hint["cid"])
    return place_info


def get_place_id(location_name, cat_num, api_key, maps_url=None):
    """Google Places API から候補を取得し、利用者に選択させる。

    Returns:
        (place_info, skip_reason)
        skip_reason は user_skipped / not_found のときのみ設定する。
    """
    if location_name is None or pd.isna(location_name):
        print("スキップ: 店名が空です")
        return None, None
    text = str(location_name).strip()
    if not text or text.lower() == "nan":
        print("スキップ: 店名が空です")
        return None, None
    location_name = text
    url_hint = parse_google_maps_url_hint(maps_url)

    resolved_place, url_hint = resolve_place_from_maps_url(maps_url, location_name, api_key)
    if resolved_place:
        places = [resolved_place]
    else:
        places = search_places(
            location_name,
            api_key,
            location_restriction=JAPAN_LOCATION_RESTRICTION,
        )
        if url_hint and url_hint.get("cid"):
            global_places = search_places(location_name, api_key)
            places = merge_places(places, global_places)
            cid_matched = [place for place in places if place_matches_cid(place, url_hint["cid"])]
            if cid_matched:
                places = cid_matched
            else:
                return try_register_stub_from_csv(location_name, cat_num, maps_url, url_hint)
    places = sort_places(places, url_hint)

    if not places:
        if url_hint and url_hint.get("cid"):
            return try_register_stub_from_csv(location_name, cat_num, maps_url, url_hint)
        print("該当する場所が見つかりませんでした")
        return None, "not_found"

    selected_place = pick_auto_selected(places, url_hint)
    if selected_place:
        selected_name = (selected_place.get("displayName") or {}).get("text", "N/A")
        print(f"\n--- {location_name} の検索結果 ---")
        if url_hint and place_matches_url_hint(selected_place, url_hint):
            print(f"CSVのURLと一致する候補を自動選択します: {selected_name}")
        else:
            print(f"飲食店として明確な候補が1件のため、自動選択します: {selected_name}")
        print_place_option(1, selected_place)
        print("-" * 100)
    else:
        if len(places) == 1 and not places[0].get("primaryType"):
            print(
                f"\n注意: 「{location_name}」の検索結果は1件ですが、"
                "飲食店ではない可能性があります（地名など）。確認してください。"
            )
        selected_place, skip_reason = prompt_place_selection(location_name, places)
        if not selected_place:
            return None, skip_reason

    business_status = selected_place.get("businessStatus")
    if business_status in NON_OPERATIONAL_STATUSES:
        display_name = (selected_place.get("displayName") or {}).get("text", location_name)
        if business_status == "CLOSED_PERMANENTLY":
            print(f"⚠️  {display_name} は閉業済みですが、再検索を避けるため登録します")
        else:
            print(f"⚠️  {display_name} は臨時休業中ですが、再検索を避けるため登録します")

    return build_place_info(selected_place, location_name, cat_num, url_hint), None

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
skip_collection = db.csv_import_skips

# CSVファイルの定義
csv_files = [
    ('犬店内（インナーテラス含む）OK飲食店.csv', CAT_INSIDE_OK),
    ('New!! 犬外席OK、散歩途中テイクアウトOK飲食店.csv', CAT_TERRACE_OK),
    ('おれたちのモグモグリスト.csv', CAT_FAV_DOG_NG)
]

def parse_arguments():
    """コマンドライン引数を解析する"""
    parser = argparse.ArgumentParser(description='CSVファイルから場所情報を取得してMongoDBに登録する')
    parser.add_argument('--categories', '-c', nargs='+', type=int,
                       choices=[CAT_INSIDE_OK, CAT_TERRACE_OK, CAT_FAV_DOG_NG],
                       help='処理するカテゴリ番号を指定（1: 犬店内OK, 2: 犬外席OK, 3: お気に入り）')
    parser.add_argument('--list', '-l', action='store_true',
                       help='利用可能なカテゴリの一覧を表示')
    
    return parser.parse_args()

def get_csv_files_by_categories(specified_categories=None):
    """指定されたカテゴリに基づいてCSVファイルのリストを取得する"""
    if specified_categories is None:
        return csv_files
    
    # 指定されたカテゴリに基づいてCSVファイルをフィルタリング
    files_to_process = []
    for file_info in csv_files:
        if file_info[1] in specified_categories:
            files_to_process.append(file_info)
    
    return files_to_process

# Google APIキー
api_key = os.environ["GOOGLE_MAPS_API_KEY"]

# 出力用CSVファイルの設定
output_file = 'output.csv'

# 出力用CSVファイルの初期化（ヘッダーを書き込む）
with open(output_file, mode='w', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    writer.writerow(['location_name', 'comment', 'url', 'category'])

def check_location_exists(location_name, maps_url=None):
    """Check if a location_name exists in the MongoDB collection by checking both location_name.text and alias fields"""
    # First check location_name.text
    result = collection.find_one({"location_name.text": location_name})
    if result is not None:
        return True

    # If not found, check alias field (if it exists)
    result = collection.find_one({"alias": location_name})
    if result is not None:
        return True

    url_hint = parse_google_maps_url_hint(maps_url)
    if url_hint and url_hint.get("cid"):
        cid_text = cid_to_storage_value(url_hint["cid"])
        if collection.find_one({"mapsCid": cid_text}):
            return True

    return False


def check_import_skip(location_name, maps_url=None):
    """CSV import でスキップ済み・未発見として記録された店かどうか。"""
    if skip_collection.find_one({"alias": location_name}):
        return True

    url_hint = parse_google_maps_url_hint(maps_url)
    if url_hint and url_hint.get("cid"):
        if skip_collection.find_one({"mapsCid": cid_to_storage_value(url_hint["cid"])}):
            return True

    return False


def record_import_skip(location_name, maps_url, category, reason, comment="", source_csv=None):
    now = utc_now()
    url_hint = parse_google_maps_url_hint(maps_url)
    skip_collection.update_one(
        {"alias": location_name},
        {"$set": {
            "alias": location_name,
            "mapsUrl": maps_url,
            "mapsCid": cid_to_storage_value(url_hint.get("cid")) if url_hint else None,
            "category": category,
            "reason": reason,
            "comment": comment,
            "sourceCsv": source_csv,
            "updatedAt": now,
        }, "$setOnInsert": {
            "createdAt": now,
        }},
        upsert=True,
    )
    print(f"✓ {location_name} をスキップ記録しました ({reason})")

# コマンドライン引数を解析
args = parse_arguments()

# 利用可能なカテゴリ一覧を表示する場合
if args.list:
    print("利用可能なカテゴリ:")
    print(f"  {CAT_INSIDE_OK}: 犬店内（インナーテラス含む）OK飲食店")
    print(f"  {CAT_TERRACE_OK}: 犬外席OK、散歩途中テイクアウトOK飲食店")
    print(f"  {CAT_FAV_DOG_NG}: おれたちのモグモグリスト")
    exit(0)

# 処理するCSVファイルを決定
files_to_process = get_csv_files_by_categories(args.categories)

if not files_to_process:
    print("処理するカテゴリが指定されていません。すべてのカテゴリを処理します。")
    files_to_process = csv_files

print(f"処理対象カテゴリ数: {len(files_to_process)}件")

# 各CSVファイルを処理
for csv_file, category in files_to_process:
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
        raw_title = row['タイトル']
        if pd.isna(raw_title):
            print(f"行スキップ (index={index}): タイトルが空です")
            continue
        location_name = str(raw_title).strip()
        if not location_name:
            print(f"行スキップ (index={index}): タイトルが空です")
            continue

        raw_memo = row['メモ']
        comment = '' if pd.isna(raw_memo) else str(raw_memo)
        raw_url = row.get('URL')
        maps_url = None if pd.isna(raw_url) else str(raw_url).strip()

        # 使用例
        if check_location_exists(location_name, maps_url):
            print(f"{location_name}は既にデータベースに存在します")
            continue
        if check_import_skip(location_name, maps_url):
            print(f"{location_name}はスキップ済みのためAPI検索しません")
            continue

        place_info, skip_reason = get_place_id(location_name, category, api_key, maps_url=maps_url)
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
            now = utc_now()
            refresh_bucket = bucket_for_place_id(place_info["id"], get_bucket_count())
            searchable_texts = [
                str(v).strip() for v in [
                    (place_info.get("location_name") or {}).get("text"),
                    place_info.get("alias"),
                    place_info.get("formattedAddress"),
                    (place_info.get("primary_type") or {}).get("text"),
                    place_info.get("primary_type_api"),
                ] if isinstance(v, str) and v.strip()
            ]
            collection.update_one(
                {"id": place_info["id"]},
                {"$set": {
                    **place_info,
                    "refreshMeta.refreshBucket": refresh_bucket,
                    "refreshMeta.nextEligibleAt": now,
                    "refreshMeta.lastEnterpriseSyncAt": now,
                    "refreshMeta.lastEnterpriseStatus": "imported",
                    "enterpriseData.searchableTexts": list(dict.fromkeys(searchable_texts)),
                }},
                upsert=True
            )
            # CSVファイルにデータを書き込む
            with open(output_file, mode='a', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow([location_name, comment, place_info['url'], category])
        elif skip_reason:
            record_import_skip(
                location_name,
                maps_url,
                category,
                skip_reason,
                comment=comment,
                source_csv=csv_file,
            )
        else:
            print(f"Failed to retrieve place ID for {location_name}")

print("\n=== 全CSVファイルの処理が完了しました ===")

