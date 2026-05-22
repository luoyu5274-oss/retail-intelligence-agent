import { useEffect, useState, useRef } from "react";
import {
  BarChart, Bar, LineChart, Line, RadarChart, Radar, PolarGrid,
  PolarAngleAxis, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ReferenceLine
} from "recharts";
import { getFinancial, getQuarterly } from "../utils/api";

const BRAND_COLORS = { Nike: "#e05000", Adidas: "#2d2d2d", Lululemon: "#9b1b3a" };
const BRAND_BG = { Nike: "rgba(250,84,0,0.08)", Adidas: "rgba(148,163,184,0.06)", Lululemon: "rgba(192,57,106,0.07)" };

const FMT_M = (v) => {
  if (v == null) return "—";
  if (v >= 1000) return `${(v / 1000).toFixed(1)}B`;
  return `${Math.round(v)}M`;
};
const FMT_PCT = (v) => (v == null ? "—" : `${v.toFixed(1)}%`);

/* ── Animated number counter ─────────────────── */
function AnimatedNumber({ value, formatter }) {
  const [display, setDisplay] = useState(0);
  const raf = useRef(null);

  useEffect(() => {
    if (value == null) { setDisplay(null); return; }
    const target = typeof value === "number" ? value : parseFloat(value);
    if (isNaN(target)) { setDisplay(value); return; }

    let start = 0;
    const duration = 800;
    const startTime = performance.now();

    function tick(now) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      start = target * eased;
      setDisplay(start);
      if (progress < 1) raf.current = requestAnimationFrame(tick);
    }
    raf.current = requestAnimationFrame(tick);
    return () => { if (raf.current) cancelAnimationFrame(raf.current); };
  }, [value]);

  if (display == null) return <span className="metric-value">—</span>;
  return <span className="metric-value">{formatter ? formatter(display) : display}</span>;
}

/* ── Custom tooltip ──────────────────────────── */
const CustomTooltip = ({ active, payload, label, unit = "" }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: "#151d2e", border: "1px solid #253452", borderRadius: 6,
      padding: "10px 14px", fontSize: 12, boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
    }}>
      <div style={{ color: "#67758b", marginBottom: 6, fontFamily: "var(--font-mono)", fontSize: 11 }}>
        {label}
      </div>
      {payload.map((p) => (
        <div key={p.name} style={{ color: p.color, marginBottom: 2, fontFamily: "var(--font-mono)" }}>
          {p.name}: <strong>{typeof p.value === "number" ? (unit === "%" ? FMT_PCT(p.value) : FMT_M(p.value)) : p.value}</strong>
        </div>
      ))}
    </div>
  );
};

/* ── Chart colors for Recharts (light theme) ─── */
const chartTheme = {
  grid: "#e8e0d5",
  axis: "#9b8d7e",
  text: "#6b5e4f",
};

export default function Dashboard({ ready }) {
  const [data, setData] = useState(null);
  const [qData, setQData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!ready) return;
    setLoading(true);
    Promise.all([
      getFinancial(),
      getQuarterly().catch(() => null),  // quarterly data is optional
    ])
      .then(([fin, qtr]) => { setData(fin); setQData(qtr); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [ready]);

  if (!ready) return (
    <div className="placeholder">
      <div className="placeholder-icon">◆</div>
      <div className="placeholder-title">请先初始化数据</div>
      <div style={{ color: "var(--text-muted)", fontSize: 13 }}>
        点击左侧「⚡ 初始化数据」按钮，系统将解析年报并提取财务指标
      </div>
    </div>
  );

  if (loading) return (
    <div className="placeholder">
      <div className="spinner" style={{ width: 36, height: 36, margin: "0 auto 14px", borderWidth: 2 }} />
      <div style={{ color: "var(--text-secondary)" }}>正在加载财务数据...</div>
    </div>
  );

  if (error) return (
    <div className="placeholder">
      <div className="placeholder-icon" style={{ opacity: 0.4 }}>✕</div>
      <div style={{ color: "var(--error)" }}>{error}</div>
    </div>
  );
  if (!data) return null;

  const { raw, charts } = data;
  const { revenue_chart, margin_chart, growth_chart, region_chart, radar_data, summary } = charts;

  // Top metric cards: latest year per brand
  const topMetrics = [];
  for (const [bk, bdata] of Object.entries(raw)) {
    const years = Object.keys(bdata).sort();
    if (!years.length) continue;
    const latest = bdata[years[years.length - 1]];
    const prev = years.length > 1 ? bdata[years[years.length - 2]] : null;
    const name = latest.brand || bk;
    const color = BRAND_COLORS[name] || "#3b82f6";
    topMetrics.push({ name, color, latest, prev, year: latest.label || years[years.length - 1], bk });
  }

  const brands = Object.keys(BRAND_COLORS);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>

      {/* ── KPI Cards ─────────────────────────── */}
      <div>
        <div className="section-header">
          <span className="section-title">关键指标 · 最新财年</span>
          <span className="section-sub">Key Financial Metrics</span>
        </div>
        <div className="metrics-grid">
          {topMetrics.map(({ name, color, latest, prev, year }) => {
            const rev = latest.revenue?.total;
            const prevRev = prev?.revenue?.total;
            const growth = latest.revenue?.yoy_growth_pct;
            const gm = latest.gross_margin_pct;
            const nm = latest.net_margin_pct;
            const revChange = rev != null && prevRev != null && prevRev !== 0
              ? ((rev - prevRev) / prevRev * 100) : null;

            return [
              /* Revenue card */
              <div key={`${name}-rev`} className="metric-card" style={{ borderTopColor: color }}>
                <div className="metric-label">{name} · {year}</div>
                <AnimatedNumber value={rev} formatter={FMT_M} />
                <div className="metric-sub">{latest.currency} 营业收入</div>
                {(growth != null || revChange != null) && (
                  <div className={`metric-delta ${(growth ?? revChange) >= 0 ? "delta-up" : "delta-down"}`}>
                    {(growth ?? revChange) >= 0 ? "▲" : "▼"} {Math.abs(growth ?? revChange).toFixed(1)}% YoY
                  </div>
                )}
              </div>,
              /* Margin card */
              <div key={`${name}-margin`} className="metric-card" style={{ borderTopColor: color }}>
                <div className="metric-label">{name} 毛利率</div>
                <AnimatedNumber value={gm} formatter={FMT_PCT} />
                <div className="metric-sub">Gross Margin</div>
                {nm != null && (
                  <div className="metric-delta" style={{ color: "var(--text-muted)" }}>
                    净利率 {FMT_PCT(nm)}
                  </div>
                )}
              </div>,
            ];
          }).flat()}
        </div>
      </div>

      {/* ── FY alignment note ─────────────────── */}
      <div style={{
        fontSize: 11.5, fontWeight: 500, color: "#8b6914", padding: "8px 14px",
        background: "rgba(217,119,6,0.08)", borderRadius: "var(--radius)",
        border: "1px solid rgba(217,119,6,0.15)",
        fontFamily: "var(--font-body)", letterSpacing: "0.01em",
      }}>
        Note: 各品牌财年截止月不同 — Nike 5月 · Adidas 12月 · Lululemon 1月，跨品牌定量对比时请注意时间错位。
      </div>

      {/* ── Charts 2×2 Grid ───────────────────── */}
      <div className="charts-grid">

        {/* Revenue comparison */}
        <div className="chart-card chart-full">
          <div className="chart-title">营业收入对比 · Revenue Comparison</div>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={revenue_chart} barGap={6} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} vertical={false} />
              <XAxis dataKey="year" tick={{ fill: chartTheme.axis, fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: chartTheme.axis, fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={FMT_M} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12, color: chartTheme.text, paddingTop: 8 }} />
              {brands.map((b) => revenue_chart.some((r) => r[b] != null) && (
                <Bar key={b} dataKey={b} fill={BRAND_COLORS[b]} radius={[5, 5, 0, 0]} maxBarSize={64} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Gross margin trends */}
        <div className="chart-card">
          <div className="chart-title">毛利率趋势 · Gross Margin Trend</div>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={margin_chart} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} vertical={false} />
              <XAxis dataKey="year" tick={{ fill: chartTheme.axis, fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: chartTheme.axis, fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `${v}%`} domain={["auto", "auto"]} />
              <Tooltip content={<CustomTooltip unit="%" />} />
              <Legend wrapperStyle={{ fontSize: 12, color: chartTheme.text }} />
              {brands.map((b) => {
                const key = `${b} 毛利率`;
                return margin_chart.some((r) => r[key] != null) && (
                  <Line key={key} type="monotone" dataKey={key} stroke={BRAND_COLORS[b]}
                    strokeWidth={2.5} dot={{ r: 5, fill: BRAND_COLORS[b], strokeWidth: 0 }}
                    activeDot={{ r: 7, strokeWidth: 0 }} />
                );
              })}
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Operating margin trends */}
        <div className="chart-card">
          <div className="chart-title">营业利润率趋势 · Operating Margin Trend</div>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={margin_chart} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} vertical={false} />
              <XAxis dataKey="year" tick={{ fill: chartTheme.axis, fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: chartTheme.axis, fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `${v}%`} domain={["auto", "auto"]} />
              <Tooltip content={<CustomTooltip unit="%" />} />
              <Legend wrapperStyle={{ fontSize: 12, color: chartTheme.text }} />
              {brands.map((b) => {
                const key = `${b} 营业利润率`;
                return margin_chart.some((r) => r[key] != null) && (
                  <Line key={key} type="monotone" dataKey={key} stroke={BRAND_COLORS[b]}
                    strokeWidth={2.5} strokeDasharray="6 3"
                    dot={{ r: 5, fill: BRAND_COLORS[b], strokeWidth: 0 }}
                    activeDot={{ r: 7, strokeWidth: 0 }} />
                );
              })}
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* YoY Growth */}
        <div className="chart-card">
          <div className="chart-title">营收增速 · YoY Revenue Growth</div>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={growth_chart} barGap={4} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} vertical={false} />
              <XAxis dataKey="year" tick={{ fill: chartTheme.axis, fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: chartTheme.axis, fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `${v}%`} />
              <ReferenceLine y={0} stroke="#364b6b" strokeWidth={1} />
              <Tooltip content={<CustomTooltip unit="%" />} />
              <Legend wrapperStyle={{ fontSize: 12, color: chartTheme.text }} />
              {brands.map((b) => growth_chart.some((r) => r[b] != null) && (
                <Bar key={b} dataKey={b} fill={BRAND_COLORS[b]} radius={[4, 4, 0, 0]} maxBarSize={52} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Radar chart */}
        <div className="chart-card">
          <div className="chart-title">品牌竞争力雷达 · Competitive Radar</div>
          <ResponsiveContainer width="100%" height={250}>
            <RadarChart data={radar_data} outerRadius={88} margin={{ top: 0, right: 20, left: 20, bottom: 0 }}>
              <PolarGrid stroke={chartTheme.grid} />
              <PolarAngleAxis dataKey="metric" tick={{ fill: chartTheme.axis, fontSize: 11 }} />
              {brands.map((b) => radar_data.some((r) => r[b] != null) && (
                <Radar key={b} name={b} dataKey={b} stroke={BRAND_COLORS[b]}
                  fill={BRAND_COLORS[b]} fillOpacity={0.1} strokeWidth={2} />
              ))}
              <Legend wrapperStyle={{ fontSize: 12, color: chartTheme.text }} />
              <Tooltip contentStyle={{
                background: "#151d2e", border: "1px solid #253452",
                borderRadius: 6, fontSize: 12, fontFamily: "var(--font-mono)"
              }} />
            </RadarChart>
          </ResponsiveContainer>
        </div>

        {/* Regional revenue */}
        {region_chart.length > 0 && (
          <div className="chart-card">
            <div className="chart-title">地区营收分布 · Regional Revenue Breakdown</div>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={region_chart} layout="vertical" margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} horizontal={false} />
                <XAxis type="number" tick={{ fill: chartTheme.axis, fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={FMT_M} />
                <YAxis type="category" dataKey="brand" tick={{ fill: chartTheme.text, fontSize: 12 }} axisLine={false} tickLine={false} width={70} />
                <Tooltip content={<CustomTooltip />} />
                <Legend wrapperStyle={{ fontSize: 11, color: chartTheme.text }} />
                {["北美", "欧洲/中东/非洲", "大中华区", "亚太/拉美"].map((region, i) => {
                  const regionColors = ["#38bdf8", "#818cf8", "#f472b6", "#fbbf24"];
                  return region_chart.some((r) => r[region] != null) && (
                    <Bar key={region} dataKey={region} stackId="a" fill={regionColors[i]}
                      radius={i === 0 ? [4, 0, 0, 4] : i === 3 ? [0, 4, 4, 0] : [0, 0, 0, 0]} />
                  );
                })}
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* ── Calendar-Aligned Quarterly ──────────── */}
      {qData && qData.chart?.length > 0 && (() => {
        const fullQuarters = qData.chart.filter((r) => brands.every((b) => r[b] != null));
        if (fullQuarters.length === 0) return null;
        return (
        <div>
          <div className="section-header">
            <span className="section-title">日历对齐季度对比 · Calendar-Aligned Quarterly</span>
            <span className="section-sub">Nike/Lululemon: USD M &nbsp;|&nbsp; Adidas: EUR M &nbsp;|&nbsp; 仅显示三家数据齐全的季度</span>
          </div>
          <div className="chart-card chart-full">
            <div className="chart-title">季度营收对比 · Quarterly Revenue (aligned by calendar quarter)</div>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={fullQuarters} barGap={6} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} vertical={false} />
                <XAxis dataKey="quarter" tick={{ fill: chartTheme.axis, fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: chartTheme.axis, fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={FMT_M} />
                <Tooltip content={<CustomTooltip />} />
                <Legend wrapperStyle={{ fontSize: 11, color: chartTheme.text, paddingTop: 8 }} />
                {brands.map((b) => (
                  <Bar key={b} dataKey={b} fill={BRAND_COLORS[b]} radius={[5, 5, 0, 0]} maxBarSize={64} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        );
      })()}

      {/* ── Highlights ─────────────────────────── */}
      <div>
        <div className="section-header">
          <span className="section-title">年报关键亮点 · Annual Report Highlights</span>
        </div>
        <div className="highlights-grid">
          {topMetrics.map(({ name, color, latest, year }) => (
            <div key={name} className="highlight-card" style={{ borderLeftColor: color }}>
              <div className="highlight-brand" style={{ color }}>{name}</div>
              <div className="highlight-fy">{year}</div>
              <ul className="highlight-list">
                {(latest.key_highlights || []).slice(0, 5).map((h, i) => (
                  <li key={i}>{h}</li>
                ))}
                {(!latest.key_highlights || latest.key_highlights.length === 0) && (
                  <li style={{ color: "var(--text-muted)", fontStyle: "italic" }}>暂无数据</li>
                )}
              </ul>
            </div>
          ))}
        </div>
      </div>

      {/* ── Summary Table ──────────────────────── */}
      <div>
        <div className="section-header">
          <span className="section-title">财务数据汇总 · Financial Data Summary</span>
        </div>
        <div style={{
          background: "var(--surface)", border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-lg)", overflow: "hidden",
        }}>
          <div style={{ overflowX: "auto" }}>
            <table className="summary-table">
              <thead>
                <tr>
                  <th>品牌</th>
                  <th>财年</th>
                  <th>营收 (M)</th>
                  <th>毛利率</th>
                  <th>营业利润率</th>
                  <th>净利润率</th>
                  <th>营收增速</th>
                  <th>库存 (M)</th>
                </tr>
              </thead>
              <tbody>
                {summary.map((row, i) => (
                  <tr key={i}>
                    <td style={{ color: BRAND_COLORS[row.brand] || "var(--text)" }}>
                      {row.brand}
                    </td>
                    <td>{row.year}</td>
                    <td>{FMT_M(row["营业收入 (M)"])}</td>
                    <td>{FMT_PCT(row["毛利率 (%)"])}</td>
                    <td>{FMT_PCT(row["营业利润率 (%)"])}</td>
                    <td>{FMT_PCT(row["净利润率 (%)"])}</td>
                    <td>
                      {row["营收增速 (%)"] != null
                        ? <span className={row["营收增速 (%)"] >= 0 ? "delta-up" : "delta-down"} style={{ fontFamily: "var(--font-mono)", fontSize: 11.5 }}>
                          {row["营收增速 (%)"] >= 0 ? "▲" : "▼"} {Math.abs(row["营收增速 (%)"]).toFixed(1)}%
                        </span>
                        : <span style={{ color: "var(--text-muted)" }}>—</span>}
                    </td>
                    <td>{FMT_M(row["库存 (M)"])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
