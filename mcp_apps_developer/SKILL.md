---
name: MCP Apps Developer
description: End-to-end UX design and implementation guide, brand theming system, architecture patterns, and starter templates for building interactive visual MCP Apps (ui:// resources with text/html;profile=mcp-app and SEP-1865 JSON-RPC postMessage bridge) on Google Cloud Run.
---

# MCP Apps Developer Skill (`ui://` Interactive Visual Workflows)

Use this skill whenever a partner or developer wants to **design and build interactive visual workflows ("MCP Apps")** on top of an MCP Server because plain-text markdown or raw JSON is insufficient for the user experience (e.g., interactive analytics dashboards, hierarchical trees, network graphs, side-by-side comparators, document/media viewers, or interactive configuration matrices).

> **Public Specification Reference:**
> This skill implements the official Model Context Protocol **MCP Apps Extension (SEP-1865)** specification (`ui://` URI scheme, `text/html;profile=mcp-app` MIME type, and JSON-RPC 2.0 over `window.parent.postMessage`).
> * Official Specification & SDK Reference: [https://github.com/modelcontextprotocol/ext-apps](https://github.com/modelcontextprotocol/ext-apps) and [https://modelcontextprotocol.io](https://modelcontextprotocol.io)
> * Companion Skills: [**Cloud Run MCP Server Creator**](../cloud_run_mcp_server_creator/SKILL.md), [**API-to-MCP Wrapper**](../api_to_mcp_wrapper/SKILL.md), and [**Gemini Enterprise MCP Registrar**](../gemini_enterprise_mcp_registrar/SKILL.md).

---

## Mandatory Two-Phase Process: UX Design First $\rightarrow$ Build Second

> [!IMPORTANT]
> **Never jump straight to generating HTML/JS code when asked to design or plan an MCP App.**
> Always follow a strict two-phase workflow:
> 1. **Phase 1 — UX, Brand Theme & Visual Wireframe Design Gate (Produce Design Document with Nano Banana Wireframes & STOP):**
>    Analyze the MCP server's tools and data payloads, define the visual workflow patterns, capture the partner's **Brand & Theme Tokens** (colors, typography, border radius, light/dark mode), specify the bidirectional MCP interactions (`tools/call` and `ui/message`), **generate visual UI wireframe mockups for each proposed MCP App using Nano Banana (`generate_image`, 16:9 aspect ratio, interface-only without device frames)**, copy the generated wireframe images into `<MCP_SERVER_DIR>/design/`, embed them into the UX Design Document (`<MCP_SERVER_DIR>/design/mcp_apps_ux_design.md`), and **STOP for user review and approval**.
> 2. **Phase 2 — Implementation, Wiring & Deployment:**
>    Once the user approves the UX design, wireframes, and brand theme, implement the self-contained MCP App module(s) from [`resources/mcp_app_template.py`](./resources/mcp_app_template.py), wire the `@mcp.resource` and `EmbeddedResource` tools in `server.py`, verify locally, and deploy to Cloud Run.

---

## Core Architecture & Hard-Won Lessons for MCP Apps on Cloud Run

```mermaid
sequenceDiagram
    participant User as End User
    participant Host as MCP Host UI (Chat + Sandboxed Iframe)
    participant Server as Cloud Run FastMCP Server

    User->>Host: "Open the interactive workbench for X"
    Host->>Server: tools/call (data tool or open_<view>_app)
    Server-->>Host: CallToolResult (TextContent + EmbeddedResource ui://... + structuredContent)
    Host->>Host: Mounts sandboxed iframe with text/html;profile=mcp-app
    Host->>Host: iframe sends ui/initialize -> Host replies & sends ui/notifications/tool-result
    User->>Host: Interacts with filters / comparison controls inside iframe
    Host->>Server: iframe sends postMessage(tools/call) -> Host proxies to Server /mcp
    Server-->>Host: Updated tool result JSON -> iframe re-renders live
    User->>Host: Clicks "Ask AI to Analyze Selection" inside iframe
    Host->>Host: iframe sends postMessage(ui/message) -> Host submits prompt to LLM
```

### 1. Corporate Brand & Theme Customization System (CSS Custom Properties & Strict Design Compliance)
Partners require MCP Apps to match their company's visual identity and approved design specification. Every MCP App built with this skill must parameterize its styling via a structured **`BRAND_THEME` token dictionary** injected into `:root` and `[data-theme="dark"]` CSS variables (see [`resources/mcp_app_template.py`](./resources/mcp_app_template.py)):
* **Color Palette Tokens:**
  * `--header-bg` & `--header-text`: Top institutional/corporate banner and inset control bar colors
  * `--brand-primary` / `--primary`: Primary corporate action color (buttons, active tab underlines, primary chart series)
  * `--brand-primary-light` / `--primary-light`: Soft tint for badges and active pill states
  * `--brand-secondary` / `--brand-accent`: Secondary chart series, status pills, and highlight accents
  * `--bg-canvas` & `--bg-surface`: Outer canvas background and card/table/chart surface colors
  * `--text-primary` & `--text-secondary`: High-contrast body and muted label typography
  * `--status-success`, `--status-warning`, `--status-danger`: Semantic status badges and delta bars
* **Typography & Shape Tokens:**
  * `--font-sans`: Company primary UI font stack (e.g., `'Inter', 'Google Sans', system-ui, sans-serif`)
  * `--font-display`: Optional heading/brand display font
  * `--font-mono`: Monospace font (`font-variant-numeric: tabular-nums`) for IDs, tickers, code, and numerical tables
  * `--radius-sm`, `--radius-md`, `--radius-lg`: Corner rounding matching the partner's UI style (sharp `4px–6px`, modern `8px–12px`, or pill `16px+`)
* **Strict Design Theme Compliance & Host Theme Lock (`LOCK_DESIGN_THEME = true`):**
  * **Always follow the exact color scheme and theme mode specified in the approved UX Design Document (`mcp_apps_ux_design.md`) and Nano Banana wireframes.**
  * By default, set `const LOCK_DESIGN_THEME = true;` and initialize `<html data-theme="light">` (or `"dark"` if the approved design doc specifies a dark theme) so that `initRes.hostContext.theme` and `ui/notifications/host-context-changed` from the MCP Host (e.g., Gemini Enterprise running in dark mode) **never silently override** the approved corporate color scheme. Only enable automatic host theme switching (`LOCK_DESIGN_THEME = false`) if the design document explicitly requests host-driven theme overrides. Provide an optional manual in-app toggle button (`☀️ / 🌙`) if dual-theme support is desired.

### 2. The 3 Required Metadata & Resource Contracts
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

### 3. Dual-Delivery Pattern (Supporting Every MCP Host)
Different MCP hosts load `ui://` apps in slightly different ways. Always implement **both** delivery mechanisms so your MCP App works across all hosts:
1. **Registered `@mcp.resource(APP_RESOURCE_URI, mime_type="text/html;profile=mcp-app")` + Linked Data Tool (`@mcp.tool(meta=APP_TOOL_META)`):**
   * When the LLM calls a standard data tool (e.g., `search_records`), cache the enriched payload (`set_cached_app_payload(enriched)`) and return the JSON string.
   * When the host inspects `meta.ui.resourceUri` and calls `resources/read` on `ui://<server>/<view>`, `build_app_html(get_cached_app_payload())` returns the HTML pre-hydrated with the latest data—even before `ui/notifications/tool-result` arrives over `postMessage`.
2. **Dedicated `open_<view>_app` Launcher Tool returning `CallToolResult` + `EmbeddedResource`:**
   * Expose an explicit launcher tool (e.g., `open_interactive_workbench_app`) that returns a `CallToolResult` containing:
     * `TextContent(type="text", text=raw_json)` (for the LLM to reason over)
     * `EmbeddedResource(type="resource", resource=TextResourceContents(uri=AnyUrl(APP_RESOURCE_URI), mimeType=MCP_APP_MIME_TYPE, text=app_html, _meta=APP_RESOURCE_META))`
     * `structuredContent=enriched_payload`

### 4. Bidirectional JSON-RPC 2.0 `window.parent.postMessage` Bridge
Inside the self-contained HTML bundle (`build_app_html()`), always include the standard SEP-1865 JSON-RPC bridge:
* **Handshake & Auto-Sizing:**
  * Send `ui/initialize` on load, keep the approved design theme locked (`LOCK_DESIGN_THEME = true`) unless host theme override is explicitly requested, send `ui/notifications/initialized`, and attach a `ResizeObserver` that emits `ui/notifications/size-changed`.
* **Receiving Data from the Host:**
  * Listen for `ui/notifications/tool-input` (to pre-fill inputs while the tool is running) and `ui/notifications/tool-result` (extracting `params.structuredContent` or parsing `params.content[0].text` JSON).
* **Smart State Merging on Partial `ui/notifications/tool-result` Events (CRITICAL):**
  * When an interactive control inside the iframe calls `sendMcpRequest("tools/call", ...)` for a secondary/filter tool (e.g., tracing a single XBRL concept or filtering filings), the MCP Host **also** broadcasts a `ui/notifications/tool-result` message back to the iframe containing only that tool's partial payload.
  * Therefore, `hydratePayload(raw)` **MUST NEVER** blindly overwrite `currentPayload = raw`. It must **merge** partial updates into `currentPayload` (preserving existing tabs, KPI strips, and entity metadata for the same entity) and re-render all tabs cleanly.
  * Additionally, every data tool decorated with `meta=APP_TOOL_META` on the server must enrich/backfill all tabs so that whichever tool the LLM invokes first, every tab in the UI is populated on initial load.
* **Triggering Live MCP Tools from Inside the UI (`tools/call`) & `srcdoc` Fallback (CRITICAL):**
  * **Instant Client-Side Synthesis First:** Whenever the user clicks a filter pill, metric switcher, or trace button for a metric already present in `currentPayload`, immediately synthesize and render the view synchronously (`<1ms`) from `currentPayload` before awaiting the network call, and preserve the user's active filter selection so delayed background `tool-result` notifications cannot overwrite it.
  * **Short Host RPC Timeout + Always Fall Through to Absolute HTTP Endpoint:** Inside a sandboxed `srcdoc` iframe (`window.location.origin === "null"`), relative `fetch("/apps/api/tool-call")` calls fail with a network error. Always inject the deployed Cloud Run base URL (`const API_BASE_URL = "https://<service>.a.run.app"`), list `API_BASE_URL` explicitly in `ui.csp.connectDomains`, use a short timeout (`2500ms`) on `sendMcpRequest("tools/call", ...)`, and **always** fall through (outside `try/catch`) to `fetch(`${API_BASE_URL}/apps/api/tool-call`, ...)` if `sendMcpRequest` times out, rejects, or resolves without an extractable payload.
* **Sending Context Back to the AI Chat (`ui/message`):**
  * Include an **"✨ Ask AI to Analyze"** action that posts `method: "ui/message"` with the user's currently filtered view or exported markdown table so the LLM can reason over what the user is inspecting.

### 5. Sandbox-Safe HTTP Preview Routes & COOP Headers
* Sandboxed iframes block external popups or documents that return `Cross-Origin-Opener-Policy: same-origin`.
* Always mount a standalone preview route (`/apps/raw/<view-slug>`) and any helper routes (`/apps/api/<view-slug>`) on your Starlette ASGI app (`get_asgi_app()`) with:
  ```python
  headers = {
      "Cross-Origin-Opener-Policy": "unsafe-none",
      "Access-Control-Allow-Origin": "*",
  }
  ```

---

## Step-by-Step Workflow

### Phase 1: UX, Brand Theme & Visual Wireframe Design (Produce Design Document with Nano Banana Wireframes & STOP)
When asked to design MCP Apps for an existing or planned MCP server:
1. **Audit Tools & Payloads:** Inspect the MCP server's existing `@mcp.tool()` functions and JSON outputs to identify where plain-text markdown falls short (e.g., dense multi-dimensional tables, time-series trends, hierarchical trees, multi-entity comparisons).
2. **Select Visual Archetype(s):**
   * **Archetype A — Executive Analytics & White-Space Dashboard:** KPI strip + click-to-filter distribution bars/charts + cross-tab opportunity matrix + detail cards.
   * **Archetype B — Side-by-Side Entity / Peer Comparator:** 2-to-N column synchronized benchmark table, metric delta badges, and live peer selector via `tools/call`.
   * **Archetype C — Hierarchy / Dependency Tree & Element Inspector:** Collapsible tree navigation + node detail pane + exportable assessment matrix.
   * **Archetype D — Network / Relationship Graph:** Interactive SVG/Canvas node-link topology with click-to-inspect side panel.
   * **Archetype E — Synchronized Document / Media Split-Viewer:** Media/chart carousel paired with structured document sections and search highlighting.
3. **Define the Brand & Theme Specification:**
   * Extract or confirm the company's brand colors (`--brand-primary`, `--brand-secondary`, `--bg-canvas`, `--bg-surface`), font stack (`--font-sans`, `--font-mono`), border radius, and header/logo treatment.
4. **Generate Visual UI Wireframes Using Nano Banana (`generate_image`):**
   * For each proposed MCP App view, generate a high-fidelity UI wireframe mockup using the **Nano Banana** image generation tool (`generate_image` with `AspectRatio="16:9"`, flat interface-only without surrounding laptop/phone device frames) reflecting the company's brand colors, KPI cards, tabs, interactive charts/tables, and `"Ask AI"` action buttons.
   * **Maintain Strict Visual Theme Consistency Across All Views:** All wireframes within the same MCP server design document MUST use the **exact same visual theme** (same background canvas, card surface color, top header bar treatment, typography, and accent palette). When generating wireframes for a second or third MCP App, pass the first generated wireframe image path in `ImagePaths` of `generate_image` as a style reference so every view looks like part of a unified product suite.
   * Copy the generated image files into `<MCP_SERVER_DIR>/design/` (e.g., `<MCP_SERVER_DIR>/design/<view>_wireframe.jpg`) and embed them directly in `<MCP_SERVER_DIR>/design/mcp_apps_ux_design.md` alongside ASCII structural layouts.
5. **Write the UX Design Document (`<MCP_SERVER_DIR>/design/mcp_apps_ux_design.md`) and STOP:**
   * Document each proposed MCP App (`ui://<server>/<view>`), its linked MCP tools, embedded Nano Banana wireframe mockup + structural layout / tabs, interactive `tools/call` & `ui/message` flows, server-side payload enrichment schema, and CSS brand theme variables.
   * **STOP and request user approval** before writing implementation code.

### Phase 2: Build, Wire & Verify (After Design Approval)
> [!CAUTION]
> **Mandatory Design Theme & Wireframe Compliance Gate:**
> The Phase 2 HTML/CSS/SVG implementation **MUST strictly comply** with the color scheme, typography, layout structure, and visual theme approved in `<MCP_SERVER_DIR>/design/mcp_apps_ux_design.md` and its Nano Banana wireframes:
> 1. **Exact Color Token Mapping:** Every background (`--bg`), card surface (`--surface`), top/inset banner (`--header-bg`), button fill, status badge, table row, and SVG/Canvas chart series **must** use the exact hex values defined in the design document's `BRAND_THEME` table. Never leave default template colors or hardcode off-palette hex values in CSS or SVG elements.
> 2. **Lock Approved Default Theme Mode (`LOCK_DESIGN_THEME = true`):** Always render the app in the exact theme mode (e.g., `data-theme="light"`) approved in the design document and wireframes, and lock `LOCK_DESIGN_THEME = true` so `hostContext.theme` from the MCP host never overrides the approved color scheme on load.
> 3. **Side-by-Side Wireframe Verification:** View the approved wireframe image(s) in `<MCP_SERVER_DIR>/design/` and verify that the implemented header banner, inset control strip, KPI cards, navigation tabs, chart series colors/legends, table columns (including inline bars/pills), and `"Ask AI"` action buttons visually match the wireframe.

1. **Create the MCP App Module(s):**
   * Copy [`resources/mcp_app_template.py`](./resources/mcp_app_template.py) into `<MCP_SERVER_DIR>/mcp_apps/<view_name>_app.py` (and shared `brand_theme.py` when building multiple views).
   * Configure `BRAND_THEME` with the exact approved corporate colors, fonts, and border radii from `<MCP_SERVER_DIR>/design/mcp_apps_ux_design.md`.
   * Implement `enrich_app_payload(raw_data)` and `build_app_html(initial_payload)` matching the approved wireframe layout and chart/table specifications.
2. **Wire into FastMCP (`server.py`):**
   * Register `@mcp.resource(APP_RESOURCE_URI, mime_type=MCP_APP_MIME_TYPE, meta=APP_RESOURCE_META)`.
   * Add `meta=APP_TOOL_META` to the linked data tool(s).
   * Add `@mcp.tool(annotations=READ_ONLY_ANNOTATIONS, meta=APP_TOOL_META) async def open_<view>_app(...) -> CallToolResult` returning `TextContent` + `EmbeddedResource` + `structuredContent`.
   * Mount `Route("/apps/raw/<view-name>", ...)` in `get_asgi_app()`.
3. **Verify Locally & Deploy to Cloud Run:**
   * Verify `GET /apps/raw/<view-name>` in browser/curl and `POST /mcp` (`resources/read` and `tools/call` for `open_<view>_app`), confirming all CSS custom properties and chart colors match the design doc.
   * Deploy using [`../cloud_run_mcp_server_creator/scripts/deploy_cloud_run_mcp.sh`](../cloud_run_mcp_server_creator/scripts/deploy_cloud_run_mcp.sh).
