#!/usr/bin/env python
"""
Fully automated Amazon affiliate blog article generation and publishing system
"""

import click
import logging
import sys
from pathlib import Path
from datetime import datetime
from config.settings import Settings
from storage.database import init_database, get_session
from storage.models import Product, Article, RunLog, ProductData, ArticleData
from discovery.paapi import PAAPIClient
from discovery.scraper import AmazonScraper
from discovery.categories import get_all_categories
from generation.article_generator import ArticleGenerator
from publishing.note_publisher import NotePublisherLite
from scheduler.jobs import setup_scheduler
import structlog

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

logger = logging.getLogger(__name__)


@click.group()
def cli():
    """Amazon Affiliate Blog Auto-Publisher CLI"""
    pass


@cli.command()
def init():
    """Initialize database and create tables"""
    try:
        # Load settings
        settings = Settings.from_env()

        # Initialize database
        init_database(settings.db_path)

        click.echo(f"✓ Database initialized at {settings.db_path}")
        click.echo(f"✓ Amazon Associate ID: {settings.amazon_associate_id}")
        click.echo(f"✓ Claude Model: {settings.claude_model}")
        click.echo(f"✓ note.com credentials: {'✓' if settings.has_note_credentials else '✗'}")
        click.echo(f"✓ PA-API credentials: {'✓' if settings.has_paapi_credentials else '✗ (using scraper)'}")

    except Exception as e:
        click.secho(f"✗ Initialization failed: {e}", fg="red")
        sys.exit(1)


@cli.command()
@click.option(
    "--category",
    type=click.Choice(get_all_categories()),
    default="家電",
    help="Product category to search"
)
@click.option("--limit", type=int, default=5, help="Number of products to discover")
def discover(category: str, limit: int):
    """Discover products from Amazon"""
    try:
        settings = Settings.from_env()
        init_database(settings.db_path)
        session = get_session()

        client = PAAPIClient(settings)
        from discovery import categories as cat_module
        keyword = cat_module.get_category_keywords(category)[0]

        click.echo(f"Searching: {category} > {keyword}")

        products = client.search(keyword, category=category, limit=limit)

        click.echo(f"\nFound {len(products)} products:\n")

        for i, product in enumerate(products, 1):
            click.echo(f"{i}. {product.title}")
            click.echo(f"   ASIN: {product.asin}")
            click.echo(f"   Price: ¥{product.price:,.0f}" if product.price else "   Price: N/A")
            click.echo(f"   Rating: {product.rating}/5.0 ({product.review_count} reviews)" if product.rating else "   Rating: N/A")
            click.echo()

    except Exception as e:
        click.secho(f"✗ Discovery failed: {e}", fg="red")
        sys.exit(1)


@cli.command()
@click.option(
    "--type",
    "article_type",
    type=click.Choice(["review", "comparison", "ranking"]),
    default="review",
    help="Article type to generate"
)
@click.option("--asin", multiple=True, help="Product ASIN(s)")
def generate(article_type: str, asin: tuple):
    """Generate article from products"""
    try:
        settings = Settings.from_env()
        init_database(settings.db_path)
        session = get_session()

        if not asin:
            # Generate from random products in database
            products_orm = session.query(Product).limit(3).all()
            if not products_orm:
                click.secho("✗ No products in database. Run 'discover' first.", fg="red")
                sys.exit(1)
        else:
            products_orm = session.query(Product).filter(Product.asin.in_(asin)).all()
            if not products_orm:
                click.secho(f"✗ Products not found: {asin}", fg="red")
                sys.exit(1)

        # Convert to ProductData
        products = [
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
            for p in products_orm
        ]

        generator = ArticleGenerator(settings)

        click.echo(f"Generating {article_type} article...")
        article = generator.generate(article_type, products)

        click.secho(f"✓ Generated: {article.title}", fg="green")
        click.echo(f"\nWord count: {article.word_count}")
        click.echo(f"Meta description: {article.meta_description}\n")
        click.echo("Content preview (first 500 chars):\n")
        click.echo(article.content[:500])
        click.echo("\n...")

        # Save to database
        db_article = Article(
            title=article.title,
            content=article.content,
            article_type=article_type,
            product_asins=article.product_asins,
            meta_description=article.meta_description,
            word_count=article.word_count,
            status="draft",
        )
        session.add(db_article)
        session.commit()

        click.echo(f"\n✓ Article saved to database (ID: {db_article.id})")

    except Exception as e:
        click.secho(f"✗ Generation failed: {e}", fg="red", err=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.option("--article-id", type=int, required=True, help="Article ID to publish")
@click.option(
    "--draft/--publish",
    default=True,
    help="Save as draft or publish immediately"
)
def publish(article_id: int, draft: bool):
    """Publish article to note.com"""
    try:
        settings = Settings.from_env()
        init_database(settings.db_path)
        session = get_session()

        article_orm = session.query(Article).filter_by(id=article_id).first()
        if not article_orm:
            click.secho(f"✗ Article not found: {article_id}", fg="red")
            sys.exit(1)

        article_data = ArticleData(
            title=article_orm.title,
            content=article_orm.content,
            article_type=article_orm.article_type,
            product_asins=article_orm.product_asins,
            meta_description=article_orm.meta_description,
            word_count=article_orm.word_count,
        )

        status_text = "draft" if draft else "published"
        click.echo(f"Publishing to note.com as {status_text}...")

        publisher = NotePublisherLite(settings)
        result = publisher.publish_sync(article_data, as_draft=draft)

        if result["success"]:
            article_orm.status = "published"
            article_orm.published_at = datetime.utcnow()
            article_orm.published_url = result.get("url")
            session.commit()

            click.secho(f"✓ Published: {article_orm.title}", fg="green")
            if result.get("url"):
                click.echo(f"  URL: {result['url']}")
        else:
            click.secho(f"✗ Publication failed: {result.get('error')}", fg="red")
            sys.exit(1)

    except Exception as e:
        click.secho(f"✗ Publish failed: {e}", fg="red", err=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


@cli.command()
def status():
    """Show system status and statistics"""
    try:
        settings = Settings.from_env()
        init_database(settings.db_path)
        session = get_session()

        products_count = session.query(Product).count()
        articles_count = session.query(Article).count()
        published_count = session.query(Article).filter_by(status="published").count()
        queued_count = session.query(Article).filter_by(status="queued").count()
        draft_count = session.query(Article).filter_by(status="draft").count()

        recent_runs = session.query(RunLog).order_by(RunLog.run_at.desc()).limit(5).all()

        click.echo("\n" + "="*50)
        click.echo("  AMAZON AFFILIATE BLOG - STATUS")
        click.echo("="*50)

        click.echo(f"\n📊 Database Statistics:")
        click.echo(f"  Products discovered: {products_count}")
        click.echo(f"  Articles generated: {articles_count}")
        click.echo(f"    ├─ Published: {published_count}")
        click.echo(f"    ├─ Queued: {queued_count}")
        click.echo(f"    └─ Draft: {draft_count}")

        click.echo(f"\n⚙️  Configuration:")
        click.echo(f"  Database: {settings.db_path}")
        click.echo(f"  Model: {settings.claude_model}")
        click.echo(f"  Timezone: {settings.scheduler_timezone}")

        click.echo(f"\n📅 Recent Job Runs:")
        for run in recent_runs:
            status_icon = "✓" if run.status == "success" else "✗"
            click.echo(f"  {status_icon} {run.job_type:12} {run.run_at.strftime('%Y-%m-%d %H:%M:%S')}")

        click.echo("\n" + "="*50 + "\n")

    except Exception as e:
        click.secho(f"✗ Status check failed: {e}", fg="red")
        sys.exit(1)


@cli.command()
def run_scheduler():
    """Start the scheduler (runs continuously)"""
    try:
        settings = Settings.from_env()
        init_database(settings.db_path)

        click.secho("🚀 Starting scheduler...", fg="green")
        click.echo(f"Timezone: {settings.scheduler_timezone}")
        click.echo(f"Discovery:  {settings.discovery_cron}")
        click.echo(f"Generation: {settings.generation_cron}")
        click.echo(f"Publishing: {settings.publishing_cron}")
        click.echo("\nPress Ctrl+C to stop\n")

        scheduler = setup_scheduler(settings)
        scheduler.start()

    except KeyboardInterrupt:
        click.echo("\n\n✓ Scheduler stopped")
    except Exception as e:
        click.secho(f"✗ Scheduler failed: {e}", fg="red", err=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


@cli.command()
def list_articles():
    """List all generated articles"""
    try:
        settings = Settings.from_env()
        init_database(settings.db_path)
        session = get_session()

        articles = session.query(Article).order_by(Article.generated_at.desc()).limit(20).all()

        click.echo("\n" + "="*80)
        click.echo(f"{'ID':<4} {'Status':<10} {'Type':<12} {'Title':<40} {'Generated':<20}")
        click.echo("="*80)

        for article in articles:
            status_icon = {
                "draft": "📝",
                "queued": "⏳",
                "published": "✓",
                "failed": "✗",
            }.get(article.status, "?")

            click.echo(
                f"{article.id:<4} {status_icon} {article.status:<8} "
                f"{article.article_type:<12} {article.title[:37]:<40} "
                f"{article.generated_at.strftime('%Y-%m-%d %H:%M'):<20}"
            )

        click.echo("="*80 + "\n")

    except Exception as e:
        click.secho(f"✗ List failed: {e}", fg="red")
        sys.exit(1)


if __name__ == "__main__":
    cli()
