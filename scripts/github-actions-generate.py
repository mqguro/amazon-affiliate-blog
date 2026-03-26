#!/usr/bin/env python3
"""
GitHub Actions 用の記事生成・投稿スクリプト
毎日自動実行される
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from storage.database import init_database, get_session
from storage.models import Product, Article
from generation.article_generator import ArticleGenerator
from publishing.note_publisher import NotePublisherLite
from discovery.paapi import PAAPIClient

import logging

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """メイン処理"""
    try:
        # 設定を読み込む
        settings = Settings.from_env()
        logger.info("✓ 設定を読み込みました")

        # データベースを初期化
        init_database(settings.db_path)
        logger.info("✓ データベースを初期化しました")

        # セッションを取得
        session = get_session()

        # 商品を取得（優先順位：未使用 > 最も古い使用日 > すべて）
        logger.info("🔍 記事生成対象の商品を確認中...")

        # 1. 未使用の商品を探す
        products = (
            session.query(Product)
            .filter(Product.last_used_at == None)
            .limit(3)
            .all()
        )

        # 2. 未使用がなければ、最も古い使用日の商品を使う
        if not products:
            logger.info("📦 未使用商品がないため、最も古い使用日の商品を使用します")
            products = (
                session.query(Product)
                .order_by(Product.last_used_at.asc())
                .limit(3)
                .all()
            )

        # 3. 発見済み商品がない場合のみ、新しく発見
        if not products:
            logger.warning("⚠️ 登録済み商品がありません。新しい商品を発見します...")
            discover_products(settings, session)
            products = (
                session.query(Product)
                .filter(Product.last_used_at == None)
                .limit(3)
                .all()
            )

        if not products:
            logger.error("❌ 商品の取得に失敗しました")
            return False

        logger.info(f"✓ {len(products)}個の商品を取得しました")

        # 記事を生成
        logger.info("📝 記事を生成中...")
        article_generator = ArticleGenerator(settings)

        # ProductData に変換
        from storage.models import ProductData
        product_data_list = [
            ProductData(
                asin=p.asin,
                title=p.title,
                url=p.url,
                category=p.category,
                price=p.price,
                rating=p.rating,
                review_count=p.review_count,
                image_url=p.image_url,
            )
            for p in products
        ]

        article_data = article_generator.generate('review', product_data_list)
        logger.info(f"✓ 記事を生成しました: {article_data.title}")

        # 記事を保存
        from storage.models import Article
        db_article = Article(
            title=article_data.title,
            content=article_data.content,
            article_type=article_data.article_type,
            product_asins=article_data.product_asins,
            meta_description=article_data.meta_description,
            word_count=article_data.word_count,
            status="draft",
        )
        session.add(db_article)

        # 商品の last_used_at を更新
        from datetime import datetime
        for product in products:
            product.last_used_at = datetime.utcnow()

        session.commit()
        logger.info("✓ 記事をデータベースに保存しました")

        # note.com に投稿
        logger.info("🚀 note.com に投稿中...")
        try:
            publisher = NotePublisherLite(settings)
            published_url = publisher.publish(article_data)

            if published_url:
                db_article.published_url = published_url
                db_article.status = "published"
                session.commit()
                logger.info(f"✓ note.com に投稿しました: {published_url}")
            else:
                logger.warning("⚠️ note.com への投稿は失敗しましたが、記事は保存されています")
        except Exception as e:
            logger.warning(f"⚠️ note.com への投稿エラー: {e}")
            logger.info("💾 記事はドラフトとして保存されています")

        logger.info("=" * 50)
        logger.info("✅ 本日の処理が完了しました")
        logger.info("=" * 50)
        return True

    except Exception as e:
        logger.error(f"❌ エラーが発生しました: {e}", exc_info=True)
        return False

    finally:
        if 'session' in locals():
            session.close()


def discover_products(settings, session):
    """新しい商品を発見"""
    try:
        from discovery.categories import get_all_categories, CATEGORIES
        import random

        logger.info("🔍 新しい商品を発見中...")

        # ランダムなカテゴリを選択
        categories = get_all_categories()
        category = random.choice(categories)
        keywords = CATEGORIES[category]["keywords"]
        keyword = random.choice(keywords)

        # PA-API で商品を検索
        paapi_client = PAAPIClient(settings)
        products = paapi_client.search(keyword, category)

        if products:
            logger.info(f"✓ {category} - {keyword} から {len(products)}個の商品を発見")
        else:
            logger.warning(f"⚠️ {category} - {keyword} から商品が見つかりません")

    except Exception as e:
        logger.warning(f"⚠️ 商品発見エラー: {e}")


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
