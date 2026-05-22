"""Scrape investor relations pages for new annual report PDFs."""
import json
import re
import time
from datetime import datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from config import BASE_DIR, BRAND_CONFIG, DATA_DIR, SCRAPE_LOG_FILE


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _load_log() -> dict:
    if SCRAPE_LOG_FILE.exists():
        with open(SCRAPE_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"entries": [], "last_run": None}


def _save_log(log: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SCRAPE_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def _existing_files() -> set[str]:
    return {p.name for p in BASE_DIR.glob("*.pdf")}


def _find_pdf_links(url: str) -> list[str]:
    """Fetch a page and extract .pdf links."""
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        return [f"ERROR: {e}"]

    soup = BeautifulSoup(resp.text, "html.parser")
    pdf_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".pdf"):
            if href.startswith("http"):
                pdf_links.append(href)
            elif href.startswith("/"):
                from urllib.parse import urlparse
                parsed = urlparse(url)
                pdf_links.append(f"{parsed.scheme}://{parsed.netloc}{href}")
    return list(set(pdf_links))


def _download_pdf(url: str, dest_dir: Path, progress_cb=None) -> str | None:
    """Download a PDF to dest_dir. Returns filename or None on failure."""
    try:
        filename = url.split("/")[-1].split("?")[0]
        if not filename.endswith(".pdf"):
            filename += ".pdf"
        dest = dest_dir / filename
        if dest.exists():
            return None  # already have it

        with httpx.stream("GET", url, headers=HEADERS, timeout=60, follow_redirects=True) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb and total:
                        progress_cb(downloaded, total)
        return filename
    except Exception as e:
        return None


def run_scrape(progress_cb=None) -> dict:
    """
    Check each brand's IR page for new PDFs.
    Returns a summary dict with results.
    """
    log = _load_log()
    existing = _existing_files()
    results: list[dict] = []

    for brand_key, cfg in BRAND_CONFIG.items():
        entry: dict = {
            "brand": cfg["name"],
            "ir_url": cfg["ir_url"],
            "timestamp": datetime.now().isoformat(),
            "new_files": [],
            "pdf_links_found": 0,
            "status": "ok",
            "message": "",
        }
        if progress_cb:
            progress_cb(f"检查 {cfg['name']} 投资者关系页面…")

        links = _find_pdf_links(cfg["ir_url"])
        error_links = [l for l in links if l.startswith("ERROR:")]
        pdf_links = [l for l in links if not l.startswith("ERROR:")]

        if error_links:
            entry["status"] = "error"
            entry["message"] = error_links[0]
            results.append(entry)
            continue

        entry["pdf_links_found"] = len(pdf_links)

        for link in pdf_links:
            fname = link.split("/")[-1].split("?")[0]
            if fname in existing:
                continue
            if progress_cb:
                progress_cb(f"  下载: {fname}")
            saved = _download_pdf(link, BASE_DIR)
            if saved:
                entry["new_files"].append(saved)
                existing.add(saved)

        entry["message"] = (
            f"发现 {len(pdf_links)} 个PDF链接，新增 {len(entry['new_files'])} 个文件"
        )
        results.append(entry)
        time.sleep(1)

    log["entries"] = (results + log.get("entries", []))[:50]
    log["last_run"] = datetime.now().isoformat()
    _save_log(log)
    return {"results": results, "last_run": log["last_run"]}


def get_scrape_log() -> dict:
    return _load_log()
