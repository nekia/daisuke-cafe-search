import os
import requests
import json
from dotenv import load_dotenv
from pymongo import MongoClient
import time

load_dotenv()

def get_opening_hours(place_id, api_key):
    """営業時間情報を取得する関数"""
    url = f"https://places.googleapis.com/v1/places/{place_id}"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-FieldMask": "currentOpeningHours",
        "X-Goog-Api-Key": api_key,
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            result = response.json()
            opening_hours = result.get('currentOpeningHours')
            if opening_hours:
                print(f"✓ 営業時間を取得しました: {place_id}")
                return opening_hours
            else:
                print(f"⚠ 営業時間情報がありません: {place_id}")
                return None
        else:
            print(f"❌ API呼び出しエラー: {place_id} - Status: {response.status_code}")
            print(f"Response: {response.text}")
            return None
    except Exception as e:
        print(f"❌ エラーが発生しました: {place_id} - {str(e)}")
        return None

def update_opening_hours_for_missing_records():
    """openingHoursを持たないレコードの営業時間を更新する"""
    
    # MongoDB接続
    client = MongoClient(os.environ["MONGODB_ADDRESS"])
    db = client.places
    collection = db.place_info
    
    # Google APIキー
    api_key = os.environ["GOOGLE_MAPS_API_KEY"]
    
    try:
        # openingHoursがNoneかつ、まだ「営業時間不明店舗」としてマーキングされていないレコードを検索
        query_condition = {
            "$and": [
                {
                    "$or": [
                        {"openingHours": {"$exists": False}},
                        {"openingHours": None}
                    ]
                },
                {
                    "$or": [
                        {"openingHoursStatus": {"$exists": False}},
                        {"openingHoursStatus": {"$ne": "営業時間不明店舗"}}
                    ]
                }
            ]
        }
        
        records_without_hours = collection.find(query_condition)
        
        # 全レコード数を確認
        all_records_count = collection.count_documents({})
        
        # レコード数を確認
        total_count = collection.count_documents(query_condition)
        
        print(f"📊 データベース統計:")
        print(f"   • 全レコード数: {all_records_count}件")
        print(f"   • 営業時間情報が不足しているレコード数: {total_count}件")
        print(f"   • 営業時間情報が存在するレコード数: {all_records_count - total_count}件")
        # total_count = 0;
        if total_count == 0:
            print("✓ すべてのレコードに営業時間情報が存在します")
            return
        
        print("=" * 60)
        
        updated_count = 0
        failed_count = 0
        
        for i, record in enumerate(records_without_hours, 1):
            place_id = record.get('id')
            location_name = record.get('location_name', {}).get('text', 'N/A')
            alias = record.get('alias', 'N/A')
            
            print(f"[{i}/{total_count}] 処理中: {location_name} (alias: {alias})")
            
            if not place_id:
                print(f"⚠ Place IDが見つかりません: {location_name}")
                failed_count += 1
                continue
            
            # 営業時間を取得
            opening_hours = get_opening_hours(place_id, api_key)
            # opening_hours = None
            if opening_hours:
                # 営業時間情報を取得できた場合
                result = collection.update_one(
                    {"_id": record["_id"]},
                    {"$set": {
                        "openingHours": opening_hours,
                        "openingHoursStatus": "available"
                    }}
                )
                
                if result.modified_count > 0:
                    updated_count += 1
                    print(f"✓ 営業時間更新完了: {location_name}")
                else:
                    print(f"⚠ 更新失敗: {location_name}")
                    failed_count += 1
            else:
                # 営業時間情報を取得できなかった場合は「営業時間不明店舗」としてマーキング
                result = collection.update_one(
                    {"_id": record["_id"]},
                    {"$set": {
                        "openingHours": None,
                        "openingHoursStatus": "営業時間不明店舗"
                    }}
                )
                
                if result.modified_count > 0:
                    updated_count += 1
                    print(f"✓ 営業時間不明店舗としてマーキング完了: {location_name}")
                else:
                    print(f"⚠ マーキング失敗: {location_name}")
                    failed_count += 1
            
            # API制限を考慮して少し待機
            time.sleep(0.1)
            
            print("-" * 40)
        
        print("=" * 60)
        print(f"📊 処理結果:")
        print(f"   • 総対象レコード数: {total_count}件")
        print(f"   • 更新成功: {updated_count}件")
        print(f"   • 更新失敗: {failed_count}件")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ 処理中にエラーが発生しました: {str(e)}")
    finally:
        client.close()

if __name__ == "__main__":
    print("🔄 営業時間情報の更新を開始します...")
    update_opening_hours_for_missing_records()
    print("✅ 処理が完了しました") 