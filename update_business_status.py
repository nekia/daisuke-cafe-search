import os
import requests
import json
from dotenv import load_dotenv
from pymongo import MongoClient
import time

load_dotenv()

def get_business_status(place_id, api_key):
    """business_status情報を取得する関数"""
    url = f"https://places.googleapis.com/v1/places/{place_id}"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-FieldMask": "businessStatus",
        "X-Goog-Api-Key": api_key,
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            result = response.json()
            business_status = result.get('businessStatus')
            if business_status:
                print(f"✓ business_statusを取得しました: {place_id} - {business_status}")
                return business_status
            else:
                print(f"⚠ business_status情報がありません: {place_id}")
                return None
        else:
            print(f"❌ API呼び出しエラー: {place_id} - Status: {response.status_code}")
            print(f"Response: {response.text}")
            return None
    except Exception as e:
        print(f"❌ エラーが発生しました: {place_id} - {str(e)}")
        return None

def update_closed_business_status():
    """閉業店舗（CLOSED_PERMANENTLY）のbusiness_statusを更新する"""
    
    # MongoDB接続
    client = MongoClient(os.environ["MONGODB_ADDRESS"])
    db = client.places
    collection = db.place_info
    
    # Google APIキー
    api_key = os.environ["GOOGLE_MAPS_API_KEY"]
    
    # 閉業店舗リストを保存するためのリスト
    closed_businesses = []
    
    try:
        # businessStatusが未設定またはCLOSED_PERMANENTLYでないレコードを検索
        query_condition = {
            "$or": [
                {"businessStatus": {"$exists": False}},
                {"businessStatus": {"$ne": "CLOSED_PERMANENTLY"}}
            ]
        }
        
        records_to_check = collection.find(query_condition)
        
        # 全レコード数を確認
        all_records_count = collection.count_documents({})
        
        # レコード数を確認
        total_count = collection.count_documents(query_condition)
        
        print(f"📊 データベース統計:")
        print(f"   • 全レコード数: {all_records_count}件")
        print(f"   • business_status確認対象レコード数: {total_count}件")
        print(f"   • 既に閉業としてマーキング済みレコード数: {all_records_count - total_count}件")
        
        if total_count == 0:
            print("✓ すべてのレコードのbusiness_statusが確認済みです")
            return
        
        print("=" * 60)
        
        updated_count = 0
        closed_count = 0
        failed_count = 0
        
        for i, record in enumerate(records_to_check, 1):
            place_id = record.get('id')
            location_name = record.get('location_name', {}).get('text', 'N/A')
            alias = record.get('alias', 'N/A')
            
            # print(f"[{i}/{total_count}] 処理中: {location_name} (alias: {alias})")
            
            if not place_id:
                print(f"⚠ Place IDが見つかりません: {location_name}")
                failed_count += 1
                continue
            
            # テスト用: 最初の1件のみ処理
            # if i > 1:
            #     print(f"⚠ テスト用: 1件のみ処理するためスキップ: {location_name}")
            #     continue
            
            # business_statusを取得
            business_status = get_business_status(place_id, api_key)
            
            if business_status:
                # business_status情報を取得できた場合
                update_data = {
                    "businessStatus": business_status
                }
                
                # 閉業の場合はカウントを増やす
                if business_status == "CLOSED_PERMANENTLY":
                    closed_count += 1
                    print(f"✓ 閉業店舗を発見: {location_name}")
                    
                    # 閉業店舗の情報をリストに追加
                    address = record.get('address', '住所情報なし')
                    closed_businesses.append({
                        'name': location_name,
                        'address': address,
                        'alias': alias,
                        'place_id': place_id
                    })
                
                # MongoDB更新を実行
                result = collection.update_one(
                    {"_id": record["_id"]},
                    {"$set": update_data}
                )
                
                if result.modified_count > 0:
                    updated_count += 1
                    print(f"✓ business_status更新完了: {location_name}")
                else:
                    print(f"⚠ 更新失敗: {location_name}")
                    failed_count += 1
            else:
                print(f"⚠ business_status取得失敗: {location_name}")
                failed_count += 1
            
            # API制限を考慮して少し待機
            time.sleep(0.1)
            
            print("-" * 40)
        
        print("=" * 60)
        print(f"📊 処理結果:")
        print(f"   • 総対象レコード数: {total_count}件")
        print(f"   • 更新成功: {updated_count}件")
        print(f"   • 閉業店舗としてマーキング: {closed_count}件")
        print(f"   • 更新失敗: {failed_count}件")
        print("=" * 60)
        
        # 閉業店舗リストをファイルに保存
        if closed_businesses:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"closed_businesses_{timestamp}.json"
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(closed_businesses, f, ensure_ascii=False, indent=2)
            
            print(f"📄 閉業店舗リストを保存しました: {filename}")
            print(f"   • 保存件数: {len(closed_businesses)}件")
            
            # テキストファイルでも保存（読みやすい形式）
            txt_filename = f"closed_businesses_{timestamp}.txt"
            with open(txt_filename, 'w', encoding='utf-8') as f:
                f.write(f"閉業店舗一覧 ({len(closed_businesses)}件)\n")
                f.write("=" * 50 + "\n\n")
                for i, business in enumerate(closed_businesses, 1):
                    f.write(f"{i}. {business['name']}\n")
                    f.write(f"   住所: {business['address']}\n")
                    f.write(f"   エイリアス: {business['alias']}\n")
                    f.write(f"   Place ID: {business['place_id']}\n")
                    f.write("-" * 30 + "\n")
            
            print(f"📄 閉業店舗リスト（テキスト形式）を保存しました: {txt_filename}")
        else:
            print("📄 閉業店舗は見つかりませんでした")
        
    except Exception as e:
        print(f"❌ 処理中にエラーが発生しました: {str(e)}")
    finally:
        client.close()

if __name__ == "__main__":
    print("🔄 business_status情報の更新を開始します...")
    update_closed_business_status()
    print("✅ 処理が完了しました") 