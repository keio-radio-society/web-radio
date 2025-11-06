# Radio Web Front

USB シリアルで接続された無線機の制御と、PC マイク音声の配信を行う FastAPI アプリケーションの土台プロジェクトです。

## セットアップ
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 外部依存
- ALSA デバイスと `ffmpeg` が必要です。
- シリアルデバイスにアクセスするため、ユーザーを `dialout` グループへ追加してください。

## 開発サーバーの起動
```bash
uvicorn app.main:app --reload
```

## ディレクトリ構成（概要）
```
app/
  main.py         # FastAPI エントリポイント
  config.py       # 環境変数ベースの設定
  db.py           # SQLite エンジンとセッション管理
  models.py       # SQLModel テーブル定義
  repositories.py # DB アクセス層
  web/            # ルーティングとテンプレート
  serial/         # シリアル制御ロジック
  audio/          # 音声ストリーミングロジック
```
