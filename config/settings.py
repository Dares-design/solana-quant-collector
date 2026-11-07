import os
from dotenv import load_dotenv

# Učitavanje promenljivih iz .env fajla
load_dotenv()

class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "data/solana_collector.db")
    HELIUS_RPC_URL: str = os.getenv("HELIUS_RPC_URL", "")
    RUGCHECK_API_URL: str = os.getenv("RUGCHECK_API_URL", "https://api.rugcheck.xyz/v1")
    POLL_INTERVAL_SECONDS: int = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))

settings = Settings()