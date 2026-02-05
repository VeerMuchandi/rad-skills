---
name: A2UI Developer
description: Expert guide and patterns for building Agent-Driven User Interfaces (A2UI) using the ADK.
---

# A2UI Developer Skill

This skill equips you with the knowledge and best practices to design, implement, and debug A2UI-compliant agents and clients.

## 0. Skill Initialization
**CRITICAL**: This skill relies on local reference documentation that must be kept in sync with the official repository.

**When starting a new session or tasks involving A2UI:**
1.  **Ask Permission**: "Shall I check for updates to the A2UI references from the official global cache?"
2.  **Execute Update**: If the user agrees, run:
    ```bash
    python3 ~/.gemini/jetski/skills/a2ui_developer/scripts/update_skill.py
    ```
3.  **Confirm**: Report the update status before proceeding.

## 1. Core Architecture

A2UI decouples UI generation (Agent) from UI rendering (Client).
*   **Producers**: AI Agents generate abstract UI descriptions (A2UI JSON) alongside natural language.
*   **Protocol**: Messages are streamed via the A2A (Agent-to-Agent) protocol or standard HTTP/SSE.
*   **Consumers**: Clients (Web, Mobile) interpret the JSON and render native components.

### Data Flow
1.  **User Input** -> Agent
2.  **Agent Logic** -> Generates Text + A2UI JSON (separated by `---a2ui_JSON---`)
3.  **Server** -> Parses stream, translates UI events, and forwards JSON to Client.
4.  **Client** -> Renders `surfaceUpdate` and `dataModelUpdate`.

## 2. A2UI Protocol & Schema

### A. `surfaceUpdate` (Structure)
Defines the component hierarchy using a flat **Adjacency List**.
*   **`surfaceId`**: Target surface (e.g., "main").
*   **`components`**: Array of component definitions.

```json
{
  "surfaceUpdate": {
    "surfaceId": "main",
    "components": [
      {
        "id": "root_col",
        "component": {
          "Column": {
            "children": { "explicitList": ["header_1", "card_1"] }
          }
        }
      }
    ]
  }
}
```

### B. `dataModelUpdate` (Data)
Populates data for components.
```json
{
  "dataModelUpdate": {
    "surfaceId": "main",
    "contents": [
      { "key": "user_name", "valueString": "Alice" }
    ]
  }
}
```

### C. `beginRendering` (Signal)
Tells the client to start drawing a specific root component on a surface.
```json
{
  "beginRendering": {
    "surfaceId": "main",
    "root": "root_col"
  }
}
```

## 3. Developing A2UI Agents

### System Prompting
Agents must be explicitly instructed to generate A2UI JSON.

**Critical Rules:**
1.  **Delimiter**: Use `---a2ui_JSON---` to separate text from JSON.
2.  **No Markdown**: Do NOT use \`\`\`json blocks for the A2UI payload.
3.  **One Block**: Only one JSON payload per turn, at the end.

**Sample Instruction:**
> You are an agent that generates UIs. You MUST separate your conversational response from your A2UI JSON output using the delimiter `---a2ui_JSON---`. The JSON must appear EXACTLY once at the end.

## 4. Server-Side Implementation (Python ADK)

### `AgentExecutor` Responsibilities
1.  **Event Translation**: Convert incoming `userAction` JSON events into natural language prompts.
2.  **Stream Accumulation**: Accumulate chunks to correctly detect the `---a2ui_JSON---` delimiter and parse the full JSON payload.

### Troubleshooting Common Issues
*   **Queue Closed**: Often caused by unhandled exceptions in the ADK `executor.execute` loop. Wrap in `try/except`.
*   **JSON Parse Error**: Occurs if `run_async` streaming splits the JSON string. **Must** accumulate before parsing.
*   **No UI Rendering**: Check if `---a2ui_JSON---` delimiter is missing or if strict markdown blocks were used.

## 5. Client-Side Implementation (Vite + Lit)

### Setup
*   `npm install @a2ui/lit @a2a-js/sdk`
*   **Renderer**: Use `<a2ui-surface>`.

### Components
*   **Layout**: `Column`, `Row`, `Divider`, `Modal`, `Tabs`
*   **Content**: `Text`, `Image`, `Video`, `AudioPlayer`, `Card`
*   **Interaction**: `Button`, `TextField`, `CheckBox`, `Slider`

### Hybrid Chat Pattern ("Text First")
1.  **Accumulate**: Buffer the stream.
2.  **Detect**: Watch for `---a2ui_JSON---`.
3.  **Yield Text**: Emit everything *before* the delimiter as a Text Part.
4.  **Yield Data**: Emit everything *after* the delimiter as a Data Part.

## 6. Integration Checklist
1.  **Server**: Run with `adk api_server . --a2a --allow_origins "*"`.
2.  **Agent Config**: Ensure `agent.json` (not `agent-card.json`) exists and has `"capabilities": { "streaming": true }`.
3.  **Client**: Configure `A2AClient` with `JsonRpcTransportFactory` and inject A2UI extension headers.

## 7. Advanced Patterns

### Tool-Based A2UI (Robust)
For complex UIs or when you need strict validation before sending data to the client, use the **Tool-Based Pattern** instead of the streaming delimiter.

**Mechanism:**
1.  **Tool Definition**: Define a tool (e.g., `send_a2ui_json_to_client`) that accepts the A2UI JSON as an argument.
2.  **Validation**: The tool implementation validates the JSON against the schema *server-side*.
3.  **Converter**: An A2A converter intercepts the tool call and transforms it into an A2UI `DataPart` for the client.

**Benefits:**
*   **Reliability**: The LLM is forced to generate valid JSON to satisfy the tool signature.
*   **Error Handling**: Validation errors are fed back to the LLM for self-correction.
*   **Clean Stream**: The client receives a clean `DataPart` event, not a raw text stream it has to parse.

**Implementation Example (Python ADK):**
```python
from a2ui.send_a2ui_to_client_toolset import SendA2uiToClientToolset

# In Agent Initialization
root_agent = LlmAgent(
    # ...
    tools=[
        SendA2uiToClientToolset(
            a2ui_enabled=True,
            a2ui_schema=A2UI_SCHEMA
        )
    ]
)
```

### Template-Based Generation
For consistent UIs, inject "Template Examples" into the system prompt.
1.  **Define Templates**: Create standard A2UI JSON files for common states (e.g., `loading.json`, `error.json`, `dashboard.json`).
2.  **Inject**: Load these into the prompt context.
3.  **Instruct**: Tell the LLM to "use the Dashboard Template and populate it with data X".

This reduces hallucination and ensures visual consistency.

## 8. A2UI Composer
The **A2UI Composer** (https://a2ui-composer.ag-ui.com/) is a visual rapid prototyping tool.
*   **Workflow**: Visually build components -> Export A2UI JSON.
*   **Usage**: Generate "gold standard" examples for Agent few-shot prompts or `examples` in basic tool definitions.

## 9. CopilotKit Integration
CopilotKit provides native support for A2UI as a "Declarative Generative UI".
1.  **Agent**: Generates standard A2UI JSON.
2.  **Client**: `<CopilotKit />` provider detects the A2UI spec and invokes the built-in renderer.
3.  **A2A**: CopilotKit's A2A protocol natively carries A2UI payloads.

## 10. Lessons Learned & Best Practices

### Client Development
*   **Mock Data Strictness**: A2UI is validating. Always validate mock data against `A2UI_SCHEMA` before debugging the renderer. A missing wrapper (e.g., `Text.literalString` vs `Text.text.literalString`) breaks rendering.
*   **Visual Grouping**: Use `Card` or styled `Column` to group related inputs. A flat list of components is valid but visually confusing.
*   **ID Management**: In `explicitList`, ensure every ID appears exactly **once** to prevent "ghost" duplicates.
*   **Component Inheritance**: Primitives like `Text` should often inherit styles (e.g., color) from their containers (Buttons, Headers) rather than having hardcoded default styles.

### Robust Retry Loop (Server-Side)
To handle LLM JSON errors gracefully:
1.  **Stream & Accumulate**: Get full text.
2.  **Parse & Validate**: Extract JSON and validate against `A2UI_SCHEMA`.
3.  **Retry**: If validation fails, feed the error back to the LLM (up to 2 retries) requesting correction.

## 11. Operational Guide & Troubleshooting

### Python 3.13 Stability (Pydantic)
**Symptom**: Server crashes on startup with `PydanticSchemaGenerationError` or `RecursionError`, especially involving `ClientSession` or `GenericAlias`.
**Cause**: Incompatibility between Pydantic's schema generator and Python 3.13's type handling in the ADK/FastAPI stack.
**Fix**: Apply strict monkey-patches to `pydantic._internal._generate_schema` to fallback to `any_schema` for unknown types.

### Vite & CORS (Local Dev)
**Symptom**: Client fails to connect to ADK server with Network Error or CORS policy block.
**Fix**:
1.  **Server**: Run with `--allow_origins "*"`.
2.  **Client (Vite)**: Configure `vite.config.ts` to proxy requests:
    ```typescript
    server: { proxy: { '/a2a': 'http://localhost:8000' } }
    ```

### Browser Verification (Playwright)
**Lesson**: When verifying A2UI in a browser (e.g., using `adk web` or Playwright):
*   **Never assume implicit success**.
*   **Explicitly Assert**: Check for the presence of specific component IDs or text content after every interaction.
*   **Wait**: Use explicit waits/polls for elements, as A2UI rendering is asynchronous.

### Dependency Management
**Lesson**: When migrating tools to A2UI agents:
*   **Audit File I/O**: `open('data.json')` fails if the file isn't copied to the new agent's folder.
*   **Action**: Grep for `open(` or `read_text` during migration.

## 12. Reference Code & Samples
The workspace contains a comprehensive library of A2UI samples. **Always** prefer reading these verified implementations over generating code from scratch.

**Root Path**: `./examples` (Relative to this SKILL.md)

### Recommended Samples
| Type | Name | Path | Key Patterns |
| :--- | :--- | :--- | :--- |
| **Agent** | **RizzCharts** | `examples/agent/rizzcharts` | Tool-Based Pattern, Dynamic Charts/Maps, Schema Wrapping |
| **Agent** | **Contact Lookup** | `examples/agent/contact_lookup` | Simple Forms, Card Layouts, Static Resources |
| **Client** | **Generic Shell** | `examples/client/generic_shell` | Hybrid Chat Loop, A2UI Renderer Integration, SSE Parsing |

**Instruction**: When asked to build a feature (e.g., "add a chart"), first use `list_dir` on the relevant local example directory to find precedent, then `view_file` to copy the proven pattern.

## 13. Full Framework Resources
This skill contains the **entire** A2UI framework source for reference.

| Resource | Path (Relative) | Description |
| :--- | :--- | :--- |
| **Specification** | `./specification` | Canonical JSON Schemas (`a2ui_schema.json`) and Protocol specs. |
| **Documentation** | `./docs` | Comprehensive Markdown guides on Architecture, Component Library, and Best Practices. |
| **Renderers** | `./renderers` | Source code for official client renderers (e.g., `./renderers/lit`, `./renderers/angular`). Use for deep debugging of client issues. |
| **Tools** | `./tools` | Helper scripts for schema validation and scaffolding. |

**Usage**:
*   To find specific component properties: `view_file ./specification/components/<Component>.json`
*   To understand renderer logic: `view_file ./renderers/lit/src/components/<Component>.ts`
