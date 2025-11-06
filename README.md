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

音声ストリームは WebSocket (`/audio/ws`) で 16bit PCM を配信し、ブラウザ側の WebAudio API で再生します。PortAudio (`libportaudio`) がインストールされていない場合、`sounddevice` が初期化に失敗し再生できません。Ubuntu では `sudo apt install python3-sounddevice portaudio19-dev` などで導入してください。

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
