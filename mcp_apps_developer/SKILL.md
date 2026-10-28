---
name: MCP Apps Developer
description: End-to-end guide, architecture patterns, and starter templates for building interactive visual MCP Apps (ui:// resources with text/html;profile=mcp-app and SEP-1865 JSON-RPC postMessage bridge) on Google Cloud Run.
---

# MCP Apps Developer Skill (`ui://` Interactive Visual Workflows)

Use this skill whenever a partner or developer wants to **enhance an MCP Server with interactive visual workflows ("MCP Apps")** because plain-text markdown or raw JSON is insufficient for the user experience (e.g., interactive analytics dashboards, dependency trees, network graphs, side-by-side document/PDF comparators, molecular viewers, or interactive configuration tables).

*(Note: This skill implements the official **MCP Apps (`ui://`, `text/html;profile=mcp-app`, SEP-1865)** specification used by MCP-App-capable hosts such as Claude, MCP Inspector, and custom enterprise hosts. Companion skills: [**Cloud Run MCP Server Creator**](../cloud_run_mcp_server_creator/SKILL.md), [**API-to-MCP Wrapper**](../api_to_mcp_wrapper/SKILL.md), and [**Gemini Enterprise MCP Registrar**](../gemini_enterprise_mcp_registrar/SKILL.md).)*

---

## Core Architecture & Hard-Won Lessons for MCP Apps on Cloud Run

```mermaid
sequenceDiagram
    participant User as End User
    participant Host as MCP Host UI (Chat + Sandbox Iframe)
    participant Server as Cloud Run FastMCP Server

    User->>Host: "Show me the interactive dashboard for X"
    Host->>Server: tools/call (search_items or open_dashboard_app)
    Server-->>Host: CallToolResult (TextContent + EmbeddedResource ui://... + structuredContent)
    Host->>Host: Mounts sandboxed iframe with text/html;profile=mcp-app
    Host->>Host: iframe sends ui/initialize -> Host replies & sends ui/notifications/tool-result
    User->>Host: Clicks filter / "Run Deep Comparison" button inside iframe
    Host->>Server: iframe sends postMessage(tools/call) -> Host proxies to Server /mcp
    Server-->>Host: Updated tool result JSON -> iframe re-renders live
    User->>Host: Clicks "Ask AI to Summarize Selection" inside iframe
    Host->>Host: iframe sends postMessage(ui/message) -> Host submits prompt to LLM
```

### 1. The 3 Required Metadata & Resource Contracts
Every MCP App requires three matching constants (see [`resources/mcp_app_template.py`](./resources/mcp_app_template.py)):
1. **Resource URI (`ui://`):** `APP_RESOURCE_URI = "ui://<server-slug>/<view-slug>"`
2. **MIME Type:** `MCP_APP_MIME_TYPE = "text/html;profile=mcp-app"`
3. **Tool & Resource `_meta`:**
   ```python
   APP_TOOL_META = {
       "ui": {
           "resourceUri": APP_RESOURCE_URI,
           "visibility": ["model", "app"],
       },
       "ui/resourceUri": APP_RESOURCE_URI,
   }

   APP_RESOURCE_META = {
       "ui": {
           "prefersBorder": True,
           "csp": {
               "connectDomains": ["https://<your-cloud-run-url>"],
               "resourceDomains": ["https://<your-cloud-run-url>"],
               "frameDomains": ["https://<your-cloud-run-url>"],
           },
       }
   }
   ```

### 2. Dual-Delivery Pattern (Supporting Every MCP Host)
Different MCP hosts load `ui://` apps in slightly different ways. Always implement **both** delivery mechanisms so your MCP App works everywhere:
1. **Registered `@mcp.resource(APP_RESOURCE_URI, mime_type="text/html;profile=mcp-app")` + Linked Data Tool (`@mcp.tool(meta=APP_TOOL_META)`):**
   * When the LLM calls your standard data tool (e.g., `search_records`), cache the enriched payload in memory (`set_cached_app_payload(enriched)`) and return the JSON string.
   * When the host inspects `meta.ui.resourceUri` and calls `resources/read` on `ui://<server>/<view>`, `build_app_html(get_cached_app_payload())` returns the HTML already pre-hydrated with the latest data—even before `ui/notifications/tool-result` arrives over `postMessage`!
2. **Dedicated `open_<view>_app` Launcher Tool returning `CallToolResult` + `EmbeddedResource`:**
   * Expose an explicit tool (e.g., `open_interactive_dashboard_app`) that returns a `CallToolResult` containing:
     * `TextContent(type="text", text=raw_json)` (so the LLM can read the data)
     * `EmbeddedResource(type="resource", resource=TextResourceContents(uri=AnyUrl(APP_RESOURCE_URI), mimeType=MCP_APP_MIME_TYPE, text=app_html, _meta=APP_RESOURCE_META))`
     * `structuredContent=enriched_payload`

### 3. Bidirectional JSON-RPC 2.0 `window.parent.postMessage` Bridge
Inside the self-contained HTML bundle (`build_app_html()`), always include the standard MCP Apps JSON-RPC bridge:
* **Handshake & Auto-Sizing:**
  * Send `ui/initialize` on load, apply `hostContext.theme` (`light`/`dark`), send `ui/notifications/initialized`, and attach a `ResizeObserver` that emits `ui/notifications/size-changed`.
* **Receiving Data from the Host:**
  * Listen for `ui/notifications/tool-input` (to pre-fill search inputs while the tool is running) and `ui/notifications/tool-result` (extracting `params.structuredContent` or parsing `params.content[0].text` JSON).
* **Triggering Live MCP Tools from Inside the UI (`tools/call`):**
  * Interactive controls (search bars, filter dropdowns, side-by-side comparison selectors) call `sendMcpRequest("tools/call", { name: "<tool_name>", arguments: {...} })` with an automatic fallback to a Cloud Run HTTP helper endpoint (`/apps/api/<view>`) when opened standalone in a browser tab.
* **Sending Context Back to the AI Chat (`ui/message`):**
  * Include an **"✨ Ask AI to Analyze Selection"** button that posts `method: "ui/message"` with the user's currently filtered slice or chart markdown so the LLM can immediately reason over what the user is looking at.

### 4. Sandbox-Safe HTTP Preview Routes & COOP Headers
* Sandboxed iframes block external popups or PDFs that return `Cross-Origin-Opener-Policy: same-origin`.
* Always mount a standalone preview route (`/apps/raw/<view-slug>`) and any helper/document routes (`/apps/api/<view-slug>`) on your Starlette ASGI app (`get_asgi_app()`) with:
  ```python
  headers = {
      "Cross-Origin-Opener-Policy": "unsafe-none",
      "Access-Control-Allow-Origin": "*",
  }
  ```

---

## Step-by-Step Workflow

### Step 1: Design the Visual Workflow
Identify why plain text falls short for the partner's use case and select the high-value visual pattern:
* **Analytics & White-Space Dashboard:** KPI strip + interactive click-to-filter bar charts + comparison matrix + detail cards (see [`resources/mcp_app_template.py`](./resources/mcp_app_template.py)).
* **Hierarchy / Dependency Tree & Side-by-Side Comparator:** Collapsible tree + element breakdown + 2-column diff comparator + exportable assessment matrix.
* **Network / Citation / Relationship Graph:** Interactive SVG/Canvas force-directed node-link graph with node inspector.
* **Synchronized Document / PDF & Media Split-Viewer:** Drawing/image carousel synced with specification text and sandbox-safe PDF reader.

### Step 2: Create the MCP App Module from Template
1. Copy [`resources/mcp_app_template.py`](./resources/mcp_app_template.py) into `<MCP_SERVER_DIR>/mcp_apps/<view_name>_app.py`.
2. Customize:
   * `APP_RESOURCE_URI = "ui://<server-name>/<view-name>"`
   * `enrich_app_payload(raw_data)` to compute server-side aggregations, KPIs, or tree structures and cache the payload.
   * `build_app_html(initial_payload)` with your custom CSS/JS tabs, charts, and interactive controls.

### Step 3: Wire Resource, Tools & Preview Routes in `server.py`
In your FastMCP `server.py`, add:
1. `@mcp.resource(APP_RESOURCE_URI, mime_type=MCP_APP_MIME_TYPE, meta=APP_RESOURCE_META)`
2. `meta=APP_TOOL_META` on the primary data tool(s).
3. `@mcp.tool(annotations=READ_ONLY_ANNOTATIONS, meta=APP_TOOL_META) async def open_<view>_app(...) -> CallToolResult` returning both `TextContent` and `EmbeddedResource`.
4. Preview route `Route("/apps/raw/<view-name>", app_raw_preview, methods=["GET"])` inside `get_asgi_app()`.

### Step 4: Verify Both MCP `resources/read` and Browser Preview
1. Start the server locally and test `GET http://localhost:8080/apps/raw/<view-name>`.
2. Test `POST /mcp` with `method: "resources/read"` for `"uri": "ui://<server-name>/<view-name>"` and `method: "tools/call"` for `open_<view>_app`.
