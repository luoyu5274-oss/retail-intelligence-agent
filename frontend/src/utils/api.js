const BASE = "http://localhost:8000";

export async function getStatus() {
  const r = await fetch(`${BASE}/api/status`);
  return r.json();
}

export async function initialize() {
  const r = await fetch(`${BASE}/api/initialize`, { method: "POST" });
  return r.json();
}

export function listenProgress(onMessage, onDone) {
  const es = new EventSource(`${BASE}/api/progress`);
  let deadline = setTimeout(() => {
    es.close();
    onMessage("❌ 初始化超时 (10分钟)，请检查后端日志");
    onDone(false);
  }, 600_000); // 10 minute timeout

  es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.type === "heartbeat") return;
    if (data.type === "done" || data.type === "error") {
      clearTimeout(deadline);
      onMessage(data.message || "完成");
      onDone(data.type === "done");
      es.close();
    } else {
      onMessage(data.message || "");
    }
  };
  es.onerror = () => {
    clearTimeout(deadline);
    es.close();
    onDone(false);
  };
  return () => {
    clearTimeout(deadline);
    es.close();
  };
}

export async function getFinancial() {
  const r = await fetch(`${BASE}/api/financial`);
  if (!r.ok) throw new Error("财务数据未就绪");
  return r.json();
}

export async function sendChat(question, brandFilter = null) {
  const r = await fetch(`${BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, brand_filter: brandFilter }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || "请求失败");
  }
  return r.json();
}

export async function getChatHistory() {
  const r = await fetch(`${BASE}/api/chat/history`);
  return r.json();
}

export async function clearChatHistory() {
  await fetch(`${BASE}/api/chat/history`, { method: "DELETE" });
}

export async function triggerScrape() {
  const r = await fetch(`${BASE}/api/scrape`, { method: "POST" });
  return r.json();
}

export async function getScrapeLog() {
  const r = await fetch(`${BASE}/api/scrape/log`);
  return r.json();
}

export async function getQuarterly() {
  const r = await fetch(`${BASE}/api/quarterly`);
  if (!r.ok) throw new Error("季度数据未就绪");
  return r.json();
}

export async function resetIndex() {
  const r = await fetch(`${BASE}/api/reset`, { method: "POST" });
  return r.json();
}
