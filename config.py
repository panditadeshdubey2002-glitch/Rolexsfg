"""Configuration, logging, and PostgreSQL pool setup."""
import os
import sys
import logging
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ============================================================
# POSTGRESQL
# ============================================================
try:
    import psycopg2
    from psycopg2 import pool as pg_pool
    from psycopg2.extras import RealDictCursor
    import atexit
    PG_AVAILABLE = True
except ImportError:
    PG_AVAILABLE = False
    logger.critical("❌ psycopg2 not installed. PostgreSQL is MANDATORY.")
    sys.exit(1)

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    logger.critical("❌ DATABASE_URL environment variable is not set. Aborting.")
    sys.exit(1)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_pg_pool = None
import threading
_pg_lock = threading.Lock()


def init_pg_pool():
    global _pg_pool
    with _pg_lock:
        if _pg_pool is not None:
            return _pg_pool
        try:
            _pg_pool = pg_pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=20,
                dsn=DATABASE_URL,
                sslmode="require",
                connect_timeout=15,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5,
            )
            conn = _pg_pool.getconn()
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
            _pg_pool.putconn(conn)
            logger.info("✅ PostgreSQL pool initialized successfully")
            return _pg_pool
        except Exception as e:
            logger.critical(f"❌ PostgreSQL pool init failed: {e}")
            _pg_pool = None
            raise


def get_pg_conn():
    if _pg_pool is None:
        raise RuntimeError("PostgreSQL pool is not initialized")
    return _pg_pool.getconn()


def release_pg_conn(conn):
    if _pg_pool and conn:
        try:
            _pg_pool.putconn(conn)
        except Exception as e:
            logger.error(f"PG putconn error: {e}")


def close_pg_pool():
    global _pg_pool
    with _pg_lock:
        if _pg_pool:
            try:
                _pg_pool.closeall()
            except Exception:
                pass
            _pg_pool = None


atexit.register(close_pg_pool)

# ============================================================
# BOT CONFIG
# ============================================================
API_TOKEN = os.environ.get("BOT_TOKEN")
if not API_TOKEN:
    logger.critical("❌ BOT_TOKEN environment variable is not set. Aborting.")
    sys.exit(1)

MAX_WORKERS = int(os.environ.get("MAX_WORKERS", 30))
SMS_MAX_WORKERS = int(os.environ.get("SMS_MAX_WORKERS", 50))
DELAY_BETWEEN_ROUNDS = float(os.environ.get("DELAY_BETWEEN_ROUNDS", 0.3))
SMS_DELAY_BETWEEN_ROUNDS = float(os.environ.get("SMS_DELAY_BETWEEN_ROUNDS", 0.1))
SMS_DOUBLE_FIRE = os.environ.get("SMS_DOUBLE_FIRE", "true").lower() == "true"
IMPORTANT_CALL_INTERVAL = 3
IMPORTANT_5S_INTERVAL = 3

_admin_env = os.environ.get("ADMIN_IDS", "8128821116")
ADMIN_IDS = [int(x.strip()) for x in _admin_env.split(",") if x.strip().isdigit()]

LEGACY_JSON_PATH = os.environ.get("ADMIN_DB_PATH", "admin_db.json")
LEGACY_MIGRATION_FLAG_KEY = "legacy_json_migrated"
CUSTOM_APIS_PATH = "custom_apis.json"

REQUIRED_CHANNEL = os.environ.get("REQUIRED_CHANNEL", "@rolexxbomber")
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "https://t.me/rolexxbomber")
CHANNEL_CHECK_ENABLED = os.environ.get("CHANNEL_CHECK", "true").lower() == "true"

import telebot
bot = telebot.TeleBot(API_TOKEN, threaded=True)
