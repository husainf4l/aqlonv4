"""
Database connection setup for SQLAlchemy
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from app.logger import logger
from app.settings import settings

# Create Base declarative class
Base = declarative_base()

# Initialize database connection
engine = None
SessionLocal = None

try:
    DATABASE_URL = settings.get_effective_database_url()
    if DATABASE_URL:
        engine = create_engine(DATABASE_URL, echo=False, future=True)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
        logger.info(f"Database connection initialized with URL: {DATABASE_URL}")
    else:
        logger.warning("No database URL available in settings")
except Exception as e:
    logger.error(f"Failed to connect to database: {e}")

def get_db_session():
    """
    Get a database session. Use in a context manager or remember to close it.
    """
    if SessionLocal:
        session = SessionLocal()
        try:
            return session
        finally:
            session.close()
    return None
