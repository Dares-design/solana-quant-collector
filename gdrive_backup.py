import os
import shutil
import asyncio
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from loguru import logger

# ID foldera sa tvog Google Drive-a (vidi uputstvo ispod kako da ga nađeš)
FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID", "TVOJ_FOLDER_ID_OVDE") 
SCOPES = ['https://www.googleapis.com/auth/drive.file']

class GDriveBackup:
    def __init__(self, db_path='data/solana_collector.db', creds_path='credentials.json'):
        self.db_path = db_path
        self.creds_path = creds_path
        self.service = self._authenticate()

    def _authenticate(self):
        try:
            creds = service_account.Credentials.from_service_account_file(self.creds_path, scopes=SCOPES)
            return build('drive', 'v3', credentials=creds)
        except Exception as e:
            logger.error(f"Greška pri autentifikaciji na Google Drive: {e}")
            return None

    async def upload_db(self):
        if not self.service:
            return
            
        logger.info("Započinjem backup baze na Google Drive...")
        
        # Pravimo sigurnu kopiju baze (da ne bismo čitali dok bot piše u nju)
        temp_db = "data/backup_temp.db"
        try:
            # SQLite komanda za bezbedno kopiranje baze
            import sqlite3
            source = sqlite3.connect(self.db_path)
            dest = sqlite3.connect(temp_db)
            with dest:
                source.backup(dest)
            source.close()
            dest.close()
            
            # Ime fajla na Drive-u
            filename = f"solana_data_{datetime.now().strftime('%Y%m%d_%H%M')}.db"
            
            file_metadata = {
                'name': filename,
                'parents': [FOLDER_ID]
            }
            media = MediaFileUpload(temp_db, mimetype='application/x-sqlite3', resumable=True)
            
            # Upload
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            logger.success(f"Uspešno uploadovan fajl: {filename} (ID: {file.get('id')})")
            
            # Brišemo privremeni fajl
            os.remove(temp_db)
            
        except Exception as e:
            logger.error(f"Greška tokom uploada na Google Drive: {e}")
            if os.path.exists(temp_db):
                os.remove(temp_db)

    async def backup_loop(self, interval_hours=6):
        """Pokreće se u pozadini i šalje bazu na svakih X sati."""
        while True:
            await self.upload_db()
            await asyncio.sleep(interval_hours * 3600)