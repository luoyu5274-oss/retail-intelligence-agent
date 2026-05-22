"""
Retail Research Agent — FastAPI Backend
"""
import asyncio
import json
import queue
import traceback
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import (
    BRAND_CONFIG, CHAT_HISTORY_FILE, FINANCIAL_DATA_FILE,
    DATA_DIR, BASE_DIR
)
import pdf_parser
import vector_store
import llm_client
import financial_extractor
import scraper
import quarterly_extractor

app = FastAPI(title="Retail Research Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Thread-safe progress queue ────────────────────────────────────────────────
_progress_queue = queue.Queue()
_init_running = False


def _push_progress(msg: str):
    try:
        _progress_queue.put({"type": "progress", "message": msg})
    except Exception:
        pass


# ── Helpers ───────────────────────────────────────────────────────────────────
def _load_chat_history() -> list[dict]:
    if CHAT_HISTORY_FILE.exists():
        with open(CHAT_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_chat_history(history: list[dict]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CHAT_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


# ── Background initialization (runs in thread to avoid blocking event loop) ──
def _run_initialization():
    global _init_running
    _init_running = True
    try:
        fin_data = financial_extractor.load_financial_data()
        all_chunks: list[dict] = []

        for brand_key, cfg in BRAND_CONFIG.items():
            for report in cfg["reports"]:
                _push_progress(f"📄 正在解析 {cfg['name']} {report['fiscal_year']}…")
                report_data = pdf_parser.load_report(brand_key, report)
                if report_data is None:
                    _push_progress(f"  ⚠️  文件不存在: {report['file']}")
                    continue

                all_chunks.extend(report_data["chunks"])
                _push_progress(f"  → {len(report_data['chunks'])} 个文本块")

                fy_key = report["fiscal_year"]
                existing = fin_data.get(brand_key, {}).get(fy_key)
                rev = existing.get("revenue") if isinstance(existing, dict) else None
                rev_total = rev.get("total") if isinstance(rev, dict) else None
                needs_extraction = existing is None or rev_total is None
                if needs_extraction:
                    if existing is not None:
                        _push_progress(f"🔄 重新提取 {cfg['name']} {fy_key}（上次数据不完整）…")
                    else:
                        _push_progress(f"🤖 AI提取 {cfg['name']} {fy_key} 财务数据…")
                    extracted = financial_extractor.extract_financials_for_report(
                        brand_key, fy_key, report_data["financial_text"]
                    )
                    extracted["label"] = report.get("label", fy_key)
                    fin_data.setdefault(brand_key, {})[fy_key] = extracted
                    financial_extractor.save_financial_data(fin_data)
                    _push_progress(f"  ✅ 财务数据提取完成")
                else:
                    _push_progress(f"  ✅ 财务数据已缓存，跳过")

        _push_progress(f"🔍 构建向量索引（{len(all_chunks)} 个文本块）…")
        if all_chunks:
            total_indexed = 0

            def index_cb(*args):
                nonlocal total_indexed
                if len(args) == 1 and isinstance(args[0], str):
                    _push_progress(args[0])  # status messages
                    return
                if len(args) == 2:
                    done, total = args
                    total_indexed = done
                    if done % 256 == 0 or done == total:
                        _push_progress(f"  索引进度: {done}/{total}")

            if not vector_store.is_indexed():
                vector_store.index_chunks(all_chunks, progress_cb=index_cb)
                _push_progress(f"  ✅ 索引完成，共 {total_indexed} 个文本块")
            else:
                _push_progress(f"  ✅ 索引已存在，跳过")

        _push_progress("🎉 初始化完成！")
        _progress_queue.put({"type": "done"})
    except Exception as e:
        _push_progress(f"❌ 错误: {e}")
        _push_progress(traceback.format_exc())
        _progress_queue.put({"type": "error", "message": str(e)})
    finally:
        _init_running = False


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/api/status")
def get_status():
    fin_data = financial_extractor.load_financial_data()
    indexed = vector_store.is_indexed()
    reports_status = []
    for bk, cfg in BRAND_CONFIG.items():
        for rep in cfg["reports"]:
            pdf_exists = (BASE_DIR / rep["file"]).exists()
            has_data = bk in fin_data and rep["fiscal_year"] in fin_data[bk]
            reports_status.append({
                "brand": cfg["name"],
                "brand_key": bk,
                "fiscal_year": rep["fiscal_year"],
                "pdf_exists": pdf_exists,
                "financial_data_ready": has_data,
                "color": cfg["color"],
            })
    return {
        "indexed": indexed,
        "init_running": _init_running,
        "financial_data_ready": bool(fin_data),
        "reports": reports_status,
        "brands": {
            bk: {"name": c["name"], "color": c["color"], "ticker": c["ticker"], "ir_url": c["ir_url"]}
            for bk, c in BRAND_CONFIG.items()
        },
    }


@app.post("/api/initialize")
async def initialize():
    global _init_running
    if _init_running:
        return {"status": "already_running"}
    # Drain old progress
    while not _progress_queue.empty():
        _progress_queue.get_nowait()
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _run_initialization)
    return {"status": "started"}


@app.get("/api/progress")
async def progress_stream():
    """SSE endpoint streaming initialization progress."""
    async def event_gen():
        loop = asyncio.get_running_loop()
        while True:
            try:
                item = await loop.run_in_executor(None, lambda: _progress_queue.get(timeout=30))
                data = json.dumps(item, ensure_ascii=False)
                yield f"data: {data}\n\n"
                if item.get("type") in ("done", "error"):
                    break
            except queue.Empty:
                yield "data: {\"type\":\"heartbeat\"}\n\n"
            except Exception:
                break

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@app.get("/api/financial")
def get_financial():
    # Use static dashboard data if available, fall back to LLM-extracted data
    dash_file = DATA_DIR / "dashboard_data.json"
    if dash_file.exists():
        with open(dash_file, "r", encoding="utf-8") as f:
            fin_data = json.load(f)
    else:
        fin_data = financial_extractor.load_financial_data()
    if not fin_data:
        raise HTTPException(status_code=404, detail="财务数据尚未生成，请先初始化")
    chart_data = financial_extractor.build_chart_data(fin_data)
    return {"raw": fin_data, "charts": chart_data}


@app.get("/api/quarterly")
def get_quarterly():
    qdata = quarterly_extractor.load_quarterly_data()
    if not qdata:
        raise HTTPException(status_code=404, detail="季度数据尚未生成")
    chart = quarterly_extractor.build_calendar_chart(qdata)
    return {"raw": qdata, "chart": chart}


@app.post("/api/quarterly/extract")
def extract_quarterly():
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, quarterly_extractor.run_quarterly_extraction)
    return {"status": "started", "message": "季度数据提取已在后台启动"}


class ChatRequest(BaseModel):
    question: str
    brand_filter: str | None = None


@app.post("/api/chat")
def chat(req: ChatRequest):
    if not vector_store.is_indexed():
        raise HTTPException(status_code=400, detail="请先初始化数据")

    # Retrieve relevant chunks
    chunks = vector_store.query(req.question, brand_filter=req.brand_filter)
    context_parts = []
    for c in chunks:
        brand_name = BRAND_CONFIG.get(c["metadata"].get("brand", ""), {}).get("name", "")
        fy = c["metadata"].get("fiscal_year", "")
        pg = c["metadata"].get("page_num", "")
        context_parts.append(f"[{brand_name} {fy} P.{pg}]\n{c['text']}")
    context = "\n\n---\n\n".join(context_parts)

    # Load financial summary for additional context (prefer static dashboard data)
    dash_file = DATA_DIR / "dashboard_data.json"
    if dash_file.exists():
        with open(dash_file, "r", encoding="utf-8") as f:
            fin_data = json.load(f)
    else:
        fin_data = financial_extractor.load_financial_data()
    fin_summary = ""
    if fin_data:
        lines = []
        for bk, bdata in fin_data.items():
            bname = BRAND_CONFIG[bk]["name"]
            for fy, fdata in sorted(bdata.items()):
                rev = fdata.get("revenue", {})
                lines.append(
                    f"{bname} {fy}: 营收={rev.get('total')}M {BRAND_CONFIG[bk]['currency']}, "
                    f"毛利率={fdata.get('gross_margin_pct')}%, "
                    f"净利润率={fdata.get('net_margin_pct')}%"
                )
        fin_summary = "\n".join(lines)

    system_prompt = """你是一位专业的零售行业研究分析师，专注于运动服饰品牌（Nike、Adidas、Lululemon）的竞品分析。
你的任务是根据年报原文回答用户问题，提供精准数据、深度分析和战略洞察。
回答时：
1. 优先引用原文数据，注明来源（品牌+财年+页码）
2. 对比分析时指出差异及背后原因
3. 提供1-2个你的分析判断（标明"分析师点评："）
4. 用中文回答，数据引用保留原始数字和单位

当需要进行数据对比时，可以在回复末尾插入可视化图表。使用以下格式（放在回复最后）：

[CHART:{"type":"bar","title":"图表标题","data":[{"name":"Nike","value":46309},{"name":"Adidas","value":24811},{"name":"Lululemon","value":11103}]}]

type 可选 bar（柱状图/对比）或 line（折线图/趋势）。
bar 的 data 格式：[{"name":"类别名","value":数值}, ...]
line 的 data 格式：[{"name":"X轴标签","系列1名":数值,"系列2名":数值}, ...]

规则：
- 只引用财务摘要中已提供的数据，不要编造
- 图表放在文字分析的最后面
- 没有合适图表可画时不要强行放"""

    user_prompt = f"""财务摘要参考：
{fin_summary}

年报原文相关段落：
{context}

用户问题：{req.question}"""

    answer = llm_client.chat([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ], temperature=0.4, max_tokens=1500)

    # Persist history
    history = _load_chat_history()
    history.append({
        "timestamp": datetime.now().isoformat(),
        "question": req.question,
        "answer": answer,
        "sources": [
            {
                "brand": BRAND_CONFIG.get(c["metadata"].get("brand", ""), {}).get("name", ""),
                "fiscal_year": c["metadata"].get("fiscal_year", ""),
                "page_num": c["metadata"].get("page_num", ""),
                "relevance": c["relevance"],
                "excerpt": c["text"][:200],
            }
            for c in chunks[:3]
        ],
    })
    _save_chat_history(history[-50:])  # keep last 50

    return {
        "answer": answer,
        "sources": history[-1]["sources"],
    }


@app.get("/api/chat/history")
def get_chat_history():
    return _load_chat_history()


@app.delete("/api/chat/history")
def clear_chat_history():
    _save_chat_history([])
    return {"status": "cleared"}


@app.post("/api/scrape")
async def trigger_scrape(background_tasks: BackgroundTasks):
    messages: list[str] = []

    def cb(msg):
        messages.append(msg)
        _push_progress(msg)

    background_tasks.add_task(scraper.run_scrape, cb)
    return {"status": "started", "message": "抓取任务已在后台启动"}


@app.get("/api/scrape/log")
def get_scrape_log():
    return scraper.get_scrape_log()


@app.post("/api/reset")
def reset_index():
    vector_store.reset()
    return {"status": "reset"}


@app.post("/api/reset-financial")
def reset_financial():
    """Delete cached financial data to force re-extraction on next init."""
    from config import FINANCIAL_DATA_FILE
    if FINANCIAL_DATA_FILE.exists():
        FINANCIAL_DATA_FILE.unlink()
    return {"status": "financial_data_reset"}
