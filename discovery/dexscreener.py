import logging
import aiohttp
from typing import List, Dict, Any, Set
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

class DexScreenerDiscovery:
    """
    Napredni modul zadužen za pronalaženje kvalitetnijih Solana tokena 
    kroz DexScreener Boosts i Community Takeovers endpointe, sa batch obogaćivanjem.
    """

    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, TimeoutError)),
        reraise=True
    )
    async def _fetch_json(session: aiohttp.ClientSession, url: str) -> Any:
        """Pomoćna metoda za mrežne pozive sa ugrađenim retry mehanizmom."""
        async with session.get(url, timeout=10) as response:
            if response.status != 200:
                logger.warning(f"DexScreener API vratio statusni kod {response.status} za URL: {url}")
                response.raise_for_status()
            return await response.json()

    @classmethod
    async def fetch_latest_solana_pairs(cls, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        """
        Dohvata tokene preko /token-boosts/latest/v1 i /community-takeovers/latest/v1,
        filtrira Solana mrežu, a zatim povlači detaljne podatke u batch-evima preko /tokens/v1/solana/{addresses}.
        """
        boosts_url = "https://api.dexscreener.com/token-boosts/latest/v1"
        takeovers_url = "https://api.dexscreener.com/community-takeovers/latest/v1"

        mint_addresses: Set[str] = set()

        # 1. Prikupljanje boost-ovanih tokena
        try:
            boosts_data = await cls._fetch_json(session, boosts_url)
            if isinstance(boosts_data, list):
                for item in boosts_data:
                    chain = item.get("chainId") or item.get("chain")
                    if chain == "solana":
                        address = item.get("tokenAddress") or item.get("address")
                        if address:
                            mint_addresses.add(address)
        except Exception as e:
            logger.error(f"Greška pri dohvatanju token-boosts: {e}")

        # 2. Prikupljanje community-takeover tokena
        try:
            takeovers_data = await cls._fetch_json(session, takeovers_url)
            if isinstance(takeovers_data, list):
                for item in takeovers_data:
                    chain = item.get("chainId") or item.get("chain")
                    if chain == "solana":
                        address = item.get("tokenAddress") or item.get("address")
                        if address:
                            mint_addresses.add(address)
        except Exception as e:
            logger.error(f"Greška pri dohvatanju community-takeovers: {e}")

        if not mint_addresses:
            logger.info("Nisu pronađeni novi Solana tokeni kroz Boosts/Takeovers endpointe u ovom ciklusu.")
            return []

        logger.info(f"Pronađeno {len(mint_addresses)} jedinstvenih Solana mint adresa iz Boosts/Takeovers. Dohvatanje detalja...")

        # 3. Batch obogaćivanje podataka preko /tokens/v1/solana/{addresses} (do 30 adresa po zahtevu)
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
                                solana_pairs.append({
                                    "mint": mint,
                                    "pair_address": pair_address,
                                    "symbol": base_token.get("symbol"),
                                    "name": base_token.get("name"),
                                    "dex": pair.get("dexId"),
                                    "price_native": pair.get("priceNative"),
                                    "price_usd": pair.get("priceUsd"),
                                    "liquidity_usd": pair.get("liquidity", {}).get("usd"),
                                    "volume_h24": pair.get("volume", {}).get("h24")
                                })
            except Exception as e:
                logger.error(f"Greška pri batch dohvatanju detalja tokena za chunk: {e}")

        logger.info(f"Uspešno formatirano {len(solana_pairs)} Solana parova iz naprednih endpointa.")
        return solana_pairs