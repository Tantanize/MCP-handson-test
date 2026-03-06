# 詳細設計書

この設計書では、インタフェース仕様書にまとめた MCP ツールインタフェースをもとに、実装時の処理フローと細部の仕様を記述する。業務シナリオの各ステップをそのまま実行できるように設計しており、ビジネス要件から導かれるデータ保存・検索ルールも反映している。以下の共通前提に従う。

- 映画関連データ（`movies.json`、`schedules.json`、`seat_availability.json`）は Azure Blob Storage の `movies` コンテナ配下に格納し、Azure Functions の `@app.blob_input` / `@app.blob_output` バインディングを使用して読み書きする。バインディングの実装パターンは既存の `get_snippet` / `save_snippet` を参照（`connection="AzureWebJobsStorage"`、`path="{container}/{blob}"` 形式）。
- 予約情報は `reservations.jsonl` としてローカルファイルに追記し、`save_snippet` で Blob へも同期する。
- ローカル開発時は Azurite を使用し、`AzureWebJobsStorage` 接続文字列で Azurite のエンドポイントを指定する。
- リクエストパラメータに対しては最小限の形式チェックと必須キー検証を行う。異常があれば JSON‑RPC のエラーコード `-32602`（Invalid params）で応答し、型が不適切な場合や必須フィールド欠落は `-32600`（Invalid Request）にマッピングする。
- 予約データは 1 行ごとに JSON オブジェクトを並べた JSON Lines 形式で `src/data/reservations.jsonl` に保存する。Blob 保存と混在してもよいがローカルファイルに必ず記録する。

---

## 共通ユーティリティ

### JSON ファイルの読み書き
1. パスを受け取り `open(..., 'r', encoding='utf-8')` で読み込み、`json.load` で Python データに変換。
2. 書き込みは `open(..., 'w', encoding='utf-8')` + `json.dump`。`reservations.jsonl` への追記は `open(..., 'a')` を使用して改行区切り。
3. ファイルが存在しない場合は空の配列/オブジェクトを返す。

### バリデーション
1. `params` が指定された型/範囲を満たすかをチェック。文字列は空でないこと、日付は `\d{4}-\d{2}-\d{2}` 形式など。
2. 必須プロパティが欠けていればエラー。
3. バリデーションロジックは各ハンドラ関数の先頭で実行する。

### Blob 連携
映画関連データへのアクセスは Azure Functions の Blob バインディングを使用する。パターンは既存の `get_snippet` / `save_snippet` と同様で、以下の形式に従う。

#### 読み取り（`blob_input`）
```python
_MOVIES_BLOB_PATH = "movies/movies.json"

@app.blob_input(arg_name="movies_blob", connection="AzureWebJobsStorage", path=_MOVIES_BLOB_PATH)
def some_tool(movies_blob: func.InputStream, ...) -> str:
    data = json.loads(movies_blob.read().decode("utf-8")) if movies_blob else []
```
- `path` は `{コンテナ名}/{Blob名}` 形式。映画関連は `movies` コンテナを使用。
- `connection` は `AzureWebJobsStorage` を指定（ローカルでは Azurite に接続）。
- Blob が存在しない場合、`InputStream` は空になるためデフォルト値（空配列 `[]`）を返す。

#### 書き込み（`blob_output`）
```python
@app.blob_output(arg_name="file", connection="AzureWebJobsStorage", path="movies/reservations.jsonl")
def some_tool(file: func.Out[str], ...) -> str:
    file.set(json_content)
```
- 予約記録の Blob バックアップは `save_snippet` を使用することも可能。

---

## 各機能の処理フロー

以下は各ツールの実装における詳細な処理フロー。番号付きの主要手順に、さらに細かいサブステップを付けている。

### 1. get_movie_list
1. **入力検証**
   - `date` が渡されていれば `YYYY-MM-DD` 形式かチェック。
   - `query` は文字列であること、長すぎないことを確認。
   - `limit` がある場合は正の整数。
   - 検証失敗時は `-32602` で終了。
2. **データ読み込み**
   - `src/data/movies.json` を読み込み、リストを取得。
3. **日付フィルタリング**（`date` が指定された場合）
   - `schedules.json` を読み込み、指定日のスケジュールから上映される `movie_id` を抽出。
   - 映画リストをその ID で絞り込む。ID が存在しない場合は空リスト。
4. **クエリ検索**（`query` が指定された場合）
   - タイトルと説明を正規化（全半角・大小文字）して部分一致検索。
   - マッチしないものを除外。
5. **推薦・ソート**
   - `recommended` フラグや `rating` による優先順位を生成。
   - 例えば `(recommended?0:1, -rating)` でソート。
6. **制限適用**
   - `limit` が設定されていたら先頭から切り出す。
7. **レスポンス生成**
   - レスポンスボディを組み立てて `{"movies": [...]}` を返す。エラーが起きた場合は `{"error": {"code": <code>, "message": "..."}}`。

<!-- 続き: 他機能 -->

### 2. get_show_schedule
1. **入力検証**
   - `movie_id` は非空文字列。空文字列や未指定の場合は `-32602` を返す。
   - `date` は任意だが指定された場合は `YYYY-MM-DD` 形式（正規表現 `\d{4}-\d{2}-\d{2}` で検証）。不正な形式は `-32602` を返す。
2. **映画存在確認**
   - Azure Blob (`movies/movies.json`) を `@app.blob_input` バインディングで読み込み、`movie_id` に一致する映画を検索。
   - Blob が空または読み取り失敗の場合は空配列として扱う。
   - 存在しない場合は `-32602`（`"Movie not found: {movie_id}"`）を返す。
3. **スケジュール抽出**
   - Azure Blob (`movies/schedules.json`) を `@app.blob_input` バインディングで読み込み、`movie_id` が一致する行を集める。
   - Blob が空または読み取り失敗の場合は空配列として扱う。
   - 行数0の場合は空配列 `{"schedules": []}` を返却。
4. **日付フィルタ**
   - `date` が指定されていればその日に一致する行だけ残す。
   - 未指定なら本日（`datetime.now().date()`）から7日以内の行に絞る。
   - 日付パース失敗の行はスキップする。
5. **レスポンス返却**
   - 正常時は `{"schedules": [...]}` 形式で返す。各要素は `schedule_id`, `date`, `start_time`, `end_time`, `theater_id`, `theater_name`, `available_seats_count`, `total_seats_count` を含む。
   - エラー時は `{"error": {"code": <code>, "message": "..."}}` の JSON-RPC エラーオブジェクト。

### 3. get_movie_popularity
1. **入力検証**
   - `date` が指定されていれば `YYYY-MM-DD` 形式（正規表現 `\d{4}-\d{2}-\d{2}` で検証）。不正な形式は `-32602` を返す。
   - 未指定または空文字列の場合は本日（`datetime.now().date()`）をデフォルトとして使用。
   - `top_n` が指定されていれば正の整数であることを確認。0以下は `-32602` を返す。
2. **予約データ読み込み**
   - Azure Blob (`movies/reservations.jsonl`) を `@app.blob_input` バインディングで読み込む。
   - Blob が空または読み取り失敗の場合は空文字列として扱う。
   - 行単位で JSON パースし、`status == "confirmed"` の予約のみを対象とする。
3. **スケジュール・映画マッピング**
   - Azure Blob (`movies/schedules.json`) を `@app.blob_input` バインディングで読み込み、`schedule_id` → `{movie_id, date}` のマッピングを構築。
   - 指定日に該当するスケジュールの `schedule_id` のみを対象とする。
   - 予約の `schedule_id` が対象日のスケジュールに含まれる場合のみ、その `reservation_seats` の件数を `movie_id` ごとに累積。
4. **映画情報付与**
   - Azure Blob (`movies/movies.json`) を `@app.blob_input` バインディングで読み込み、`movie_id` → `title` のマップを構築。
   - 各映画に `title` を付与する。
5. **ランキング算出**
   - `booked_seats_count` の降順でソートし、`popularity_rank` を 1 から付番。
   - `popularity_score` は最大予約数を基準に 0〜100 のスケールで算出（`max_count` が 0 の場合は全て 0.0）。
6. **結果整形と制限**
   - `top_n` が指定されていればその件数まで切り詰め。
   - 予約データが空なら空配列を返す。
7. **レスポンス出力**
   - `{"popularity_ranking": [...]}` 形式。各要素は `movie_id`, `title`, `booked_seats_count`, `popularity_rank`, `popularity_score` を含む。
   - エラー時は `{"error": {"code": <code>, "message": "..."}}` の JSON-RPC エラーオブジェクト。

### 4. get_seat_availability
1. **入力検証**
   - `schedule_id` は非空文字列。空文字列や未指定の場合は `-32602`（`"schedule_id is required"`）を返す。
2. **データ検索**
   - Azure Blob (`movies/seat_availability.json`) を `@app.blob_input` バインディングで読み込む。
   - Blob が空または読み取り失敗の場合は空配列として扱う。
   - `schedule_id` に一致するエントリを検索。見つからない場合は `-32602`（`"Schedule not found: {schedule_id}"`）を返す。
3. **カウント処理**
   - 各座席の `status` を集計し、`available_count` / `reserved_count` を算出する。
   - Blob 上のカウント値（`available_count`, `reserved_count`）が存在する場合でも、実際の座席ステータスから再計算する。
4. **レスポンス出力**
   - `{"schedule_id": "...", "seats": [...], "available_count": N, "reserved_count": N}` 形式で返す。
   - 各座席オブジェクトは `seat_id`, `row`, `column`, `status` を含む。
   - エラー時は `{"error": {"code": <code>, "message": "..."}}` の JSON-RPC エラーオブジェクト。

### 5. reserve_seats
1. **入力検証**
   - `schedule_id` は非空文字列。未指定の場合は `-32602`。
   - `reservation_seats` は非空の配列で各要素が文字列。未指定・空配列・型不正は `-32602`。
   - `reservation_pw` は非空文字列。未指定は `-32602`。
   - `customer_name` は任意（文字列）。
   - 不備があれば `-32602` を返す。
2. **空き確認と競合制御**
   - Azure Blob (`movies/seat_availability.json`) を `@app.blob_input` バインディングで読み込み、`schedule_id` に一致するエントリを検索。
   - 見つからない場合は `-32602`（`"Schedule not found"`）を返す。
   - 指定された全座席が `available` であるか確認。`available` でない座席がある場合は `409`（`"Seat conflict"`）で競合座席リスト `conflicted_seats` を返す。
3. **予約レコード生成**
   - `reservation_id` は `"r" + datetime.now().strftime("%Y%m%d%H%M%S")` + 連番で一意に生成。
   - `reservation_pw` は `hashlib.sha256` でハッシュ化して保存（`reservation_pw_hash`）。
   - タイムスタンプは ISO 8601 形式（`datetime.now(timezone.utc).isoformat()`）。
   - レコードは `{reservation_id, schedule_id, reservation_seats, reservation_pw_hash, customer_name, reservation_time, status}` を含む。
4. **座席状態更新**
   - `seat_availability.json` 内の該当座席を `reserved` に更新。
   - `available_count` / `reserved_count` を再計算。
   - 更新後のデータを Azure Blob (`movies/seat_availability.json`) に `@app.blob_output` バインディングで書き戻す。
5. **予約データ永続化**
   - `src/data/reservations.jsonl` にレコードを JSON Lines 形式で追記。
   - 同時に Azure Blob (`movies/reservations.jsonl`) にも `@app.blob_output` バインディングで全内容を書き込む。
6. **レスポンス生成**
   - 成功時は `{"reservation_id", "reservation_pw_hash", "reservation_seats", "reservation_time", "status": "confirmed"}` を返す。
   - 競合時は `{"error": {"code": 409, "message": "Seat conflict", "data": {"conflicted_seats": [...]}}}` を返す。
   - その他エラー時は適切なエラーコード・メッセージを付加。

### 6. get_reservation_details
1. **入力検証**
   - `reservation_id` は非空文字列。未指定または空文字列の場合は `-32602`（`"reservation_id is required"`）を返す。
   - `reservation_pw` は非空文字列。未指定または空文字列の場合は `-32602`（`"reservation_pw is required"`）を返す。
2. **予約データ読み込み**
   - Azure Blob (`movies/reservations.jsonl`) を `@app.blob_input` バインディングで読み込む。
   - Blob が空または読み取り失敗の場合は空文字列として扱う。
   - 行単位で JSON パースし、`reservation_id` が一致するレコードを検索。
3. **存在確認**
   - 指定 ID の予約が見つからない場合は `404`（`"Reservation not found"`）を返す。
4. **パスワード検証**
   - 入力の `reservation_pw` を `hashlib.sha256` でハッシュ化し、保存済みの `reservation_pw_hash` と比較。
   - 不一致の場合は `403`（`"Forbidden"`, `"Invalid reservation password"`）を返す。
   - パスワードをログに出力しない。
5. **映画・スケジュール情報付与**
   - Azure Blob (`movies/schedules.json`) を `@app.blob_input` バインディングで読み込み、`schedule_id` に一致するスケジュールを取得。
   - Azure Blob (`movies/movies.json`) を `@app.blob_input` バインディングで読み込み、`movie_id` に一致する映画を取得。
   - スケジュールが見つからない場合は空オブジェクトをデフォルトとする。
6. **レスポンス出力**
   - 成功時は `{reservation_id, movie: {movie_id, title}, schedule: {schedule_id, date, start_time, theater_id, theater_name}, reservation_seats, reservation_time, status}` を返す。
   - エラー時は `{"error": {"code": <code>, "message": "...", "data": "..."}}` の JSON-RPC エラーオブジェクト。

---

## ファイル構成例
```text
src/data/movies.json          # 映画定義
src/data/schedules.json       # 上映スケジュール
src/data/seat_availability.json # 座席状態
src/data/reservations.jsonl   # 追加される予約履歴 (1行1件)
```

## バックアップ・同期
- 毎回ローカルファイルを更新する度に、同内容を `save_snippet` (container="reservations", blob_name="latest.jsonl") で Blob へ送信。
- 起動時や定期バッチで `get_snippet` から最新スナップショットを取り出し、ローカルファイルを復元可能にする。

---

この設計に基づき各 Azure Function ハンドラを実装する。入力の検証とファイルI/Oの共通処理はユーティリティモジュールとして抽象化すると保守性が向上する。