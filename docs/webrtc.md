# WebRTC オーディオ機能

本アプリケーションでは `aiortc` を利用してブラウザとの間で WebRTC セッションを確立し、Opus コーデックで高音質な双方向音声をやり取りします。ここでは仕組みとセットアップのポイントをまとめます。

## 全体構成

```
┌───────────────┐             ┌───────────────────────┐
│   Browser      │  SDP/ICE    │ FastAPI / aiortc       │
│  (getUserMedia)├────────────►│  /webrtc/session       │
│                │◄────────────┤                       │
│  Audio Element │   RTP(Opus) │ StreamerAudioTrack     │
│  WebRTC Peer   │◄────────────┤  (SoundDeviceStreamer) │
│  Connection    │             │                       │
│  Microphone    │────────────►│ PlaybackService (PortAudio)
└───────────────┘             └───────────────────────┘
```

- **サーバー → ブラウザ**: `SoundDeviceStreamer` が PortAudio から取得した 48kHz/16bit モノラル PCM を `StreamerAudioTrack` 経由で aiortc に渡し、Opus エンコードを伴う RTP ストリームとしてブラウザへ送ります。
- **ブラウザ → サーバー**: ブラウザのマイクを getUserMedia で取得し、同じ WebRTC ピア接続に `RTCRtpSender` として追加。サーバー側では `PlaybackService.handle_frame` が受信フレームを downmix → PortAudio RawOutputStream へ出力します。
- **シグナリング**: `/webrtc/session` エンドポイントで SDP Offer/Answer（JSON）を交換します。接続開始・マイク送信開始・停止時は毎回 `negotiate()` を呼び、最新 SDP を同期させます。

## 依存パッケージ

- `aiortc` 1.9.0 (WebRTC 実装)
- `av` 12.0.0 (FFmpeg バインディング)
- `numpy` 2.1.2 (PCM 配列処理)
- `sounddevice` 0.4.7 + PortAudio ライブラリ

PortAudio 未導入の環境では `sudo apt install python3-sounddevice portaudio19-dev` などで導入してください。

## ブラウザ要件

- HTTPS か `localhost` でアクセスしてください（マイク権限の制約）。
- Audio/Video の自動再生ブロックを避けるため、ユーザー操作（再生開始ボタン）をトリガーにしています。
- 音声再生は `<audio>` 要素、送信は getUserMedia + `RTCPeerConnection`。追加プラグイン不要です。

## 設定画面

`/settings` で以下を選択し、SQLite (`AppSettings`) に保存します。

- シリアルポート・通信パラメータ
- **マイク入力デバイス**（サーバー側 PortAudio Input）
- **スピーカー出力デバイス**（PortAudio Output）

保存後、自動的に `SoundDeviceStreamer` / `PlaybackService` に適用されます。変更後はブラウザ側で再接続してください。

## 開発・テスト

1. `. .venv/bin/activate && pip install -r requirements.txt`
2. `uvicorn app.main:app --reload`
3. ブラウザで `http://localhost:8000/` を開き、再生開始→送信開始ボタンを押す。
4. `pytest` でシグナリングや設定永続化を確認済みです（音声品質の自動テストは含みません）。

## トラブルシューティング

- **音が再生されない**: ブラウザコンソールで `NotAllowedError` が出ていないか確認し、マイク/スピーカー許可を付与。HTTPS で再アクセス。
- **音質が悪い / 遅延**: PortAudio デバイスのサンプルレートを 48kHz に合わせる、`PlaybackService` の `latency`・`block_size` を環境に合わせて調整。
- **送信ができない**: 同時送信は 1 クライアントのみです。誰かが送信中の場合はエラー表示が出ます。送信停止ボタンで解放してください。

## 今後の拡張案

- DTLS-SRTP 用証明書の永続化/管理。
- 複数ブラウザからの同時送受信やサーバー側のミキシング。
- 音量メーターやネットワーク品質指標の可視化。
