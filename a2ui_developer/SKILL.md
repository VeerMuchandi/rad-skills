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
    python3 scripts/update_skill.py
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

### Choosing your Deployment Target (Cloud Run vs Vertex AI Agent Engine)
**CRITICAL IF UNKNOWN**: Before writing any integration code, you must ask the user:
> "Are you deploying this A2UI agent to Cloud Run (Raw HTTP/A2A Mode) or natively to Vertex AI Agent Engine (Native Tools Mode)?"

The implementation architecture differs significantly between the two (see Section 4).

### Pre-requisites
An A2UI agent MUST inherently be an A2A (Agent-to-Agent) agent first. The A2A protocol serves as the base data transfer and transport layer for A2UI structured payloads. Therefore, before adding A2UI generation or parsing, you must ensure the agent successfully implements the A2A specification.

### System Prompting
Agents must be explicitly instructed to generate A2UI JSON.

**Critical Rules:**
1.  **Delimiter**: Use `---a2ui_JSON---` to separate text from JSON.
2.  **No Markdown**: Do NOT use \`\`\`json blocks for the A2UI payload.
3.  **One Block**: Only one JSON payload per turn, at the end.

**Sample Instruction:**
> You are an agent that generates UIs. You MUST separate your conversational response from your A2UI JSON output using the delimiter `---a2ui_JSON---`. The JSON must appear EXACTLY once at the end.

## 4. Server-Side Implementation (Python ADK)

### 4.A. Cloud Run (Raw HTTP/A2A Agent)
Requires a custom `AgentExecutor` to intercept tool responses or stream outputs and yield a native `DataPart` with `mimeType="application/json+a2ui"` directly to the HTTP stream.

#### standard custom_executor.py
```python
import json
from a2a import types
from a2a.server import agent_execution
from a2a.server import events
from google.adk import runners

class AdkAgentToA2AExecutor(agent_execution.AgentExecutor):
  def __init__(self):
    self._agent = local_agent.root_agent  # Your ADK LlmAgent
    self._runner = runners.Runner(...)

  async def execute(self, context: agent_execution.RequestContext, event_queue: events.EventQueue) -> None:
    query = context.get_user_input()
    # 1. Run the agent stream
    final_response_content = ""
    async for event in self._runner.run_async(...):
       if event.is_final_response():
          final_response_content += event.content.parts[0].text

    # 2. Extract A2UI JSON and convert to DataPart
    text_part, json_string = final_response_content.split("---a2ui_JSON---", 1)
    # ... parse json_string ...
    
    parts = []
    parts.append(types.Part(root=types.TextPart(text=text_part)))
    parts.append(types.Part(root=types.DataPart(
        data=json.loads(json_string),
        metadata={"mimeType": "application/json+a2ui"}
    )))

    # 3. Yield to stream
    await updater.add_artifact(parts, name="response")
    await updater.complete()
```

#### standard app.py (FastAPI/Starlette)
```python
from starlette.applications import Starlette
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler

agent_executor = DefaultRequestHandler() # Or appropriate executor
request_handler = DefaultRequestHandler(agent_executor=agent_executor)
app = Starlette()

a2a_app = A2AStarletteApplication(agent_card=agent_card, http_handler=request_handler)
a2a_app.add_routes_to_app(app, rpc_url="/a2a/my_agent", agent_card_url="/a2a/my_agent/.well-known/agent-card.json")
```

### 4.B. Vertex AI Agent Engine (Native Tools)
In this mode, standard tools return text by default. The Gemini Model reads that text and decides how to present it. Native binary `application/json+a2ui` injection inside standard tools can cause platform-level security blocks (or get stringified for the model).

For Agent Engine, you **must use the text-based delimiter fallbacks** (`---JSON_DATA---`) so the model can render them in plain text for readability (often as ASCII-art charts) when interactive cards are not supported natively by the runtime layer.

#### File Requirements Matrix for Agent Engine (Native Mode)

| File | Why it's Needed | Required for Text-Based Delimiter? | Required for Tool-Based Validation? |
| :--- | :--- | :--- | :--- |
| **`app.py`** | Entry point for WSGI/ASGI compute (`AdkApp`). | **YES** (Can be manually created or generated dynamically via Terraform). | **YES** |
| **`a2ui_tools.py`** | Defines Python function `render_ui` for LLM validation. | **NO** | **YES** |
| **`a2ui_schema.json`** | Validates LLM tool arguments using `jsonschema`. | **NO** | **YES** |
| **`agent_executor.py`** | Custom stream interceptor (Translates text blocks context to binary DataParts). | **NO** (Agent Engine handles native parsing without it). | **NO** |

> [!TIP]
> **Simplicity First**: If you use standard text delimiters (`---JSON_DATA---`), you do not need `a2ui_tools.py` or `a2ui_schema.json` in your file archive. The platform intercepts text automatically!


### 4.C. Python Dependencies
For A2UI agents deployed on Agent Engine using the Python SDK, you MUST include the `a2ui-agent` SDK from the git repository in your `requirements.txt`. Removing it will break A2A communication and cause `400 Bad Request` errors.

```text
a2ui-agent @ git+https://github.com/google/A2UI.git#subdirectory=agent_sdks/python
```

> [!IMPORTANT]
> **Do NOT remove unpublished dependencies from git repos if they are required by the system architecture.**

### Avoiding Hardcoded Intercepts
When implementing a custom `AgentExecutor` (like `AdkAgentToA2AExecutor`), ensure it **translates** the LLM's output stream into A2UI DataParts rather than **replacing** it with static mock data. 
- **Anti-pattern**: Forcing a static `DataPart` inside the loop for testing.
- **Best Practice**: Use environment variables (e.g., `MOCK_A2UI_RESPONSE=True`) to toggle intercepts, and ensure the default flow always accumulates the real `run_async` stream from the LLM.

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

### Prompt-Based A2UI Rendering (Redirection to Python)

> [!WARNING]
> While the platform documentation may describe "native text interception" using delimiters like `---JSON_DATA---` for standard Agent Engine deployments, **in practice this has been found to be unreliable and is unsupported for rich A2UI rendering in this repository.**

**For reliable A2UI rendering (yielding binary `DataPart` objects), you MUST use the Custom Executor approach deployed via the Python SDK (Pickle-based).** 

Refer to the `Agent Engine Python Deployer` skill for instructions on how to package your agent with a custom `agent_executor.py`.

13. **Unique Component IDs**: To avoid client-side state collisions, component IDs must be unique across the session, especially when generating identical templated items like search result cards (e.g., `doctor_card_1`, `doctor_card_2`).

### Conversational UX & Flow (Avoid "Happy Path" Pitfalls)
*   **Agent Greetings & Onboarding**: Any agent you build in A2UI should first introduce itself on invocation and clearly explain what it can do, rather than just displaying a standalone selection box or input field without context. Set clear expectations from the first turn.
*   **Do Not Force Tightly-Coupled Flows**: Avoid encoding strict "happy path" funnels or chained tool executions in the system prompt (e.g., "Once Action A is complete, immediately perform Action B"). Always explicitly configure the agent to *ask* the user for their preference before automatically branching into optional workflows.
*   **Implicit vs Explicit Selection**: Avoid A2UI buttons that solely emit raw user text (e.g., "Select Item X") into the chat stream if the agent relies on that text to manage state. While acceptable for rapid prototypes, production applications should strictly use **Structured Action Contexts** via tools, ensuring the agent maintains state explicitly and deterministically, rather than parsing its own conversation history.
*   **Verification and Choices Confirmation (Crucial UX Rule)**: It is a critical best practice to explicitly display the choices a user has made *before* proceeding to the next step or presenting terminal UI elements (like "Confirm Purchase" or "Submit Form"). This visually confirms the user's selections and builds trust. Never silently transition states without reflecting the accumulated choices back to the user in a UI card.
*   **Proactive vs. Reactive Actions (e.g., Discounts)**: Do not explicitly program agents to promote or proactively offer discounts, upsells, or bypasses unless explicitly directed by the product spec. The default posture should be reactive: assist with a discount only if the user explicitly requests one or is clearly hesitating on a decision.
*   **Neutral Prompting**: Do not prime the agent's instructions with specific examples of dynamic entities (like mocking specific brand names, user profiles, or product categories) unless those are fundamental, mandatory constraints. Doing so can cause the LLM to hallucinate inventory or skew recommendations during live interactions.

### A2UI v0.8 Schema Strictness (Gemini Enterprise)
When deploying to environments like Gemini Enterprise, the frontend strictly enforces the official **A2UI v0.8 Schema**. If any component is structurally invalid, it actively blocks rendering (via `TrustedHTML` CSP policies) to protect the UI, resulting in blank responses despite correct network payloads. 
**Common Schema Pitfalls to Avoid:**
1.  **`MultipleChoice` (Nesting Strictness)**: Use the `options` array containing objects with `label` and `value`. 
    -   **`label` MUST be an object** with a `literalString` property (e.g., `{"label": {"literalString": "Option A"}}`).
    -   **`value` MUST be a plain string** (e.g., `{"value": "option_a"}`). 
    -   Do NOT use a `choices` property. Do NOT over-nest `value` (making it an object like `{"value": {"literalString": "option_a"}}`).
2.  **`Button`**: The text on a button must be provided via the `child` property (which refers to a separate `Text` component id). Do NOT use a `text` property directly on the `Button`.
3.  **`Card`**: A Card only accepts a single `child` component (typically a `Column` or `Row` used to stack multiple elements). Do NOT use `title` or `subtitle` properties directly on the `Card`.
4.  **`Column` and `Row` (Nesting Strictness)**: The `explicitList` of child IDs MUST be wrapped in a `children` object.
    -   **CORRECT**: `"Column": { "children": { "explicitList": ["id1", "id2"] } }`
    -   **INCORRECT**: `"Column": { "explicitList": ["id1", "id2"] }` (Missing `children` wrapper!)
5.  **`TextField` Hallucinations (`TextInput`)**: A highly common LLM hallucination is generating an `Unknown element TextInput`. The official v0.8 A2UI schema component for free-form text entry is strictly named `TextField`. You MUST instruct your agent to use `TextField` and explicitly forbid `TextInput`. The `TextField` properties `text` and `label` must be objects (e.g. `{"text": {"path": "my_txt"}, "label": {"literalString": "Reason"}}`), NOT plain strings, and the property is `text`, not `content`.
6.  **`CheckBox` Hallucinations (`selected`)**: LLMs frequently hallucinate `selected` or `checked` properties for the `CheckBox` component. The official schema strictly requires `value` (e.g. `{"value": {"path": "is_checked"}}`).
7.  **`dataModelUpdate` Hallucinations (`valueBool`)**: When populating booleans in `dataModelUpdate`, LLMs may hallucinate `valueBool`. The schema strictly requires `valueBoolean`.
8.  **The Array-vs-Object Wrapper Pitfall (Top-Level)**: The A2UI payload returned by the agent MUST be a JSON object with a top-level `"a2ui_messages"` key.
    -   **CORRECT**: `{ "a2ui_messages": [ ... ] }`
    -   **INCORRECT**: `[ ... ]` (Returning a raw array fails parsing!).
9.  **The Python f-string Escaping Trap**: When using Python f-strings to define prompts that contain inline JSON examples, literal curly braces `{}` MUST be escaped as `{{}}`. Failure to do so triggers `SyntaxError: Expression nested too deeply`.
10. **Deployment Pack Completeness (extra_packages)**: When deploying via the Python SDK (Pickle-based), if your agent imports local helper modules (e.g., `a2ui_examples.py`, `a2ui_schema.py`), you MUST add them to the `extra_packages` list in your deployment script. Unlisted files will not be uploaded to the server, causing `ModuleNotFoundError` at runtime.

### 11. Volatile Memory & Visible Context Echoing
*   **The Problem**: Scaled serverless fleets (like Vertex AI Agent Engine) often use ephemeral in-memory session persistence. Standard load balancers bounce sequential turns across different container workers. If Turn 1 saves a dynamic entity ID in Replica A's RAM, a subsequent A2UI action click might hit Replica B (which has empty RAM), losing the context and forcing an unwelcome conversation reset.
*   **The Solution**: **Force Context Persistence via Visible Transcript Echoing.** For all generated A2UI iterative lists (e.g. search result cards) or option toggles, always generate button `message` literals that explicitly append the target IDs inside the user-visible text string part (e.g. `I want to book Dr. Smith (id: p1).`). This guarantees that even if the server-side RAM cache flushes, the next replica reads the ID directly from the client-passed transcript body, enabling it to invoke continuity tool checks instantly!

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

### Project ID Resolution Failures (A2A on Reasoning Engine)
**Symptom**: `400 REMOTE_AGENT_FAILURE` (internal `403 PermissionDenied` in `initializer.py`).
**Cause**: The SDK reads the project number injected by the runtime and tries to resolve it to a name via Cloud Resource Manager API (which fails if the Service Account lacks `resourcemanager.projects.get`).
**Fix**: Initialize the Vertex AI SDK explicitly using `aiplatform.init(project=...)` using a user-provided `PROJECT_ID` environment variable (e.g., from Terraform) before any other `vertexai` imports. This forces the SDK to use the correct project ID and bypasses the project number resolution lookup:

```python
import os
import google.cloud.aiplatform as aiplatform

if "PROJECT_ID" in os.environ:
    aiplatform.init(project=os.environ["PROJECT_ID"])
    os.environ["GOOGLE_CLOUD_PROJECT"] = os.environ["PROJECT_ID"]
```

### Pydantic 3.13 Packaging patch (Recursion Drops)
**Symptom**: Server crashes on startup with `RecursionError` or compilation drops during `cloudpickle` unpickling.
**Cause**: Missing template type alignments in the runtime `vertexai._genai` suite.
**Fix**: At the very top of your `agent_executor.py` (before ADK imports), force alignment of Starlette request types:

```python
import sys
from typing import Any
try:
    import vertexai.preview.reasoning_engines.templates.a2a as a2a_module
    import starlette.requests
    import a2a.server.apps.rest.rest_adapter as adapter_module
    
    if "Request" not in a2a_module.__dict__:
        a2a_module.__dict__["Request"] = starlette.requests.Request
    if "ServerCallContext" not in a2a_module.__dict__:
        a2a_module.__dict__["ServerCallContext"] = adapter_module.ServerCallContext
except ImportError:
    pass
```

## 12. Reference Code & Samples
The workspace contains a comprehensive library of A2UI samples. **Always** prefer reading these verified implementations over generating code from scratch.

**Root Path**: `./examples` (Relative to this SKILL.md)

### Recommended Samples
| Type | Name | Path | Key Patterns |
| :--- | :--- | :--- | :--- |
| **Agent** | **RizzCharts** | `examples/agent/rizzcharts` | Tool-Based Pattern, Dynamic Charts/Maps, Schema Wrapping |
| **Agent** | **Contact Lookup** | `examples/agent/contact_lookup` | Simple Forms, Card Layouts, Static Resources |
| **Agent** | **Reasoning Engine (A2A)** | `examples/agent/agent_engine_a2a` | A2aAgent, agent_executor.py, a2ui_schema.py |
| **Client** | **Generic Shell** | `examples/client/generic_shell` | Hybrid Chat Loop, A2UI Renderer Integration, SSE Parsing |

**Instruction**: When asked to build a feature (e.g., "add a chart"), first use `list_dir` on the relevant local example directory to find precedent, then `view_file` to copy the proven pattern.

## 13. Full Framework Resources
This skill contains the **entire** A2UI framework source for reference.

| Resource | Path (Relative) | Description |
| :--- | :--- | :--- |
| **Online Specification** | `https://a2ui.org/reference/components` | Official web component gallery and behavioral reference. |
| **Specification** | `./specification` | Canonical JSON Schemas (`a2ui_schema.json`) and Protocol specs. |
| **Documentation** | `./docs` | Comprehensive Markdown guides on Architecture, Component Library, and Best Practices. |
| **Renderers** | `./renderers` | Source code for official client renderers (e.g., `./renderers/lit`, `./renderers/angular`). Use for deep debugging of client issues. |
| **Tools** | `./tools` | Helper scripts for schema validation and scaffolding. |

**Usage**:
*   To find specific component properties: `view_file ./specification/components/<Component>.json`
*   To understand renderer logic: `view_file ./renderers/lit/src/components/<Component>.ts`

## 14. Canonical A2UI Canonical v0.8 Schema Stub

Use this `a2ui_schema.py` module to validate generated LLM payloads against platform validation strictness before streaming:

```python
A2UI_SCHEMA = r"""{
  "title": "A2UI Message Schema",
  "description": "Describes a JSON payload for an A2UI (Agent to UI) message...",
  "type": "object",
  "properties": {
    "beginRendering": { ... },
    "surfaceUpdate": { ... },
    "dataModelUpdate": { ... },
    "deleteSurface": { ... }
  }
}
"""
```
> [!TIP]
> Refer to the repository root `/usr/local/google/home/veermuchandi/code/agents/rad-workshop/careconnect_navigator_a2ui/a2ui_schema.py` for the full 300+ line JSON Schema string block ensuring v0.8 compliance.
