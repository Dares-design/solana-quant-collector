import logging
import aiohttp
from typing import Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from config.settings import settings

logger = logging.getLogger(__name__)

class SecurityGate:
    """
    Modul za bezbednosnu proveru tokena preko RugCheck-a i Helius RPC-ova.
    Implementira strogo pravilo: UNKNOWN NIKADA NIJE PASS.
    """

    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, TimeoutError)),
        reraise=True
    )
    async def _fetch_rugcheck(session: aiohttp.ClientSession, mint: str) -> Optional[Dict[str, Any]]:
        url = f"{settings.RUGCHECK_API_URL}/tokens/{mint}/report"
        try:
            async with session.get(url, timeout=10) as response:
                if response.status == 404:
                    logger.warning(f"RugCheck izveštaj nije pronađen (404) za mint: {mint}")
                    return None
                if response.status != 200:
                    logger.warning(f"RugCheck vratio status {response.status} za mint: {mint}")
                    return None
                return await response.json()
        except Exception as e:
            logger.error(f"Greška pri pozivu RugCheck API-ja za mint {mint}: {e}")
            raise

    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, TimeoutError)),
        reraise=True
    )
    async def _fetch_helius_data(session: aiohttp.ClientSession, mint: str) -> Optional[Dict[str, Any]]:
        if not settings.HELIUS_RPC_URL:
            logger.error("HELIUS_RPC_URL nije podešen u .env fajlu!")
            return None
        
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getAsset",
            "params": {"id": mint}
        }
        try:
            async with session.post(settings.HELIUS_RPC_URL, json=payload, timeout=10) as response:
                if response.status != 200:
                    logger.warning(f"Helius RPC vratio status {response.status} za mint: {mint}")
                    return None
                data = await response.json()
                return data.get("result")
        except Exception as e:
            logger.error(f"Greška pri pozivu Helius RPC-a za mint {mint}: {e}")
            raise

    @classmethod
    async def evaluate_token(cls, session: aiohttp.ClientSession, mint: str) -> Dict[str, Any]:
        """
        Vrši kompletnu proveru bezbednosti tokena.
        Pravilo: Ako bilo koji servis pukne ili vrati nepoznato, token NIJE bezbedan (is_safe = False).
        """
        result = {
            "is_safe": False,
            "rugcheck_score": None,
            "rugcheck_risks": None,
            "helius_verified": None,
            "lp_locked": None,
            "holder_count": None
        }

        try:
            # 1. Provera preko RugCheck-a
            rugcheck_data = await cls._fetch_rugcheck(session, mint)
            if not rugcheck_data:
                logger.info(f"Token {mint} odbačen: RugCheck nije vratio podatke (UNKNOWN -> REJECT).")
                return result

            result["rugcheck_score"] = rugcheck_data.get("score")
            result["rugcheck_risks"] = rugcheck_data.get("risks", [])
            
            # Provera da li je LP zaključan (ako postoji ta informacija u izveštaju)
            markets = rugcheck_data.get("markets", [])
            lp_locked = False
            if markets:
                for market in markets:
                    if market.get("lpLocked", False) or market.get("lpPercent", 0) > 80:
                        lp_locked = True
                        break
                result["lp_locked"] = lp_locked
            else:
                result["lp_locked"] = None

            # 2. Provera preko Helius RPC-a (Digital Asset Standard / getAsset)
            helius_data = await cls._fetch_helius_data(session, mint)
            if not helius_data:
                logger.info(f"Token {mint} odbačen: Helius RPC nije vratio podatke (UNKNOWN -> REJECT).")
                return result

            result["helius_verified"] = True
            
            # Ekstrakcija dodatnih bezbednosnih metrika ako postoje
            ownership = helius_data.get("ownership", {})
            frozen = ownership.get("frozen", False)
            
            # Osnovna logika bezbednosti (Prilagoditi po potrebi, npr. score < 5000, bez zamrznutih tokena itd.)
            score = result["rugcheck_score"]
            is_rugcheck_ok = score is not None and score < 5000
            
            if is_rugcheck_ok and not frozen:
                result["is_safe"] = True
                logger.info(f"Token {mint} PROŠAO bezbednosnu proveru (RugCheck score: {score}).")
            else:
                logger.info(f"Token {mint} ODBIJEN: RugCheck score {score}, frozen: {frozen}.")

        except Exception as e:
            logger.error(f"Kritična greška tokom bezbednosne provere za {mint}: {e}. Token se odbija.")
            result["is_safe"] = False

        return result