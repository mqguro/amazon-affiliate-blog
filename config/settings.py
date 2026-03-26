from dataclasses import dataclass, field
from pathlib import Path
import os
from dotenv import load_dotenv


@dataclass
class Settings:
    """Typed configuration loaded from .env"""

    # Required fields (no defaults)
    amazon_associate_id: str
    anthropic_api_key: str
    
    # Optional fields (with defaults)
    amazon_marketplace: str = "www.amazon.co.jp"
    paapi_access_key: str = ""
    paapi_secret_key: str = ""
    paapi_partner_tag: str = ""
    claude_model: str = "claude-haiku-4-5-20251001"
    claude_max_tokens: int = 4096
    articles_per_run: int = 3
    min_word_count: int = 1500
    article_types: list = field(default_factory=lambda: ["review", "ranking", "comparison"])
    default_category: str = "家電"
    note_email: str = ""
    note_password: str = ""
    note_default_draft: bool = True
    db_path: str = "./data/affiliate_blog.db"
    log_path: str = "./logs/affiliate_blog.log"
    scheduler_timezone: str = "Asia/Tokyo"
    discovery_cron: str = "0 6 * * *"
    generation_cron: str = "0 8 * * *"
    publishing_cron: str = "0 10,14,18 * * *"
    paapi_requests_per_second: float = 1.0
    scraper_delay_seconds: float = 4.0
    claude_requests_per_minute: int = 50

    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from .env file and environment variables"""
        env_path = Path.cwd() / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            load_dotenv()

        # Required fields
        amazon_associate_id = os.getenv("AMAZON_ASSOCIATE_ID")
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

        if not amazon_associate_id:
            raise ValueError("AMAZON_ASSOCIATE_ID is required in .env")
        if not anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required in .env")

        # Parse article types
        article_types_str = os.getenv("ARTICLE_TYPES", "review,ranking,comparison")
        article_types = [t.strip() for t in article_types_str.split(",")]

        return cls(
            amazon_associate_id=amazon_associate_id,
            anthropic_api_key=anthropic_api_key,
            amazon_marketplace=os.getenv("AMAZON_MARKETPLACE", "www.amazon.co.jp"),
            paapi_access_key=os.getenv("PAAPI_ACCESS_KEY", ""),
            paapi_secret_key=os.getenv("PAAPI_SECRET_KEY", ""),
            paapi_partner_tag=os.getenv("PAAPI_PARTNER_TAG", amazon_associate_id),
            claude_model=os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001"),
            claude_max_tokens=int(os.getenv("CLAUDE_MAX_TOKENS", "4096")),
            articles_per_run=int(os.getenv("ARTICLES_PER_RUN", "3")),
            min_word_count=int(os.getenv("MIN_WORD_COUNT", "1500")),
            article_types=article_types,
            default_category=os.getenv("DEFAULT_CATEGORY", "家電"),
            note_email=os.getenv("NOTE_EMAIL", ""),
            note_password=os.getenv("NOTE_PASSWORD", ""),
            note_default_draft=os.getenv("NOTE_DEFAULT_DRAFT", "true").lower() == "true",
            db_path=os.getenv("DB_PATH", "./data/affiliate_blog.db"),
            log_path=os.getenv("LOG_PATH", "./logs/affiliate_blog.log"),
            scheduler_timezone=os.getenv("SCHEDULER_TIMEZONE", "Asia/Tokyo"),
            discovery_cron=os.getenv("DISCOVERY_CRON", "0 6 * * *"),
            generation_cron=os.getenv("GENERATION_CRON", "0 8 * * *"),
            publishing_cron=os.getenv("PUBLISHING_CRON", "0 10,14,18 * * *"),
            paapi_requests_per_second=float(
                os.getenv("PAAPI_REQUESTS_PER_SECOND", "1.0")
            ),
            scraper_delay_seconds=float(os.getenv("SCRAPER_DELAY_SECONDS", "4.0")),
            claude_requests_per_minute=int(
                os.getenv("CLAUDE_REQUESTS_PER_MINUTE", "50")
            ),
        )

    @property
    def has_paapi_credentials(self) -> bool:
        """Check if PA-API credentials are configured"""
        return bool(self.paapi_access_key and self.paapi_secret_key)

    @property
    def has_note_credentials(self) -> bool:
        """Check if note.com credentials are configured"""
        return bool(self.note_email and self.note_password)
