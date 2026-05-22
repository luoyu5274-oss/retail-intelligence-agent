import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
CHROMA_DIR = DATA_DIR / "chroma"
FINANCIAL_DATA_FILE = DATA_DIR / "financial_data.json"
CHAT_HISTORY_FILE = DATA_DIR / "chat_history.json"
SCRAPE_LOG_FILE = DATA_DIR / "scrape_log.json"

# Load .env from backend directory first, then fall back to env vars
load_dotenv(Path(__file__).parent / ".env")

# Priority: .env DEEPSEEK_API_KEY → ANTHROPIC_AUTH_TOKEN (Claude Code) → empty
DEEPSEEK_API_KEY = (
    os.getenv("DEEPSEEK_API_KEY")
    or os.getenv("ANTHROPIC_AUTH_TOKEN")
    or ""
)
_raw_base = os.getenv("DEEPSEEK_BASE_URL") or os.getenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_BASE_URL = _raw_base.replace("/anthropic", "")
DEEPSEEK_MODEL = "deepseek-chat"

BRAND_CONFIG = {
    "nike": {
        "name": "Nike",
        "ticker": "NKE",
        "color": "#FA5400",
        "currency": "USD",
        "currency_unit": "millions",
        "ir_url": "https://investors.nike.com/investors/financial-information/annual-reports/default.aspx",
        "reports": [
            {"file": "nke-20220531.pdf", "fiscal_year": "FY2022", "label": "FY2022 (5月)", "period_end": "2022-05-31"},
            {"file": "nke-20230531.pdf", "fiscal_year": "FY2023", "label": "FY2023 (5月)", "period_end": "2023-05-31"},
            {"file": "nke-20240531.pdf", "fiscal_year": "FY2024", "label": "FY2024 (5月)", "period_end": "2024-05-31"},
            {"file": "nke-20250531.pdf", "fiscal_year": "FY2025", "label": "FY2025 (5月)", "period_end": "2025-05-31"},
        ],
    },
    "adidas": {
        "name": "Adidas",
        "ticker": "ADS.DE",
        "color": "#1A1A1A",
        "currency": "EUR",
        "currency_unit": "millions",
        "ir_url": "https://www.adidas-group.com/en/investors/financial-reports/annual-reports/",
        "reports": [
            {"file": "annual-report-adidas-ar22.pdf", "fiscal_year": "FY2022", "label": "FY2022 (12月)", "period_end": "2022-12-31"},
            {"file": "annual-report-adidas-ar23.pdf", "fiscal_year": "FY2023", "label": "FY2023 (12月)", "period_end": "2023-12-31"},
            {"file": "annual-report-adidas-ar24.pdf", "fiscal_year": "FY2024", "label": "FY2024 (12月)", "period_end": "2024-12-31"},
            {"file": "annual-report-adidas-ar25.pdf", "fiscal_year": "FY2025", "label": "FY2025 (12月)", "period_end": "2025-12-31"},
        ],
    },
    "lululemon": {
        "name": "Lululemon",
        "ticker": "LULU",
        "color": "#8C1D40",
        "currency": "USD",
        "currency_unit": "millions",
        "ir_url": "https://investor.lululemon.com/financial-information/annual-reports",
        "reports": [
            {"file": "lulu-20230129.pdf", "fiscal_year": "FY2022", "label": "FY2022 (1月)", "period_end": "2023-01-29"},
            {"file": "lulu-20240128.pdf", "fiscal_year": "FY2023", "label": "FY2023 (1月)", "period_end": "2024-01-28"},
            {"file": "lulu-20250202.pdf", "fiscal_year": "FY2024", "label": "FY2024 (1月)", "period_end": "2025-02-02"},
            {"file": "lulu-20260201.pdf", "fiscal_year": "FY2025", "label": "FY2025 (1月)", "period_end": "2026-02-01"},
        ],
    },
}

CHUNK_SIZE = 3500
CHUNK_OVERLAP = 400
TOP_K_RESULTS = 6
MAX_FINANCIAL_PAGES = 60  # max pages to scan for financial data
