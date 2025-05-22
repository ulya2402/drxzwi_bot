import asyncio
import logging
logger = logging.getLogger(__name__)

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode


from config import BOT_TOKEN, SUPER_ADMIN_ID 
from utils import database, admin_manager 
from handlers import common

async def main():
    log_format = '%(asctime)s - %(levelname)s - %(name)s - [%(filename)s:%(lineno)d] - %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_format, force=True) 

    logging.info("Konfigurasi logging selesai di fungsi main.")

    if not BOT_TOKEN:
        logging.error("BOT_TOKEN tidak ditemukan! Bot tidak bisa berjalan.")
        return
    logging.info("BOT_TOKEN ditemukan.")

    if SUPER_ADMIN_ID is None:
        logging.warning("SUPER_ADMIN_ID tidak diset di .env! Fitur manajemen admin mungkin tidak berfungsi dengan benar.")
        

    if not database.supabase:
        logging.error("Klien Supabase GAGAL diinisialisasi. Operasi database tidak akan berfungsi.")
        
    else:
        logging.info("Klien Supabase berhasil diinisialisasi.")
        
        if not await admin_manager.load_admins_to_cache():
             logging.error("Gagal memuat admin ke cache saat startup.")
        else:
             logging.info("Admin berhasil dimuat ke cache saat startup.")


    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.include_router(common.router)
    logging.info("Router telah di-include.")

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        logging.info("Memulai polling bot...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logging.error(f"Terjadi error saat polling: {e}", exc_info=True)
    finally:
        if hasattr(bot, 'session') and bot.session: 
            await bot.session.close()
        logging.info("Polling bot selesai.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot dihentikan secara manual.")
    except Exception as e:
        logging.critical(f"Terjadi error fatal di level atas: {e}", exc_info=True)
