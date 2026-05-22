"""Extract quarterly revenue + operating income from quarterly report PDFs.
Maps each report to a calendar quarter for cross-brand alignment."""

import json
import pdfplumber
from pathlib import Path
from config import BASE_DIR, DATA_DIR
from llm_client import extract_json

QUARTERLY_REPORTS = {
    "nike": [
        {"file": "Nike-Q1-25-Press-Release-FINAL.pdf", "fiscal_q": "Q1FY25",
         "months": "Jun-Aug 2024", "cal_q": "2024 Jul-Sep"},
        {"file": "Nike-Q2-25-Press-Release-FINAL.pdf", "fiscal_q": "Q2FY25",
         "months": "Sep-Nov 2024", "cal_q": "2024 Oct-Dec"},
        {"file": "Nike-Q3-25-Press-Release-FINAL.pdf", "fiscal_q": "Q3FY25",
         "months": "Dec 2024-Feb 2025", "cal_q": "2025 Jan-Mar"},
    ],
    "adidas": [
        {"file": "adidasAG_Q3_2024_Results_EN_final_aqkvyz.pdf", "fiscal_q": "Q3FY24",
         "months": "Jul-Sep 2024", "cal_q": "2024 Jul-Sep"},
        {"file": "adidasAG_Q1_2025_Results_EN_Final_mju03h.pdf", "fiscal_q": "Q1FY25",
         "months": "Jan-Mar 2025", "cal_q": "2025 Jan-Mar"},
        {"file": "adidasAG_Q2_2025_Results_EN_Final_pa2trd.pdf", "fiscal_q": "Q2FY25",
         "months": "Apr-Jun 2025", "cal_q": "2025 Apr-Jun"},
        {"file": "adidasAG_Q3_2025_Results_EN_Final_rylckc.pdf", "fiscal_q": "Q3FY25",
         "months": "Jul-Sep 2025", "cal_q": "2025 Jul-Sep"},
    ],
    "lululemon": [
        {"file": "lulu-20241027-Q3.pdf", "fiscal_q": "Q3FY24",
         "months": "Aug-Oct 2024", "cal_q": "2024 Jul-Sep"},
        {"file": "lulu-20250504-10Q.pdf", "fiscal_q": "Q1FY25",
         "months": "Feb-Apr 2025", "cal_q": "2025 Jan-Mar"},
        {"file": "lulu-2025.08.03-10Q.pdf", "fiscal_q": "Q2FY25",
         "months": "May-Jul 2025", "cal_q": "2025 Apr-Jun"},
        {"file": "lulu-20251102-10Q.pdf", "fiscal_q": "Q3FY25",
         "months": "Aug-Oct 2025", "cal_q": "2025 Jul-Sep"},
    ],
}

BRAND_NAMES = {"nike": "Nike", "adidas": "Adidas", "lululemon": "Lululemon"}
BRAND_CURRENCIES = {"nike": "USD", "adidas": "EUR", "lululemon": "USD"}
QUARTERLY_DATA_FILE = DATA_DIR / "quarterly_data.json"

EXTRACT_Q_PROMPT = """Extract ONLY these two numbers from this quarterly financial report:

Brand: {brand_name}
Period: {months} (Fiscal {fiscal_q})
Currency: {currency}

1. Revenue / Net Sales for the quarter (in millions of stated currency)
2. Operating Income / Operating Profit / Income from Operations for the quarter (in millions)

Look for:
- "Net revenues", "Revenue", "Revenues", "Net sales" — the quarter's total
- "Operating income", "Income from operations", "Operating profit", "Operating earnings"
- IMPORTANT: Take the CURRENT quarter figure ONLY, not the year-ago comparison
- IMPORTANT: If quarterly data is shown alongside year-to-date or full-year, pick the quarter

Return ONLY:
{{"revenue_m": <number>, "operating_income_m": <number>}}

Report text:
{text}"""


def extract_quarterly(brand_key: str, report: dict) -> dict | None:
    pdf_path = BASE_DIR / report["file"]
    if not pdf_path.exists():
        print(f"  [MISSING] {report['file']}")
        return None

    print(f"  Parsing {report['file']}...")
    with pdfplumber.open(pdf_path) as pdf:
        # Take first 30 pages (quarterly reports are short)
        text_parts = []
        for page in pdf.pages[:30]:
            t = page.extract_text() or ""
            text_parts.append(t)
        full_text = "\n".join(text_parts)[:20000]

    prompt = EXTRACT_Q_PROMPT.format(
        brand_name=BRAND_NAMES[brand_key],
        months=report["months"],
        fiscal_q=report["fiscal_q"],
        currency=BRAND_CURRENCIES[brand_key],
        text=full_text,
    )

    result = extract_json([
        {"role": "system", "content": "Extract quarterly revenue and operating income. Return ONLY valid JSON with two numbers. Values in millions."},
        {"role": "user", "content": prompt},
    ], max_tokens=2000)

    if isinstance(result, dict) and result:
        result["brand"] = BRAND_NAMES[brand_key]
        result["cal_quarter"] = report["cal_q"]
        result["fiscal_q"] = report["fiscal_q"]
        result["months"] = report["months"]
        result["currency"] = BRAND_CURRENCIES[brand_key]
        print(f"    rev={result.get('revenue_m')}M, oi={result.get('operating_income_m')}M")
        return result
    return None


def run_quarterly_extraction():
    all_data: dict[str, list] = {}
    for bk in ["nike", "adidas", "lululemon"]:
        all_data[bk] = []
        for rep in QUARTERLY_REPORTS[bk]:
            result = extract_quarterly(bk, rep)
            if result:
                all_data[bk].append(result)

    # Derive Nike Q4 FY2025 (Mar-May 2025 → Calendar 2025-Q2) from annual data
    _derive_nike_q4(all_data)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(QUARTERLY_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {QUARTERLY_DATA_FILE}")
    return all_data


def _derive_nike_q4(all_data: dict):
    """Derive Nike Q4 FY2025 from annual total minus Q1+Q2+Q3."""
    nike_qs = all_data.get("nike", [])
    # Find Q1, Q2, Q3
    q1_q3 = [e for e in nike_qs if e["fiscal_q"] in ("Q1FY25", "Q2FY25", "Q3FY25")]
    if len(q1_q3) != 3:
        return
    q_sum = sum(e["revenue_m"] for e in q1_q3)
    # Nike FY2025 annual revenue from dashboard data
    import json
    dash_file = DATA_DIR / "dashboard_data.json"
    if dash_file.exists():
        with open(dash_file, "r", encoding="utf-8") as f:
            dash = json.load(f)
        annual_rev = dash.get("nike", {}).get("FY2025", {}).get("revenue", {}).get("total")
        annual_oi = dash.get("nike", {}).get("FY2025", {}).get("operating_income")
        if annual_rev and annual_oi:
            q4_rev = round(annual_rev - q_sum, 1)
            q4_oi = round(annual_oi - sum(e["operating_income_m"] for e in q1_q3), 1)
            nike_qs.append({
                "brand": "Nike",
                "cal_quarter": "2025 Apr-Jun",
                "fiscal_q": "Q4FY25 (derived)",
                "months": "Mar-May 2025",
                "revenue_m": q4_rev,
                "operating_income_m": q4_oi,
                "currency": "USD",
            })
            print(f"  Derived Nike Q4 FY2025: rev={q4_rev}M, oi={q4_oi}M → Calendar 2025 Apr-Jun")


def build_calendar_chart(quarterly_data: dict) -> list[dict]:
    """Build chart data aligned by calendar quarter."""
    cal_quarters = set()
    for entries in quarterly_data.values():
        for e in entries:
            cal_quarters.add(e["cal_quarter"])

    # Sort by year then by month order (Jan, Apr, Jul, Oct)
    _month_order = {"jan": 1, "apr": 4, "jul": 7, "oct": 10}
    def _sort_key(q: str):
        parts = q.split()
        year = int(parts[0])
        mo = _month_order.get(parts[1].lower()[:3], 0)
        return (year, mo)

    sorted_qs = sorted(cal_quarters, key=_sort_key)

    chart = []
    for q in sorted_qs:
        row = {"quarter": q}
        for bk in ["nike", "adidas", "lululemon"]:
            name = BRAND_NAMES[bk]
            for entry in quarterly_data.get(bk, []):
                if entry["cal_quarter"] == q:
                    row[name] = entry.get("revenue_m")
                    row[f"{name}_oi"] = entry.get("operating_income_m")
        chart.append(row)
    return chart


def load_quarterly_data() -> dict:
    if QUARTERLY_DATA_FILE.exists():
        with open(QUARTERLY_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}
