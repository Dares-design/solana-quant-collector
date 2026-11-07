import logging
import aiosqlite
import asyncio
import os
from datetime import datetime, timezone
from typing import Dict, Any
from config.settings import settings

logger = logging.getLogger(__name__)

class DatabaseWriter:
    """
    Jedini entitet koji upravlja upisom u SQLite bazu podataka (Single Writer Pattern).
    Koristi asyncio.Queue za primanje zahteva za upis.
    """
    def __init__(self, db_path: str = settings.DATABASE_URL):
        self.db_path = db_path
        self.queue: asyncio.Queue = asyncio.Queue()
        self._running = False

    async def initialize(self):
        """Inicijalizuje bazu podataka i kreira tabelu ako ne postoji."""
        # --- OVA LINIJA OSIGURAVA DA FOLDER POSTOJI ---
        folder = os.path.dirname(self.db_path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        # ----------------------------------------------

        async with aiosqlite.connect(self.db_path) as db:
            # WAL mod za bolje performanse i istovremeni pristup
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous=NORMAL;")
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS token_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    mint TEXT NOT NULL,
                    pair_address TEXT NOT NULL,
                    symbol TEXT,
                    name TEXT,
                    dex TEXT,
                    price_native REAL,
                    price_usd REAL,
                    liquidity_usd REAL,
                    volume_h24 REAL,
                    is_safe BOOLEAN NOT NULL,
                    rugcheck_score INTEGER,
                    lp_locked BOOLEAN,
                    helius_verified BOOLEAN
                )
            """)
            # Indeksiranje za bržu pretragu po paru i mintu (istorija)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_mint_pair 
                ON token_snapshots (mint, pair_address)
            """)
            await db.commit()
        logger.info(f"Baza podataka uspešno inicijalizovana na putanji: {self.db_path}")

    async def start(self):
        """Pokreće pozadinski worker task koji obrađuje red za upis (Writer Task)."""
        await self.initialize()
        self._running = True
        logger.info("DatabaseWriter task je pokrenut i sluša queue.")
        
        while self._running:
            try:
                # Čeka podatke iz reda
                snapshot_data = await self.queue.get()
                if snapshot_data is None:
                    self.queue.task_done()
                    break
                
                await self._write_to_db(snapshot_data)
                self.queue.task_done()
            except Exception as e:
                logger.error(f"Greška u DatabaseWriter worker-u: {e}")

    async def stop(self):
        """Zaustavlja writer task."""
        self._running = False
        await self.queue.put(None)

    async def enqueue_snapshot(self, data: Dict[str, Any]):
        """Omogućava drugim taskovima da ubace snapshot u red za upis."""
        await self.queue.put(data)

    async def _write_to_db(self, data: Dict[str, Any]):
        """Izvršava append-only upis u SQLite bazu."""
        # Pravilo 6: Obavezna UTC vremenska oznaka
        utc_now = datetime.now(timezone.utc).isoformat()
        
        query = """
            INSERT INTO token_snapshots (
                timestamp, mint, pair_address, symbol, name, dex,
                price_native, price_usd, liquidity_usd, volume_h24,
                is_safe, rugcheck_score, lp_locked, helius_verified
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        # Pravilo 7: Nedostajući podaci se upisuju kao NULL (None u Python-u), nikada kao 0.
        params = (
            utc_now,
            data.get("mint"),
            data.get("pair_address"),
            data.get("symbol"),
            data.get("name"),
            data.get("dex"),
            data.get("price_native"),
            data.get("price_usd"),
            data.get("liquidity_usd"),
            data.get("volume_h24"),
            data.get("is_safe", False),
            data.get("rugcheck_score"),
            data.get("lp_locked"),
            data.get("helius_verified")
        )

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(query, params)
            await db.commit()
            logger.debug(f"Upisan snapshot za mint: {data.get('mint')} | pair: {data.get('pair_address')}")