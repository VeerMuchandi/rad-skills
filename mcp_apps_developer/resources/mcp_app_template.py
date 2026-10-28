"""Starter Template for an Interactive MCP App (`ui://`, `text/html;profile=mcp-app`).

Implements:
1. Standard MCP Apps Resource & Tool Metadata (`APP_RESOURCE_URI`, `APP_TOOL_META`, `APP_RESOURCE_META`).
2. In-memory pre-hydration cache (`set_cached_app_payload`, `get_cached_app_payload`) and server-side payload enricher.
3. Self-contained HTML/CSS/JS workbench (`build_app_html`) featuring:
   - Full SEP-1865 JSON-RPC 2.0 `window.parent.postMessage` bridge (`ui/initialize`, `ui/notifications/initialized`,
     `ui/notifications/tool-input`, `ui/notifications/tool-result`, `ui/notifications/host-context-changed`,
     `ui/notifications/size-changed`, `tools/call`, and `ui/message`).
   - KPI summary strip, interactive click-to-filter category bars, live search bar invoking `tools/call`,
     and an "Ask AI to Analyze" button emitting `ui/message`.
"""

from __future__ import annotations

from collections import Counter
import json
from typing import Any, Dict, List, Optional

MCP_APP_MIME_TYPE = "text/html;profile=mcp-app"

# Customize these for your MCP server and view name
APP_RESOURCE_URI = "ui://custom-mcp/interactive-workbench"
LINKED_SEARCH_TOOL_NAME = "search_records"

APP_TOOL_META: Dict[str, Any] = {
    "ui": {
        "resourceUri": APP_RESOURCE_URI,
        "visibility": ["model", "app"],
    },
    "ui/resourceUri": APP_RESOURCE_URI,
}

APP_RESOURCE_META: Dict[str, Any] = {
    "ui": {
        "prefersBorder": True,
        "csp": {
            "connectDomains": ["*"],
            "resourceDomains": ["*"],
            "frameDomains": ["*"],
        },
    }
}

_LAST_APP_PAYLOAD: Optional[Dict[str, Any]] = None


def set_cached_app_payload(payload: Dict[str, Any]) -> None:
    """Stores the most recent enriched payload so `resources/read` can pre-hydrate the UI."""
    global _LAST_APP_PAYLOAD
    if isinstance(payload, dict):
        _LAST_APP_PAYLOAD = payload


def get_cached_app_payload() -> Optional[Dict[str, Any]]:
    """Returns the most recent enriched payload."""
    return _LAST_APP_PAYLOAD


def enrich_app_payload(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalizes tool output and computes summary analytics for the interactive MCP App."""
    if not isinstance(raw_data, dict):
        return {"status": "error", "message": "Invalid payload"}

    items: List[Dict[str, Any]] = raw_data.get("results") or raw_data.get("items") or []
    category_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()

    normalized_items: List[Dict[str, Any]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        rec_id = str(item.get("id") or f"ITEM-{idx + 1}")
        title = str(item.get("title") or item.get("name") or "Untitled Record")
        category = str(item.get("category") or item.get("type") or "General")
        status = str(item.get("status") or "Active")
        summary = str(item.get("summary") or item.get("description") or item.get("snippet") or "")

        category_counts[category] += 1
        status_counts[status] += 1

        normalized_items.append({
            "id": rec_id,
            "title": title,
            "category": category,
            "status": status,
            "summary": summary,
            "raw": item,
        })

    enriched = {
        **raw_data,
        "app_resource_uri": APP_RESOURCE_URI,
        "normalized_items": normalized_items,
        "analytics": {
            "total_items": len(normalized_items),
            "unique_categories": len(category_counts),
            "top_categories": [{"name": k, "count": v} for k, v in category_counts.most_common(8)],
            "status_breakdown": [{"status": k, "count": v} for k, v in status_counts.most_common(6)],
        },
    }
    set_cached_app_payload(enriched)
    return enriched


def build_app_html(initial_payload: Optional[Dict[str, Any]] = None) -> str:
    """Builds a self-contained HTML5/CSS/JS bundle for `ui://` (`text/html;profile=mcp-app`)."""
    safe_json = json.dumps(initial_payload or get_cached_app_payload() or None).replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Interactive MCP App Workbench</title>
  <style>
    :root {{
      --bg: #f8fafc;
      --surface: #ffffff;
      --border: #e2e8f0;
      --text: #0f172a;
      --text-muted: #64748b;
      --primary: #4f46e5;
      --primary-light: #eef2ff;
      --emerald: #059669;
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, monospace;
    }}
    [data-theme="dark"] {{
      --bg: #0f172a;
      --surface: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #818cf8;
      --primary-light: #1e1b4b;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: var(--font-sans);
      background: var(--bg);
      color: var(--text);
      padding: 14px;
      line-height: 1.45;
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px 14px;
      margin-bottom: 12px;
    }}
    .title {{ font-size: 15px; font-weight: 700; }}
    .subtitle {{ font-size: 12px; color: var(--text-muted); }}
    .toolbar {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
    .input {{
      padding: 6px 10px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--bg);
      color: var(--text);
      font-size: 12.5px;
    }}
    .btn {{
      padding: 6px 12px;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: var(--surface);
      color: var(--text);
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
    }}
    .btn-primary {{
      background: var(--primary);
      color: #ffffff;
      border-color: var(--primary);
    }}
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 10px;
      margin-bottom: 12px;
    }}
    .kpi-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px 12px;
    }}
    .kpi-label {{ font-size: 11px; color: var(--text-muted); text-transform: uppercase; }}
    .kpi-val {{ font-size: 18px; font-weight: 700; color: var(--primary); margin-top: 2px; }}
    .layout {{
      display: grid;
      grid-template-columns: 260px 1fr;
      gap: 12px;
    }}
    @media (max-width: 680px) {{
      .layout {{ grid-template-columns: 1fr; }}
    }}
    .panel {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px;
    }}
    .panel-title {{
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      color: var(--text-muted);
      margin-bottom: 10px;
    }}
    .bar-row {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      margin-bottom: 7px;
      cursor: pointer;
      padding: 4px;
      border-radius: 5px;
    }}
    .bar-row:hover {{ background: var(--primary-light); }}
    .bar-track {{
      flex: 1;
      height: 7px;
      background: var(--border);
      border-radius: 4px;
      overflow: hidden;
    }}
    .bar-fill {{ height: 100%; background: var(--primary); }}
    .card {{
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px 12px;
      margin-bottom: 8px;
    }}
    .badge {{
      display: inline-block;
      padding: 2px 7px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 600;
      background: var(--primary-light);
      color: var(--primary);
    }}
    .statusbar {{
      margin-top: 10px;
      font-size: 11px;
      color: var(--text-muted);
      display: flex;
      justify-content: space-between;
    }}
  </style>
</head>
<body>
  <header class="header">
    <div>
      <div class="title">Interactive MCP App Workbench</div>
      <div class="subtitle">Click any category bar to filter • Trigger live MCP tools or send insights to AI</div>
    </div>
    <div class="toolbar">
      <input id="queryInput" class="input" type="text" placeholder="Search via MCP tool..." />
      <button id="runToolBtn" class="btn btn-primary">🔍 Search via MCP</button>
      <button id="askAiBtn" class="btn">✨ Ask AI to Analyze</button>
    </div>
  </header>

  <section class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-label">Total Records</div>
      <div class="kpi-val" id="kpiTotal">0</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Categories</div>
      <div class="kpi-val" id="kpiCategories">0</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Active Filter</div>
      <div class="kpi-val" id="kpiFilter" style="font-size:13px;cursor:pointer;" title="Click to clear">All (Click to clear)</div>
    </div>
  </section>

  <main class="layout">
    <aside class="panel">
      <div class="panel-title">By Category (Click to Filter)</div>
      <div id="categoryBars"></div>
    </aside>
    <section class="panel">
      <div class="panel-title">Matching Records</div>
      <div id="recordsContainer"></div>
    </section>
  </main>

  <footer class="statusbar">
    <span id="statusText">Ready</span>
    <span>{APP_RESOURCE_URI}</span>
  </footer>

  <script>
    const INITIAL_PAYLOAD = {safe_json};
    const SEARCH_TOOL_NAME = "{LINKED_SEARCH_TOOL_NAME}";
    let currentPayload = null;
    let activeCategoryFilter = null;

    // =========================================================================
    // 1. SEP-1865 MCP Apps JSON-RPC 2.0 postMessage Bridge
    // =========================================================================
    let rpcId = 1;
    const pendingRpc = new Map();

    function sendMcpRequest(method, params) {{
      return new Promise((resolve, reject) => {{
        if (!window.parent || window.parent === window) {{
          reject(new Error("No parent MCP host window"));
          return;
        }}
        const id = rpcId++;
        pendingRpc.set(id, {{ resolve, reject }});
        window.parent.postMessage({{ jsonrpc: "2.0", id, method, params }}, "*");
        setTimeout(() => {{
          if (pendingRpc.has(id)) {{
            pendingRpc.delete(id);
            reject(new Error("MCP RPC timeout"));
          }}
        }}, 20000);
      }});
    }}

    function sendMcpNotification(method, params = {{}}) {{
      if (window.parent && window.parent !== window) {{
        window.parent.postMessage({{ jsonrpc: "2.0", method, params }}, "*");
      }}
    }}

    window.addEventListener("message", (event) => {{
      const msg = event.data;
      if (!msg || typeof msg !== "object" || msg.jsonrpc !== "2.0") return;

      if (msg.id !== undefined && pendingRpc.has(msg.id)) {{
        const {{ resolve, reject }} = pendingRpc.get(msg.id);
        pendingRpc.delete(msg.id);
        if (msg.error) reject(msg.error);
        else resolve(msg.result);
        return;
      }}

      if (msg.method === "ui/notifications/tool-input" && msg.params?.arguments) {{
        const q = msg.params.arguments.query || "";
        if (q) document.getElementById("queryInput").value = q;
      }} else if (msg.method === "ui/notifications/tool-result" && msg.params) {{
        const p = msg.params;
        if (p.structuredContent) hydratePayload(p.structuredContent);
        else if (Array.isArray(p.content)) {{
          for (const block of p.content) {{
            if (block.type === "text" && block.text) {{
              try {{
                hydratePayload(JSON.parse(block.text));
                break;
              }} catch (_) {{}}
            }}
          }}
        }}
      }} else if (msg.method === "ui/notifications/host-context-changed") {{
        const theme = msg.params?.theme;
        if (theme === "dark" || theme === "light") {{
          document.documentElement.setAttribute("data-theme", theme);
        }}
      }}
    }});

    async function initBridge() {{
      if (window.parent && window.parent !== window) {{
        try {{
          const res = await sendMcpRequest("ui/initialize", {{
            protocolVersion: "2025-06-18",
            appInfo: {{ name: "Interactive MCP App Workbench", version: "1.0.0" }},
            appCapabilities: {{}},
          }});
          if (res?.hostContext?.theme) {{
            document.documentElement.setAttribute("data-theme", res.hostContext.theme);
          }}
        }} catch (_) {{}}
        sendMcpNotification("ui/notifications/initialized", {{}});
      }}
      if (typeof ResizeObserver !== "undefined") {{
        new ResizeObserver(() => {{
          sendMcpNotification("ui/notifications/size-changed", {{
            width: document.documentElement.scrollWidth,
            height: document.documentElement.scrollHeight,
          }});
        }}).observe(document.body);
      }}
    }}

    // =========================================================================
    // 2. Client-Side Normalization & Rendering
    // =========================================================================
    function escapeHtml(s) {{
      return String(s || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }}

    function hydratePayload(raw) {{
      if (!raw || typeof raw !== "object") return;
      currentPayload = raw;
      renderAll();
    }}

    function renderAll() {{
      if (!currentPayload) return;
      const items = currentPayload.normalized_items || currentPayload.results || [];
      const analytics = currentPayload.analytics || {{}};
      const filtered = activeCategoryFilter
        ? items.filter((i) => i.category === activeCategoryFilter)
        : items;

      document.getElementById("kpiTotal").textContent = filtered.length;
      document.getElementById("kpiCategories").textContent = analytics.unique_categories ?? 0;
      document.getElementById("kpiFilter").textContent = activeCategoryFilter || "All (Click to clear)";

      const cats = analytics.top_categories || [];
      const maxCount = Math.max(1, ...cats.map((c) => c.count || 1));
      document.getElementById("categoryBars").innerHTML = cats.length
        ? cats.map((c) => `
            <div class="bar-row" data-cat="${{escapeHtml(c.name)}}">
              <span style="width:95px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${{escapeHtml(c.name)}}</span>
              <div class="bar-track"><div class="bar-fill" style="width:${{Math.round((c.count / maxCount) * 100)}}%"></div></div>
              <span style="font-family:var(--font-mono);font-size:11px;">${{c.count}}</span>
            </div>
          `).join("")
        : '<div style="font-size:12px;color:var(--text-muted)">No categories yet.</div>';

      document.querySelectorAll("[data-cat]").forEach((el) => {{
        el.addEventListener("click", () => {{
          const cat = el.getAttribute("data-cat");
          activeCategoryFilter = activeCategoryFilter === cat ? null : cat;
          renderAll();
        }});
      }});

      document.getElementById("recordsContainer").innerHTML = filtered.length
        ? filtered.map((item) => `
            <div class="card">
              <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
                <strong style="font-size:13.5px;">${{escapeHtml(item.title || item.id)}}</strong>
                <span class="badge">${{escapeHtml(item.category || "General")}}</span>
              </div>
              <div style="font-size:12px;color:var(--text-muted);margin-top:4px;">${{escapeHtml(item.summary)}}</div>
            </div>
          `).join("")
        : '<div style="font-size:12px;color:var(--text-muted)">No records to display.</div>';
    }}

    document.getElementById("kpiFilter").addEventListener("click", () => {{
      activeCategoryFilter = null;
      renderAll();
    }});

    document.getElementById("runToolBtn").addEventListener("click", async () => {{
      const query = document.getElementById("queryInput").value.trim();
      document.getElementById("statusText").textContent = "Calling MCP tool " + SEARCH_TOOL_NAME + "...";
      try {{
        const res = await sendMcpRequest("tools/call", {{
          name: SEARCH_TOOL_NAME,
          arguments: {{ query }},
        }});
        if (res?.structuredContent) hydratePayload(res.structuredContent);
        else if (Array.isArray(res?.content)) {{
          for (const c of res.content) {{
            if (c.type === "text" && c.text) {{
              hydratePayload(JSON.parse(c.text));
              break;
            }}
          }}
        }}
        document.getElementById("statusText").textContent = "Updated via MCP tools/call";
      }} catch (e) {{
        document.getElementById("statusText").textContent = "Host tools/call unavailable in standalone mode";
      }}
    }});

    document.getElementById("askAiBtn").addEventListener("click", () => {{
      const items = (currentPayload?.normalized_items || []).slice(0, 5);
      const summaryText = items.map((i) => `- ${{i.title}} (${{i.category}}): ${{i.summary}}`).join("\\n");
      sendMcpNotification("ui/message", {{
        role: "user",
        content: [{{
          type: "text",
          text: `Please analyze the currently displayed records in the workbench (Filter: ${{activeCategoryFilter || "All"}}):\\n${{summaryText}}`
        }}]
      }});
      document.getElementById("statusText").textContent = "Sent analysis prompt to AI host";
    }});

    initBridge();
    if (INITIAL_PAYLOAD) hydratePayload(INITIAL_PAYLOAD);
  </script>
</body>
</html>"""
