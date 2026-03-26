from sqlalchemy import Column, String, Integer, Float, DateTime, Text, JSON, Boolean, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session
from datetime import datetime
from dataclasses import dataclass, asdict

Base = declarative_base()


class Product(Base):
    """Discovered products from Amazon"""
    __tablename__ = "products"

    asin = Column(String(10), primary_key=True)
    title = Column(String(500), nullable=False)
    url = Column(String(500), nullable=False)
    category = Column(String(100), nullable=False)
    price = Column(Float, nullable=True)
    rating = Column(Float, nullable=True)
    review_count = Column(Integer, nullable=True)
    image_url = Column(String(500), nullable=True)
    discovered_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)

    def to_dict(self):
        return {
            "asin": self.asin,
            "title": self.title,
            "url": self.url,
            "category": self.category,
            "price": self.price,
            "rating": self.rating,
            "review_count": self.review_count,
            "image_url": self.image_url,
        }


class Article(Base):
    """Generated articles ready for publishing"""
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)  # Markdown content
    article_type = Column(String(50), nullable=False)  # review / comparison / ranking
    product_asins = Column(JSON, nullable=False)  # List of ASINs used
    meta_description = Column(String(160), nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)
    published_url = Column(String(500), nullable=True)  # note.com URL after publish
    status = Column(String(50), default="draft")  # draft / queued / published / failed
    error_message = Column(Text, nullable=True)
    word_count = Column(Integer, nullable=True)
    publisher = Column(String(50), default="note.com")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "article_type": self.article_type,
            "product_asins": self.product_asins,
            "status": self.status,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "published_url": self.published_url,
            "word_count": self.word_count,
        }


class RunLog(Base):
    """Execution logs for scheduled jobs"""
    __tablename__ = "run_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_at = Column(DateTime, default=datetime.utcnow)
    job_type = Column(String(50), nullable=False)  # discovery / generation / publishing
    articles_processed = Column(Integer, default=0)
    articles_succeeded = Column(Integer, default=0)
    articles_failed = Column(Integer, default=0)
    duration_seconds = Column(Float, nullable=True)
    status = Column(String(50), default="success")  # success / error / partial
    error_message = Column(Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "run_at": self.run_at.isoformat() if self.run_at else None,
            "job_type": self.job_type,
            "articles_processed": self.articles_processed,
            "articles_succeeded": self.articles_succeeded,
            "articles_failed": self.articles_failed,
            "duration_seconds": self.duration_seconds,
            "status": self.status,
        }


@dataclass
class ProductData:
    """Python dataclass for product data"""
    asin: str
    title: str
    url: str
    category: str
    price: float = None
    rating: float = None
    review_count: int = None
    image_url: str = None


@dataclass
class ArticleData:
    """Python dataclass for article content"""
    title: str
    content: str
    article_type: str
    product_asins: list
    meta_description: str = None
    word_count: int = None
