from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from pathlib import Path
from .models import Base, Product, Article, RunLog


class Database:
    """SQLite database manager"""

    def __init__(self, db_path: str = "./data/affiliate_blog.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        connection_string = f"sqlite:///{self.db_path.absolute()}"
        self.engine = create_engine(connection_string, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def init_db(self):
        """Create all tables"""
        Base.metadata.create_all(self.engine)

    def get_session(self) -> Session:
        """Get a new database session"""
        return self.SessionLocal()

    def close(self):
        """Close the engine"""
        self.engine.dispose()


# Global singleton instance
_db_instance = None


def init_database(db_path: str = "./data/affiliate_blog.db") -> Database:
    """Initialize the global database instance"""
    global _db_instance
    _db_instance = Database(db_path)
    _db_instance.init_db()
    return _db_instance


def get_database() -> Database:
    """Get the global database instance"""
    global _db_instance
    if _db_instance is None:
        raise RuntimeError(
            "Database not initialized. Call init_database() first."
        )
    return _db_instance


def get_session() -> Session:
    """Get a new database session from the global instance"""
    db = get_database()
    return db.get_session()
