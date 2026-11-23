

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError


# Project root: the parent directory of backend/
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

# Load environment variables.
load_dotenv(ENV_FILE)


# Database settings
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "airvision")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")

if not DB_PASSWORD:
    raise RuntimeError(
        f"DB_PASSWORD is missing. Check your .env file: {ENV_FILE}"
    )


# Safely construct the connection URL.
DATABASE_URL = URL.create(
    drivername="postgresql+psycopg",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME,
)


# Shared SQLAlchemy engine.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    connect_args={"connect_timeout": 10},
)


def test_connection():
    """Test the connection and return database information."""

    with engine.connect() as connection:
        result = connection.execute(
            text(
                """
                SELECT
                    current_database() AS database_name,
                    current_user AS connected_user,
                    version() AS postgresql_version,
                    CURRENT_TIMESTAMP AS server_time
                """
            )
        )

        return result.mappings().one()


if __name__ == "__main__":
    try:
        details = test_connection()

        print("=" * 55)
        print("AIRVISION DATABASE CONNECTION SUCCESSFUL")
        print("=" * 55)
        print(f"Database: {details['database_name']}")
        print(f"User: {details['connected_user']}")
        print(f"PostgreSQL: {details['postgresql_version']}")
        print(f"Server time: {details['server_time']}")
        print("=" * 55)

    except (SQLAlchemyError, RuntimeError, ValueError) as error:
        print("AIRVISION DATABASE CONNECTION FAILED")
        print(f"Error: {error}")

    finally:
        engine.dispose()
