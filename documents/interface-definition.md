# インタフェース仕様書（MCP ツール群）

## 概要

本仕様書は、`documents/operation-scenario.md` で定義された業務シナリオと `documents/business-requirements.md` で定義された要件定義書に基づき、映画館窓口業務を実現する MCP（Model Context Protocol）ツール群のインタフェース仕様を定義したものです。

各 MCP ツールは JSON-RPC 2.0 形式で定義され、以下のような機能構成をサポートします:
- 映画一覧取得と推薦機能
- 上映スケジュール管理
- 座席空き状況確認
- 座席予約とキャンセル管理
- 予約情報照会

---

## 1. get_movie_list

### 概要

現在上映中の映画または指定日に上映予定の映画一覧を取得します。日付指定、テキスト検索、評価・人気度による推薦に対応しており、映画名の表記揺れも許容します。業務シナリオの「映画と上映時間枠を対話的に確定する」フェーズの初期段階で利用されます。

### ツール定義（JSON-RPC 形式）

```json
{
  "name": "get_movie_list",
  "description": "現在上映中または指定日の映画一覧を取得します。推薦ロジック（評価・ジャンル・人気度）に対応。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "date": {
        "type": "string",
        "format": "date",
        "description": "検索対象の日付（YYYY-MM-DD形式。省略時は本日を基準）"
      },
      "query": {
        "type": "string",
        "description": "映画名による検索テキスト（部分一致対応。映画名の揺れを許容）"
      },
      "limit": {
        "type": "integer",
        "description": "返却する最大件数（デフォルト: 20）"
      }
    },
    "required": []
  },
  "outputSchema": {
    "type": "object",
    "properties": {
      "movies": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "movie_id": { "type": "string", "description": "映画ID" },
            "title": { "type": "string", "description": "映画タイトル" },
            "genre": { "type": "string", "description": "ジャンル（例: SF, 恋愛, 冒険）" },
            "duration": { "type": "integer", "description": "上映時間（分）" },
            "rating": { "type": "number", "description": "評価スコア（1.0-5.0）" },
            "description": { "type": "string", "description": "映画の概要" },
            "release_date": { "type": "string", "format": "date", "description": "公開日（YYYY-MM-DD形式）" },
            "recommended": { "type": "boolean", "description": "推薦フラグ（評価・人気度が高い場合など）" }
          },
          "required": ["movie_id", "title", "rating"]
        }
      }
    },
    "required": ["movies"]
  }
}
```

### Request（サンプル）

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "get_movie_list",
  "params": {
    "date": "2026-02-20",
    "query": "スター",
    "limit": 10
  }
}
```

### Response（サンプル - 成功）

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "movies": [
      {
        "movie_id": "m001",
        "title": "スタームービー",
        "genre": "SF",
        "duration": 120,
        "rating": 4.5,
        "description": "宇宙冒険ストーリー",
        "release_date": "2026-02-01",
        "recommended": true
      },
      {
        "movie_id": "m002",
        "title": "スターダスト",
        "genre": "ファンタジー",
        "duration": 135,
        "rating": 4.2,
        "description": "星降る夜の恋物語",
        "release_date": "2026-01-15",
        "recommended": false
      }
    ]
  }
}
```

### Response（サンプル - エラー）

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32600,
    "message": "Invalid Request",
    "data": "Invalid date format"
  }
}
```

---

## 2. get_show_schedule

### 概要

指定した映画の上映スケジュールを日付単位で取得します。各スケジュール情報には上映日時、上映館、空席数などが含まれます。業務シナリオの「映画と上映時間枠を対話的に確定する」フェーズで、映画選択後の上映枠選択に使用されます。

### ツール定義（JSON-RPC 形式）

```json
{
  "name": "get_show_schedule",
  "description": "指定した映画の上映スケジュール一覧を取得します。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "movie_id": {
        "type": "string",
        "description": "対象の映画ID"
      },
      "date": {
        "type": "string",
        "format": "date",
        "description": "検索対象の日付（YYYY-MM-DD形式。省略時は本日以降7日間）"
      }
    },
    "required": ["movie_id"]
  },
  "outputSchema": {
    "type": "object",
    "properties": {
      "schedules": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "schedule_id": { "type": "string", "description": "上映スケジュールID" },
            "date": { "type": "string", "format": "date", "description": "上映日（YYYY-MM-DD形式）" },
            "start_time": { "type": "string", "description": "開始時刻（HH:MM形式）" },
            "end_time": { "type": "string", "description": "終了時刻（HH:MM形式）" },
            "theater_id": { "type": "string", "description": "上映館ID" },
            "theater_name": { "type": "string", "description": "上映館名" },
            "available_seats_count": { "type": "integer", "description": "空き座席数" },
            "total_seats_count": { "type": "integer", "description": "全座席数" }
          },
          "required": ["schedule_id", "date", "start_time", "theater_id", "available_seats_count"]
        }
      }
    },
    "required": ["schedules"]
  }
}
```

### Request（サンプル）

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "get_show_schedule",
  "params": {
    "movie_id": "m001",
    "date": "2026-02-20"
  }
}
```

### Response（サンプル - 成功）

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "schedules": [
      {
        "schedule_id": "s001",
        "date": "2026-02-20",
        "start_time": "10:00",
        "end_time": "12:00",
        "theater_id": "t01",
        "theater_name": "シアター1",
        "available_seats_count": 25,
        "total_seats_count": 100
      },
      {
        "schedule_id": "s002",
        "date": "2026-02-20",
        "start_time": "14:00",
        "end_time": "16:00",
        "theater_id": "t02",
        "theater_name": "シアター2",
        "available_seats_count": 42,
        "total_seats_count": 100
      }
    ]
  }
}
```

---

## 3. get_movie_popularity

### 概要

現在上映中の映画について、既予約座席数に基づき人気度ランキングを算出して返却します。指定日付または期間の集計に対応し、上位 N 件への絞り込みが可能です。業務シナリオでユーザーへの映画推薦や人気度表示に利用されます。

### ツール定義（JSON-RPC 形式）

```json
{
  "name": "get_movie_popularity",
  "description": "上映中映画の人気度ランキングを集計・算出して返却します。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "date": {
        "type": "string",
        "format": "date",
        "description": "集計対象日（YYYY-MM-DD形式。省略時は本日）"
      },
      "top_n": {
        "type": "integer",
        "description": "上位 N 件を返却（省略時は全件）"
      }
    },
    "required": []
  },
  "outputSchema": {
    "type": "object",
    "properties": {
      "popularity_ranking": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "movie_id": { "type": "string", "description": "映画ID" },
            "title": { "type": "string", "description": "映画タイトル" },
            "booked_seats_count": { "type": "integer", "description": "既予約座席数（入場者数推定）" },
            "popularity_rank": { "type": "integer", "description": "人気度順位" },
            "popularity_score": { "type": "number", "description": "人気度スコア（0-100）" }
          },
          "required": ["movie_id", "title", "booked_seats_count", "popularity_rank"]
        }
      }
    },
    "required": ["popularity_ranking"]
  }
}
```

### Request（サンプル）

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "get_movie_popularity",
  "params": {
    "date": "2026-02-20",
    "top_n": 5
  }
}
```

### Response（サンプル - 成功）

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "popularity_ranking": [
      {
        "movie_id": "m002",
        "title": "ヒット作',
        "booked_seats_count": 180,
        "popularity_rank": 1,
        "popularity_score": 95.5
      },
      {
        "movie_id": "m001",
        "title": "スタームービー",
        "booked_seats_count": 142,
        "popularity_rank": 2,
        "popularity_score": 87.3
      }
    ]
  }
}
```

---

## 4. get_seat_availability

### 概要

指定した上映回（schedule_id）の座席マップと各座席の状態を取得します。座席は行（A, B, C...）と列（1, 2, 3...）で識別され、各座席の予約状態（空き/予約済み/使用不可）を返却します。業務シナリオの「空いている座席を提示し、指定してもらう」フェーズで使用されます。

### ツール定義（JSON-RPC 形式）

```json
{
  "name": "get_seat_availability",
  "description": "指定上映回の座席一覧と各座席の状態を取得します。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "schedule_id": {
        "type": "string",
        "description": "対象の上映スケジュールID"
      }
    },
    "required": ["schedule_id"]
  },
  "outputSchema": {
    "type": "object",
    "properties": {
      "schedule_id": { "type": "string", "description": "上映スケジュールID" },
      "seats": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "seat_id": { "type": "string", "description": "座席ID（例: A1, B5）" },
            "row": { "type": "string", "description": "行（A, B, C...）" },
            "column": { "type": "integer", "description": "列（1, 2, 3...）" },
            "status": {
              "type": "string",
              "enum": ["available", "reserved", "blocked"],
              "description": "座席状態: available=空き, reserved=予約済み, blocked=使用不可"
            }
          },
          "required": ["seat_id", "row", "column", "status"]
        }
      },
      "available_count": { "type": "integer", "description": "空き座席総数" },
      "reserved_count": { "type": "integer", "description": "予約済み座席総数" }
    },
    "required": ["schedule_id", "seats", "available_count"]
  }
}
```

### Request（サンプル）

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "get_seat_availability",
  "params": {
    "schedule_id": "s001"
  }
}
```

### Response（サンプル - 成功）

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "result": {
    "schedule_id": "s001",
    "seats": [
      { "seat_id": "A1", "row": "A", "column": 1, "status": "available" },
      { "seat_id": "A2", "row": "A", "column": 2, "status": "reserved" },
      { "seat_id": "A3", "row": "A", "column": 3, "status": "available" },
      { "seat_id": "B1", "row": "B", "column": 1, "status": "available" },
      { "seat_id": "B2", "row": "B", "column": 2, "status": "blocked" }
    ],
    "available_count": 25,
    "reserved_count": 8
  }
}
```

---

## 5. reserve_seats

### 概要

ユーザーが選択した複数の座席に対し、原子性を保ちながら予約を実行します。処理フローは以下の通りです:
1. 入力検証（座席ID形式チェック、スケジュール存在確認）
2. 座席空きかどうかの確認
3. トランザクション / 楽観ロックによる競合制御
4. 予約レコード作成
5. 予約パスワードのハッシュ化と保存

競合（既に予約済みの座席を選択）が発生した場合は、明確なエラーを返却し再選択を促します。業務シナリオの「座席予約を確定する」フェーズで使用されます。

### ツール定義（JSON-RPC 形式）

```json
{
  "name": "reserve_seats",
  "description": "指定した座席の予約を実行します。競合時はエラーを返却。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "schedule_id": {
        "type": "string",
        "description": "上映スケジュールID"
      },
      "seats": {
        "type": "array",
        "items": { "type": "string" },
        "description": "予約座席IDのリスト（例: [\"A1\", \"A2\"]）"
      },
      "reservation_password": {
        "type": "string",
        "description": "予約確認用パスワード（プレーンテキスト、保存時にハッシュ化）"
      },
      "customer_name": {
        "type": "string",
        "description": "顧客名（オプション）"
      }
    },
    "required": ["schedule_id", "seats", "reservation_password"]
  },
  "outputSchema": {
    "type": "object",
    "properties": {
      "reservation_id": { "type": "string", "description": "予約ID" },
      "reservation_password_hash": { "type": "string", "description": "パスワードのハッシュ値（検証用）" },
      "reserved_seats": { "type": "array", "items": { "type": "string" }, "description": "確保された座席IDリスト" },
      "reservation_time": { "type": "string", "format": "date-time", "description": "予約完了時刻（ISO 8601形式）" },
      "status": {
        "type": "string",
        "enum": ["confirmed", "failed"],
        "description": "予約ステータス"
      }
    },
    "required": ["reservation_id", "reserved_seats", "reservation_time", "status"]
  }
}
```

### Request（サンプル - 成功ケース）

```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "method": "reserve_seats",
  "params": {
    "schedule_id": "s001",
    "seats": ["A1", "A3"],
    "reservation_password": "mypassword123",
    "customer_name": "田中太郎"
  }
}
```

### Response（サンプル - 成功）

```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "result": {
    "reservation_id": "r20260220001",
    "reservation_password_hash": "$2b$12$...",
    "reserved_seats": ["A1", "A3"],
    "reservation_time": "2026-02-20T12:34:56Z",
    "status": "confirmed"
  }
}
```

### Response（サンプル - 競合エラー）

```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "error": {
    "code": 409,
    "message": "Seat conflict",
    "data": {
      "conflicted_seats": ["A3"],
      "message": "Seat A3 is already reserved"
    }
  }
}
```

---

## 6. get_reservation_details

### 概要

予約 ID と予約パスワードを用いて取得した予約の詳細情報を返却します。パスワード検証に成功した場合のみ、映画情報、上映スケジュール、予約座席、予約時刻などの情報が返されます。パスワード検証失敗時はアクセス拒否エラーを返却し、存在しない予約 ID の場合は 404 エラーを返却します。

### ツール定義（JSON-RPC 形式）

```json
{
  "name": "get_reservation_details",
  "description": "予約 ID とパスワードで予約詳細を取得します。パスワード検証必須。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "reservation_id": {
        "type": "string",
        "description": "予約ID"
      },
      "reservation_password": {
        "type": "string",
        "description": "予約確認用パスワード（プレーンテキスト）"
      }
    },
    "required": ["reservation_id", "reservation_password"]
  },
  "outputSchema": {
    "type": "object",
    "properties": {
      "reservation_id": { "type": "string", "description": "予約ID" },
      "movie": {
        "type": "object",
        "properties": {
          "movie_id": { "type": "string", "description": "映画ID" },
          "title": { "type": "string", "description": "映画タイトル" }
        },
        "required": ["movie_id", "title"]
      },
      "schedule": {
        "type": "object",
        "properties": {
          "schedule_id": { "type": "string", "description": "上映スケジュールID" },
          "date": { "type": "string", "format": "date" },
          "start_time": { "type": "string", "description": "開始時刻（HH:MM形式）" },
          "theater_id": { "type": "string", "description": "上映館ID" },
          "theater_name": { "type": "string", "description": "上映館名" }
        },
        "required": ["schedule_id", "date", "start_time", "theater_id"]
      },
      "reserved_seats": { "type": "array", "items": { "type": "string" }, "description": "予約座席IDリスト" },
      "reservation_time": { "type": "string", "format": "date-time", "description": "予約完了時刻（ISO 8601形式）" },
      "status": { "type": "string", "description": "予約ステータス（confirmed, cancelled等）" }
    },
    "required": ["reservation_id", "movie", "schedule", "reserved_seats", "reservation_time", "status"]
  }
}
```

### Request（サンプル）

```json
{
  "jsonrpc": "2.0",
  "id": 6,
  "method": "get_reservation_details",
  "params": {
    "reservation_id": "r20260220001",
    "reservation_password": "mypassword123"
  }
}
```

### Response（サンプル - 成功）

```json
{
  "jsonrpc": "2.0",
  "id": 6,
  "result": {
    "reservation_id": "r20260220001",
    "movie": {
      "movie_id": "m001",
      "title": "スタームービー"
    },
    "schedule": {
      "schedule_id": "s001",
      "date": "2026-02-20",
      "start_time": "10:00",
      "theater_id": "t01",
      "theater_name": "シアター1"
    },
    "reserved_seats": ["A1", "A3"],
    "reservation_time": "2026-02-20T12:34:56Z",
    "status": "confirmed"
  }
}
```

### Response（サンプル - パスワード検証失敗）

```json
{
  "jsonrpc": "2.0",
  "id": 6,
  "error": {
    "code": 403,
    "message": "Forbidden",
    "data": "Invalid reservation password"
  }
}
```

---

## 付記

本インタフェース仕様書は MCP ツール群の基本実装に向けた仕様です。実装時には以下の点を考慮してください:

- **セキュリティ**: すべての通信は HTTPS 経由で行い、予約パスワードはハッシュ化 (bcrypt/argon2 等) して保存します。
- **並行制御**: 座席予約時の競合を防ぐために楽観ロック（バージョン番号）またはトランザクションを使用します。
- **ロギング**: 予約 PW をログに出力しないなど、機密情報保護に配慮します。
- **エラーハンドリング**: 各エラーケース（入力検証、座席競合、認証失敗等）を明示的に処理します。

