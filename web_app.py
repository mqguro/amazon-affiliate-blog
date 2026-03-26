#!/usr/bin/env python
"""
Flask Web Dashboard for Amazon Affiliate Blog
iPhone アクセス対応
"""

from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
from config.settings import Settings
from storage.database import init_database, get_session
from storage.models import Product, Article, RunLog, ProductData, ArticleData
from discovery.paapi import PAAPIClient
from discovery.categories import get_all_categories
import discovery.categories as cat_module
from generation.article_generator import ArticleGenerator
from generation.product_finder import ProductFinder
from publishing.note_publisher import NotePublisherLite
from datetime import datetime, timedelta
import threading
import logging
import random
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

# Global settings
settings = None


def init_app():
    """Initialize app settings and database"""
    global settings
    settings = Settings.from_env()
    init_database(settings.db_path)
    logger.info("Web app initialized")


@app.route('/')
def dashboard():
    """Main dashboard page"""
    session = get_session()

    try:
        # Get statistics
        products_count = session.query(Product).count()
        articles_count = session.query(Article).count()
        published_count = session.query(Article).filter_by(status="published").count()
        queued_count = session.query(Article).filter_by(status="queued").count()
        draft_count = session.query(Article).filter_by(status="draft").count()

        # Get recent runs
        recent_runs = (
            session.query(RunLog).order_by(RunLog.run_at.desc()).limit(10).all()
        )

        # Get recent articles
        recent_articles = (
            session.query(Article).order_by(Article.generated_at.desc()).limit(5).all()
        )

        stats = {
            "products": products_count,
            "articles": articles_count,
            "published": published_count,
            "queued": queued_count,
            "draft": draft_count,
        }

        runs_data = [
            {
                "id": r.id,
                "job_type": r.job_type,
                "run_at": r.run_at.strftime("%Y-%m-%d %H:%M:%S"),
                "status": r.status,
                "articles_processed": r.articles_processed,
                "articles_succeeded": r.articles_succeeded,
            }
            for r in recent_runs
        ]

        articles_data = [
            {
                "id": a.id,
                "title": a.title[:50],
                "status": a.status,
                "type": a.article_type,
                "generated_at": a.generated_at.strftime("%Y-%m-%d %H:%M"),
            }
            for a in recent_articles
        ]

        return render_template(
            "index.html",
            stats=stats,
            runs=runs_data,
            articles=articles_data,
        )

    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return render_template(
            "error.html", error=str(e)
        ), 500
    finally:
        session.close()


@app.route('/api/products', methods=['POST'])
def api_add_product():
    """商品を手動追加"""
    session = get_session()
    try:
        data = request.json

        # 必須フィールド確認
        if not data.get('asin') or not data.get('title'):
            return jsonify({"error": "ASIN と title は必須"}), 400

        # 既存商品をチェック
        existing = session.query(Product).filter_by(asin=data['asin']).first()
        if existing:
            return jsonify({"error": f"商品は既に登録されています: {existing.title}"}), 400

        # 新規商品を作成
        product = Product(
            asin=data['asin'],
            title=data['title'],
            url=data.get('url', data['asin']),
            category=data.get('category', 'その他'),
            price=data.get('price'),
            rating=data.get('rating'),
            review_count=data.get('review_count'),
            image_url=data.get('image_url'),
        )

        session.add(product)
        session.commit()

        logger.info(f"✓ 商品を追加しました: {product.title} ({product.asin})")

        return jsonify({
            "status": "success",
            "message": f"商品を追加しました: {product.title}",
            "product": {
                "asin": product.asin,
                "title": product.title,
                "category": product.category,
            }
        })

    except Exception as e:
        logger.error(f"Product add error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


@app.route('/api/products', methods=['GET'])
def api_products_list():
    """登録済みの商品一覧"""
    session = get_session()
    try:
        products = session.query(Product).order_by(Product.discovered_at.desc()).all()

        products_data = [
            {
                "asin": p.asin,
                "title": p.title,
                "category": p.category,
                "price": p.price,
                "rating": p.rating,
                "discovered_at": p.discovered_at.isoformat() if p.discovered_at else None,
                "last_used_at": p.last_used_at.isoformat() if p.last_used_at else None,
            }
            for p in products
        ]

        return jsonify({
            "products": products_data,
            "total": len(products),
        })

    except Exception as e:
        logger.error(f"Products list error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


@app.route('/api/articles')
def api_articles():
    """Get all articles as JSON"""
    session = get_session()

    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status_filter = request.args.get('status', None)

        query = session.query(Article).order_by(Article.generated_at.desc())

        if status_filter:
            query = query.filter_by(status=status_filter)

        total = query.count()
        articles = query.offset((page - 1) * per_page).limit(per_page).all()

        articles_data = [
            {
                "id": a.id,
                "title": a.title,
                "status": a.status,
                "type": a.article_type,
                "generated_at": a.generated_at.isoformat(),
                "published_at": a.published_at.isoformat() if a.published_at else None,
                "word_count": a.word_count,
            }
            for a in articles
        ]

        return jsonify(
            {
                "articles": articles_data,
                "total": total,
                "page": page,
                "per_page": per_page,
            }
        )

    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


@app.route('/api/articles/<int:article_id>')
def api_article_detail(article_id: int):
    """Get article detail"""
    session = get_session()

    try:
        article = session.query(Article).filter_by(id=article_id).first()

        if not article:
            return jsonify({"error": "Article not found"}), 404

        return jsonify(
            {
                "id": article.id,
                "title": article.title,
                "content": article.content,
                "status": article.status,
                "type": article.article_type,
                "product_asins": article.product_asins,
                "meta_description": article.meta_description,
                "word_count": article.word_count,
                "generated_at": article.generated_at.isoformat(),
                "published_at": article.published_at.isoformat()
                if article.published_at
                else None,
                "published_url": article.published_url,
            }
        )

    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


@app.route('/articles')
def articles():
    """Articles list page"""
    session = get_session()

    try:
        status_filter = request.args.get('status', None)
        query = session.query(Article).order_by(Article.generated_at.desc())

        if status_filter:
            query = query.filter_by(status=status_filter)

        articles = query.limit(50).all()

        articles_data = [
            {
                "id": a.id,
                "title": a.title,
                "status": a.status,
                "type": a.article_type,
                "generated_at": a.generated_at,
                "word_count": a.word_count,
            }
            for a in articles
        ]

        return render_template(
            "articles.html", articles=articles_data, status_filter=status_filter
        )

    except Exception as e:
        logger.error(f"Articles page error: {e}")
        return render_template("error.html", error=str(e)), 500
    finally:
        session.close()


@app.route('/articles/<int:article_id>')
def article_detail(article_id: int):
    """Article detail page"""
    session = get_session()

    try:
        article = session.query(Article).filter_by(id=article_id).first()

        if not article:
            return render_template("error.html", error="Article not found"), 404

        return render_template(
            "article_detail.html",
            article={
                "id": article.id,
                "title": article.title,
                "content": article.content,
                "status": article.status,
                "type": article.article_type,
                "product_asins": article.product_asins,
                "word_count": article.word_count,
                "generated_at": article.generated_at,
                "published_url": article.published_url,
            },
        )

    except Exception as e:
        logger.error(f"Article detail error: {e}")
        return render_template("error.html", error=str(e)), 500
    finally:
        session.close()


@app.route('/api/generate-single-review', methods=['POST'])
def api_generate_single_review():
    """Generate a single product review article"""
    try:
        data = request.json
        asin = data.get('asin')

        if not asin:
            return jsonify({"error": "ASIN is required"}), 400

        # Create RunLog entry
        session = get_session()
        run_log = RunLog(
            job_type="generation",
            status="in_progress",
        )
        session.add(run_log)
        session.commit()
        job_id = run_log.id
        session.close()

        # Run in thread to avoid blocking
        def generate_task():
            session = get_session()  # Get new session for thread
            try:
                # Get product from database
                product_orm = session.query(Product).filter_by(asin=asin).first()

                if not product_orm:
                    logger.warning(f"Product not found: {asin}")
                    run_log = session.query(RunLog).filter_by(id=job_id).first()
                    if run_log:
                        run_log.status = "error"
                        run_log.error_message = f"商品が見つかりません: {asin}"
                        session.commit()
                    return

                generator = ArticleGenerator(settings)

                # Convert to ProductData
                product_data = ProductData(
                    asin=product_orm.asin,
                    title=product_orm.title,
                    url=product_orm.url,
                    category=product_orm.category,
                    price=product_orm.price,
                    rating=product_orm.rating,
                    review_count=product_orm.review_count,
                    image_url=product_orm.image_url,
                )

                # Generate single product review
                article_data = generator.generate('single_review', [product_data], product_orm.category)

                if generator.validate_article(article_data):
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

                    # Update product usage
                    product_orm.last_used_at = datetime.utcnow()

                    session.commit()

                    # Update RunLog
                    run_log = session.query(RunLog).filter_by(id=job_id).first()
                    if run_log:
                        run_log.status = "success"
                        run_log.articles_succeeded = 1
                        session.commit()

                    logger.info(f"Generated single review for: {article_data.title}")
                else:
                    run_log = session.query(RunLog).filter_by(id=job_id).first()
                    if run_log:
                        run_log.status = "error"
                        run_log.error_message = "記事の検証に失敗しました"
                        session.commit()

            except Exception as e:
                logger.error(f"Generation error: {e}", exc_info=True)
                run_log = session.query(RunLog).filter_by(id=job_id).first()
                if run_log:
                    run_log.status = "error"
                    run_log.error_message = str(e)
                    session.commit()
            finally:
                session.close()

        thread = threading.Thread(target=generate_task)
        thread.daemon = True
        thread.start()

        return jsonify(
            {"status": "generating", "message": "単品レビュー記事を生成中...", "job_id": job_id}
        )

    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/generate-product-by-asin', methods=['POST'])
def api_generate_product_by_asin():
    """Generate article for a specific product by ASIN (deprecated, use /api/generate-single-review)"""
    # Redirect to new endpoint
    return api_generate_single_review()


@app.route('/api/generate', methods=['POST'])
def api_generate():
    """Trigger article generation"""
    try:
        article_type = request.json.get('type', 'review')

        # Create RunLog entry for this generation job
        session = get_session()
        run_log = RunLog(
            job_type="generation",
            status="in_progress",
        )
        session.add(run_log)
        session.commit()
        job_id = run_log.id
        session.close()

        # Run in thread to avoid blocking
        def generate_task():
            session = get_session()  # Get new session for thread
            try:
                products_orm = (
                    session.query(Product)
                    .filter(Product.last_used_at == None)
                    .limit(5)
                    .all()
                )

                if not products_orm:
                    logger.warning("No products available for generation")
                    run_log = session.query(RunLog).filter_by(id=job_id).first()
                    if run_log:
                        run_log.status = "error"
                        run_log.error_message = "利用可能な商品がありません"
                        session.commit()
                    return

                generator = ArticleGenerator(settings)

                # Select products based on type
                if article_type == "review":
                    # Review now generates 3-product comparison (cost/std/prem style)
                    products = products_orm[:3]
                elif article_type == "single_review":
                    # Single review for one product
                    products = [products_orm[0]]
                elif article_type == "comparison":
                    products = products_orm[:3]
                else:  # ranking
                    products = products_orm[:5]

                # Convert to ProductData
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

                # Generate with category-specific template
                category = product_data_list[0].category if product_data_list else None
                article_data = generator.generate(article_type, product_data_list, category)

                if generator.validate_article(article_data):
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

                    # Update product usage (use products_orm, not ProductData)
                    for product in products_orm[:len(product_data_list)]:
                        product.last_used_at = datetime.utcnow()

                    session.commit()

                    # Update RunLog with success
                    run_log = session.query(RunLog).filter_by(id=job_id).first()
                    if run_log:
                        run_log.status = "success"
                        run_log.articles_succeeded = 1
                        session.commit()

                    logger.info(f"Generated: {article_data.title}")
                else:
                    logger.warning(f"Article validation failed for type: {article_type}")
                    run_log = session.query(RunLog).filter_by(id=job_id).first()
                    if run_log:
                        run_log.status = "error"
                        run_log.error_message = "記事の検証に失敗しました"
                        session.commit()

            except Exception as e:
                logger.error(f"Generation error: {e}", exc_info=True)
                # Update RunLog with error
                run_log = session.query(RunLog).filter_by(id=job_id).first()
                if run_log:
                    run_log.status = "error"
                    run_log.error_message = str(e)
                    session.commit()
            finally:
                session.close()

        thread = threading.Thread(target=generate_task)
        thread.daemon = True
        thread.start()

        return jsonify(
            {"status": "generating", "message": "記事生成を開始しました", "job_id": job_id}
        )

    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/generation-status', methods=['GET'])
def api_generation_status():
    """Get status of most recent generation job"""
    session = get_session()
    try:
        # Get most recent generation job
        run_log = (
            session.query(RunLog)
            .filter_by(job_type="generation")
            .order_by(RunLog.run_at.desc())
            .first()
        )

        if not run_log:
            return jsonify({
                "status": "idle",
                "message": "生成ジョブはありません"
            })

        return jsonify({
            "status": run_log.status,
            "job_id": run_log.id,
            "message": run_log.error_message if run_log.status == "error" else f"状態: {run_log.status}",
            "articles_succeeded": run_log.articles_succeeded,
            "error_message": run_log.error_message,
            "run_at": run_log.run_at.isoformat() if run_log.run_at else None,
        })

    finally:
        session.close()


@app.route('/api/generate-comparison', methods=['POST'])
def api_generate_comparison():
    """Generate comparison article for 3-tier products (cost/std/prem)"""
    try:
        data = request.json
        category = data.get('category')

        if not category:
            return jsonify({"error": "Category is required"}), 400

        # Load products master
        import json
        master_file = Path(__file__).parent / 'generation' / 'products_master.json'

        if not master_file.exists():
            return jsonify({"error": "Products master not found"}), 404

        with open(master_file, 'r', encoding='utf-8') as f:
            products_master = json.load(f)

        if category not in products_master:
            return jsonify({"error": f"Category '{category}' not found in products master"}), 404

        category_products = products_master[category]

        # Create RunLog entry
        session = get_session()
        run_log = RunLog(
            job_type="generation",
            status="in_progress",
        )
        session.add(run_log)
        session.commit()
        job_id = run_log.id
        session.close()

        # Run in thread to avoid blocking
        def generate_comparison_task():
            session = get_session()  # Get new session for thread
            try:
                # Create ProductData objects from the 3 tiers
                product_data_list = [
                    ProductData(
                        asin=category_products['cost']['asin'],
                        title=category_products['cost']['name'],
                        url=category_products['cost'].get('url', category_products['cost']['asin']),
                        category=category,
                        price=None,
                        rating=None,
                        review_count=None,
                        image_url=None,
                    ),
                    ProductData(
                        asin=category_products['std']['asin'],
                        title=category_products['std']['name'],
                        url=category_products['std'].get('url', category_products['std']['asin']),
                        category=category,
                        price=None,
                        rating=None,
                        review_count=None,
                        image_url=None,
                    ),
                    ProductData(
                        asin=category_products['prem']['asin'],
                        title=category_products['prem']['name'],
                        url=category_products['prem'].get('url', category_products['prem']['asin']),
                        category=category,
                        price=None,
                        rating=None,
                        review_count=None,
                        image_url=None,
                    ),
                ]

                generator = ArticleGenerator(settings)
                article_data = generator.generate('comparison', product_data_list, category)

                if generator.validate_article(article_data):
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
                    session.commit()

                    # Update RunLog
                    run_log = session.query(RunLog).filter_by(id=job_id).first()
                    if run_log:
                        run_log.status = "success"
                        run_log.articles_succeeded = 1
                        session.commit()

                    logger.info(f"Generated comparison article: {article_data.title}")
                else:
                    run_log = session.query(RunLog).filter_by(id=job_id).first()
                    if run_log:
                        run_log.status = "error"
                        run_log.error_message = "記事の検証に失敗しました"
                        session.commit()

            except Exception as e:
                logger.error(f"Comparison generation error: {e}", exc_info=True)
                run_log = session.query(RunLog).filter_by(id=job_id).first()
                if run_log:
                    run_log.status = "error"
                    run_log.error_message = str(e)
                    session.commit()
            finally:
                session.close()

        thread = threading.Thread(target=generate_comparison_task)
        thread.daemon = True
        thread.start()

        return jsonify(
            {"status": "generating", "message": "比較記事生成を開始しました", "job_id": job_id}
        )

    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/publish/<int:article_id>', methods=['POST'])
def api_publish(article_id: int):
    """Publish article to note.com"""
    session = get_session()

    try:
        article_orm = session.query(Article).filter_by(id=article_id).first()

        if not article_orm:
            return jsonify({"error": "Article not found"}), 404

        as_draft = request.json.get('draft', True)

        def publish_task():
            try:
                from storage.models import ArticleData

                article_data = ArticleData(
                    title=article_orm.title,
                    content=article_orm.content,
                    article_type=article_orm.article_type,
                    product_asins=article_orm.product_asins,
                    meta_description=article_orm.meta_description,
                    word_count=article_orm.word_count,
                )

                publisher = NotePublisherLite(settings)
                result = publisher.publish_sync(article_data, as_draft=as_draft)

                if result["success"]:
                    article_orm.status = "published"
                    article_orm.published_at = datetime.utcnow()
                    article_orm.published_url = result.get("url")
                    logger.info(f"Published: {article_orm.title}")
                else:
                    article_orm.status = "failed"
                    article_orm.error_message = result.get("error")
                    logger.error(f"Publish failed: {result.get('error')}")

                session.commit()

            except Exception as e:
                logger.error(f"Publish error: {e}", exc_info=True)
                article_orm.status = "failed"
                article_orm.error_message = str(e)
                session.commit()
            finally:
                session.close()

        thread = threading.Thread(target=publish_task)
        thread.daemon = True
        thread.start()

        return jsonify(
            {"status": "publishing", "message": "投稿を開始しました"}
        )

    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/discover', methods=['POST'])
def api_discover():
    """Trigger product discovery"""
    session = get_session()

    try:
        category = request.json.get('category', '家電')

        def discover_task():
            try:
                client = PAAPIClient(settings)
                keywords = cat_module.get_category_keywords(category)
                keyword = random.choice(keywords)

                products = client.search(keyword, category=category, limit=5)

                added_count = 0
                for product_data in products:
                    existing = (
                        session.query(Product)
                        .filter_by(asin=product_data.asin)
                        .first()
                    )
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
                logger.info(f"Discovered {added_count} new products")

            except Exception as e:
                logger.error(f"Discovery error: {e}", exc_info=True)
            finally:
                session.close()

        thread = threading.Thread(target=discover_task)
        thread.daemon = True
        thread.start()

        return jsonify(
            {"status": "discovering", "message": "商品検索を開始しました"}
        )

    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/find-products', methods=['POST'])
def api_find_products():
    """Find products for a category using Claude"""
    try:
        data = request.json
        category = data.get('category')

        if not category:
            return jsonify({"error": "Category is required"}), 400

        logger.info(f"Finding products for: {category}")

        finder = ProductFinder(settings)
        products = finder.find_and_cache(category)

        if not products:
            return jsonify({
                "error": "Could not find products",
                "category": category
            }), 400

        return jsonify({
            "category": category,
            "products": products,
            "status": "success"
        })

    except Exception as e:
        logger.error(f"Find products error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/api/products-master')
def api_products_master():
    """Get products master data as JSON"""
    try:
        master_file = Path(__file__).parent / 'generation' / 'products_master.json'
        if master_file.exists():
            import json
            with open(master_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return jsonify(data)
        else:
            return jsonify({"error": "Products master not found"}), 404
    except Exception as e:
        logger.error(f"Products master API error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/products')
def api_products():
    """Get all products as JSON"""
    session = get_session()

    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)

        query = session.query(Product).order_by(Product.discovered_at.desc())
        total = query.count()
        products = query.offset((page - 1) * per_page).limit(per_page).all()

        products_data = [
            {
                "asin": p.asin,
                "title": p.title,
                "category": p.category,
                "price": p.price,
                "rating": p.rating,
                "review_count": p.review_count,
                "discovered_at": p.discovered_at.isoformat(),
                "last_used_at": p.last_used_at.isoformat() if p.last_used_at else None,
            }
            for p in products
        ]

        return jsonify(
            {
                "products": products_data,
                "total": total,
                "page": page,
                "per_page": per_page,
            }
        )

    except Exception as e:
        logger.error(f"Products API error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


@app.route('/api/categories')
def api_categories():
    """Get all categories with their items"""
    try:
        categories_data = {}
        for category_name, category_info in cat_module.CATEGORIES.items():
            categories_data[category_name] = {
                "items": category_info.get("items", category_info.get("keywords", []))
            }
        return jsonify(categories_data)
    except Exception as e:
        logger.error(f"Categories API error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/stats')
def api_stats():
    """Get dashboard statistics as JSON"""
    session = get_session()

    try:
        products_count = session.query(Product).count()
        articles_count = session.query(Article).count()
        published_count = session.query(Article).filter_by(status="published").count()
        queued_count = session.query(Article).filter_by(status="queued").count()
        draft_count = session.query(Article).filter_by(status="draft").count()

        recent_run = (
            session.query(RunLog).order_by(RunLog.run_at.desc()).first()
        )

        return jsonify(
            {
                "products": products_count,
                "articles": articles_count,
                "published": published_count,
                "queued": queued_count,
                "draft": draft_count,
                "last_run": recent_run.run_at.isoformat()
                if recent_run
                else None,
            }
        )

    except Exception as e:
        logger.error(f"Stats error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


if __name__ == "__main__":
    init_app()
    # Run on 0.0.0.0:5000 so it's accessible from iPhone on same network
    app.run(host="0.0.0.0", port=9000, debug=True)
