# daisuke-cafe-search

犬同伴可能な飲食店などの Place 情報を MongoDB に蓄積し、地図アプリから検索するためのプロジェクトです。

この README では、**店舗情報の取り込み・更新方法**と **Python スクリプトの使い分け**を説明します。

## 前提

リポジトリ直下に `.env` を置き、少なくとも次を設定します。

```env
MONGODB_ADDRESS=...
GOOGLE_MAPS_API_KEY=...
```

依存関係:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

PowerShell で日本語ログが崩れる場合:

```powershell
$env:PYTHONIOENCODING = "utf-8"
```

---

## 情報の流れ（概要）

| 目的 | 使うスクリプト | API のざっくり位置づけ |
|------|----------------|------------------------|
| Google Takeout CSV から新規登録 | `main.py` | Text Search / Autocomplete + 基本 Details（Pro 寄り） |
| Place ID を指定して1件登録 | `register_place_by_id.py` | Place Details |
| 営業状態・要約・営業時間などをまとめて更新 | `update_business_status.py` | Place Details **Enterprise + Atmosphere** |
| 営業状態（`businessStatus`）だけ更新 | `update_business_status_only.py` | Place Details **Pro** |
| 営業時間まわりを更新（レガシー寄り） | `update_opening_hours.py` | Enterprise 系（月次カウンタを `update_business_status.py` と共有） |

**新規追加は安価な登録 → 必要なら後から高コストの Enterprise 更新**、が基本です。

```
Takeout CSV
    │
    ▼
 main.py（基本情報を登録）
    │
    ▼
 update_business_status.py（Enterprise+Atmosphere で snapshot / 検索用テキスト等を付与）
```

`main.py` だけでは `generativeSummary` / `reviewSummary` などの Atmosphere 情報は入りません。検索用の充実したスナップショットが必要なら、続けて `update_business_status.py` を実行します。

---

## スクリプトの使い分け

### `main.py` — Takeout CSV からの新規取り込み

Google Maps のリストを Takeout でエクスポートした CSV を読み、未登録の店だけ Places API で解決して MongoDB に upsert します。

想定ファイル名（リポジトリ直下）:

| ファイル | カテゴリ |
|----------|----------|
| `犬店内（インナーテラス含む）OK飲食店.csv` | 1 |
| `New!! 犬外席OK、散歩途中テイクアウトOK飲食店.csv` | 2 |
| `おれたちのモグモグリスト.csv` | 3 |

想定カラム: `タイトル` / `メモ` / `URL`

```powershell
python main.py --list          # カテゴリ一覧
python main.py                 # 全 CSV
python main.py -c 2            # 外席 OK のみ
python main.py -c 1 2          # 複数指定
```

挙動の要点:

- 既存（名前 / alias / Maps CID）や `csv_import_skips` 済みはスキップ
- 登録時に `refreshMeta` と簡易 `enterpriseData.searchableTexts` をセット
- Enterprise の `latestSnapshot`（要約など）はここでは取らない

### `register_place_by_id.py` — Place ID 指定の単発登録

CSV 照合が難しいときなど、Place ID が分かっている店を直接登録します。

### `update_business_status.py` — Enterprise(+Atmosphere) 更新（推奨の本更新）

`businessStatus`・営業時間・`generativeSummary`・`reviewSummary` などを取得し、`enterpriseData.latestSnapshot` / `searchableTexts` を更新します。

無料枠（月おおよそ 1000 回）を超えないよう、月次ハードキャップ・1実行上限・クールダウン・バケット分割があります。

```powershell
python update_business_status.py --count-remaining
python update_business_status.py --dry-run -n 50
python update_business_status.py --per-run 50
python update_business_status.py --all-buckets --per-run 500
```

| オプション | 意味 |
|------------|------|
| `--per-run` / `-n` | 1実行あたりの最大 API 呼び出し数（上限。必ずその件数取るわけではない） |
| `--dry-run` | API を呼ばず候補だけ表示 |
| `--count-remaining` | 残候補を集計して終了（API・バケット進行なし） |
| `--all-buckets` | バケット分割を無視し、全候補を1実行で処理（月次枠と `--per-run` は有効。回転状態は進めない） |

主な環境変数（任意）:

- `MONTHLY_ENTERPRISE_CALL_BUDGET`（既定 1000）
- `ENTERPRISE_HARD_MONTHLY_CAP`（既定 1000）
- `PER_RUN_MAX_CALLS`（既定 50）
- `BUSINESS_STATUS_STALE_DAYS`（既定 30）
- `ENTERPRISE_COOLDOWN_HOURS`（既定 72）

#### バケットとは

店舗を `place_id` 由来で **30 グループ（0〜29）** に分け、通常実行では **次の1バケットだけ** を処理します。日次ジョブ想定で全件を少しずつ回し、無料枠と負荷を抑えるための仕分けです。

- `--per-run 50` でも、そのバケットの候補が 3 件なら 3 件で終わります
- 一気に消化したいときだけ `--all-buckets` を使います

### `update_business_status_only.py` — businessStatus のみ（Pro・安価）

Field mask を `businessStatus` に絞り、Place Details **Pro** で更新します。要約や Atmosphere は入りません。閉業判定の巡回など、回数を多く回したいときに使います。

Enterprise とは **別カウンタ・別予算** です。

```powershell
python update_business_status_only.py --count-remaining
python update_business_status_only.py --dry-run -n 50
python update_business_status_only.py --per-run 100
```

### `update_opening_hours.py` — 営業時間中心の更新

営業時間欠落・陳腐化向けの更新ジョブです。月次の Enterprise 利用カウンタを `update_business_status.py` と共有するため、同時に大きく回すと枠を食い合います。新規の「必要な情報一式」の更新は、基本的に `update_business_status.py` を優先してください。

### その他

- `enterprise_refresh_utils.py` — 予算・バケット・クールダウンなどの共通ユーティリティ（直接実行しない）
- `list_primary_type_texts.py` — primary type テキストの一覧用途
- `copy_favorite_list.py` — お気に入りリスト系の補助

---

## よくある作業手順

### A. Takeout で増えた店を取り込む

1. CSV を想定ファイル名でリポジトリ直下に置く  
2. `python main.py`（必要なら `-c`）  
3. `python update_business_status.py --count-remaining` で残候補を確認  
4. `python update_business_status.py --all-buckets --per-run <予算内の件数>` などで Enterprise 情報を付与  

### B. 既存店の営業状態だけ安く巡回する

```powershell
python update_business_status_only.py --count-remaining
python update_business_status_only.py --per-run 100
```

### C. 既存店の要約・スナップショット込みで更新する

```powershell
python update_business_status.py --count-remaining
python update_business_status.py --per-run 50
# または
python update_business_status.py --all-buckets --per-run 500
```

---

## フロント / バックエンド

- 地図 UI: [`place-map-app/README.md`](place-map-app/README.md)
- インフラ: [`infra/terraform/README.md`](infra/terraform/README.md)
