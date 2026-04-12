#!/usr/bin/env python3
"""
place_info から primary_type.text の重複なし一覧を取得する（プリセットフィルタ用）。

環境変数（いずれか）:
  MONGODB_ADDRESS — 既存スクリプトと同様
  MONGODB_CONNECTION_STRING — backend と同様の接続 URI

使い方:
  python list_primary_type_texts.py
  python list_primary_type_texts.py --include-closed
  python list_primary_type_texts.py --json
"""
import argparse
import json
import os
import sys

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

DB_NAME = "places"
COLLECTION_NAME = "place_info"


def mongo_uri() -> str:
    uri = os.environ.get("MONGODB_ADDRESS") or os.environ.get(
        "MONGODB_CONNECTION_STRING"
    )
    if not uri:
        print(
            "エラー: MONGODB_ADDRESS または MONGODB_CONNECTION_STRING を設定してください。",
            file=sys.stderr,
        )
        sys.exit(1)
    return uri


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MongoDB の primary_type.text を一意に列挙する"
    )
    parser.add_argument(
        "--include-closed",
        action="store_true",
        help="businessStatus が CLOSED_PERMANENTLY のドキュメントも含める（既定は除外）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON 配列として標準出力に出す",
    )
    args = parser.parse_args()

    query = {}
    if not args.include_closed:
        query["businessStatus"] = {"$ne": "CLOSED_PERMANENTLY"}

    client = MongoClient(mongo_uri())
    try:
        coll = client[DB_NAME][COLLECTION_NAME]
        raw = coll.distinct("primary_type.text", query)
    finally:
        client.close()

    # None / 空文字はプリセットに不向きなので除外
    texts = sorted(
        t for t in raw if isinstance(t, str) and t.strip() != ""
    )

    if args.json:
        print(json.dumps(texts, ensure_ascii=False, indent=2))
    else:
        for t in texts:
            print(t)

    print(f"# 件数: {len(texts)}", file=sys.stderr)


if __name__ == "__main__":
    main()
