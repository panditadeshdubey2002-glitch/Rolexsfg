#!/usr/bin/env python3
"""CollBomber Bot — entry point."""
import sys
import time
from config import logger, init_pg_pool, ADMIN_IDS, REQUIRED_CHANNEL, CHANNEL_CHECK_ENABLED
from database import admin_db
from apis import ALL_APIS, CALL_APIS, SMS_APIS, WHATSAPP_APIS
from bomber import bomber
import bot_handlers  # noqa — registers handlers on import


def startup_check():
    logger.info("🔍 Running startup checks...")
    try:
        init_pg_pool()
    except Exception as e:
        logger.critical(f"❌ PostgreSQL pool failed at startup: {e}")
        sys.exit(1)

    if not admin_db.verify_health():
        logger.critical("❌ DB health verification failed. Aborting startup.")
        sys.exit(1)

    logger.info(f"📊 APIs: {len(ALL_APIS)} total | "
                f"📞 {len(CALL_APIS)} call | 💬 {len(SMS_APIS)} sms | 📱 {len(WHATSAPP_APIS)} WA")
    logger.info(f"👑 Admins: {ADMIN_IDS}")
    logger.info(f"📢 Channel: {REQUIRED_CHANNEL}")
    logger.info(f"🔒 Channel check: {CHANNEL_CHECK_ENABLED}")
    logger.info("✅ Startup checks passed")


if __name__ == "__main__":
    startup_check()
    logger.info("🚀 Bot running with AUTO-RESTART loop!")
    while True:
        try:
            from config import bot
            bot.infinity_polling(timeout=60, long_polling_timeout=60, none_stop=True)
        except KeyboardInterrupt:
            logger.info("Stopping...")
            bomber.stop_all()
            break
        except Exception as e:
            logger.error(f"Polling crashed: {e}")
            logger.info("🔄 Restarting in 5 seconds...")
            time.sleep(5)
