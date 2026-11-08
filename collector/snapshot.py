import logging
import asyncio
import aiohttp
from discovery.dexscreener import DexScreenerDiscovery
from security.gate import SecurityGate
from collector.writer import DatabaseWriter
from config.settings import settings

logger = logging.getLogger(__name__)

class SnapshotCollector:
    def __init__(self, writer: DatabaseWriter):
        self.writer = writer

    async def run_polling_loop(self):
        logger.info(f"SnapshotCollector pokrenut. Interval: {settings.POLL_INTERVAL_SECONDS}s.")
        
        # IGNORISANJE SSL GRESKE ZA RUGCHECK (koju smo ranije podesili)
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

                        security_result = await SecurityGate.evaluate_token(session, mint)
                        
                        snapshot_payload = {**pair, **security_result}
                        await self.writer.enqueue_snapshot(snapshot_payload)

                    logger.info(f"Ciklus završen. Poslato {len(pairs)} tokena u red za upis.")

                except Exception as e:
                    logger.error(f"Greška tokom polling ciklusa: {e}")

                await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)