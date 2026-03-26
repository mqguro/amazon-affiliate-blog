"""
APScheduler job definitions and setup
"""

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from pytz import timezone
from config.settings import Settings
from storage.database import get_session
from storage.models import Product, Article, RunLog
from discovery.paapi import PAAPIClient
from discovery.scraper import AmazonScraper
from discovery.categories import get_all_categories
import discovery.categories as cat_module
from generation.article_generator import ArticleGenerator
from publishing.note_publisher import NotePublisherLite
from datetime import datetime
import time
import logging
import random

logger = logging.getLogger(__name__)


def discovery_job(settings: Settings):
    """
    Scheduled job: Discover new products from Amazon.
    Runs at configured DISCOVERY_CRON time (default: 06:00 JST).
    """
    logger.info("=== Discovery Job Started ===")
    start_time = time.time()
    session = get_session()

    try:
        # Initialize product discoverer
        client = PAAPIClient(settings)

        # 70%の確率で「一人暮らし」、30%で他のカテゴリ
        if random.random() < 0.7:
            category = "一人暮らし"
        else:
            all_categories = get_all_categories()
            all_categories = [c for c in all_categories if c != "一人暮らし"]
            category = random.choice(all_categories)

        keywords = cat_module.get_category_keywords(category)
        keyword = random.choice(keywords)

        logger.info(f"Discovering products: category={category}, keyword={keyword}")

        # Search for products
        products = client.search(keyword, category=category, limit=5)

        # Save to database (skip duplicates)
        added_count = 0
        for product_data in products:
            existing = session.query(Product).filter_by(asin=product_data.asin).first()
            if not existing:
                db_product = Product(
                    asin=product_data.asin,
                    title=product_data.title,
                    url=product_data.url,
                    category=product_data.category,
                    price=product_data.price,
                    rating=product_data.rating,
                    review_count=product_data.review_count,
                    image_url=product_data.image_url,
                )
                session.add(db_product)
                added_count += 1

        session.commit()

        duration = time.time() - start_time
        run_log = RunLog(
            job_type="discovery",
            articles_processed=len(products),
            articles_succeeded=added_count,
            articles_failed=len(products) - added_count,
            duration_seconds=duration,
            status="success",
        )
        session.add(run_log)
        session.commit()

        logger.info(
            f"Discovery job completed: {added_count} new products in {duration:.1f}s"
        )

    except Exception as e:
        logger.error(f"Discovery job failed: {e}", exc_info=True)
        duration = time.time() - start_time
        run_log = RunLog(
            job_type="discovery",
            duration_seconds=duration,
            status="error",
            error_message=str(e),
        )
        session.add(run_log)
        session.commit()

    finally:
        session.close()


def generation_job(settings: Settings):
    """
    Scheduled job: Generate articles from recent products.
    Runs at configured GENERATION_CRON time (default: 08:00 JST).
    """
    logger.info("=== Generation Job Started ===")
    start_time = time.time()
    session = get_session()

    try:
        # Get products that haven't been used recently
        unused_products = (
            session.query(Product)
            .filter(
                (Product.last_used_at == None)
                | (Product.last_used_at < datetime.utcnow())
            )
            .order_by(Product.discovered_at.desc())
            .limit(settings.articles_per_run * 2)
            .all()
        )

        if not unused_products:
            logger.warning("No products available for article generation")
            return

        generator = ArticleGenerator(settings)
        generated_count = 0

        for i in range(min(settings.articles_per_run, len(unused_products))):
            try:
                # Select article type randomly
                article_type = random.choice(settings.article_types)

                # For comparison/ranking, use multiple products
                if article_type == "review":
                    products = [unused_products[i]]
                elif article_type == "comparison":
                    num_products = min(3, len(unused_products) - i)
                    products = unused_products[i : i + num_products]
                else:  # ranking
                    num_products = min(5, len(unused_products) - i)
                    products = unused_products[i : i + num_products]

                # Convert Product ORM to ProductData
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

                # Generate article with category-specific template
                category = products[0].category if products else None
                article_data = generator.generate(article_type, product_data_list, category)

                # Validate
                if not generator.validate_article(article_data):
                    logger.warning(f"Generated article validation failed: {article_data.title}")
                    continue

                # Save to database
                db_article = Article(
                    title=article_data.title,
                    content=article_data.content,
                    article_type=article_data.article_type,
                    product_asins=article_data.product_asins,
                    meta_description=article_data.meta_description,
                    word_count=article_data.word_count,
                    status="queued",
                )
                session.add(db_article)

                # Update product last_used_at
                for product in products:
                    product.last_used_at = datetime.utcnow()

                session.commit()
                generated_count += 1

                logger.info(
                    f"Generated article {generated_count}: '{article_data.title}' ({article_type})"
                )

            except Exception as e:
                logger.error(f"Failed to generate article: {e}", exc_info=True)
                continue

        duration = time.time() - start_time
        run_log = RunLog(
            job_type="generation",
            articles_processed=settings.articles_per_run,
            articles_succeeded=generated_count,
            articles_failed=settings.articles_per_run - generated_count,
            duration_seconds=duration,
            status="success" if generated_count > 0 else "partial",
        )
        session.add(run_log)
        session.commit()

        logger.info(f"Generation job completed: {generated_count} articles in {duration:.1f}s")

    except Exception as e:
        logger.error(f"Generation job failed: {e}", exc_info=True)
        duration = time.time() - start_time
        run_log = RunLog(
            job_type="generation",
            duration_seconds=duration,
            status="error",
            error_message=str(e),
        )
        session.add(run_log)
        session.commit()

    finally:
        session.close()


def publishing_job(settings: Settings):
    """
    Scheduled job: Publish queued articles to note.com.
    Runs at configured PUBLISHING_CRON times (default: 10:00, 14:00, 18:00 JST).
    """
    logger.info("=== Publishing Job Started ===")
    start_time = time.time()
    session = get_session()

    try:
        # Get queued articles (limit to 1 per execution to avoid spam)
        queued_articles = (
            session.query(Article)
            .filter_by(status="queued")
            .order_by(Article.generated_at.asc())
            .limit(1)
            .all()
        )

        if not queued_articles:
            logger.info("No articles queued for publishing")
            return

        publisher = NotePublisherLite(settings)
        published_count = 0

        for article_orm in queued_articles:
            try:
                # Convert Article ORM to ArticleData
                from storage.models import ArticleData
                article_data = ArticleData(
                    title=article_orm.title,
                    content=article_orm.content,
                    article_type=article_orm.article_type,
                    product_asins=article_orm.product_asins,
                    meta_description=article_orm.meta_description,
                    word_count=article_orm.word_count,
                )

                # Publish to note.com
                result = publisher.publish_sync(
                    article_data, as_draft=settings.note_default_draft
                )

                if result["success"]:
                    article_orm.status = "published"
                    article_orm.published_at = datetime.utcnow()
                    article_orm.published_url = result.get("url")
                    published_count += 1
                    logger.info(f"Published: {article_orm.title}")
                else:
                    article_orm.status = "failed"
                    article_orm.error_message = result.get("error")
                    logger.error(f"Publication failed: {article_orm.title}")

            except Exception as e:
                logger.error(f"Error publishing article: {e}", exc_info=True)
                article_orm.status = "failed"
                article_orm.error_message = str(e)

            session.commit()

        duration = time.time() - start_time
        run_log = RunLog(
            job_type="publishing",
            articles_processed=len(queued_articles),
            articles_succeeded=published_count,
            articles_failed=len(queued_articles) - published_count,
            duration_seconds=duration,
            status="success" if published_count > 0 else "partial",
        )
        session.add(run_log)
        session.commit()

        logger.info(f"Publishing job completed: {published_count} articles in {duration:.1f}s")

    except Exception as e:
        logger.error(f"Publishing job failed: {e}", exc_info=True)
        duration = time.time() - start_time
        run_log = RunLog(
            job_type="publishing",
            duration_seconds=duration,
            status="error",
            error_message=str(e),
        )
        session.add(run_log)
        session.commit()

    finally:
        session.close()


def setup_scheduler(settings: Settings) -> BlockingScheduler:
    """
    Setup and configure APScheduler with jobs.

    Args:
        settings: Settings object with cron configuration

    Returns:
        Configured BlockingScheduler instance
    """

    # Create scheduler with SQLite job store
    jobstores = {
        "default": SQLAlchemyJobStore(
            url=f"sqlite:///{settings.db_path}",
            tablename="apscheduler_jobs",
        )
    }

    scheduler = BlockingScheduler(
        jobstores=jobstores,
        timezone=timezone(settings.scheduler_timezone),
    )

    # Add jobs
    scheduler.add_job(
        discovery_job,
        "cron",
        args=[settings],
        cron_string=settings.discovery_cron,
        id="discovery_job",
        name="Product Discovery",
        replace_existing=True,
    )

    scheduler.add_job(
        generation_job,
        "cron",
        args=[settings],
        cron_string=settings.generation_cron,
        id="generation_job",
        name="Article Generation",
        replace_existing=True,
    )

    scheduler.add_job(
        publishing_job,
        "cron",
        args=[settings],
        cron_string=settings.publishing_cron,
        id="publishing_job",
        name="Article Publishing",
        replace_existing=True,
    )

    logger.info("Scheduler setup completed")
    logger.info(f"Discovery:  {settings.discovery_cron}")
    logger.info(f"Generation: {settings.generation_cron}")
    logger.info(f"Publishing: {settings.publishing_cron}")

    return scheduler
