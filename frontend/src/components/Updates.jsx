import { useState, useEffect } from "react";
import { triggerScrape, getScrapeLog, resetIndex, listenProgress } from "../utils/api";

const BRAND_COLORS = { nike: "#e05000", adidas: "#2d2d2d", lululemon: "#9b1b3a" };

export default function Updates({ status, onRefresh }) {
  const [scraping, setScraping] = useState(false);
  const [scrapeLog, setScrapeLog] = useState(null);
  const [progressMsgs, setProgressMsgs] = useState([]);

  useEffect(() => {
    getScrapeLog().then(setScrapeLog).catch(() => {});
  }, []);

  async function handleScrape() {
    setScraping(true);
    setProgressMsgs([]);
    await triggerScrape();
    const stop = listenProgress(
      (msg) => setProgressMsgs((m) => [...m, msg]),
      () => {
        setScraping(false);
        getScrapeLog().then(setScrapeLog);
        onRefresh();
        stop?.();
      }
    );
  }

  async function handleReset() {
    if (!confirm("确认重置向量索引？下次访问仪表盘时需重新初始化。")) return;
    await resetIndex();
    onRefresh();
  }

  const brands = status?.brands || {};
  const reports = status?.reports || [];
  const brandEntries = Object.entries(brands);

  return (
    <div className="updates-section">
      <div className="section-header">
        <div>
          <span className="section-title">数据源管理</span>
          <span className="section-sub" style={{ marginLeft: 12 }}>Data Source Management</span>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-primary" onClick={handleScrape} disabled={scraping}>
            {scraping ? <><div className="spinner" style={{ width: 13, height: 13 }} />Scraping...</> : "Fetch New Reports"}
          </button>
          <button className="btn btn-ghost" onClick={handleReset}>Reset Index</button>
        </div>
      </div>

      {/* Brand report status */}
      <div className="updates-grid">
        {brandEntries.map(([bk, cfg]) => {
          const brandReports = reports.filter((r) => r.brand_key === bk);
          const allDone = brandReports.every((r) => r.financial_data_ready);
          const allPdf = brandReports.every((r) => r.pdf_exists);
          return (
            <div key={bk} className="update-card">
              <div className="update-card-header">
                <div className="update-brand-dot" style={{
                  background: BRAND_COLORS[bk] || "#3b82f6",
                  boxShadow: `0 0 8px ${BRAND_COLORS[bk] || "#3b82f6"}`,
                }} />
                <div className="update-brand-name">{cfg.name}</div>
                <span className="badge badge-blue" style={{ marginLeft: "auto" }}>
                  {cfg.ticker}
                </span>
                <span
                  className="status-dot"
                  style={{
                    background: allDone ? "var(--success)" : "var(--warning)",
                    boxShadow: allDone ? "0 0 6px var(--success)" : "none",
                  }}
                  title={allDone ? "所有数据已就绪" : "有数据缺失"}
                />
              </div>

              <div className="update-reports">
                {brandReports.map((rep) => (
                  <div key={rep.fiscal_year} className="update-report-row">
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 11.5 }}>
                      {rep.fiscal_year}
                    </span>
                    <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
                      <span className={`badge ${rep.pdf_exists ? "badge-green" : "badge-red"}`}>
                        {rep.pdf_exists ? "PDF" : "缺失"}
                      </span>
                      <span className={`badge ${rep.financial_data_ready ? "badge-green" : "badge-yellow"}`}>
                        {rep.financial_data_ready ? "已提取" : "待提取"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              <div style={{
                marginTop: 12, fontSize: 11, color: "var(--text-muted)",
                fontFamily: "var(--font-mono)", letterSpacing: "0.02em",
              }}>
                IR: <a href={cfg.ir_url || "#"} target="_blank" rel="noreferrer">
                  {cfg.ir_url ? (new URL(cfg.ir_url)).hostname : "—"} ↗
                </a>
              </div>
            </div>
          );
        })}
      </div>

      {/* Scrape progress */}
      {progressMsgs.length > 0 && (
        <div className="log-panel">
          <div className="log-panel-title">▸ 抓取进度</div>
          <div className="log-entries" style={{ maxHeight: 200 }}>
            {progressMsgs.map((m, i) => (
              <div key={i} className="log-line">{m}</div>
            ))}
          </div>
        </div>
      )}

      {/* Scrape history */}
      {scrapeLog?.entries?.length > 0 && (
        <div className="log-panel">
          <div className="log-panel-title">▸ 抓取历史</div>
          {scrapeLog.last_run && (
            <div style={{
              fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-muted)",
              marginBottom: 12, letterSpacing: "0.02em",
            }}>
              上次运行: {new Date(scrapeLog.last_run).toLocaleString("zh-CN")}
            </div>
          )}
          <div className="log-entries">
            {scrapeLog.entries.map((entry, i) => (
              <div key={i} className={`log-entry ${entry.status === "ok" ? "ok" : "error"}`}>
                <div className="log-entry-brand">{entry.brand}</div>
                <div className="log-entry-msg">{entry.message}</div>
                {entry.new_files?.length > 0 && (
                  <div style={{ marginTop: 6, display: "flex", gap: 4, flexWrap: "wrap" }}>
                    {entry.new_files.map((f) => (
                      <span key={f} className="source-chip" style={{ fontSize: 10.5 }}>📥 {f}</span>
                    ))}
                  </div>
                )}
                <div className="log-entry-time">
                  {new Date(entry.timestamp).toLocaleString("zh-CN")}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* How it works */}
      <div style={{
        background: "var(--surface)", border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-lg)", padding: "18px 22px",
        fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.9,
      }}>
        <div style={{
          fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 14,
          color: "var(--text)", marginBottom: 10, letterSpacing: "0.03em",
        }}>
          工作原理
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
            <span style={{
              fontFamily: "var(--font-mono)", color: "var(--amber)",
              fontWeight: 600, fontSize: 11, minWidth: 20,
            }}>01</span>
            <span>
              <strong style={{ color: "var(--text)" }}>点击「抓取新年报」</strong> — 访问三个品牌的投资者关系页面，自动发现并下载新的年报 PDF
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
            <span style={{
              fontFamily: "var(--font-mono)", color: "var(--amber)",
              fontWeight: 600, fontSize: 11, minWidth: 20,
            }}>02</span>
            <span>
              下载完成后，回到左侧点击<strong style={{ color: "var(--text)" }}>「重新初始化」</strong> — 解析新文件、AI 提取财务数据、重建向量索引
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
            <span style={{
              fontFamily: "var(--font-mono)", color: "var(--amber)",
              fontWeight: 600, fontSize: 11, minWidth: 20,
            }}>03</span>
            <span>
              仪表盘和智能问答将自动包含新数据
            </span>
          </div>
        </div>
        <div style={{
          marginTop: 14, padding: "10px 16px",
          background: "rgba(245,158,11,0.04)",
          borderRadius: "var(--radius)",
          border: "1px solid rgba(245,158,11,0.1)",
          fontFamily: "var(--font-mono)", fontSize: 11,
          color: "var(--text-secondary)", letterSpacing: "0.02em",
        }}>
          ◆ 当前已加载: Nike FY2022 / FY2023 / FY2024 / FY2025 · Adidas FY2022 / FY2023 / FY2024 · Lululemon FY2022 / FY2023 / FY2024 / FY2025 （共 11 份年报）
        </div>
      </div>
    </div>
  );
}
