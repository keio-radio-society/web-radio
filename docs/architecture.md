# アーキテクチャ概要

## 技術スタック
- **言語 / ランタイム**: Python 3.11（`venv` を利用）
- **Web フレームワーク**: FastAPI + Uvicorn
- **テンプレート**: Jinja2
- **永続化**: SQLite（SQLModel を利用した ORM とバリデーション）
- **シリアル通信**: pyserial
- **音声ストリーミング**: `ffmpeg` サブプロセスで ALSA デバイス入力を Ogg/Opus にエンコードし HTTP ストリームとして配信

## ディレクトリ構成（予定）
```
radio-web-front/
├── docs/
│   └── architecture.md
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py            # FastAPI エントリポイント
│   ├── dependencies.py    # DI 用の依存性定義
│   ├── config.py          # 設定モデルとロードロジック
│   ├── db.py              # SQLModel セッション管理
│   ├── models.py          # DB モデル
│   ├── repositories.py    # 設定永続化ロジック
│   ├── serial/
│   │   ├── __init__.py
│   │   ├── service.py     # シリアル制御サービス（async 対応）
│   │   └── schemas.py     # Web/API 用スキーマ
│   ├── audio/
│   │   ├── __init__.py
│   │   └── streamer.py    # ffmpeg ベースの音声取得/配信
│   ├── web/
│   │   ├── __init__.py
│   │   ├── routes.py      # ルーティングとビュー
│   │   ├── forms.py       # 入力検証
│   │   └── templates/
│   │       ├── base.html
│   │       ├── index.html
│   │       └── settings.html
│   └── static/
│       └── css/
└── tests/
    └── __init__.py
```

## 主なコンポーネント
### 1. 設定管理
- SQLModel で単一レコードの `AppSettings` を保持（シリアルポート、ボーレート、パリティ、ストップビット、オーディオデバイスなど）。
- FastAPI の依存性注入でリクエストごとに設定リポジトリを取得し、更新時は即時 DB 書き込み。
- UI 操作後、関連サービス（シリアル／音声）へリロードイベントを送出。

### 2. シリアルサービス
- `asyncio.Queue` を用いて送信要求を直列化。
- バックグラウンドタスクでポートをオープンし、設定変更時は安全にリオープン。
- エラーは Web UI へステータスフィードバック。

### 3. 音声ストリーマー
- `sounddevice` (PortAudio) でマイク入力を取得し、そのまま 16bit PCM を配信。
- WebSocket (`/audio/ws`) 経由でクライアントごとに生 PCM データを送信し、ブラウザ側で WebAudio API を用いて再生。
- サーバーは購読者ごとのキューを持ち、RawInputStream コールバックから届いたフレームを非同期に配布する。

### 4. ブラウザ→サーバー送信
- ブラウザで getUserMedia + AudioWorklet を使って PCM を収集し、WebSocket (`/audio/upload`) で 16bit PCM を送信。
- サーバーでは PlaybackService が PortAudio の RawOutputStream 経由で選択した出力デバイスへ再生、送信者は 1 クライアントに限定。
- 設定画面で入出力デバイスを個別に選択し、AppSettings に永続化する。

### 4. Web UI
- `/`：テキスト入力＋送信ボタン、送信結果の簡易ログ表示、オーディオプレーヤー（`<audio>` タグでストリーム再生）。
- `/settings`：シリアルポートとマイクデバイスの選択ドロップダウン、通信パラメータフォーム。送信後は即保存。
- 今後の拡張を見据え、テンプレートをベース＋コンテンツブロック構造で実装。

### 5. 背景タスクと監視
- 起動時に利用可能なシリアルポートとオーディオデバイスをスキャン。
- 定期的に再スキャンして UI に提供する API を用意（初期バージョンでは手動更新ボタンでも可）。
- サービスの状態は FastAPI の `lifespan` 管理で初期化と終了処理を集約。
