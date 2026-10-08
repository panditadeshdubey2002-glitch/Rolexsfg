"""PostgreSQL-backed AdminDB + Custom API storage."""
import threading
import time
import json
import os
import uuid
import hashlib
import random
from datetime import datetime, timedelta

from config import (
    logger, get_pg_conn, release_pg_conn, init_pg_pool,
    LEGACY_JSON_PATH, LEGACY_MIGRATION_FLAG_KEY, CUSTOM_APIS_PATH
)
from psycopg2.extras import RealDictCursor


class AdminDB:
    """
    PostgreSQL-backed persistent storage.
    JSON is used ONLY for one-time legacy migration.
    """

    def __init__(self):
        self.lock = threading.RLock()
        self._ready = False
        self._ensure_pool()
        self._init_schema()
        self._run_legacy_migration_once()
        self._ready = True
        logger.info("✅ AdminDB ready (PostgreSQL)")

    def _ensure_pool(self):
        init_pg_pool()

    def _init_schema(self):
        conn = get_pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id TEXT PRIMARY KEY, username TEXT, first_seen TIMESTAMP,
                        phone TEXT, total_sessions INTEGER DEFAULT 0, total_hits INTEGER DEFAULT 0,
                        total_ok INTEGER DEFAULT 0, total_fail INTEGER DEFAULT 0,
                        total_rounds INTEGER DEFAULT 0, modes_used TEXT[] DEFAULT '{}',
                        last_active TIMESTAMP, last_phone TEXT, last_mode TEXT);""")
                cur.execute("""CREATE TABLE IF NOT EXISTS banned (
                    user_id TEXT PRIMARY KEY, banned_at TIMESTAMP DEFAULT NOW(),
                    banned_by TEXT);""")
                cur.execute("""CREATE TABLE IF NOT EXISTS admins (
                    user_id TEXT PRIMARY KEY, added_by TEXT,
                    added_at TIMESTAMP DEFAULT NOW());""")
                cur.execute("""CREATE TABLE IF NOT EXISTS verified (
                    user_id TEXT PRIMARY KEY, verified_at TIMESTAMP DEFAULT NOW());""")
                cur.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
                    user_id TEXT PRIMARY KEY, plan TEXT, started_at TIMESTAMP,
                    expires_at TIMESTAMP, max_concurrent INTEGER DEFAULT 2,
                    max_hours INTEGER DEFAULT 8, price INTEGER DEFAULT 0,
                    active BOOLEAN DEFAULT TRUE);""")
                cur.execute("""CREATE TABLE IF NOT EXISTS keys (
                    key TEXT PRIMARY KEY, plan TEXT, days INTEGER, concurrent INTEGER,
                    max_hours INTEGER, price INTEGER, created_by TEXT,
                    created_at TIMESTAMP, used BOOLEAN DEFAULT FALSE,
                    used_by TEXT, used_at TIMESTAMP, expires_at TIMESTAMP);""")
                cur.execute("""CREATE TABLE IF NOT EXISTS api_stats (
                    api_name TEXT PRIMARY KEY, success INTEGER DEFAULT 0,
                    fail INTEGER DEFAULT 0);""")
                cur.execute("""CREATE TABLE IF NOT EXISTS contact_messages (
                    id TEXT PRIMARY KEY, user_id TEXT, username TEXT, message TEXT,
                    timestamp TIMESTAMP, replied BOOLEAN DEFAULT FALSE,
                    reply_text TEXT);""")
                cur.execute("""CREATE TABLE IF NOT EXISTS global_stats (
                    key TEXT PRIMARY KEY, value BIGINT DEFAULT 0);""")
                cur.execute("""INSERT INTO global_stats(key, value)
                    VALUES ('total_bombs', 0) ON CONFLICT (key) DO NOTHING;""")

                safe_alters = [
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_phone TEXT;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_mode TEXT;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS modes_used TEXT[] DEFAULT '{}';",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS total_hits INTEGER DEFAULT 0;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS total_ok INTEGER DEFAULT 0;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS total_fail INTEGER DEFAULT 0;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS total_rounds INTEGER DEFAULT 0;",
                    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS max_concurrent INTEGER DEFAULT 2;",
                    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS max_hours INTEGER DEFAULT 8;",
                    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS price INTEGER DEFAULT 0;",
                    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE;",
                    "ALTER TABLE keys ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP;",
                    "ALTER TABLE contact_messages ADD COLUMN IF NOT EXISTS reply_text TEXT;",
                ]
                for sql in safe_alters:
                    cur.execute(sql)
            conn.commit()
            logger.info("✅ Schema verified/created (existing data preserved)")
        except Exception as e:
            conn.rollback()
            logger.critical(f"❌ Schema init failed: {e}")
            raise
        finally:
            release_pg_conn(conn)

    def _exec(self, query, params=None, fetch=None, retries=2):
        attempt = 0
        while attempt <= retries:
            conn = None
            try:
                conn = get_pg_conn()
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, params or ())
                    if fetch == "one":
                        result = cur.fetchone()
                    elif fetch == "all":
                        result = cur.fetchall()
                    else:
                        result = True
                    conn.commit()
                    return result
            except Exception as e:
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                try:
                    if conn:
                        conn.close()
                        conn = None
                except Exception:
                    pass
                attempt += 1
                logger.error(f"PG exec error (attempt {attempt}): {e} | q={str(query)[:100]}")
                if attempt > retries:
                    return None if fetch else False
                time.sleep(0.2 * attempt)
            finally:
                if conn:
                    release_pg_conn(conn)
        return None if fetch else False

    def _run_legacy_migration_once(self):
        try:
            r = self._exec(
                "SELECT value FROM global_stats WHERE key = %s;",
                (LEGACY_MIGRATION_FLAG_KEY,), fetch="one"
            )
            if r and int(r["value"]) == 1:
                logger.info("ℹ️ Legacy migration already done. Skipping.")
                return
        except Exception as e:
            logger.error(f"Migration flag read failed: {e}")

        if not os.path.exists(LEGACY_JSON_PATH):
            self._exec(
                """INSERT INTO global_stats(key, value) VALUES (%s, 1)
                   ON CONFLICT (key) DO UPDATE SET value = 1;""",
                (LEGACY_MIGRATION_FLAG_KEY,)
            )
            logger.info("ℹ️ No legacy JSON found. Migration marked complete.")
            return

        try:
            with open(LEGACY_JSON_PATH, "r") as f:
                legacy = json.load(f)
        except Exception as e:
            logger.error(f"Legacy JSON read failed: {e}")
            return

        logger.info("🔄 Migrating legacy admin_db.json → PostgreSQL (once)...")
        migrated = {"users": 0, "banned": 0, "admins": 0, "verified": 0,
                    "keys": 0, "subscriptions": 0, "api_stats": 0,
                    "contacts": 0, "total_bombs": 0}

        try:
            for uid, u in (legacy.get("users") or {}).items():
                self._exec("""
                    INSERT INTO users (user_id, username, first_seen, phone,
                        total_sessions, total_hits, total_ok, total_fail, total_rounds,
                        modes_used, last_active, last_phone, last_mode)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (user_id) DO NOTHING;
                """, (str(uid), u.get("username"), u.get("first_seen"), u.get("phone"),
                      u.get("total_sessions", 0), u.get("total_hits", 0), u.get("total_ok", 0),
                      u.get("total_fail", 0), u.get("total_rounds", 0),
                      u.get("modes_used", []) or [], u.get("last_active"),
                      u.get("last_phone"), u.get("last_mode")))
                migrated["users"] += 1

            for uid in (legacy.get("banned") or []):
                self._exec("INSERT INTO banned(user_id) VALUES (%s) ON CONFLICT DO NOTHING;", (str(uid),))
                migrated["banned"] += 1

            for uid in (legacy.get("admins") or []):
                self._exec("INSERT INTO admins(user_id) VALUES (%s) ON CONFLICT DO NOTHING;", (str(uid),))
                migrated["admins"] += 1

            for uid in (legacy.get("verified") or []):
                self._exec("INSERT INTO verified(user_id) VALUES (%s) ON CONFLICT DO NOTHING;", (str(uid),))
                migrated["verified"] += 1

            for uid, s in (legacy.get("subscriptions") or {}).items():
                self._exec("""
                    INSERT INTO subscriptions (user_id, plan, started_at, expires_at,
                        max_concurrent, max_hours, price, active)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (user_id) DO NOTHING;
                """, (str(uid), s.get("plan"), s.get("started_at"), s.get("expires_at"),
                      s.get("max_concurrent", 2), s.get("max_hours", 8),
                      s.get("price", 0), s.get("active", True)))
                migrated["subscriptions"] += 1

            for k, kv in (legacy.get("keys") or {}).items():
                self._exec("""
                    INSERT INTO keys (key, plan, days, concurrent, max_hours, price,
                        created_by, created_at, used, used_by, used_at, expires_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (key) DO NOTHING;
                """, (k, kv.get("plan"), kv.get("days"), kv.get("concurrent"),
                      kv.get("max_hours"), kv.get("price"), kv.get("created_by"),
                      kv.get("created_at"), kv.get("used", False), kv.get("used_by"),
                      kv.get("used_at"), kv.get("expires_at")))
                migrated["keys"] += 1

            for name, st in (legacy.get("api_stats") or {}).items():
                self._exec("""INSERT INTO api_stats(api_name, success, fail)
                    VALUES (%s,%s,%s) ON CONFLICT (api_name) DO NOTHING;""",
                    (name, st.get("success", 0), st.get("fail", 0)))
                migrated["api_stats"] += 1

            for mid, cm in (legacy.get("contact_messages") or {}).items():
                self._exec("""INSERT INTO contact_messages (id, user_id, username,
                    message, timestamp, replied, reply_text)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING;""",
                    (cm.get("id", mid), cm.get("user_id"), cm.get("username"),
                     cm.get("message"), cm.get("timestamp"),
                     cm.get("replied", False), cm.get("reply_text")))
                migrated["contacts"] += 1

            tb = legacy.get("total_bombs", 0)
            if tb:
                self._exec("""UPDATE global_stats SET value = GREATEST(value, %s)
                    WHERE key = 'total_bombs';""", (tb,))
                migrated["total_bombs"] = tb

            self._exec(
                """INSERT INTO global_stats(key, value) VALUES (%s, 1)
                   ON CONFLICT (key) DO UPDATE SET value = 1;""",
                (LEGACY_MIGRATION_FLAG_KEY,)
            )
            logger.info(f"✅ Legacy migration complete: {migrated}")
        except Exception as e:
            logger.error(f"❌ Legacy migration partial failure: {e}")

    def verify_health(self):
        try:
            counts = {}
            for table in ["users", "banned", "admins", "verified",
                          "subscriptions", "keys", "api_stats",
                          "contact_messages", "global_stats"]:
                r = self._exec(f"SELECT COUNT(*) AS c FROM {table};", fetch="one")
                counts[table] = r["c"] if r else "ERR"
            logger.info(f"✅ DB health check passed: {counts}")
            return True
        except Exception as e:
            logger.critical(f"❌ DB health check failed: {e}")
            return False

    # -------- USERS --------
    def track_user(self, user_id, username, phone, mode):
        uid = str(user_id)
        self._exec("""
            INSERT INTO users (user_id, username, first_seen, phone, total_sessions,
                               modes_used, last_active, last_phone, last_mode)
            VALUES (%s, %s, NOW(), %s, 1, ARRAY[%s], NOW(), %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                username = COALESCE(EXCLUDED.username, users.username),
                last_active = NOW(), last_phone = EXCLUDED.last_phone,
                last_mode = EXCLUDED.last_mode, phone = EXCLUDED.phone,
                total_sessions = users.total_sessions + 1,
                modes_used = (SELECT ARRAY(SELECT DISTINCT unnest(users.modes_used || EXCLUDED.modes_used)));
        """, (uid, username, phone, mode, phone, mode))

    def update_stats(self, user_id, ok, fail, rounds, total):
        uid = str(user_id)
        with self.lock:
            self._exec("""UPDATE users SET total_hits = total_hits + %s,
                          total_ok = total_ok + %s, total_fail = total_fail + %s,
                          total_rounds = total_rounds + %s, last_active = NOW()
                          WHERE user_id = %s;""", (total, ok, fail, rounds, uid))
            self._exec("UPDATE global_stats SET value = value + %s WHERE key = 'total_bombs';", (total,))

    def get_all_users(self):
        rows = self._exec("SELECT * FROM users;", fetch="all") or []
        return {r["user_id"]: dict(r) for r in rows}

    def get_user_count(self):
        r = self._exec("SELECT COUNT(*) AS c FROM users;", fetch="one")
        return r["c"] if r else 0

    # -------- BANNED --------
    def is_banned(self, user_id):
        r = self._exec("SELECT 1 FROM banned WHERE user_id = %s;", (str(user_id),), fetch="one")
        return r is not None

    def ban_user(self, user_id, admin_id):
        self._exec("INSERT INTO banned(user_id, banned_by) VALUES (%s, %s) ON CONFLICT DO NOTHING;",
                   (str(user_id), str(admin_id)))
        return True

    def unban_user(self, user_id, admin_id):
        self._exec("DELETE FROM banned WHERE user_id = %s;", (str(user_id),))
        return True

    def get_banned_list(self):
        rows = self._exec("SELECT user_id FROM banned;", fetch="all") or []
        return [r["user_id"] for r in rows]

    def get_banned_count(self):
        r = self._exec("SELECT COUNT(*) AS c FROM banned;", fetch="one")
        return r["c"] if r else 0

    # -------- ADMINS --------
    def is_admin(self, user_id):
        from config import ADMIN_IDS
        if user_id in ADMIN_IDS:
            return True
        r = self._exec("SELECT 1 FROM admins WHERE user_id = %s;", (str(user_id),), fetch="one")
        return r is not None

    def add_admin(self, user_id, added_by):
        self._exec("INSERT INTO admins(user_id, added_by) VALUES (%s, %s) ON CONFLICT DO NOTHING;",
                   (str(user_id), str(added_by)))
        return True

    def remove_admin(self, user_id):
        self._exec("DELETE FROM admins WHERE user_id = %s;", (str(user_id),))
        return True

    # -------- VERIFIED --------
    def verify_user(self, user_id):
        self._exec("INSERT INTO verified(user_id) VALUES (%s) ON CONFLICT DO NOTHING;", (str(user_id),))
        return True

    def is_verified(self, user_id):
        r = self._exec("SELECT 1 FROM verified WHERE user_id = %s;", (str(user_id),), fetch="one")
        return r is not None

    # -------- GLOBAL STATS --------
    def get_total_bombs(self):
        r = self._exec("SELECT value FROM global_stats WHERE key = 'total_bombs';", fetch="one")
        return int(r["value"]) if r else 0

    # -------- KEYS --------
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
        self._exec("""INSERT INTO keys(key, plan, days, concurrent, max_hours, price,
                      created_by, created_at, used) VALUES (%s,%s,%s,%s,%s,%s,%s,NOW(),FALSE);""",
                   (key, plan, cfg["days"], cfg["concurrent"], cfg["hours"], cfg["price"], str(created_by)))
        return key

    def redeem_key(self, key, user_id):
        uid = str(user_id)
        row = self._exec("SELECT * FROM keys WHERE key = %s;", (key,), fetch="one")
        if not row:
            return False, "❌ Invalid key!"
        if row["used"]:
            return False, "❌ Yeh key already used ho chuki hai!"
        now = datetime.now()
        days = row["days"]
        expires = (now.replace(year=now.year + 50)) if days >= 99999 else (now + timedelta(days=days))
        ok1 = self._exec("""INSERT INTO subscriptions(user_id, plan, started_at, expires_at,
                            max_concurrent, max_hours, price, active)
                            VALUES (%s,%s,NOW(),%s,%s,%s,%s,TRUE)
                            ON CONFLICT (user_id) DO UPDATE SET
                                plan=EXCLUDED.plan, started_at=EXCLUDED.started_at,
                                expires_at=EXCLUDED.expires_at, max_concurrent=EXCLUDED.max_concurrent,
                                max_hours=EXCLUDED.max_hours, price=EXCLUDED.price, active=TRUE;""",
                         (uid, row["plan"], expires, row["concurrent"], row["max_hours"], row["price"]))
        ok2 = self._exec("UPDATE keys SET used = TRUE, used_by = %s, used_at = NOW() WHERE key = %s;",
                         (uid, key))
        if not ok1 or not ok2:
            return False, "❌ Database error while redeeming key. Try again."
        return True, (f"✅ *Plan Activated!*\n\n🎯 Plan: {row['plan'].upper()}\n"
                      f"⏱ Duration: {days} days\n⚡ Concurrent: {row['concurrent']}\n"
                      f"⏰ Max Hours: {row['max_hours']}h")

    def get_all_keys(self):
        rows = self._exec("SELECT * FROM keys;", fetch="all") or []
        return {r["key"]: dict(r) for r in rows}

    # -------- SUBSCRIPTIONS --------
    def get_subscription(self, user_id):
        row = self._exec("SELECT * FROM subscriptions WHERE user_id = %s;", (str(user_id),), fetch="one")
        if not row:
            return None
        if row.get("expires_at") and row["expires_at"] < datetime.now():
            self._exec("UPDATE subscriptions SET active = FALSE WHERE user_id = %s;", (str(user_id),))
            return None
        return dict(row)

    def get_premium_users(self):
        rows = self._exec("SELECT user_id FROM subscriptions WHERE active = TRUE;", fetch="all") or []
        return [r["user_id"] for r in rows]

    def get_premium_count(self):
        r = self._exec("""SELECT COUNT(*) AS c FROM subscriptions
            WHERE active = TRUE AND expires_at > NOW();""", fetch="one")
        return r["c"] if r else 0

    def give_premium(self, user_id, days=30, plan="custom"):
        uid = str(user_id)
        expires = datetime.now() + timedelta(days=days)
        ok = self._exec("""INSERT INTO subscriptions(user_id, plan, started_at, expires_at,
                            max_concurrent, max_hours, price, active)
                            VALUES (%s,%s,NOW(),%s,5,24,0,TRUE)
                            ON CONFLICT (user_id) DO UPDATE SET
                                plan=EXCLUDED.plan, started_at=EXCLUDED.started_at,
                                expires_at=EXCLUDED.expires_at, active=TRUE;""",
                        (uid, plan, expires))
        return bool(ok)

    def remove_premium(self, user_id):
        ok = self._exec("DELETE FROM subscriptions WHERE user_id = %s;", (str(user_id),))
        return bool(ok)

    # -------- API STATS --------
    def update_api_stats(self, api_name, success):
        if success:
            self._exec("""INSERT INTO api_stats(api_name, success, fail) VALUES (%s,1,0)
                ON CONFLICT (api_name) DO UPDATE SET success = api_stats.success + 1;""", (api_name,))
        else:
            self._exec("""INSERT INTO api_stats(api_name, success, fail) VALUES (%s,0,1)
                ON CONFLICT (api_name) DO UPDATE SET fail = api_stats.fail + 1;""", (api_name,))

    def get_api_stats(self):
        rows = self._exec("SELECT api_name, success, fail FROM api_stats;", fetch="all") or []
        return {r["api_name"]: {"success": r["success"], "fail": r["fail"]} for r in rows}

    # -------- CONTACT MESSAGES --------
    def add_contact_message(self, user_id, username, message):
        msg_id = uuid.uuid4().hex[:10]
        self._exec("""INSERT INTO contact_messages(id, user_id, username, message,
                      timestamp, replied) VALUES (%s,%s,%s,%s,NOW(),FALSE);""",
                   (msg_id, str(user_id), username, message))
        return msg_id

    def get_contact_message(self, msg_id):
        r = self._exec("SELECT * FROM contact_messages WHERE id = %s;", (str(msg_id),), fetch="one")
        return dict(r) if r else None

    def mark_replied(self, msg_id, reply_text):
        ok = self._exec("UPDATE contact_messages SET replied = TRUE, reply_text = %s WHERE id = %s;",
                        (reply_text, str(msg_id)))
        return bool(ok)

    def get_pending_contacts(self):
        rows = self._exec("SELECT * FROM contact_messages WHERE replied = FALSE;", fetch="all") or []
        return [dict(r) for r in rows]


# ============================================================
# CUSTOM API STORAGE (JSON — config file)
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


admin_db = AdminDB()
custom_api_db = CustomAPIDB()
