"""All Telegram bot handlers, keyboards, channel check."""
import re
import time
from datetime import datetime
import requests
from telebot import types

from config import (
    logger, bot, ADMIN_IDS, REQUIRED_CHANNEL, CHANNEL_LINK, CHANNEL_CHECK_ENABLED
)
from database import admin_db, custom_api_db
from apis import (
    ALL_APIS, CALL_APIS, SMS_APIS, WHATSAPP_APIS,
    reload_apis, get_all_apis
)
from bomber import bomber, user_data, admin_data


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
# COMMANDS
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
            "❓ *Help*\n\n1️⃣ Number bhejein (10 digits)\n2️⃣ Mode select karein\n"
            "3️⃣ Bombing start ho jayegi\n4️⃣ 🛑 Stop se band karein\n\n"
            f"📊 Total APIs: {len(ALL_APIS)}\n"
            f"📞 Call: {len(CALL_APIS)} | 💬 SMS: {len(SMS_APIS)} | 📱 WA: {len(WHATSAPP_APIS)}\n\n"
            "*Commands:*\n/start — Restart\n/status — Session status\n/stop — Stop bombing\n"
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
        exp = sub["expires_at"]
        if isinstance(exp, str):
            exp = datetime.fromisoformat(exp)
        days_left = (exp - datetime.now()).days
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
        bot.reply_to(message, "⚙️ *Admin Panel* — Full Controls",
                     parse_mode="Markdown", reply_markup=admin_keyboard())
    except Exception as e:
        logger.error(f"cmd_admin error: {e}")


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
# CALLBACKS
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
            bot.send_message(chat_id, f"💳 *{plan.upper()} Plan*\n\nAdmin se contact karein: /contact",
                             parse_mode="Markdown")
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
            bot.send_message(chat_id, "💰 *Give Premium*\n\nFormat: `<user_id> <days>`\nExample: `8128821116 30`",
                             parse_mode="Markdown")

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
            bot.send_message(chat_id,
                "🔑 *Generate Key*\n\nPlan: `daily` / `monthly` / `3month` / `custom:<days>`\n\nExample: `custom:15`",
                parse_mode="Markdown")

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
            bot.send_message(chat_id, "💬 *Reply to User*\n\nFormat: `<msg_id> <reply_text>`",
                             parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Callback error: {e}")


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
                    bot.send_message(uid, f"⭐ *Premium Activated!*\n\nAdmin ne aapko {days} days premium diya hai!",
                                     parse_mode="Markdown")
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
                bot.reply_to(message, f"{'✅' if removed else '❌'} Premium {'removed' if removed else 'not found'} for `{uid}`",
                             parse_mode="Markdown")
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
                    bot.reply_to(message, f"✅ API added: `{name}`\n\n📊 Total APIs: {len(ALL_APIS)}",
                                 parse_mode="Markdown")
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

        if user_data.users[chat_id].get("awaiting_key"):
            user_data.users[chat_id].pop("awaiting_key", None)
            ok, msg = admin_db.redeem_key(text.upper(), chat_id)
            bot.reply_to(message, msg, parse_mode="Markdown")
            return

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
