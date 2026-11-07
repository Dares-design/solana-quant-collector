import logging
import asyncio
import aiohttp
from typing import Set, Tuple
from discovery.dexscreener import DexScreenerDiscovery
from security.gate import SecurityGate
from collector.writer import DatabaseWriter
from config.settings import settings

logger = logging.getLogger(__name__)

class SnapshotCollector:
    """
    Modul zadužen za periodični polling (cikluse prikupljanja podataka).
    """
    def __init__(self, writer: DatabaseWriter):
        self.writer = writer
        # Pamti obrađene parove u trenutnoj sesiji da se izbegne bespotrebno gušenje,
        # mada se istorija svakako upisuje ako prođe interval.
        self.processed_tokens: Set[Tuple[str, str]] = set()

    async def run_polling_loop(self):
        """Glavna petlja koja se izvršava u zadatim vremenskim intervalima."""
        logger.info(f"SnapshotCollector pokrenut. Interval polling-a: {settings.POLL_INTERVAL_SECONDS} sekundi.")
        
        # Privremeno ignorišemo SSL greške za RugCheck
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            while True:
                try:
                    logger.info("Pokretanje novog ciklusa prikupljanja podataka...")
                    pairs = await DexScreenerDiscovery.fetch_latest_solana_pairs(session)
                    
                    for pair in pairs:
                        mint = pair.get("mint")
                        pair_address = pair.get("pair_address")
                        
                        if not mint or not pair_address:
                            continue

                        # Bezbednosna provera (Helius + RugCheck) - Pravilo 1
                        security_result = await SecurityGate.evaluate_token(session, mint)
                        
                        # Kreiranje paketa podataka za upis
                        snapshot_payload = {
                            **pair,
                            **security_result
                        }

                        # Prosljeđivanje isključivo Writer-u preko reda (Pravilo 4)
                        await self.writer.enqueue_snapshot(snapshot_payload)

                    logger.info(f"Ciklus završen. Posato {len(pairs)} tokena u red za upis.")

                except Exception as e:
                    logger.error(f"Greška tokom polling ciklusa: {e}")

                # Čekanje do sledećeg intervala
                await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)