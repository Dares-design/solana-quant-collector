import os
import sqlite3
import asyncio
import aiohttp
from datetime import datetime
from loguru import logger

class TelegramBackup:
    def __init__(self, db_path='data/solana_collector.db'):
        self.db_path = db_path
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if not self.bot_token or not self.chat_id:
            logger.warning("⚠️ Telegram Token ili Chat ID nisu podešeni. Backup je onemogućen.")

    def _create_safe_copy(self):
        """Pravi bezbednu kopiju SQLite baze dok bot piše u nju."""
        temp_db = "data/backup_temp.db"
        try:
            source = sqlite3.connect(self.db_path)
            dest = sqlite3.connect(temp_db)
            with dest:
                source.backup(dest)
            source.close()
            dest.close()
            return temp_db
        except Exception as e:
            logger.error(f"Greška pri pravljenju kopije baze: {e}")
            return None

    async def send_to_telegram(self):
        if not self.bot_token or not self.chat_id:
            return

        logger.info("📤 Pravim backup baze za Telegram...")
        temp_db = self._create_safe_copy()
        
        if not temp_db:
            return

        try:
            # Pravimo lepo ime fajla sa datumom
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
            filename = f"solana_data_{timestamp}.db"
            
            url = f"https://api.telegram.org/bot{self.bot_token}/sendDocument"
            
            async with aiohttp.ClientSession() as session:
                # Pripremamo fajl za slanje
                with open(temp_db, 'rb') as f:
                    data = aiohttp.FormData()
                    data.add_field('chat_id', self.chat_id)
                    data.add_field('caption', f"📊 Solana Quant Data Collector\n🕒 Vreme: {timestamp}")
                    data.add_field('document', f, filename=filename)
                    
                    async with session.post(url, data=data) as response:
                        if response.status == 200:
                            logger.success(f"✅ Baza uspešno poslata na Telegram! ({filename})")
                        else:
                            error_text = await response.text()
                            logger.error(f"Greška pri slanju na Telegram: {error_text}")
                            
        except Exception as e:
            logger.error(f"Greška tokom Telegram backup-a: {e}")
            
        finally:
            # Uvek brišemo privremeni fajl
            if os.path.exists(temp_db):
                os.remove(temp_db)

    async def backup_loop(self, interval_hours=6):
        """Beskonačna petlja koja šalje bazu na Telegram na svakih X sati."""
        await asyncio.sleep(60) # Sačekaj minut pre prvog slanja da se baza napuni
        while True:
            await self.send_to_telegram()
            logger.info(f"💤 Sledeći Telegram backup za {interval_hours} sati.")
            await asyncio.sleep(interval_hours * 3600)