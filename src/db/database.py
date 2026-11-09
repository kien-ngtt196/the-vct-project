import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ".env.neon" if os.getenv("VCT_USE_NEON") == "1" else ".env"
load_dotenv(ROOT / ENV_FILE)


def connect():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url, connect_timeout=5)

    password = os.getenv("VCT_DB_PASSWORD")
    if not password:
        raise RuntimeError(
            "VCT_DB_PASSWORD is not set. Configure the database environment before connecting."
        )

    return psycopg2.connect(
        dbname=os.getenv("VCT_DB_NAME", "vct_db"),
        user=os.getenv("VCT_DB_USER", "postgres"),
        password=password,
        host=os.getenv("VCT_DB_HOST", "localhost"),
        port=os.getenv("VCT_DB_PORT", "5432"),
        connect_timeout=5,
    )
