import asyncio
import logging
import sys
from collector.writer import DatabaseWriter
from collector.snapshot import SnapshotCollector
from config.settings import settings
from telegram_backup import TelegramBackup # <--- DODAT IMPORT

# Konfiguracija logovanja
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("main")

async def main():
    logger.info("Pokretanje Solana Data Collector v1.0 sistema...")
    
    # Inicijalizacija baze i writera
    writer = DatabaseWriter(settings.DATABASE_URL)
    
    # Pokretanje Single Writer task-a u pozadini
    writer_task = asyncio.create_task(writer.start())
    
    # Inicijalizacija collector-a
    collector = SnapshotCollector(writer)
    
    # Pokretanje polling loop-a u pozadini
    collector_task = asyncio.create_task(collector.run_polling_loop())
    
    # Inicijalizacija Telegram backup-a (šalje bazu na svakih 6 sati)
    backup_bot = TelegramBackup(settings.DATABASE_URL)
    backup_task = asyncio.create_task(backup_bot.backup_loop(interval_hours=6))
    
    try:
        # Održavanje aplikacije aktivnom (sada čeka sva 3 taska)
        await asyncio.gather(writer_task, collector_task, backup_task)
    except asyncio.CancelledError:
        logger.info("Zaustavljanje sistema...")
    finally:
        # Bezbedno gasenje
        await writer.stop()
        logger.info("Sistem je uspešno ugašen.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Aplikacija prekinuta od strane korisnika (Ctrl+C).")