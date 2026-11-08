import logging
import aiosqlite
import asyncio
import os
from datetime import datetime, timezone
from typing import Dict, Any
from config.settings import settings

logger = logging.getLogger(__name__)

class DatabaseWriter:
    def __init__(self, db_path: str = settings.DATABASE_URL):
        self.db_path = db_path
        self.queue: asyncio.Queue = asyncio.Queue()
        self._running = False

    async def initialize(self):
        folder = os.path.dirname(self.db_path)
        if folder:
            os.makedirs(folder, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous=NORMAL;")
            
            # Kreiramo osnovnu tabelu ako ne postoji
            await db.execute("""
                CREATE TABLE IF NOT EXISTS token_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    mint TEXT NOT NULL,
                    pair_address TEXT NOT NULL,
                    symbol TEXT, name TEXT, dex TEXT,
                    price_native REAL, price_usd REAL, liquidity_usd REAL, volume_h24 REAL,
                    is_safe BOOLEAN NOT NULL, rugcheck_score INTEGER, lp_locked BOOLEAN, helius_verified BOOLEAN
                )
            """)
            
            # AUTO-MIGRACIJA: Dodajemo nove kolone ako ne postoje
            new_columns = {
                "buys_m5": "INTEGER", "sells_m5": "INTEGER",
                "volume_m5": "REAL", "volume_h1": "REAL",
                "fdv": "REAL", "market_cap": "REAL",
                "price_change_m5": "REAL", "pair_created_at": "INTEGER",
                "discovery_source": "TEXT"
            }
            
            # Provera postojećih kolona
            cursor = await db.execute("PRAGMA table_info(token_snapshots)")
            existing_cols = [row[1] for row in await cursor.fetchall()]
            
            for col, col_type in new_columns.items():
                if col not in existing_cols:
                    await db.execute(f"ALTER TABLE token_snapshots ADD COLUMN {col} {col_type}")
                    logger.info(f"Migracija: Dodata kolona {col}")

            # Kreiramo token_lifecycle tabelu
            await db.execute("""
                CREATE TABLE IF NOT EXISTS token_lifecycle (
                    mint TEXT PRIMARY KEY,
                    first_seen TEXT, first_pair_seen TEXT, last_seen TEXT,
                    last_price REAL, last_liquidity REAL,
                    current_pair_address TEXT, discovery_source TEXT,
                    status TEXT NOT NULL DEFAULT 'OBSERVED',
                    inactive_since TEXT
                )
            """)
            
            await db.commit()
        logger.info(f"Baza podataka spremna (V2): {self.db_path}")

    async def start(self):
        await self.initialize()
        self._running = True
        logger.info("DatabaseWriter V2 pokrenut.")
        
        while self._running:
            try:
                snapshot_data = await self.queue.get()
                if snapshot_data is None:
                    self.queue.task_done()
                    break
                
                await self._write_to_db(snapshot_data)
                self.queue.task_done()
            except Exception as e:
                logger.error(f"Greška u DatabaseWriter-u: {e}")

    async def stop(self):
        self._running = False
        await self.queue.put(None)

    async def enqueue_snapshot(self, data: Dict[str, Any]):
        await self.queue.put(data)

    async def _write_to_db(self, data: Dict[str, Any]):
        utc_now = datetime.now(timezone.utc).isoformat()
        
        # 1. Upis u snapshots
        query_snap = """
            INSERT INTO token_snapshots (
                timestamp, mint, pair_address, symbol, name, dex,
                price_native, price_usd, liquidity_usd, volume_h24,
                is_safe, rugcheck_score, lp_locked, helius_verified,
                buys_m5, sells_m5, volume_m5, volume_h1, fdv, market_cap,
                price_change_m5, pair_created_at, discovery_source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params_snap = (
            utc_now, data.get("mint"), data.get("pair_address"), data.get("symbol"), data.get("name"), data.get("dex"),
            data.get("price_native"), data.get("price_usd"), data.get("liquidity_usd"), data.get("volume_h24"),
            data.get("is_safe", False), data.get("rugcheck_score"), data.get("lp_locked"), data.get("helius_verified"),
            data.get("buys_m5"), data.get("sells_m5"), data.get("volume_m5"), data.get("volume_h1"), 
            data.get("fdv"), data.get("market_cap"), data.get("price_change_m5"), data.get("pair_created_at"),
            data.get("discovery_source")
        )

        # 2. Upis u token_lifecycle (UPSERT)
        query_life = """
            INSERT INTO token_lifecycle (
                mint, first_seen, first_pair_seen, last_seen, last_price, last_liquidity, current_pair_address, discovery_source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(mint) DO UPDATE SET
                last_seen = excluded.last_seen,
                last_price = COALESCE(excluded.last_price, token_lifecycle.last_price),
                last_liquidity = COALESCE(excluded.last_liquidity, token_lifecycle.last_liquidity),
                current_pair_address = excluded.current_pair_address
        """
        params_life = (
            data.get("mint"), utc_now, utc_now, utc_now, data.get("price_usd"), data.get("liquidity_usd"), data.get("pair_address"), data.get("discovery_source")
        )

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(query_snap, params_snap)
            await db.execute(query_life, params_life)
            await db.commit()