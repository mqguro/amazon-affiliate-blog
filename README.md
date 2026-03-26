# Amazon Affiliate Auto-Publisher

全自動Amazonアフィリエイトブログ生成・投稿システム。Claude APIで記事を自動生成し、note.comに自動投稿します。

## 機能

- 🤖 **自動商品発見**: Amazon.co.jp から商品を自動検索
- ✍️ **AI記事生成**: Claude APIで日本語SEO最適化記事を自動作成
  - 単品レビュー
  - 比較記事
  - ランキング記事
- 📤 **自動投稿**: note.com へ自動投稿（Playwright ブラウザ自動化）
- ⏰ **スケジューラ**: APScheduler で定時実行
- 💾 **状態管理**: SQLite でアフィリエイトリンク・重複防止

## セットアップ

### 1. リポジトリクローン・環境構築

```bash
cd /Users/jh/amazon-affiliate-blog

# 依存パッケージをインストール
pip install -r requirements.txt

# Playwright Chromium ブラウザをダウンロード
playwright install
```

### 2. .env 設定

```bash
cp .env.example .env
# .env を編集してください
```

必須項目:
- `AMAZON_ASSOCIATE_ID`: Amazon アソシエイトID（例: `yourname-20`）
- `ANTHROPIC_API_KEY`: Claude API キー
- `NOTE_EMAIL`: note.com ログインメール
- `NOTE_PASSWORD`: note.com パスワード

オプション:
- `PAAPI_ACCESS_KEY`, `PAAPI_SECRET_KEY`: PA-API キー（未設定でもスクレーパーで動作）

### 3. データベース初期化

```bash
python main.py init
```

## 使い方

### 1. 商品発見

```bash
# ランダムな商品を発見
python main.py discover --category 家電 --limit 5

# 結果がデータベースに保存されます
```

### 2. 記事生成

```bash
# レビュー記事を生成
python main.py generate --type review

# 複数の ASIN を指定
python main.py generate --type comparison --asin B0XXXXX --asin B0YYYYY
```

### 3. 記事投稿

```bash
# 記事をnote.comに下書き投稿
python main.py publish --article-id 1 --draft

# 公開投稿
python main.py publish --article-id 1 --publish
```

### 4. ステータス確認

```bash
python main.py status
```

記事一覧表示:
```bash
python main.py list-articles
```

### 5. 自動スケジューラ起動

```bash
python main.py run-scheduler
```

スケジュール（.env で設定可能）:
- **06:00 JST**: 商品発見
- **08:00 JST**: 記事生成
- **10:00, 14:00, 18:00 JST**: note.com 投稿

### 6. Web ダッシュボード起動（iPhone 対応）

```bash
python web_app.py
```

**iPhone からアクセス**:
1. ターミナルで `python web_app.py` を実行
2. Mac の IP アドレスを確認: `ifconfig | grep "inet "`
3. iPhone のSafari で http://YOUR_MAC_IP:5000 にアクセス

例: http://192.168.1.100:5000

**ダッシュボード機能**:
- 📊 記事数・商品数リアルタイム表示
- ▶️ ワンクリック「商品発見」「記事生成」「投稿」
- 📝 記事一覧・詳細表示
- ⏱️ ジョブ実行履歴
- 📤 note.com 自動投稿状況

## ディレクトリ構成

```
amazon-affiliate-blog/
├── config/               # 設定管理
├── discovery/            # 商品検索 (PA-API / スクレーパー)
├── generation/           # 記事生成 (Claude API)
│   └── prompts/         # 記事用プロンプト
├── publishing/           # note.com 投稿 (Playwright)
├── storage/              # データベース (SQLAlchemy)
├── scheduler/            # スケジューラ (APScheduler)
├── data/                 # SQLite DB
├── logs/                 # ログファイル
└── main.py              # CLI エントリポイント
```

## 記事タイプ

### 1. レビュー（単品）
- 1つの商品についての詳細レビュー
- 特徴・メリット・デメリット・推奨ユーザー
- 2000-3000字

### 2. 比較記事
- 2-5 製品の比較表・詳細比較
- 選び方のポイント
- 2500-4000字

### 3. ランキング記事
- 複数製品のランキング形式
- 各ランキング理由・基準説明
- 2500-3500字

## 注意事項

### Amazon 利用規約
- PA-API 推奨（スクレーパーは開発用）
- 許可ない商品情報の大量スクレーピングは違反の可能性
- `robots.txt` と利用規約を遵守

### アフィリエイト
- 記事内のアフィリエイトリンクは自動生成
- Amazon Associate ID は `.env` で設定
- 不実表示・虚偽の記事生成は禁止

### API レート制限
- PA-API: 1 リクエスト/秒
- Claude API: 確認してください
- note.com: 連続投稿は1投稿/実行 に制限

## トラブルシューティング

### login failed (note.com)
- メール・パスワード確認
- 2段階認証が有効な場合はアプリパスワード使用

### Playwright installation error
```bash
playwright install chromium
```

### PA-API error
- API キーの確認
- 申請・承認状況確認（新規は3-5営業日）
- スクレーパーが自動で使用されます

### Claude API error
- API キーの確認
- 利用可能額の確認
- レート制限の確認

## 開発・テスト

単体テスト:
```bash
pytest
```

ログレベル指定:
```bash
LOG_LEVEL=DEBUG python main.py discover --category 家電
```

## ライセンス

MIT License

## 更新・メンテナンス

- 定期的に `.env` を確認
- 生成記事の品質監視
- note.com 規約変更への対応
- Claude モデルの最新版へのアップグレード検討

---

全自動で Amazonアフィリエイト収益を得られるシステムです。
ただし、ユーザーは最初 3-5 記事を確認してから自動投稿を有効にすることを強く推奨します。
