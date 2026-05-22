import { useState, useEffect, useCallback } from "react";
import Dashboard from "./components/Dashboard";
import Chat from "./components/Chat";
import Updates from "./components/Updates";
import { getStatus, initialize, listenProgress } from "./utils/api";
import "./App.css";

const NAV = [
  { id: "dashboard", label: "仪表盘" },
  { id: "chat", label: "智能问答" },
  { id: "updates", label: "数据管理" },
];

const BRAND_COLORS = { nike: "#e05000", adidas: "#2d2d2d", lululemon: "#9b1b3a" };

export default function App() {
  const [page, setPage] = useState("dashboard");
  const [status, setStatus] = useState(null);
  const [initLog, setInitLog] = useState([]);
  const [initing, setIniting] = useState(false);
  const [initDone, setInitDone] = useState(false);

  const refreshStatus = useCallback(async () => {
    try { setStatus(await getStatus()); } catch {}
  }, []);

  useEffect(() => { refreshStatus(); }, [refreshStatus]);

  async function handleInit() {
    setIniting(true);
    setInitLog([]);
    setInitDone(false);
    const stop = listenProgress(
      (msg) => setInitLog((l) => [...l, msg]),
      (ok) => { setIniting(false); setInitDone(ok); refreshStatus(); stop?.(); }
    );
    await new Promise((r) => setTimeout(r, 300));
    await initialize();
  }

  const ready = status?.financial_data_ready;
  const chatReady = status?.indexed;

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="logo">
            <div className="logo-icon">R</div>
            <div>
              <div className="logo-title">Retail Intel</div>
              <div className="logo-sub">Competitive Analysis</div>
            </div>
          </div>
        </div>

        {status?.reports && (
          <div className="brand-status">
            {["nike", "adidas", "lululemon"].map((bk) => {
              const cfg = status.brands?.[bk];
              const reps = status.reports.filter((r) => r.brand_key === bk);
              const doneCount = reps.filter((r) => r.financial_data_ready).length;
              const full = doneCount === reps.length;
              return (
                <div key={bk} className="brand-pill" style={{ borderLeftColor: BRAND_COLORS[bk] }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span className="status-dot" style={{
                      background: full ? BRAND_COLORS[bk] : "var(--text-muted)",
                      boxShadow: full ? `0 0 5px ${BRAND_COLORS[bk]}` : "none",
                    }} />
                    <span className="brand-pill-name">{cfg?.name}</span>
                  </div>
                  <span className={`badge ${full ? "badge-green" : "badge-yellow"}`}>
                    {doneCount}/{reps.length}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        <nav className="nav">
          {NAV.map((n) => (
            <button
              key={n.id}
              className={`nav-item ${page === n.id ? "active" : ""}`}
              onClick={() => setPage(n.id)}
            >
              <span>{n.label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          {!ready && !initing && (
            <button className="btn btn-primary init-btn" onClick={handleInit}>
              Initialize
            </button>
          )}
          {initing && (
            <div className="init-status">
              <div className="spinner" />
              <span>Initializing...</span>
            </div>
          )}
          {ready && !initing && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div className="ready-badge">Data Ready</div>
              <button
                className="btn btn-ghost"
                style={{ width: "100%", justifyContent: "center", fontFamily: "var(--font-display)", letterSpacing: "0.03em" }}
                onClick={handleInit}
              >
                Re-index
              </button>
            </div>
          )}
        </div>
      </aside>

      <main className="main-content">
        {(initing || (initLog.length > 0 && !initDone)) && (
          <div className="init-log">
            <div className="init-log-title">
              {initing ? "Initializing..." : "Complete"}
            </div>
            <div className="init-log-body">
              {initLog.map((l, i) => (
                <div key={i} className="log-line">{l}</div>
              ))}
            </div>
          </div>
        )}
        {page === "dashboard" && <Dashboard status={status} ready={ready} />}
        {page === "chat" && <Chat ready={chatReady} brands={status?.brands} />}
        {page === "updates" && <Updates status={status} onRefresh={refreshStatus} />}
      </main>
    </div>
  );
}
