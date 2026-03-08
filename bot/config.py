import os
import shutil
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
EDGEX_BASE_URL = os.getenv("EDGEX_BASE_URL", "https://pro.edgex.exchange")
EDGEX_WS_URL = os.getenv("EDGEX_WS_URL", "wss://quote.edgex.exchange")

# Demo account for one-click login (临时, loaded from server env only)
DEMO_ACCOUNT_ID = os.getenv("DEMO_ACCOUNT_ID", "")
DEMO_STARK_KEY = os.getenv("DEMO_STARK_KEY", "")

# Tool paths — resolve via env, then shutil.which, then known fallbacks
EDGEX_CLI_PATH = os.getenv("EDGEX_CLI_PATH") or shutil.which("edgex") or "/home/ubuntu/.npm-global/bin/edgex"
DROID_CLI_PATH = os.getenv("DROID_CLI_PATH") or shutil.which("droid") or "/home/ubuntu/.local/bin/droid"

# Safety limits
MAX_POSITION_USD = 500
MAX_LEVERAGE = 5
LOSS_CIRCUIT_BREAKER_PCT = 0.20
MAX_CONCURRENT_POSITIONS = 3

# Static contract ID mapping (fallback — edgex-cli resolves symbols dynamically)
# This is used for order placement via Python SDK. The AI uses edgex-cli for live resolution.
CONTRACTS = {
    "BTC": "10000001", "ETH": "10000002", "SOL": "10000003", "BNB": "10000004",
    "LTC": "10000005", "LINK": "10000006", "AVAX": "10000007", "MATIC": "10000008",
    "XRP": "10000009", "DOGE": "10000010", "PEPE": "10000011", "AAVE": "10000012",
    "TRX": "10000013", "SUI": "10000014", "WIF": "10000015", "TIA": "10000016",
    "TON": "10000017", "LDO": "10000018", "ARB": "10000019", "OP": "10000020",
    "ORDI": "10000021", "JTO": "10000022", "JUP": "10000023", "UNI": "10000024",
    "ATOM": "10000027", "NEAR": "10000029", "SATS": "10000030", "ONDO": "10000031",
    "APE": "10000032", "CRV": "10000033", "AEVO": "10000034", "ENS": "10000035",
    "DOT": "10000036", "FET": "10000037", "WLD": "10000038", "ENA": "10000039",
    "DYDX": "10000040", "APT": "10000041", "ADA": "10000042", "SEI": "10000043",
    "MEME": "10000044", "PNUT": "10000045", "MOVE": "10000046", "TRUMP": "10000052",
    "MELANIA": "10000048", "PENGU": "10000049", "VIRTUAL": "10000050", "KAITO": "10000051",
    # US Equities (stock perpetuals)
    "TSLA": "10000273", "AAPL": "10000054", "NVDA": "10000272", "GOOG": "10000056",
    "AMZN": "10000057", "META": "10000058",
    # Commodities
    "XAUT": "10000234", "SILVER": "10000278",
    # Additional
    "CRCL": "10000253",
    # Index ETF perpetuals
    "QQQ": "10000284",
}

SYMBOL_BY_CONTRACT = {v: k for k, v in CONTRACTS.items()}
