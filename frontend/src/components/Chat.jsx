import { useState, useRef, useEffect } from "react";
import { BarChart, Bar, Cell, LineChart, Line, ComposedChart, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { sendChat, getChatHistory, clearChatHistory } from "../utils/api";

const SUGGESTED = [
  { q: "Three brands' latest fiscal year revenue?" },
  { q: "Who has the highest gross margin and why?" },
  { q: "How did Nike perform in Greater China?" },
  { q: "What is Lululemon's growth strategy?" },
  { q: "Compare inventory health across all three brands" },
  { q: "What is Adidas's biggest strategic risk?" },
];

const BRAND_COLORS = { nike: "#e05000", adidas: "#2d2d2d", lululemon: "#9b1b3a" };

export default function Chat({ ready, brands }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [brandFilter, setBrandFilter] = useState(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    getChatHistory().then((hist) => {
      if (!hist?.length) return;
      const msgs = hist.flatMap((h) => [
        { role: "user", content: h.question },
        { role: "ai", content: h.answer, sources: h.sources || [] },
      ]);
      setMessages(msgs);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSend(q = input.trim()) {
    if (!q || loading || !ready) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: q }]);
    setLoading(true);
    try {
      const res = await sendChat(q, brandFilter);
      setMessages((m) => [...m, { role: "ai", content: res.answer, sources: res.sources || [] }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "ai", content: `❌ 错误：${e.message}`, sources: [] }]);
    } finally {
      setLoading(false);
    }
  }

  function handleKey(e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }

  async function handleClear() {
    await clearChatHistory();
    setMessages([]);
  }

  const brandList = brands ? Object.entries(brands) : [];

  if (!ready) return (
    <div className="placeholder">
      <div className="placeholder-title">Index Required</div>
      <div style={{ color: "var(--text-muted)", fontSize: 13 }}>
        Build the vector index to enable AI-powered Q&A
      </div>
    </div>
  );

  return (
    <div className="chat-layout">
      {/* Controls */}
      <div className="chat-controls">
        <div className="brand-filter-chips">
          <button
            className={`chip ${brandFilter === null ? "active" : ""}`}
            onClick={() => setBrandFilter(null)}
          >
            全部品牌
          </button>
          {brandList.map(([bk, cfg]) => (
            <button
              key={bk}
              className={`chip ${brandFilter === bk ? "active" : ""}`}
              onClick={() => setBrandFilter(bk === brandFilter ? null : bk)}
              style={brandFilter === bk ? {
                borderColor: BRAND_COLORS[bk],
                color: BRAND_COLORS[bk],
                background: `${BRAND_COLORS[bk]}18`,
              } : {}}
            >
              {cfg.name}
            </button>
          ))}
        </div>
        {messages.length > 0 && (
          <button
            className="btn btn-ghost"
            style={{ marginLeft: "auto", fontSize: 12 }}
            onClick={handleClear}
          >
            ✕ 清空记录
          </button>
        )}
      </div>

      {/* Messages */}
      <div className="messages-area">
        {messages.length === 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
            <div style={{ textAlign: "center", padding: "24px 0 8px" }}>
              <div style={{
                fontSize: 40, marginBottom: 12, opacity: 0.5,
                fontFamily: "var(--font-display)", color: "var(--amber)",
              }}>
                R
              </div>
              <div style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 4 }}>
                AI-powered analysis of Nike, Adidas & Lululemon annual reports
              </div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                Data queries, cross-brand comparison, strategic insights
              </div>
            </div>
            <div className="suggestion-grid">
              {SUGGESTED.map(({ q }) => (
                <button
                  key={q}
                  className="suggestion-card"
                  onClick={() => handleSend(q)}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => {
          const blocks = msg.role === "ai" ? parseContent(msg.content) : null;
          return (
          <div key={i} className={`message ${msg.role === "user" ? "message-user" : ""}`}>
            <div className={`message-bubble ${msg.role === "user" ? "bubble-user" : "bubble-ai"}`}>
              {msg.role === "ai" ? blocks.map((block, bi) =>
                block.type === "table" ? (
                  <TableBlock key={bi} table={block.table} />
                ) : (
                  <div key={bi} dangerouslySetInnerHTML={{ __html: formatMarkdown(block.content) }} />
                )
              ) : msg.content}
            </div>
            {msg.role === "ai" && msg.sources?.length > 0 && (
              <div className="sources-row">
                {msg.sources.map((s, si) => (
                  <span key={si} className="source-chip">
                    {s.brand} · {s.fiscal_year} · P.{s.page_num} · {(s.relevance * 100).toFixed(0)}%
                  </span>
                ))}
              </div>
            )}
          </div>
        )})}
        {loading && (
          <div className="message">
            <div className="message-bubble bubble-ai thinking">
              <div className="spinner" style={{ width: 13, height: 13 }} />
              <span>正在分析年报数据...</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="chat-input-row">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="输入问题，Enter 发送，Shift+Enter 换行..."
          disabled={loading}
        />
        <button className="send-btn" onClick={() => handleSend()} disabled={loading || !input.trim()}>
          发送 →
        </button>
      </div>
    </div>
  );
}

function formatMarkdown(text) {
  if (!text) return "";

  // Fix: split single-line tables (LLM sometimes outputs all rows as one line)
  // Pattern: "| col1 | col2 | | :--- | :--- | | val1 | val2 |" has no newlines between rows
  text = text.replace(/\|\s*\|\s*/g, (match) => {
    // "|| " or "| | " = row break in a single-line table
    return "|\n|";
  });

  // Step 1: convert markdown tables to HTML
  let lines = text.split("\n");
  let out = [];
  let tableRows = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    // Detect pipe-separated table rows (consecutive lines with |...|)
    if (/^\|.+\|/.test(line)) {
      tableRows.push(line);
      i++;
      while (i < lines.length && /^\|.+\|/.test(lines[i])) {
        tableRows.push(lines[i]);
        i++;
      }
      // Render collected table rows
      out.push(renderTable(tableRows));
      tableRows = [];
      continue;
    }
    out.push(line);
    i++;
  }
  // Flush remaining
  if (tableRows.length > 0) out.push(renderTable(tableRows));

  text = out.join("\n");

  // Step 2: inline formatting
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code>$1</code>")
    .replace(/^### (.+)$/gm, "<h4>$1</h4>")
    .replace(/^## (.+)$/gm, "<h3>$1</h3>")
    .replace(/^# (.+)$/gm, "<h2>$1</h2>")
    .replace(/^- (.+)$/gm, "<li>$1</li>")
    .replace(/\n\n/g, "<br/><br/>")
    .replace(/\n/g, "<br/>");
}

const CHART_COLORS = ["#e05000", "#2d2d2d", "#9b1b3a", "#d97706", "#059669", "#0ea5e9"];
const BRAND_COLOR_MAP = { nike: "#e05000", adidas: "#2d2d2d", lululemon: "#9b1b3a" };
const LINE_COLORS = { nike: "#38bdf8", adidas: "#a78bfa", lululemon: "#34d399" };  // distinct from bar fills
const FALLBACK = ["#d97706", "#059669", "#0ea5e9", "#7c3aed", "#db2777", "#0891b2"];
function brandColor(name) {
  const lower = (name || "").toLowerCase();
  for (const [b, c] of Object.entries(BRAND_COLOR_MAP)) { if (lower.includes(b)) return c; }
  return null;
}
function lineColor(name) {
  const lower = (name || "").toLowerCase();
  for (const [b, c] of Object.entries(LINE_COLORS)) { if (lower.includes(b)) return c; }
  return null;
}
/* ── Parse AI content: |...| → table, rest → text ── */
function parseContent(content) {
  const blocks = [];
  const lines = content.split("\n");
  let inner = [];
  let tableLines = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (/^\|.+\|/.test(line)) {
      if (inner.length > 0) { blocks.push({ type: "text", content: inner.join("\n") }); inner = []; }
      tableLines.push(line);
      i++;
      while (i < lines.length && /^\|.+\|/.test(lines[i])) { tableLines.push(lines[i]); i++; }
      blocks.push({ type: "table", table: parseTable(tableLines) });
      tableLines = [];
    } else {
      inner.push(line);
      i++;
    }
  }
  if (inner.length > 0) blocks.push({ type: "text", content: inner.join("\n") });
  return blocks;
}

function parseTable(lines) {
  const rows = lines
    .map((l) => l.replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim()))
    .filter((cells) => !cells.every((c) => /^:?-+:?$/.test(c))); // skip separator
  if (rows.length === 0) return { headers: [], rows: [] };
  return { headers: rows[0], rows: rows.slice(1) };
}

function tableToChartData(table) {
  if (table.rows.length === 0) return null;
  // Classify each column as: label (col 0), bar (absolute numbers), line (percentages/rates)
  const labelCol = 0;
  const barCols = [];
  const lineCols = [];
  for (let ci = 1; ci < table.headers.length; ci++) {
    const header = table.headers[ci].toLowerCase();
    const isPct = /[%％]|rate|growth|margin|增速|率/.test(header);
    const numericCount = table.rows.filter((r) => {
      const v = parseFloat(String(r[ci] || "").replace(/[,%$€£\s]/g, ""));
      return !isNaN(v);
    }).length;
    if (numericCount < table.rows.length * 0.5) continue;  // at least half must be numeric
    if (isPct) lineCols.push(ci);
    else barCols.push(ci);
  }
  if (barCols.length === 0 && lineCols.length === 0) return null;

  const data = table.rows.map((r) => {
    const obj = { name: r[labelCol] };
    for (const ci of [...barCols, ...lineCols]) {
      obj[table.headers[ci]] = parseFloat(String(r[ci] || "").replace(/[,%$€£\s]/g, ""));
    }
    return obj;
  });
  return {
    type: lineCols.length > 0 ? "combo" : "bar",
    data,
    barCols: barCols.map((ci) => table.headers[ci]),
    lineCols: lineCols.map((ci) => table.headers[ci]),
  };
}

/* ── Table block with Chart toggle ─────────── */
function TableBlock({ table }) {
  const [chartMode, setChartMode] = useState(false);
  const chartData = tableToChartData(table);
  const canChart = chartData && chartData.data.length > 0;

  if (chartMode && canChart) {
    const isCombo = chartData.type === "combo";
    const Chart = isCombo ? ComposedChart : BarChart;
    return (
      <div className="chat-chart">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <span className="chat-chart-title">Chart</span>
          <button className="chart-toggle-btn" onClick={() => setChartMode(false)}>Table</button>
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <Chart data={chartData.data} margin={{ top: 4, right: isCombo ? 8 : 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e8e0d5" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#9b8d7e" }} axisLine={false} tickLine={false} />
            <YAxis yAxisId="left" tick={{ fontSize: 10, fill: "#9b8d7e" }} axisLine={false} tickLine={false} />
            {isCombo && <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: "#9b8d7e" }} axisLine={false} tickLine={false} unit="%" />}
            <Tooltip contentStyle={{ background: "#fff", border: "1px solid #ddd5c9", borderRadius: 4, fontSize: 11 }} />
            {(chartData.barCols.length + chartData.lineCols.length) > 1 && <Legend wrapperStyle={{ fontSize: 10 }} />}
            {chartData.barCols.length === 1 && chartData.lineCols.length === 0 ? (
              <Bar yAxisId="left" dataKey={chartData.barCols[0]} radius={[4, 4, 0, 0]} maxBarSize={44}>
                {chartData.data.map((row, idx) => (
                  <Cell key={idx} fill={brandColor(row.name) || FALLBACK[idx % FALLBACK.length]} />
                ))}
              </Bar>
            ) : chartData.barCols.map((col, ci) => (
              <Bar key={col} yAxisId="left" dataKey={col} fill={brandColor(col) || CHART_COLORS[ci % CHART_COLORS.length]} radius={[4, 4, 0, 0]} maxBarSize={44} />
            ))}
            {chartData.lineCols.map((col, ci) => {
              const lc = lineColor(col) || ["#38bdf8","#a78bfa","#34d399","#fbbf24","#f472b6"][ci % 5];
              return (
                <Line key={col} yAxisId="right" dataKey={col} stroke={lc} strokeWidth={2.5}
                  connectNulls dot={{ r: 4, fill: lc, strokeWidth: 0 }} />
              );
            })}
          </Chart>
        </ResponsiveContainer>
      </div>
    );
  }

  return (
    <div className="table-wrapper">
      {canChart && (
        <button className="chart-toggle-btn" onClick={() => setChartMode(true)}>Chart</button>
      )}
      <div dangerouslySetInnerHTML={{ __html: renderTableHtml(table) }} />
    </div>
  );
}

function renderTableHtml(table) {
  let html = '<table class="md-table"><thead><tr>';
  table.headers.forEach((h) => { html += `<th>${h}</th>`; });
  html += '</tr></thead><tbody>';
  table.rows.forEach((row) => {
    html += '<tr>';
    row.forEach((cell) => { html += `<td>${cell}</td>`; });
    html += '</tr>';
  });
  html += '</tbody></table>';
  return html;
}

/* ── Legacy: keep renderTable for formatMarkdown ─── */
function renderTable(rows) {
  if (rows.length === 0) return "";
  let html = '<table class="md-table">';
  rows.forEach((row, idx) => {
    // Strip leading/trailing |, split by |
    const cells = row.replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
    // Skip separator rows (e.g. :---, ---, :---:)
    if (cells.every((c) => /^:?-+:?$/.test(c))) return;
    const tag = idx === 0 ? "th" : "td";
    html += "<tr>" + cells.map((c) => `<${tag}>${c}</${tag}>`).join("") + "</tr>";
  });
  html += "</table>";
  return html;
}
