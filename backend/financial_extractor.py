"""Extract structured financial metrics from PDF text using DeepSeek."""
import json
from pathlib import Path
from config import FINANCIAL_DATA_FILE, BRAND_CONFIG, DATA_DIR
from llm_client import extract_json

EXTRACTION_PROMPT = """You are a senior financial analyst. Extract key financial metrics from this annual report text. Be thorough: search the text carefully for every number. If a metric is mentioned in ANY form (tabular, prose, footnotes), capture it.

Brand: {brand_name}
Fiscal Year: {fiscal_year}
Currency: {currency} (report values in millions of the stated currency — do NOT convert currencies)

CRITICAL INSTRUCTIONS:
1. Scan EVERY page for the consolidated income statement / statement of operations / profit and loss statement
2. Look for sections labeled "ITEM 8" (for SEC 10-K filings), "Financial Statements", "Consolidated Statements of Income", "Consolidated Statements of Operations", "Income Statement", "Financial Review", or "Five-Year Summary"
3. In tables, extract the LATEST fiscal year column (not prior years)
4. Revenue may be labeled as: "Revenues", "Revenue", "Net sales", "Net revenues", "Total revenues", "Total net sales"
5. Gross profit = Revenue - Cost of sales/Cost of goods sold. Calculate it if you find both numbers but no explicit gross profit
6. CRITICAL — UNIT CONVERSION: All numbers must be in MILLIONS. If the report states "$5.1 billion", output 5100. If it states "$51,362 million", output 51362. If it states "$46,710,000,000" or "$46,710,000 thousand", output 46710. NEVER output numbers larger than 999,999 — if your extracted number is that large, divide by 1000 until it is below 999,999.
7. For margins: if the text states "Gross margin increased 50 basis points to 46.1%", extract 46.1. If raw numbers are given, calculate: Gross Profit / Revenue * 100
8. Operating Income may appear as: "Operating Income", "Income from Operations", "Operating Profit", "Operating Earnings". Search carefully — it is ALWAYS present in the income statement
9. Segment/geographic breakdowns — search for "Segment Information", "Geographic Information", "Operating Segments", "Revenue by Geography", "Net Revenue by Segment", "Revenues by Geographic Area". Regional data is often in a separate footnote table with headers like "North America", "EMEA", "Greater China"
10. Diluted EPS = "Diluted earnings per share", "Diluted net income per common share", "Diluted EPS"
11. YoY growth: look for percentage changes stated in the Management Discussion section, or calculate from the current and prior year revenue if stated side-by-side

Report text:
{text}

Return ONLY a valid JSON object with this exact structure:

{{
  "brand": "{brand_name}",
  "fiscal_year": "{fiscal_year}",
  "currency": "{currency}",
  "revenue": {{
    "total": <number|null>,
    "yoy_growth_pct": <number|null>,
    "north_america": <number|null>,
    "europe_middle_east_africa": <number|null>,
    "asia_pacific_latin_america": <number|null>,
    "greater_china": <number|null>,
    "dtc": <number|null>,
    "wholesale": <number|null>,
    "digital_pct": <number|null>
  }},
  "gross_profit": <number|null>,
  "gross_margin_pct": <number|null>,
  "operating_income": <number|null>,
  "operating_margin_pct": <number|null>,
  "net_income": <number|null>,
  "net_margin_pct": <number|null>,
  "eps_diluted": <number|null>,
  "inventory": <number|null>,
  "capex": <number|null>,
  "free_cash_flow": <number|null>,
  "store_count": <integer|null>,
  "employees": <integer|null>,
  "key_highlights": [<max 5 concise highlight strings in Chinese>],
  "strategic_priorities": [<max 5 strategic priority strings in Chinese>],
  "risks": [<max 3 key risk strings in Chinese>]
}}"""

RETRY_PROMPT = """You previously attempted to extract financial data but missed some critical fields. The brand is {brand_name}, Fiscal Year {fiscal_year}, Currency {currency} (millions).

Please CAREFULLY re-examine the report text below and fill in the missing metrics. Focus especially on:
{focus_fields}

Report text:
{text}

Return ONLY a valid JSON with the SAME structure as the original request, but this time ensure ALL fields you can find are populated. Do not return null for fields that exist in the text."""

# ── Monetary fields that should be in millions ──────────────────────────
_MONETARY_FIELDS = [
    (("revenue", "total"),),
    (("revenue", "north_america"),),
    (("revenue", "europe_middle_east_africa"),),
    (("revenue", "asia_pacific_latin_america"),),
    (("revenue", "greater_china"),),
    (("revenue", "dtc"),),
    (("revenue", "wholesale"),),
    ("gross_profit",),
    ("operating_income",),
    ("net_income",),
    ("inventory",),
    ("capex",),
    ("free_cash_flow",),
]

# Fields that are percentages (0-100 scale, not 0-1)
_PCT_FIELDS = [
    (("revenue", "yoy_growth_pct"),),
    (("revenue", "digital_pct"),),
    ("gross_margin_pct",),
    ("operating_margin_pct",),
    ("net_margin_pct",),
]

# Critical fields that should never be null
_CRITICAL_FIELDS = [
    "revenue.total",
    "gross_profit",
    "gross_margin_pct",
    "operating_income",
    "net_income",
]


def _get_nested(data: dict, path: str):
    """Get value at dot-separated path, e.g. 'revenue.total'."""
    parts = path.split(".")
    val = data
    for p in parts:
        if isinstance(val, dict):
            val = val.get(p)
        else:
            return None
    return val


def _set_nested(data: dict, path: str, value):
    """Set value at dot-separated path."""
    parts = path.split(".")
    d = data
    for p in parts[:-1]:
        if p not in d or not isinstance(d[p], dict):
            d[p] = {}
        d = d[p]
    d[parts[-1]] = value


def _normalize_units(result: dict) -> dict:
    """Detect and fix unit inconsistencies — e.g. LLM returns raw dollars instead of millions."""
    rev_total = _get_nested(result, "revenue.total")
    if rev_total is None or not isinstance(rev_total, (int, float)):
        return result

    # Heuristic: revenue > 500,000 million is impossible for these brands
    if rev_total <= 500_000:
        return result

    # Determine scale factor
    if rev_total > 10_000_000:
        divisor = 1_000_000
    elif rev_total > 500_000:
        divisor = 1_000
    else:
        return result

    # Apply divisor to all monetary fields
    for field_path in _MONETARY_FIELDS:
        if isinstance(field_path[0], tuple):
            path = ".".join(field_path[0])
        else:
            path = field_path[0]

        val = _get_nested(result, path)
        if val is not None and isinstance(val, (int, float)):
            _set_nested(result, path, round(val / divisor, 1))

    return result


def _validate_extraction(result: dict) -> list[str]:
    """Return list of critical field paths that are null."""
    missing = []
    for path in _CRITICAL_FIELDS:
        val = _get_nested(result, path)
        if val is None:
            missing.append(path)
    return missing


def _describe_missing(missing: list[str], brand_name: str) -> str:
    """Build a human-readable focus instruction for retry."""
    descriptions = {
        "revenue.total": f"- {brand_name}'s total revenue/net sales",
        "gross_profit": f"- {brand_name}'s gross profit (revenue minus cost of sales / cost of goods sold)",
        "gross_margin_pct": f"- {brand_name}'s gross margin percentage",
        "operating_income": f"- {brand_name}'s operating income (profit from operations)",
        "net_income": f"- {brand_name}'s net income/net earnings",
    }
    return "\n".join(descriptions.get(m, f"- {m}") for m in missing)


# Brand-specific segment mapping notes for the extraction prompt
BRAND_SEGMENT_NOTES = {
    "adidas": """Adidas-specific geographic segment guidance:
Adidas reports segments under "Operating Segments" / "Segment Information" in the notes (often page 180+).
Look for a table with columns for each segment listing "Net sales" / "Revenue". Adidas operating segments:
  Europe, Emerging Markets, North America, Greater China, Latin America, Japan, South Korea
Map them to the JSON output fields:
  - north_america = "North America"
  - europe_middle_east_africa = "Europe" + "Emerging Markets" (sum both if both have numbers)
  - greater_china = "Greater China"
  - asia_pacific_latin_america = "Latin America" + "Japan" + "South Korea" (sum all that have numbers)
Each segment's net sales is usually a single number in millions of EUR. Search carefully for this table — it IS in the text.""",
    "nike": """Nike-specific geographic segment guidance:
Nike reports "Revenues by Geographic Area" or "Segment Information" in its 10-K footnotes.
Look for columns: North America, Europe Middle East & Africa (EMEA), Greater China, Asia Pacific & Latin America (APLA).
Map directly: north_america, europe_middle_east_africa, greater_china, asia_pacific_latin_america.""",
    "lululemon": """Lululemon-specific geographic segment guidance:
Lululemon reports geographic revenue in its footnotes or MD&A. Look for Americas / North America,
China Mainland / Greater China, and Rest of World / Asia Pacific categories.
Map: north_america = "Americas" or "North America", greater_china = "China Mainland",
asia_pacific_latin_america = sum of Asia Pacific / Rest of World amounts.""",
}

def extract_financials_for_report(brand_key: str, fiscal_year: str, financial_text: str) -> dict:
    """Call LLM to extract structured data from a report's financial text.
    Includes unit normalization and focused retry for missing critical fields."""
    cfg = BRAND_CONFIG[brand_key]
    seg_notes = BRAND_SEGMENT_NOTES.get(brand_key, "")

    def _do_extract(text_budget: int = 28000) -> dict:
        prompt = EXTRACTION_PROMPT.format(
            brand_name=cfg["name"],
            fiscal_year=fiscal_year,
            currency=cfg["currency"],
            text=financial_text[:text_budget],
        )
        result = extract_json([
            {"role": "system", "content": "You are a precise financial data extractor. Return only valid JSON. Output ALL numbers in MILLIONS of the stated currency."},
            {"role": "user", "content": prompt},
        ], max_tokens=8000)
        if isinstance(result, list):
            result = {}
        return result

    result = _do_extract()
    if not result or not isinstance(result, dict):
        result = {}

    # Step 1: Normalize units
    result = _normalize_units(result)

    # Step 2: Check for missing critical fields, retry once with focused prompt
    missing = _validate_extraction(result)
    if missing:
        focus = _describe_missing(missing, cfg["name"])
        retry_prompt = RETRY_PROMPT.format(
            brand_name=cfg["name"],
            fiscal_year=fiscal_year,
            currency=cfg["currency"],
            focus_fields=focus,
            text=financial_text[:30000],
        )
        retry = extract_json([
            {"role": "system", "content": "You are a precise financial data extractor. Find the missing metrics. Return only valid JSON. ALL numbers in MILLIONS."},
            {"role": "user", "content": retry_prompt},
        ], max_tokens=8000)
        if isinstance(retry, dict) and retry:
            retry = _normalize_units(retry)
            for field_path in missing:
                retry_val = _get_nested(retry, field_path)
                if retry_val is not None:
                    _set_nested(result, field_path, retry_val)

    # Step 3: Cross-calculate between margins and absolute values
    rev_total = _get_nested(result, "revenue.total")
    op_margin = _get_nested(result, "operating_margin_pct")
    op_income = _get_nested(result, "operating_income")
    gross_profit = _get_nested(result, "gross_profit")
    gross_margin = _get_nested(result, "gross_margin_pct")
    net_income = _get_nested(result, "net_income")
    net_margin = _get_nested(result, "net_margin_pct")

    # Forward: margin → income
    if op_income is None and rev_total is not None and op_margin is not None:
        _set_nested(result, "operating_income", round(rev_total * op_margin / 100, 1))
    if gross_profit is None and rev_total is not None and gross_margin is not None:
        _set_nested(result, "gross_profit", round(rev_total * gross_margin / 100, 1))
    if net_income is None and rev_total is not None and net_margin is not None:
        _set_nested(result, "net_income", round(rev_total * net_margin / 100, 1))

    # Reverse: income → margin (more reliable — LLM extracts absolute numbers better than margins)
    if rev_total is not None and rev_total != 0:
        if op_income is not None and op_margin is None:
            _set_nested(result, "operating_margin_pct", round(op_income / rev_total * 100, 1))
        if gross_profit is not None and gross_margin is None:
            _set_nested(result, "gross_margin_pct", round(gross_profit / rev_total * 100, 1))
        if net_income is not None and net_margin is None:
            _set_nested(result, "net_margin_pct", round(net_income / rev_total * 100, 1))
        # Always recalculate net/op margin from raw numbers when both exist — LLM margins are less reliable
        if op_income is not None:
            _set_nested(result, "operating_margin_pct", round(op_income / rev_total * 100, 1))
        if net_income is not None:
            _set_nested(result, "net_margin_pct", round(net_income / rev_total * 100, 1))

    # Step 4: Normalize percentages — if margins are in 0-1 decimal form, multiply by 100.
    # Skip margin fields that were already calculated from absolute numbers (more reliable).
    _CALCULATED_PCTS = {"operating_margin_pct", "net_margin_pct", "gross_margin_pct"}
    for pct_path in _PCT_FIELDS:
        if isinstance(pct_path[0], tuple):
            path = ".".join(pct_path[0])
        else:
            path = pct_path[0]
        field_name = path.split(".")[-1]
        if field_name in _CALCULATED_PCTS:
            continue  # already handled in Step 3
        val = _get_nested(result, path)
        if val is not None and isinstance(val, (int, float)):
            if 0 < abs(val) < 1:
                _set_nested(result, path, round(val * 100, 1))

    result["brand_key"] = brand_key
    result["fiscal_year"] = fiscal_year

    # Step 5: If ALL regional fields are null, do a targeted extraction just for segments
    regional_fields = ["north_america", "europe_middle_east_africa", "greater_china", "asia_pacific_latin_america"]
    all_region_null = all(_get_nested(result, f"revenue.{f}") is None for f in regional_fields)
    if all_region_null:
        # Extract only pages containing segment data for targeted extraction
        segment_pages = []
        for line in financial_text.split("---PAGE BREAK---"):
            lower = line.lower()
            if any(kw in lower for kw in ["operating segment", "segmental information",
                "segment information", "net sales by segment", "revenue by geography",
                "net sales (third parties)", "broken down by segment"]):
                segment_pages.append(line.strip())
        seg_text = "\n\n".join(segment_pages)[:15000] if segment_pages else financial_text[:15000]

        region_prompt = f"""Find the geographic segment revenue in this annual report footnote.
Brand: {cfg["name"]}, Fiscal Year: {fiscal_year}, Currency: {cfg["currency"]} (already in millions).

Look for a table like "Segmental information" or "Net sales by segment". The table lists regions
(e.g. Europe, North America, Greater China, Emerging Markets, Latin America, Japan) with revenue numbers.
There may be two year columns — always pick the LATEST / most recent / current year column.
Extract ALL segment labels EXACTLY as they appear and their revenue values.

Return ONLY:
{{"segments": [{{"name": "<exact segment label>", "revenue": <number in millions>}}, ...]}}

Segment footnote text:
{seg_text}"""
        region_result = extract_json([
            {"role": "system", "content": "You are a precise data extractor. Extract geographic segment revenue EXACTLY as labeled. Return only valid JSON."},
            {"role": "user", "content": region_prompt},
        ], max_tokens=2000)
        if isinstance(region_result, dict):
            segments = region_result.get("segments", [])
            if segments:
                # Map Adidas segment labels to our standard categories
                seg_map = _map_segments_to_regions(segments, brand_key)
                for f in regional_fields:
                    v = seg_map.get(f)
                    if v is not None:
                        _set_nested(result, f"revenue.{f}", v)

    return result


def _map_segments_to_regions(segments: list[dict], brand_key: str) -> dict[str, float]:
    """Map raw segment labels from the LLM to our standard regional categories."""
    result: dict[str, float] = {}
    name_to_val: dict[str, float] = {}
    for s in segments:
        name = (s.get("name") or "").strip().lower()
        val = s.get("revenue")
        if name and val is not None and isinstance(val, (int, float)):
            name_to_val[name] = float(val)

    if brand_key == "adidas":
        # Adidas segments: Europe, Emerging Markets, North America, Greater China,
        # Latin America, Japan, South Korea, Russia/CIS (varies by year)
        def _get(*aliases):
            total = 0.0
            for a in aliases:
                for n, v in name_to_val.items():
                    if a in n:
                        total += v
                        break
            return round(total, 1) if total > 0 else None

        result["north_america"] = _get("north america")
        result["europe_middle_east_africa"] = _get("europe", "emea", "emerging markets", "russia/cis", "middle east", "africa")
        result["greater_china"] = _get("greater china", "china")
        result["asia_pacific_latin_america"] = _get("latin america", "japan", "south korea", "asia pacific", "asia-pacific", "apac")
    elif brand_key == "nike":
        result["north_america"] = name_to_val.get("north america")
        result["europe_middle_east_africa"] = name_to_val.get("europe, middle east & africa") or name_to_val.get("emea")
        result["greater_china"] = name_to_val.get("greater china")
        result["asia_pacific_latin_america"] = name_to_val.get("asia pacific & latin america") or name_to_val.get("apla")
    elif brand_key == "lululemon":
        result["north_america"] = name_to_val.get("americas") or name_to_val.get("north america") or name_to_val.get("united states") or name_to_val.get("us") or name_to_val.get("canada")
        result["greater_china"] = name_to_val.get("china mainland") or name_to_val.get("greater china") or name_to_val.get("china")
        result["asia_pacific_latin_america"] = name_to_val.get("rest of world") or name_to_val.get("asia pacific") or name_to_val.get("australia") or name_to_val.get("apac")

    return result


def load_financial_data() -> dict:
    """Load cached financial data from disk, with post-processing to fix missing margins."""
    if not FINANCIAL_DATA_FILE.exists():
        return {}
    with open(FINANCIAL_DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Post-process: recalculate margins from absolute numbers for all entries
    for brand_data in data.values():
        for entry in brand_data.values():
            if not isinstance(entry, dict):
                continue
            rev = _get_nested(entry, "revenue.total")
            if rev is None or rev == 0:
                continue
            oi = entry.get("operating_income")
            gp = entry.get("gross_profit")
            ni = entry.get("net_income")
            if oi is not None:
                entry["operating_margin_pct"] = round(oi / rev * 100, 1)
            if gp is not None:
                entry["gross_margin_pct"] = round(gp / rev * 100, 1)
            if ni is not None:
                entry["net_margin_pct"] = round(ni / rev * 100, 1)
    return data


def save_financial_data(data: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(FINANCIAL_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_chart_data(financial_data: dict) -> dict:
    """Transform raw financial data into chart-ready structures."""
    brand_keys = ["nike", "adidas", "lululemon"]
    brand_names = {k: BRAND_CONFIG[k]["name"] for k in brand_keys}
    brand_colors = {k: BRAND_CONFIG[k]["color"] for k in brand_keys}

    # Build (brand_key, fiscal_year) -> label mapping
    fy_to_label: dict[tuple[str, str], str] = {}
    for bk in brand_keys:
        for rep in BRAND_CONFIG[bk]["reports"]:
            fy_to_label[(bk, rep["fiscal_year"])] = rep["label"]

    # X-axis: all unique fiscal years across all brands
    all_years: set[str] = set()
    for brand_data in financial_data.values():
        all_years.update(brand_data.keys())
    years = sorted(all_years)

    def get(brand, year, *keys):
        val = financial_data.get(brand, {}).get(year, {})
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return None
        return val

    # ── Revenue comparison ──────────────────────
    revenue_chart = []
    for yr in years:
        row: dict = {"year": yr}
        for bk in brand_keys:
            v = get(bk, yr, "revenue", "total")
            if v is not None:
                row[brand_names[bk]] = v
        revenue_chart.append(row)

    # ── Margin trends ───────────────────────────
    margin_chart = []
    for yr in years:
        row: dict = {"year": yr}
        for bk in brand_keys:
            gm = get(bk, yr, "gross_margin_pct")
            if gm is not None:
                row[f"{brand_names[bk]} 毛利率"] = round(gm, 1)
            om = get(bk, yr, "operating_margin_pct")
            if om is not None:
                row[f"{brand_names[bk]} 营业利润率"] = round(om, 1)
        margin_chart.append(row)

    # ── YoY growth ──────────────────────────────
    # Always calculate from revenue data — LLM's yoy_growth_pct is unreliable.
    growth_chart = []
    for yr in years:
        row: dict = {"year": yr}
        for bk in brand_keys:
            idx = years.index(yr)
            if idx > 0:
                prev_yr = years[idx - 1]
                cur_rev = get(bk, yr, "revenue", "total")
                prev_rev = get(bk, prev_yr, "revenue", "total")
                if cur_rev is not None and prev_rev is not None and prev_rev != 0:
                    row[brand_names[bk]] = round((cur_rev - prev_rev) / prev_rev * 100, 1)
        growth_chart.append(row)

    # ── Regional revenue (latest year per brand) ─
    region_chart = []
    region_keys = [
        ("north_america", "北美"),
        ("europe_middle_east_africa", "欧洲/中东/非洲"),
        ("greater_china", "大中华区"),
        ("asia_pacific_latin_america", "亚太/拉美"),
    ]
    for bk in brand_keys:
        brand_years = sorted(financial_data.get(bk, {}).keys())
        if not brand_years:
            continue
        latest = brand_years[-1]
        entry: dict = {"brand": brand_names[bk]}
        for rk, rlabel in region_keys:
            v = get(bk, latest, "revenue", rk)
            if v is not None:
                entry[rlabel] = v
        entry["year"] = fy_to_label.get((bk, latest), latest)
        region_chart.append(entry)

    # ── Radar chart ─────────────────────────────
    radar_dims = [
        ("gross_margin_pct", "毛利率", 100),
        ("operating_margin_pct", "营业利润率", 30),
        ("net_margin_pct", "净利润率", 25),
    ]
    radar_data: list[dict] = []
    latest_by_brand: dict[str, str] = {}
    for bk in brand_keys:
        ys = sorted(financial_data.get(bk, {}).keys())
        if ys:
            latest_by_brand[bk] = ys[-1]

    for dim_key, dim_label, max_val in radar_dims:
        row: dict = {"metric": dim_label}
        for bk in brand_keys:
            yr = latest_by_brand.get(bk)
            if not yr:
                continue
            v = get(bk, yr, dim_key)
            if v is not None:
                row[brand_names[bk]] = round(min(v / max_val * 100, 100), 1)
        radar_data.append(row)

    row = {"metric": "营收增速"}
    for bk in brand_keys:
        yr = latest_by_brand.get(bk)
        if not yr:
            continue
        # Calculate YoY growth from revenue (same as growth_chart)
        ys = sorted(financial_data.get(bk, {}).keys())
        idx = ys.index(yr) if yr in ys else -1
        if idx > 0:
            cur = get(bk, yr, "revenue", "total")
            prev = get(bk, ys[idx - 1], "revenue", "total")
            if cur and prev and prev != 0:
                yoy = (cur - prev) / prev * 100
                row[brand_names[bk]] = round(min(max(yoy + 20, 0) / 40 * 100, 100), 1)
    radar_data.append(row)

    # ── Summary table ───────────────────────────
    summary: list[dict] = []
    metrics = [
        ("revenue.total", "营业收入 (M)"),
        ("gross_margin_pct", "毛利率 (%)"),
        ("operating_margin_pct", "营业利润率 (%)"),
        ("net_margin_pct", "净利润率 (%)"),
        ("revenue.yoy_growth_pct", "营收增速 (%)"),
        ("inventory", "库存 (M)"),
    ]
    for bk in brand_keys:
        ys = sorted(financial_data.get(bk, {}).keys())
        for i, yr in enumerate(ys):
            entry = {"brand": brand_names[bk], "year": fy_to_label.get((bk, yr), yr)}
            for mpath, mlabel in metrics:
                if mpath == "revenue.yoy_growth_pct":
                    # Calculate YoY from revenue — LLM values are unreliable
                    if i > 0:
                        prev_yr = ys[i - 1]
                        cur = get(bk, yr, "revenue", "total")
                        prev = get(bk, prev_yr, "revenue", "total")
                        if cur and prev and prev != 0:
                            entry[mlabel] = round((cur - prev) / prev * 100, 1)
                    continue
                parts = mpath.split(".")
                v = financial_data.get(bk, {}).get(yr, {})
                for p in parts:
                    v = v.get(p) if isinstance(v, dict) else v
                entry[mlabel] = v
            summary.append(entry)

    return {
        "revenue_chart": revenue_chart,
        "margin_chart": margin_chart,
        "growth_chart": growth_chart,
        "region_chart": region_chart,
        "radar_data": radar_data,
        "summary": summary,
        "brand_colors": brand_colors,
        "brand_names": brand_names,
    }
