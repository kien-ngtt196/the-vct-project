from pathlib import Path

from src.db.database import connect


MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def initialize_database():
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        raise RuntimeError(f"No database migrations found in {MIGRATIONS_DIR}")

    connection = connect()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version VARCHAR(100) PRIMARY KEY,
                        applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                cursor.execute("SELECT version FROM schema_migrations")
                applied = {row[0] for row in cursor.fetchall()}

                for migration_path in migration_files:
                    version = migration_path.name
                    if version in applied:
                        continue

                    cursor.execute(migration_path.read_text(encoding="utf-8"))
                    cursor.execute(
                        "INSERT INTO schema_migrations (version) VALUES (%s)",
                        (version,),
                    )
    finally:
        connection.close()


if __name__ == "__main__":
    initialize_database()
    print("Database migrations applied.")
