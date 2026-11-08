import logging
import aiohttp
from datetime import datetime, timezone
from typing import List, Dict, Any, Set
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

class DexScreenerDiscovery:
    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, TimeoutError)),
        reraise=True
    )
    async def _fetch_json(session: aiohttp.ClientSession, url: str) -> Any:
        async with session.get(url, timeout=10) as response:
            if response.status != 200:
                logger.warning(f"DexScreener API status {response.status} za URL: {url}")
                response.raise_for_status()
            return await response.json()

    @classmethod
    async def fetch_latest_solana_pairs(cls, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        boosts_url = "https://api.dexscreener.com/token-boosts/latest/v1"
        takeovers_url = "https://api.dexscreener.com/community-takeovers/latest/v1"

        mint_addresses: Set[str] = set()

        for url in [boosts_url, takeovers_url]:
            try:
                data = await cls._fetch_json(session, url)
                if isinstance(data, list):
                    for item in data:
                        chain = item.get("chainId") or item.get("chain")
                        if chain == "solana":
                            address = item.get("tokenAddress") or item.get("address")
                            if address:
                                mint_addresses.add(address)
            except Exception as e:
                logger.error(f"Greška pri dohvatanju sa {url}: {e}")

        if not mint_addresses:
            return []

        mints_list = list(mint_addresses)
        chunk_size = 30
        solana_pairs = []

        for i in range(0, len(mints_list), chunk_size):
            chunk = mints_list[i:i + chunk_size]
            addresses_str = ",".join(chunk)
            details_url = f"https://api.dexscreener.com/tokens/v1/solana/{addresses_str}"

            try:
                pairs_data = await cls._fetch_json(session, details_url)
                if isinstance(pairs_data, list):
                    for pair in pairs_data:
                        if pair.get("chainId") == "solana":
                            base_token = pair.get("baseToken", {})
                            mint = base_token.get("address")
                            pair_address = pair.get("pairAddress")

                            if mint and pair_address:
                                # Ekstrakcija novih polja po ChatGPT-jevom predlogu
                                txns = pair.get("txns") or {}
                                m5_txns = txns.get("m5") or {}
                                volume = pair.get("volume") or {}
                                price_change = pair.get("priceChange") or {}
                                
                                # Normalizacija timestampa (ms u sekunde)
                                created_at = pair.get("pairCreatedAt")
                                if created_at and created_at > 10**12:
                                    created_at = created_at // 1000

                                solana_pairs.append({
                                    "mint": mint,
                                    "pair_address": pair_address,
                                    "symbol": base_token.get("symbol"),
                                    "name": base_token.get("name"),
                                    "dex": pair.get("dexId"),
                                    "price_native": pair.get("priceNative"),
                                    "price_usd": pair.get("priceUsd"),
                                    "liquidity_usd": (pair.get("liquidity") or {}).get("usd"),
                                    "volume_h24": volume.get("h24"),
                                    
                                    # NOVA POLJA
                                    "buys_m5": m5_txns.get("buys"),
                                    "sells_m5": m5_txns.get("sells"),
                                    "volume_m5": volume.get("m5"),
                                    "volume_h1": volume.get("h1"),
                                    "fdv": pair.get("fdv"),
                                    "market_cap": pair.get("marketCap"),
                                    "price_change_m5": price_change.get("m5"),
                                    "pair_created_at": created_at,
                                    
                                    "discovery_source": "boosts/takeovers"
                                })
            except Exception as e:
                logger.error(f"Greška pri batch dohvatanju detalja: {e}")

        return solana_pairs