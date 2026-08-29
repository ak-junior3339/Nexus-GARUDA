from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Replace 'postgres' and 'your_password' with your actual PostgreSQL credentials.
# Format: postgresql://username:password@server:port/database_name
SQLALCHEMY_DATABASE_URL = "postgresql://garuda-db_owner:npg_9C6WhKPjYrez@ep-square-voice-azlnmadv-pooler.c-3.ap-southeast-1.aws.neon.tech/garuda-db?sslmode=require&channel_binding=require"

# Change your engine creation line in backend/db/database.py to this:
engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency to inject the database session into your FastAPI routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()