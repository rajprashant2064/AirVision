    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=1,
    max_overflow=0,
    pool_recycle=300,
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
