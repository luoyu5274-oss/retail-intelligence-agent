"""Extract and chunk text from annual report PDFs."""
import re
import pdfplumber
from pathlib import Path
from config import BASE_DIR, BRAND_CONFIG, CHUNK_SIZE, CHUNK_OVERLAP, MAX_FINANCIAL_PAGES


def _clean_text(text: str) -> str:
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {3,}', '  ', text)
    return text.strip()


def extract_pages(pdf_path: Path) -> list[dict]:
    """Return list of {page_num, text} for every page in the PDF."""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            tables = page.extract_tables() or []
            table_text = ""
            for tbl in tables:
                for row in (tbl or []):
                    if row:
                        row_str = " | ".join(str(c) if c else "" for c in row)
                        table_text += row_str + "\n"
            combined = _clean_text(text)
            if table_text:
                combined += "\n[TABLE]\n" + table_text.strip()
            pages.append({"page_num": i, "text": combined})
    return pages


def get_financial_section_text(pages: list[dict]) -> str:
    """Pull pages that are likely financial statements for LLM extraction."""
    # Core financial keywords (weight 1)
    keywords = [
        "consolidated statements", "income statement", "profit and loss",
        "balance sheet", "financial highlights", "net revenue", "net sales",
        "gross profit", "operating income", "net income", "earnings per share",
        "net earnings", "revenue", "fiscal", "annual", "total revenue",
        "total net revenue", "cost of sales", "cost of goods sold",
        "selling, general and administrative", "operating expenses",
        "diluted earnings", "basic earnings", "comprehensive income",
        "total assets", "total liabilities", "total equity",
        "statement of operations", "statement of earnings",
        "financial summary", "key financial", "selected financial",
        "management discussion", "results of operations",
    ]
    # Segment/geographic keywords (weight 3) — these pages contain critical regional data
    segment_keywords = [
        "operating segments", "segment information", "geographic information",
        "segmental information", "revenue by geography", "net sales by segment",
        "segment reporting", "reportable segments",
    ]
    scored: list[tuple[int, dict]] = []
    for p in pages:
        lower = p["text"].lower()
        score = sum(1 for kw in keywords if kw in lower)
        score += sum(3 for kw in segment_keywords if kw in lower)
        if score >= 1:
            scored.append((score, p))

    scored.sort(key=lambda x: -x[0])
    top_pages = [p for _, p in scored[:MAX_FINANCIAL_PAGES]]
    return "\n\n---PAGE BREAK---\n\n".join(
        f"[Page {p['page_num']}]\n{p['text']}" for p in top_pages
    )


def chunk_text(pages: list[dict], brand: str, fiscal_year: str) -> list[dict]:
    """Slide a window over the full text, returning chunks with metadata."""
    # Concatenate all pages with separators
    full_parts: list[tuple[int, str]] = []
    pos = 0
    page_starts: list[tuple[int, int]] = []  # (char_pos, page_num)
    for p in pages:
        page_starts.append((pos, p["page_num"]))
        full_parts.append(p["text"])
        pos += len(p["text"]) + 1

    full_text = "\n".join(full_parts)

    def page_for(char_pos: int) -> int:
        result = 1
        for start, pnum in page_starts:
            if char_pos >= start:
                result = pnum
        return result

    chunks = []
    i = 0
    cid = 0
    while i < len(full_text):
        chunk = full_text[i: i + CHUNK_SIZE].strip()
        if chunk:
            chunks.append({
                "id": f"{brand}_{fiscal_year}_{cid}",
                "text": chunk,
                "metadata": {
                    "brand": brand,
                    "fiscal_year": fiscal_year,
                    "page_num": page_for(i),
                    "chunk_id": cid,
                },
            })
            cid += 1
        i += CHUNK_SIZE - CHUNK_OVERLAP

    return chunks


def load_report(brand_key: str, report: dict) -> dict | None:
    """Parse one report file; returns None if file missing."""
    pdf_path = BASE_DIR / report["file"]
    if not pdf_path.exists():
        print(f"  [WARN] Not found: {pdf_path}")
        return None
    print(f"  Parsing {brand_key} {report['fiscal_year']} ({pdf_path.name})…")
    pages = extract_pages(pdf_path)
    return {
        "brand": brand_key,
        "fiscal_year": report["fiscal_year"],
        "period_end": report["period_end"],
        "pages": pages,
        "chunks": chunk_text(pages, brand_key, report["fiscal_year"]),
        "financial_text": get_financial_section_text(pages),
    }
