# GitHub Actions セットアップガイド

このガイドでは、GitHub Actions を使って毎日自動的に記事を生成・投稿するようにセットアップします。

## 前提条件

- GitHub アカウント
- このリポジトリを GitHub にプッシュ済み

## セットアップ手順

### 1. GitHub リポジトリを作成

GitHub で新しいリポジトリを作成します（例：`amazon-affiliate-blog`）

### 2. ローカルリポジトリをリモートに接続

```bash
cd /Users/jh/amazon-affiliate-blog

git remote add origin https://github.com/YOUR_USERNAME/amazon-affiliate-blog.git
git branch -M main
git push -u origin main
```

### 3. GitHub リポジトリに Secrets を追加

リポジトリの **Settings** → **Secrets and variables** → **Actions** に以下を追加：

| シークレット名 | 値 | 説明 |
|---|---|---|
| `ANTHROPIC_API_KEY` | `sk-ant-...` | Claude API キー |
| `AMAZON_ASSOCIATE_ID` | `your-associate-20` | Amazon アソシエイト ID |
| `NOTE_EMAIL` | `your@email.com` | note.com のメールアドレス |
| `NOTE_PASSWORD` | `your-password` | note.com のパスワード |
| `SLACK_WEBHOOK` | `https://hooks.slack.com/...` | (オプション) Slack 通知 |

### 4. ワークフローの確認

`.github/workflows/daily-generation.yml` が以下の内容になっていることを確認：

- **毎日 6:00 JST** に自動実行（UTC では 21:00 前日）
- Python 3.11 で記事生成スクリプトを実行
- note.com に自動投稿
- エラー時は Slack に通知（オプション）

### 5. 手動でテスト実行

GitHub リポジトリの **Actions** タブから：

1. **毎日記事自動生成** ワークフローを選択
2. **Run workflow** → **Run workflow** をクリック

すぐに実行が開始されます。ログを確認して、エラーがないか確認してください。

## トラブルシューティング

### ワークフローが実行されない場合

```bash
# ローカルでスクリプトをテスト
python scripts/github-actions-generate.py
```

環境変数を設定してからテストしてください：

```bash
export ANTHROPIC_API_KEY="your-key"
export AMAZON_ASSOCIATE_ID="your-id"
export NOTE_EMAIL="your@email.com"
export NOTE_PASSWORD="your-password"
python scripts/github-actions-generate.py
```

### クレジット残高エラーが出る場合

Anthropic のアカウントにクレジットを追加してください：
https://console.anthropic.com/account/billing

### note.com への投稿に失敗する場合

- メールアドレス・パスワードが正しいか確認
- 2 段階認証が有効になっていないか確認

## ワークフローのカスタマイズ

### 実行時間を変更

`.github/workflows/daily-generation.yml` の `cron` を編集：

```yaml
schedule:
  - cron: '0 21 * * *'  # UTC 21:00（JST 6:00）
```

Cron 式：`分 時 日 月 曜日`

例：
- `0 21 * * *` = 毎日 UTC 21:00（JST 6:00）
- `0 9,18 * * *` = 毎日 9:00, 18:00 に実行
- `0 21 * * 1-5` = 平日のみ実行

### 実行頻度を変更

毎日ではなく週に 1 回にしたい場合：

```yaml
schedule:
  - cron: '0 21 * * 1'  # 毎週月曜日
```

## 成功時の通知

Slack 連携（オプション）

1. Slack ワークスペースで Incoming Webhook を作成
2. GitHub の Secrets に `SLACK_WEBHOOK` として追加
3. ワークフロー実行後、Slack に通知されます

## その他

詳細は以下を参照：
- [GitHub Actions ドキュメント](https://docs.github.com/actions)
- [Cron 式リファレンス](https://crontab.guru/)
