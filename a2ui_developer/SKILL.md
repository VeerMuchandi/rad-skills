---
name: A2UI Developer
description: Expert guide and patterns for building Agent-Driven User Interfaces (A2UI) using the ADK.
---

# A2UI Developer Skill

This skill equips you with the knowledge and best practices to design, implement, and debug A2UI-compliant agents and clients.

## 0. Version Standard & Skill Initialization

### A2UI v0.9 is the Default Standard
* **Default Standard**: You MUST use **A2UI v0.9** by default for all new agent implementations, components, prompts, and schema structures.
* **Legacy Version Upgrade Rule**: If an existing agent codebase or design is found using an older version (e.g., A2UI v0.8 with `surfaceUpdate`, `beginRendering`, `MultipleChoice`, or raw array wrappers), you MUST proactively suggest upgrading to A2UI v0.9, explain the improvements (flat component architecture, native `ChoicePicker`, cleaner envelope commands `createSurface`/`updateComponents`/`updateDataModel`), and **request explicit approval before upgrading the code to v0.9**.

### Skill Initialization
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
*   **Producers**: AI Agents generate abstract UI descriptions (A2UI v0.9 JSON) alongside natural language.
*   **Protocol**: Messages are streamed via the A2A (Agent-to-Agent) protocol or standard HTTP/SSE.
*   **Consumers**: Clients (Web, Mobile) interpret the JSON and render native components.

### Data Flow
1.  **User Input** -> Agent
2.  **Agent Logic** -> Generates Text + A2UI v0.9 JSON (separated by `---a2ui_JSON---`)
3.  **Server** -> Parses stream, translates UI events, and forwards JSON to Client.
4.  **Client** -> Renders `createSurface`, `updateComponents`, and `updateDataModel`.

## 2. A2UI Protocol & Schema (v0.9 - Default Standard)

Version 0.9 represents the standard flat component definition model with declarative envelope commands.

### A. Envelope Messages (v0.9)
> [!IMPORTANT]
> **Use Unique Surface IDs**: While the following examples show `"surfaceId": "main"`, in any multi-turn conversational interface you must use a unique, descriptive `"surfaceId"` for each step/turn of the flow (e.g. `"plan_selection"`, `"search_form"`, `"provider_list"`) to prevent rendering and history conflicts in the Gemini Enterprise browser client.

All envelopes are wrapped in a top-level `"messages"` list, and each message must contain `"version": "v0.9"`:

1. **`createSurface`**: Initializes a new surface.
   ```json
   {
     "version": "v0.9",
     "createSurface": {
       "surfaceId": "main",
       "catalogId": "https://a2ui.org/specification/v0_9/material_catalog.json",
       "theme": { "primaryColor": "#00BFFF" },
       "sendDataModel": true
     }
   }
   ```
2. **`updateComponents`**: Updates the structural components in the adjacency list.
   ```json
   {
     "version": "v0.9",
     "updateComponents": {
       "surfaceId": "main",
       "components": [
         { "id": "root", "component": "Card", "child": "container" },
         { "id": "container", "component": "Column", "children": ["title", "picker", "btn"] }
       ]
     }
   }
   ```
3. **`updateDataModel`**: Updates values within the client data model.
   ```json
   {
     "version": "v0.9",
     "updateDataModel": {
       "surfaceId": "main",
       "path": "/",
       "value": { "choices": ["PPO"] }
     }
   }
   ```
4. **`deleteSurface`**: Deletes the surface.
   ```json
   {
     "version": "v0.9",
     "deleteSurface": { "surfaceId": "main" }
   }
   ```

### B. Key v0.9 Components
- **Flat Component Type**: Component names are direct strings on the `"component"` property, and properties are flat top-level keys.
- **`ChoicePicker`**: Replaces `MultipleChoice`. Supports single select (`variant: "mutuallyExclusive"`) or multi-select (`variant: "multipleSelection"`). The value property is bound to a string array path in the data model.
- **`DateTimeInput`**: Supports date/time selections (`enableDate: true`, `enableTime: false`).
- **`Button`**: Action event properties use the nested `event` structure:
  ```json
  "action": {
    "event": {
      "name": "submit",
      "context": {
        "message": "User-visible text response",
        "value": { "path": "/data_path" }
      }
    }
  }
  ```

### C. Legacy A2UI Protocol (v0.8 - Deprecated / Migration Reference)
Older implementations used `surfaceUpdate`, `dataModelUpdate`, and `beginRendering`:
* `surfaceUpdate` (defined adjacency list with nested component keys, e.g. `"Column": {"children": {"explicitList": [...]}}`)
* `dataModelUpdate` (key/valueString maps)
* `beginRendering` (signal pointing to root component ID)
* `MultipleChoice` (legacy component with nested `options` array containing objects with `label.literalString` and `value`)

> [!IMPORTANT]
> **Migration Rule**: If you encounter existing code using v0.8 primitives (`surfaceUpdate`, `beginRendering`, `MultipleChoice`), proactively explain the advantages of v0.9 (flat declarative envelopes, `ChoicePicker`, cleaner data models) and **request user approval before migrating the codebase to v0.9**.

## 3. Developing A2UI Agents

### Mandatory Workflow & Isolation Rules
1. **Separate Folder**: Always create a separate folder for the A2UI implementation (e.g., `[agent_name]_a2ui`). **NEVER** modify the original reference agent code in place.
2. **Test Locally First**: You **MUST** generate the code and test it locally using the `A2UI Local Tester` skill before attempting any deployment.
3. **Deploy Only on Request**: Do **NOT** deploy to Agent Engine or Gemini Enterprise unless the user explicitly asks you to do so, and only after the agent works locally and the user is happy with it.
4. **Complete Working Examples**: When asked to generate an A2UI agent or a working example, you MUST generate the complete set of files required for it to function, including `agent.py`, `a2ui_examples.py`, `a2ui_schema.py`, and `a2ui_tools.py` (if using the tool-based pattern). Do not omit these supporting files unless the user explicitly says they are not needed.

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
3.  **Copy Exactly**: When using tools to generate UI strings, you MUST output the exact string returned by the tool, starting from `---a2ui_JSON---`.
4.  **No Modification**: Do NOT summarize, truncate, or alter the JSON string in any way. Copy it character-for-character.
5.  **One Block**: Only one JSON payload per turn, at the end.
6.  **Unique surfaceId per turn (v0.9)**: In Gemini Enterprise, every distinct step or turn of the conversation flow must use a unique, descriptive `"surfaceId"` (e.g., `"plan_selection"`, `"search_form"`, `"provider_list"`). Reusing the same surface ID (such as `"main"`) across multiple turns causes client-side rendering conflicts.

**Sample Instruction:**
> You are an agent that generates UIs. You MUST separate your conversational response from your A2UI JSON output using the delimiter `---a2ui_JSON---`. The JSON must appear EXACTLY once at the end. When calling a tool that returns UI JSON, you MUST copy the returned string exactly without modification or adding markdown code blocks.
> **Unique Surface ID Constraint**: *"Use a unique, descriptive 'surfaceId' for each distinct step of the flow (e.g. 'plan_selection', 'search_form', 'provider_list'). Never reuse the same surface ID across different turns."*
> **Echo Constraint**: *"When a tool returns a string starting with '---a2ui_JSON---', you MUST include that exact string in your response without modification."*

## 4. Server-Side Implementation (Python ADK)

### 4.A. Cloud Run (`adk api_server` / A2A Agent)
When running A2UI agents via `adk api_server` in Cloud Run containers, the server by default spins up the standard text-only executor. To route requests through your custom A2UI-aware executor (`AdkAgentToA2AExecutor`), configure the following wiring:

#### 1. `agent.py` Monkey-Patch
Include this snippet near the top of the agent entrypoint file (`agent.py`):
```python
# Monkey-patch ADK's default A2A executor to use our custom A2UI-aware executor
try:
    import google.adk.a2a.executor.a2a_agent_executor as a2a_executor_mod
    import agent_executor
    a2a_executor_mod.A2aAgentExecutor = agent_executor.AdkAgentToA2AExecutor
except Exception as e:
    import logging
    logging.warning(f"Failed to monkey-patch A2aAgentExecutor: {e}")
```

#### 2. `agent_executor.py` Constructor
Ensure your custom executor constructor accepts `*args` and `**kwargs`, pulling the runner provided by `adk api_server`:
```python
class AdkAgentToA2AExecutor(agent_execution.AgentExecutor):
    def __init__(self, *args, **kwargs):
        self._runner = kwargs.get('runner')
        if not self._runner:
            self._runner = runners.Runner(
                app_name="A2UIAgent",
                agent=root_agent,
                session_service=in_memory_session_service.InMemorySessionService(),
                auto_create_session=True,
            )
```

#### 3. Container `PYTHONPATH`
In the Dockerfile, add the agent directory to `PYTHONPATH` so `import agent_executor` resolves:
```dockerfile
ENV PYTHONPATH="/app/agents/{agent_name}:$PYTHONPATH"
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
For A2UI agents deployed on Agent Engine using the Python SDK, you MUST include the `a2ui-agent-sdk` package in your `requirements.txt` and in the `config["requirements"]` list of your deployment script. Removing it will break A2A communication and cause `400 Bad Request` errors.

```text
a2ui-agent-sdk
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

### Handling Rich UI Inputs in Gemini Enterprise (A2UI Button Clicks)
When deploying A2UI agents to Gemini Enterprise and using rich UI components (like buttons or forms), be aware of how user inputs are delivered to the backend:
*   **The Problem**: Clicking a button in the UI often sends a generic text message like `"User action triggered."` as the primary user input. Relying solely on `context.get_user_input()` will cause the agent to receive this generic string and ignore the underlying intent, leading to loops, stalls, or resets.
*   **The Solution**: The actual data payload (including the `context` defined in the button action) is delivered in a separate **`DataPart`** of the message with mimeType `application/json+a2ui`.
*   **Implementation Pattern (Custom Executor)**: In your custom `agent_executor.py`, you MUST iterate through the `parts` of the incoming message, unwrap nested `data` envelopes if present, extract the `userAction` or `action` payload (including nested `event` dictionaries), assign the hidden `message` to the LLM query, and save all other context variables to `session.state`. Also inject `session.state` into the LLM query as `[State: key=val]` so the agent has full context:

```python
    # Example extraction logic inside agent_executor.py context extraction loop:
    action_context = {}
    action_query = None
    try:
        if hasattr(context, 'message') and context.message and hasattr(context.message, 'parts'):
            for part in context.message.parts:
                if hasattr(part, 'root') and hasattr(part.root, 'data'):
                    data = part.root.data
                    if hasattr(part.root, 'metadata') and part.root.metadata and part.root.metadata.get('mimeType') == 'application/json+a2ui':
                        # Unwrap nested data wrapper if present
                        if isinstance(data, dict) and "data" in data:
                            data = data["data"]
                        action_data = None
                        if isinstance(data, dict):
                            if "action" in data:
                                action_data = data["action"]
                            elif "userAction" in data:
                                action_data = data["userAction"]
                        if isinstance(action_data, dict):
                            # Support nested 'event' field
                            if "event" in action_data and isinstance(action_data["event"], dict):
                                action_data = action_data["event"]
                            
                            ctx = action_data.get("context", {})
                            if isinstance(ctx, dict):
                                if "message" in ctx:
                                    action_query = ctx["message"]
                                action_context.update(ctx)
                                
        if action_query:
            query = action_query  # Override query with hidden intent message
            
        # Save other context variables to session state
        for k, v in action_context.items():
            if k != 'message':
                session.state[k] = v
                
        # Inject session state variables into the LLM query for context continuity
        state_vars = [f"{k}={v}" for k, v in session.state.items()]
        if state_vars:
            query = f"{query} [State: {', '.join(state_vars)}]"
            logger.info("[DEBUG] Injected state into query: %s", query)
    except Exception as e:
        logger.warning("Failed to extract action context: %s", e)
```

### Local Mock Testing of A2UI (Crucial for Rapid Prototyping)
When building a custom local tester (e.g., using FastAPI and a standalone HTML file) to test A2UI agents before deployment, be aware of these common pitfalls:

1.  **Button Actions Ignored**: If your mock client (`index.html`) hardcodes the check for action name (e.g., `if (action.name === 'submit')`), it will ignore buttons with custom action names like `submit_route_plan`.
    *   **Solution**: Make the button handler generic in `index.html` to process *all* actions and send them to the server via `DataPart`.
2.  **Time Picker rendered as Date Picker**: If your mock client uses `<input type="date">` blindly for `DateTimeInput`, it will ignore the `enableTime` property.
    *   **Solution**: Check `enableDate` and `enableTime` properties in the A2UI component definition and set the input type to `time`, `date`, or `datetime-local` accordingly.
3.  **Agent Ignoring Form Submissions**: When a button sends an action, the agent might not realize it has the data if it's just in the `DataPart` or state, and might re-render the form!
    *   **Solution**: In your mock server, extract the `message` from the action context and **override** the query passed to the agent, rather than just appending it. This forces the agent to read the intent (e.g., "Plan my route with these details") as the primary user input!
4.  **Strict Prompting for Form Triggering**: LLMs tend to fallback to text conversation instead of generating rich UI forms on the first turn.
    *   **Solution**: Use strict negative constraints in the system prompt: *"You are FORBIDDEN from asking for [details] in text. You MUST call the [tool_name] tool to gather these details."*
5.  **Bypassing Tools for Form Generation**: LLMs frequently fail to generate large valid JSON payloads in the stream.
    *   **Solution**: Use the **Tool-Based Pattern** (Section 7) even for simple forms. Let a Python tool generate the JSON via `json.dumps` and return it, rather than letting the LLM type it out. This guarantees valid JSON delivery.

### TrustedHTML Errors as Red Herrings
*   **The Problem**: You may see `TrustedHTML` CSP policy errors in the browser console when A2UI components fail to render. This can easily be mistaken for a component schema or sanitization issue.
*   **The Cause**: In many cases, these errors are actually caused by **improper authorization or registration** of the agent in Gemini Enterprise, which prevents the client from safely loading the resources.
*   **The Solution**: Do not waste time refactoring components to fix the HTML. Instead, check the agent registration. You may need to unregister the agent, delete the authorization resource, recreate the authorization resource with correct credentials, and then re-register the agent.

### State Persistence vs. Transcript Echoing in Multi-Replica Environments
*   **The Problem**: In multi-replica environments like Gemini Enterprise, relying on ADK's in-memory `session.state` to preserve user choices (like plan type) across turns can fail. If Turn 2 hits a different replica than Turn 1, the in-memory state is lost, causing the agent to loop back and ask for the information again.
*   **The Solution**: Use **Visible Transcript Echoing** as a fallback or primary mechanism when a shared persistent database is not configured.
*   **Implementation**: Instruct the agent to customize the `message` field in the action context of buttons (e.g., `"Search for providers for my PPO plan."`) to explicitly include the state variables. This forces the client to store the state and send it back to whatever replica handles the next turn, guaranteeing state continuity!

### State Injection Pattern for Multi-Replica Continuity
*   **The Problem**: Ephemeral session state is often lost in multi-replica environments when sequential turns hit different replicas.
*   **The Solution**: Inject the extracted session state directly into the query string before passing it to the agent. This ensures that the agent always sees the accumulated context in the transcript, effectively using "Transcript Echoing" at the system level.
*   **Implementation Pattern**:
```python
    # Inject session state into query
    state_vars = [f"{k}={v}" for k, v in session.state.items()]
    if state_vars:
        query = f"{query} [State: {', '.join(state_vars)}]"
        logger.warning("[DEBUG] Appended state to query: %s", query)
```

### Session ID and Context Preservation in A2A Proxy Servers
*   **The Problem**: In multi-turn A2UI agents, the conversation resets to the initial stage (e.g. Needs Assessment) on subsequent clicks or text entries, despite utilizing persistent session storage.
*   **The Cause**: The A2A HTTP proxy server did not map the JSON-RPC `session_id` parameter to the `context_id` field inside the forwarded A2A Message payload. Because of this, the A2A SDK generated a new, random UUID context ID for every turn, creating a fresh, empty session on each request.
*   **The Solution**: The proxy server must explicitly map and forward the incoming session/conversation ID inside the `context_id` property of the A2A message definition:
    ```python
    a2a_message = {
        "role": "ROLE_USER",
        "content": a2a_parts,
        "context_id": params.get("session_id")
    }
    ```

### Configuring Platform Session/Memory Services on Vertex AI
*   **The Requirement**: To prevent state loss across container recycling or multi-replica workers, use `VertexAiSessionService` and `VertexAiMemoryBankService`.
*   **Mandatory Configuration**: Both platform services require the `agent_engine_id` parameter. At runtime, read this from the environment variable `GOOGLE_CLOUD_AGENT_ENGINE_ID` which is automatically injected by the platform:
    ```python
    agent_engine_id = os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID")
    session_service = VertexAiSessionService(
        project=project_id, location=location, agent_engine_id=agent_engine_id
    )
    ```

### VertexAiSessionService Limitations
*   **The Problem**: You might attempt to use `VertexAiSessionService` to solve the multi-replica state issue by persisting state in Vertex AI.
*   **The Limitation**: `VertexAiSessionService` does **NOT** support user-provided session IDs when creating sessions (raises `ValueError: User-provided Session id is not supported`).
*   **The Consequence**: If your custom `agent_executor.py` relies on mapping external task/context IDs to specific ADK session IDs, you cannot use `VertexAiSessionService` directly. You must either adapt your ID mapping strategy or fallback to `InMemorySessionService` combined with Transcript Echoing!

### Multi-Replica Session Recovery (The Golden Pattern)

> [!IMPORTANT]
> Reasoning Engine replicas are stateless. Under JSON-RPC, `RequestContext.metadata` returns a transient dictionary if the underlying `_params.metadata` is `None`. To prevent updates from being discarded, you must read/write states using `context._params.metadata` directly.

**Implementation Logic:**
1.  **Polymorphic Extraction**: Iterate through the message parts, checking if the part has `data` as an attribute or key, and support converting Protobuf `Struct` objects to dictionaries using `MessageToDict`.
2.  **Capture Inputs**: Check `userAction.inputs` for form elements and `userAction.context` for custom parameters.
3.  **Persistent Write-Back**: Save the recovered metadata dictionary back to `context._params.metadata` (if `_params` exists) so that it persists across reasoning engine tasks.
4.  **Inject State (Transcript Echoing)**: Append state variables directly to the query prompt (e.g. `query = f"{query} [State: key=value]"`), allowing stateless model worker replicas to recover context easily.


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
    -   **Consistency Rule**: Ensure all few-shot examples provided in the system prompt or external files (like `a2ui_examples.py`) use this object wrapper instead of raw arrays, so the LLM learns the correct top-level structure.
    -   **Executor Adaptation (CRITICAL for Gemini Enterprise)**: When using a custom executor (like `agent_executor.py`) to deliver A2UI payloads, you MUST extract the list of messages from the top-level `"a2ui_messages"` object and send **each message as a separate `DataPart`** with `mimeType="application/json+a2ui"`. Sending the entire wrapped object in a single part will cause rendering failures (like raw JSON display or blank responses) in the platform client because the A2A SDK's Pydantic model (`DataPart`) will nest the dict inside a double `"data": {"data": ...}` wrapper.
        
        **Code Pattern:**
        ```python
        for message in messages:
            ui_data_part = types.Part(
                root=types.DataPart(
                    data=message,
                    metadata={"mimeType": "application/json+a2ui"}
                )
            )
            parts.append(ui_data_part)
        ```

9.  **Message Order Sensitivity (CRITICAL)**: When sending multiple A2UI instructions in the same response (e.g., `beginRendering` and `surfaceUpdate`), ensure that **`beginRendering` appears FIRST** in the list of messages. The platform client renderer may fail to process updates if it doesn't know the root container target first!
10. **The Python f-string Escaping Trap**: When using Python f-strings to define prompts that contain inline JSON examples, literal curly braces `{}` MUST be escaped as `{{}}`. Failure to do so triggers `SyntaxError: Expression nested too deeply`.
11. **Deployment Pack Completeness (extra_packages)**: When deploying via the Python SDK (Pickle-based), if your agent imports local helper modules (e.g., `a2ui_examples.py`, `a2ui_schema.py`), you MUST add them to the `extra_packages` list in your deployment script. Unlisted files will not be uploaded to the server, causing `ModuleNotFoundError` at runtime.
12. **`usageHint` Schema Strictness**: Gemini Enterprise strictly enforces the `usageHint` enum values (e.g., `"icon"`, `"avatar"`, `"header"`). Using unsupported values like `"body"`, `"caption"`, or `"h4"` (even if seen in some examples) can cause silent rendering failures, displaying raw JSON instead. When in doubt, omit `usageHint` or stick to the official enum list.
13. **Re-rendering and Re-creating Surfaces (Preventing duplicate surface ID errors)**: Under the A2UI v0.9 specification, it is an error to send a `createSurface` command for a surface ID that already exists in the viewport/client-state. To display an updated or new surface of the same type without breaking client rendering, you must either:
    - **Use Dynamic/Unique Surface IDs**: e.g., `"order_summary"` for the initial turn, and `"order_summary_discounted"` for the next turn. This preserves both surfaces in the chat history.
    - **Explicitly Prepend deleteSurface**: Prepend a `deleteSurface` message targeting the same `surfaceId` right before `createSurface` to clear the old instance first:
      ```json
      [
        {
          "version": "v0.9",
          "deleteSurface": { "surfaceId": "my_surface" }
        },
        {
          "version": "v0.9",
          "createSurface": { "surfaceId": "my_surface", "catalogId": "..." }
        }
      ]
      ```

### Model Selection for A2UI
*   **The Problem**: Smaller models like `gemini-2.5-flash` may occasionally fail to generate perfectly valid JSON payloads for complex UIs, or may truncate output due to token limits when prompt instructions are long.
*   **The Solution**: For complex, multi-step A2UI workflows (e.g., shopping flows with forms, lists, and summaries), recommend using a more capable model like **`gemini-2.5-pro`**.
*   **Verification**: In the Phone Plan Shopper case study, switching from `flash` to `pro` resolved persistent JSON truncation errors and allowed the workflow to complete successfully.

### Image Sizing and Usage Hints
*   **The Problem**: A2UI does not support direct width/height properties for images in the schema. Developers must rely on `usageHint` and `fit` to guide the client renderer.
*   **Guidance by Use Case**:
    *   **Logos & List Thumbnails**: Use **`"smallFeature"`** or **`"mediumFeature"`** (e.g., for phone plan logos or device images in a list).
    *   **Icons**: Use **`"icon"`** for small status indicators or UI controls.
    *   **Profile Pictures**: Use **`"avatar"`** specifically for user/agent faces (often rendered circular).
    *   **Banners**: Use **`"header"`** for large images at the top of a card.
*   **Scaling**: Always consider the **`fit`** property (`contain`, `cover`, etc.) to ensure the image scales correctly within the area allocated by the client based on the hint.

### 11. Volatile Memory & Visible Context Echoing
*   **The Problem**: Scaled serverless fleets (like Vertex AI Agent Engine) often use ephemeral in-memory session persistence. Standard load balancers bounce sequential turns across different container workers. If Turn 1 saves a dynamic entity ID in Replica A's RAM, a subsequent A2UI action click might hit Replica B (which has empty RAM), losing the context and forcing an unwelcome conversation reset.
*   **The Solution**: **Force Context Persistence via Visible Transcript Echoing.** For all generated A2UI iterative lists (e.g. search result cards) or option toggles, always generate button `message` literals that explicitly append the target IDs inside the user-visible text string part (e.g. `I want to book Dr. Smith (id: p1).`). This guarantees that even if the server-side RAM cache flushes, the next replica reads the ID directly from the client-passed transcript body, enabling it to invoke continuity tool checks instantly!

### Client Development
*   **Mock Data Strictness**: A2UI is validating. Always validate mock data against `A2UI_SCHEMA` before debugging the renderer. A missing wrapper (e.g., `Text.literalString` vs `Text.text.literalString`) breaks rendering.
*   **Visual Grouping**: Use `Card` or styled `Column` to group related inputs. A flat list of components is valid but visually confusing.
*   **ID Management**: In `explicitList`, ensure every ID appears exactly **once** to prevent "ghost" duplicates.
### Gemini Enterprise UI Styling Limitations & Workarounds
Gemini Enterprise enforces strict styling on certain primitive A2UI components, ignoring inline `"style"` dictionaries. The A2UI Developer Skill must recommend the following universal workarounds for custom theming, regardless of whether the agent uses a light or dark theme:

#### A. The `Tabs` Primitive
* **Limitation:** The primitive `Tabs` component ignores all custom styling (such as font size and text color) in Gemini Enterprise.
* **Workaround:** Do not use the `Tabs` primitive if you need custom styling. Instead, build a "Tab Bar" using a `MaterialRow` containing `MaterialButton` components (with `"variant": "text"`). You can then apply any theme-specific styling (like active border bottoms or custom text colors) directly to the buttons.
* **State Management:** These buttons should trigger a `select_scope` event (via the action parser above) which sends a message back to the agent to re-render the view with the new active tab.

#### B. The `MaterialCheckbox` Label
* **Limitation:** The `label` property inside `MaterialCheckbox` cannot be reliably styled (e.g., it may default to an illegible grey depending on the environment's base theme).
* **Workaround:** Omit the `label` property entirely from the `MaterialCheckbox`. Wrap the checkbox in a `MaterialRow` alongside a `MaterialText` component. `MaterialText` fully respects the `"style"` dictionary, allowing you to explicitly set the text color to match your agent's specific theme.

#### D. Gemini Enterprise Canvas & Composite Catalog v0.9 (CRITICAL)
When deploying A2UI agents to **Gemini Enterprise**, the chat UI hosts rich interfaces inside an interactive **Canvas** panel:
* **Catalog ID**: Must be set to `"https://www.gstatic.com/vertexaisearch/a2ui/v0_9/gemini_enterprise_composite_catalog.json"`.
* **Root Canvas Component**: The root component in `updateComponents` for side-panel views MUST be `"component": "Canvas"`, with properties:
  - `"id": "root"`
  - `"component": "Canvas"`
  - `"cardTitle": "Title"`
  - `"cardDescription": "Subtitle"`
  - `"cardIcon": "icon_name"`
  - `"autoOpen": true` (automatically expands the canvas side-panel)
  - `"children": ["root_card_id"]`
* **Material Component Names & Syntax**:
  - `MaterialCard` (uses `"appearance": "raised"|"outlined"|"flat"`, `"children": ["col_id"]`, `"style": {"padding": "16px"}`)
  - `MaterialColumn` (uses `"children": [...]`, `"align": "stretch"|"start"|"center"|"end"`, `"style": {"gap": "12px"}`)
  - `MaterialRow` (uses `"children": [...]`, `"align": "center"|"start"|"end"`)
  - `MaterialText` (uses `"text": "..."`, `"usageHint": "h1"|"h2"|"h3"|"body"`)
  - `MaterialButton` (uses `"label": "..."`, `"variant": "raised"|"flat"|"stroked"|"basic"`, `"color": "primary"|"accent"|"warn"`, `"action": {"event": {"name": "...", "context": {...}}}}`)
  - `MaterialDivider`
* **Input Fields (CRITICAL: `MaterialInput`, NOT `MaterialTextField`)**:
  - In the Gemini Enterprise Composite Catalog, text input fields are strictly named **`MaterialInput`** (do NOT use `MaterialTextField` or `TextField`).
  - Properties:
    ```json
    {
      "id": "user_email",
      "component": "MaterialInput",
      "label": "Email Address",
      "placeholder": "user@example.com",
      "type": "text",
      "value": { "path": "/user/email" }
    }
    ```
  - Supported `type` values: `"text"`, `"email"`, `"number"`, `"password"`, `"tel"`, `"url"`.
* **Iframe Embeds (CRITICAL: `IFrameUrl` & `IFrameSrcdoc`)**:
  - **`IFrameUrl`**: Embeds allowlisted external web applications inside a canvas panel.
    ```json
    {
      "id": "app_frame",
      "component": "IFrameUrl",
      "url": "https://example.com/app",
      "height": 650
    }
    ```
  - **`IFrameSrcdoc`**: Embeds sandboxed, network-restricted inline HTML.
    ```json
    {
      "id": "custom_html",
      "component": "IFrameSrcdoc",
      "htmlContent": "<!DOCTYPE html><html><head><meta http-equiv=\"Content-Security-Policy\" content=\"connect-src 'none'\"></head><body>...</body></html>",
      "height": 400
    }
    ```
* **Silent Dropping of Unregistered Components**:
  - The Gemini Enterprise client renderer validates components against the composite catalog schema. If a component name is invalid or misspelled (e.g. `MaterialTextField`, `WebFrameUrl`, `TextInput`), the renderer **silently skips** the invalid component and renders the remaining valid children without throwing an error message in the chat. If an input field or iframe fails to appear while the surrounding card and buttons render normally, verify the exact component name against the composite catalog schema.

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

### Protobuf Payload Parsing Patch (Gemini Enterprise A2UI v0.8)
**Issue:** The A2UI frontend in Gemini Enterprise sometimes sends slightly malformed `data` payloads inside `parts` (e.g., missing the nested `data: { data: {...} }` wrapper expected by the strict Protobuf parser). This causes deserialization errors. In addition, Python 3.13 can encounter `KeyError: 'serialized'` in `google/protobuf/message.py` during `cloudpickle.loads`.
**Fix:** Inject the monkey-patches for `Message.__setstate__` and `google.protobuf.json_format.Parse` at the top of `agent_executor.py` before instantiating the runner:

```python
# Apply Protobuf & Pydantic compatibility patches for Python 3.9/3.10/3.13
try:
    from google.protobuf.message import Message
    _orig_setstate = Message.__setstate__

    def _patched_setstate(self, state):
        if isinstance(state, dict) and "serialized" not in state:
            state["serialized"] = b""
        return _orig_setstate(self, state)

    Message.__setstate__ = _patched_setstate
except Exception:
    pass

import google.protobuf.json_format as json_format

# MONKEY-PATCH: Fix Gemini Enterprise client payload format mismatch (A2UI v0.8)
original_parse = json_format.Parse

def patched_parse(text, message, *args, **kwargs):
    from a2a.grpc import a2a_pb2
    if isinstance(message, a2a_pb2.SendMessageRequest):
        try:
            if isinstance(text, bytes):
                text_str = text.decode('utf-8')
            else:
                text_str = text
            
            data = json.loads(text_str)
            
            def fix_a2a_payload(d):
                if not isinstance(d, dict):
                    return d
                if "message" in d and isinstance(d["message"], dict):
                    msg = d["message"]
                    if "parts" in msg and isinstance(msg["parts"], list):
                        for part in msg["parts"]:
                            if isinstance(part, dict) and "data" in part:
                                part_data = part["data"]
                                if isinstance(part_data, dict) and "data" not in part_data:
                                    part["data"] = {"data": part_data}
                if "content" in d and isinstance(d["content"], list):
                    for part in d["content"]:
                        if isinstance(part, dict) and "data" in part:
                            part_data = part["data"]
                            if isinstance(part_data, dict) and "data" not in part_data:
                                part["data"] = {"data": part_data}
            fix_a2a_payload(data)
            text = json.dumps(data)
        except Exception:
            pass
    return original_parse(text, message, *args, **kwargs)

json_format.Parse = patched_parse
```

### Dependency Parity (Local vs Remote)
**Lesson**: When deploying via the Python SDK (Pickle-based), the local environment's package versions are captured in the pickle. If the remote environment installs different versions (due to unpinned requirements), unpickling failures like `KeyError: 'serialized'` are highly likely.
**Action**: 
1. Pin all key dependencies in `deploy_sdk.py` (or `deploy_ae.py`) to match known working versions (e.g., from a reference working file).
2. **CRITICAL**: Ensure you include `"a2ui-agent-sdk"` in the `requirements` list of the `config` dictionary passed to `client.agent_engines.create`.
3. Ensure your local environment matches these pinned versions before running the deployment script.
4. Add a local requirements check in your deployment script to warn about mismatches.

### Dependency Naming
**Lesson**: Always reference the package by its official name `a2ui-agent-sdk`:
```text
a2ui-agent-sdk
```

## 12. Reference Code & Samples
The workspace contains a comprehensive library of A2UI samples. **Always** prefer reading these verified implementations over generating code from scratch.

For additional examples of agents that work with Gemini Enterprise, refer to: https://github.com/GCPartner/partner-reference-agents

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

## 15. Mock Tester Template (FastAPI + HTML)

Use this template to build a robust local tester for A2UI agents.

### A. `server.py` (FastAPI)

```python
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import json

app = FastAPI()

@app.post("/jsonrpc")
async def handle_jsonrpc(request: Request):
    body = await request.json()
    params = body.get("params", {})
    message = params.get("message", {})
    query = message.get("text", "")
    parts = message.get("parts", [])
    
    # Extract userAction from DataPart
    user_action = None
    for part in parts:
        if part.get("metadata", {}).get("mimeType") == "application/json+a2ui":
            data = part.get("data")
            if isinstance(data, dict) and 'userAction' in data:
                user_action = data['userAction']
                break
                
    # Process Action Context
    state = {}
    if user_action:
        action_context = user_action.get('context', {})
        for key, value in action_context.items():
            state[key] = value
            if key == 'message':
                query = value  # Override query with message from context
                
    # Call your agent here...
    # response = agent.run(query, state)
    
    # Return A2UI response...
```

### B. `index.html` (Client Snippets)

```html
<!-- Handle DateTimeInput -->
if (comp.DateTimeInput) {
    const input = document.createElement('input');
    const dt = comp.DateTimeInput;
    if (dt.enableDate === false && dt.enableTime === true) {
        input.type = 'time';
    } else if (dt.enableDate === true && dt.enableTime === false) {
        input.type = 'date';
    } else {
        input.type = 'datetime-local';
    }
    ...
}

<!-- Handle Button Actions -->
if (comp.Button.action) { // Generic handler
    btn.onclick = () => {
        const context = comp.Button.action.context || [];
        // Extract data from model and send...
    };
}
```

## 16. Golden Boilerplate: agent_executor.py

This template handles session recovery, state injection, and robust A2UI output parsing.

> [!NOTE]
> A standalone version of this template is available at `templates/golden_agent_executor.py` within the skill directory.

```python
import json, logging, re
from a2a import types, utils
from a2a.server import agent_execution, events, tasks
from google.adk import runners
from google.adk.sessions import in_memory_session_service
from google.genai import types as genai_types
from agent import root_agent

# Apply Protobuf & Pydantic compatibility patches for Python 3.9/3.10/3.13
try:
    from google.protobuf.message import Message
    _orig_setstate = Message.__setstate__

    def _patched_setstate(self, state):
        if isinstance(state, dict) and "serialized" not in state:
            state["serialized"] = b""
        return _orig_setstate(self, state)

    Message.__setstate__ = _patched_setstate
except Exception:
    pass

import google.protobuf.json_format as json_format

# MONKEY-PATCH: Fix Gemini Enterprise client payload format mismatch (A2UI v0.8)
original_parse = json_format.Parse

def patched_parse(text, message, *args, **kwargs):
    from a2a.grpc import a2a_pb2
    if isinstance(message, a2a_pb2.SendMessageRequest):
        try:
            if isinstance(text, bytes):
                text_str = text.decode('utf-8')
            else:
                text_str = text
            
            data = json.loads(text_str)
            
            def fix_a2a_payload(d):
                if not isinstance(d, dict):
                    return d
                if "message" in d and isinstance(d["message"], dict):
                    msg = d["message"]
                    if "parts" in msg and isinstance(msg["parts"], list):
                        for part in msg["parts"]:
                            if isinstance(part, dict) and "data" in part:
                                part_data = part["data"]
                                if isinstance(part_data, dict) and "data" not in part_data:
                                    part["data"] = {"data": part_data}
                if "content" in d and isinstance(d["content"], list):
                    for part in d["content"]:
                        if isinstance(part, dict) and "data" in part:
                            part_data = part["data"]
                            if isinstance(part_data, dict) and "data" not in part_data:
                                part["data"] = {"data": part_data}
            fix_a2a_payload(data)
            text = json.dumps(data)
        except Exception:
            pass
    return original_parse(text, message, *args, **kwargs)

json_format.Parse = patched_parse

logger = logging.getLogger(__name__)

class AdkAgentToA2AExecutor(agent_execution.AgentExecutor):
    def __init__(self, *args, **kwargs):
        self._runner = kwargs.get('runner')
        if not self._runner:
            self._runner = runners.Runner(
                app_name="A2UIAgent",
                agent=root_agent,
                session_service=in_memory_session_service.InMemorySessionService(),
                auto_create_session=True,
            )

    async def execute(self, context: agent_execution.RequestContext, event_queue: events.EventQueue) -> None:
        query = context.get_user_input()
        task = context.current_task
        task_id = context.task_id or (task.id if task else "default_task")
        context_id = context.context_id or (task.context_id if task else "default")
        session_id = context_id or "default"
        
        # 1. SESSION RECOVERY & ACTION PARSING: Extract state & hidden action from A2UI payload
        action_context = {}
        action_query = None
        try:
            if hasattr(context, 'message') and context.message:
                for part in context.message.parts:
                    if hasattr(part, 'root') and hasattr(part.root, 'data'):
                        data = part.root.data
                        if hasattr(part.root, 'metadata') and part.root.metadata and part.root.metadata.get('mimeType') == 'application/json+a2ui':
                            # Unwrap nested data wrapper if present
                            if isinstance(data, dict) and "data" in data:
                                data = data["data"]

                            action_data = None
                            if isinstance(data, dict):
                                if "action" in data:
                                    action_data = data["action"]
                                elif "userAction" in data:
                                    action_data = data["userAction"]

                            if isinstance(action_data, dict):
                                # Support nested 'event' field
                                if "event" in action_data and isinstance(action_data["event"], dict):
                                    action_data = action_data["event"]
                                
                                ctx = action_data.get("context", {})
                                if isinstance(ctx, dict):
                                    if "message" in ctx:
                                        action_query = ctx["message"]
                                    action_context.update(ctx)

                                # Recover Form Inputs
                                for item in action_data.get("inputs", []):
                                    if isinstance(item, dict) and item.get("id"):
                                        context.metadata[item["id"]] = item["value"]
                                        action_context[item["id"]] = item["value"]

            if action_query:
                query = action_query  # Override query with hidden intent message
                
            for k, v in action_context.items():
                if k != 'message':
                    context.metadata[k] = v
        except Exception as e: logger.warning(f"Recovery failed: {e}")

        # 2. STATE INJECTION: Persist state via prompt (Transcript Echoing)
        state_str = " ".join([f"[State: {k}={v}]" for k, v in context.metadata.items() if k != 'message'])
        if state_str: query = f"{query} {state_str}"

        # 3. EXECUTION: Run ADK Runner with correct types
        updater = tasks.TaskUpdater(event_queue, task_id, context_id)
        await updater.start_work()
        
        full_text = ""
        async for event in self._runner.run_async(
            user_id="user", 
            session_id=session_id, 
            new_message=genai_types.Content(parts=[genai_types.Part(text=query)])
        ):
            if event.is_final_response():
                full_text += "".join([p.text for p in event.content.parts if hasattr(p, 'text')])

        # 4. OUTPUT PARSING: Regex-based extraction (Required for v0.8)
        json_match = re.search(r"(\{.*\"a2ui_messages\".*\})", full_text, re.DOTALL)
        parts = [types.Part(root=types.TextPart(text=re.sub(r"---a2ui_JSON---.*", "", full_text, flags=re.DOTALL).strip()))]
        if json_match:
            try:
                for msg in json.loads(json_match.group(1)).get("a2ui_messages", []):
                    parts.append(types.Part(root=types.DataPart(data=msg, metadata={"mimeType": "application/json+a2ui"})))
            except: pass
            
        await updater.add_artifact(parts, name="response")
        await updater.complete()

    async def cancel(self, context, event_queue): pass
```

## 17. Reasoning Engine Troubleshooting Bible

This section summarizes critical fixes for issues encountered when deploying A2UI agents to Vertex AI Reasoning Engine.

| Issue Category & Name | Log/Browser Signature 🔍 | Generic Root Cause 🧠 | The Reusable Solution 🛠️ |
| :--- | :--- | :--- | :--- |
| **Model Access Lockout (404)** | `404 Publisher Model ... was not found`. | The project/region has either deprecated the model or restricted it. | **Implementation**: Never assume a model is available. Create a standalone `troubleshoot_access.py` and run a "probe" across the frontier (e.g., `gemini-2.5-flash`, `gemini-3.1-flash`) to find the valid regional standard. |
| **Input Form Loop** | Browser keeps showing the same input form again after submission. | Missing user action in few-shot examples. | **Architectural Patches**: 1. Add intent-specific **examples** to `AgentSkill` card. 2. Refine **System Instructions** with a numbered "Turn Sequence". |
| **State Persistence Gap** | `NO STATE RECOVERED`. Model asks for data you just provided. | Statelessness of Reasoning Engine. | **The "Recovery Loop" Pattern**: In your executor's `execute()` method, recursively search for `userAction` objects in `context.message.parts` and inject their `inputs` back into the prompt as a `[State: key=val]` block. |
| **Protocol UI rejection** | Browser says "Missing Card" or blank UI. | Malformed JSON or missing mimeType. | **A2UI v0.8 Compliance**: Ensure the executor wraps all JSON after `---a2ui_JSON---` into an `a2a.types.DataPart` with `metadata={"mimeType": "application/json+a2ui"}`. Use regex to strip conversational text. |
| **Cloud Serialization Error** | `TASK_STATE_FAILED` or `PickleError`. | Protobuf unpickling issues. | **The Serialization Patch**: Add a monkey-patch to your deployment script that injects a `__setstate__` method into `google.protobuf.message.Message`. |
| **Execution Context Flickering** | Permissions errors or "Project not found". | Loss of env vars. | **Forced Initialization**: Use the **numeric Project Number**. Call `aiplatform.init` and `vertexai.init` inside the `__init__` AND the `execute()` methods of your executor. |
| **Chain-of-Thought Break** | Agent calls Turn 1 tools instead of Turn 2 tools. | Attention on text rather than state. | **Delimited Prompts**: Append state to query: `Actual User Text [State: param1=val|param2=val]`. Instruct model to prioritize `[State]` data. |
| **Dependency Build Failure** | Deployment fails with "requirements not satisfied". | Version conflicts. | **Clean Build Strategy**: Avoid pinning `google-cloud-aiplatform` to a specific sub-version. Use `@ git+https://github.com/...` syntax for side-loaded SDKs. |
| **Echo Behavior Failure** | Tool JSON is swallowed or double-wrapped. | Agent tries to be "helpful" by summarizing. | **Echo Constraint**: Add hard constraint: *"When a tool returns a string starting with '---a2ui_JSON---', you MUST include that exact string in your response without modification."* |
| **Wizard/Multi-turn Panel Flashing or Obscurity** | Canvas side panel flashes, closes, or fails to show the target step's UI on forward/backward navigation. | Using unique surface IDs per turn and constantly deleting/recreating surfaces causes client container panel teardowns and stack overlapping issues. | **Single Persistent Surface Pattern**: Use a single surface ID (e.g. `"navigator"`) for the entire flow. Create the surface ONLY once on the first turn using `createSurface`. For all subsequent turns (Next/Back), output ONLY `updateComponents` and `updateDataModel` targeting that same surface. Do NOT send `createSurface` or `deleteSurface` during transitions. |
| **State Preservation on Back Navigation** | Navigating back shows default/empty forms, losing previous user selections. | The data model values are not pre-populated in subsequent updates. | **Data Model State Sync**: When outputting `updateDataModel` (especially when going back), dynamically populate the `value` dictionary with the current values of all selections in the state (`plan_type`, `specialty`, etc.) to pre-fill the UI controls. |
| **Catalog Drift & Component Rejection** | Client displays broken images or silent rendering failure. | Live browser client schema implementation drifts from properties in the online composite catalog (e.g. `roundedCorners` on `MaterialImage` or `style` on standard `Image`). | **Strict Schema Validation & Component Selection**: 1. Avoid custom Material wraps (`MaterialImage`) if standard equivalents (`Image`) exist. 2. Standard components are strict; do NOT append unevaluated properties like `style` to standard components if they restrict it via `unevaluatedProperties: false`. 3. Rely on standard enum properties like `variant: "smallFeature"` to scale standard components rather than custom styles. |

### 🚀 Best Practice Deployment Workflow
1. **Verify Model**: Run the probe script to confirm the target region supports the chosen Gemini version.
2. **Patch Serialization**: Include the Protobuf monkey-patch by default in the `agent_executor.py`.
3. **Harden Protocol**: Use a regex-based unwrapper for `---a2ui_JSON---` to ensure text and data are separated.
4. **Inject State**: Always implement the recursive history crawler to ensure multi-turn continuity.
5. **Use Numeric IDs**: Use Project Number and specified Location persistently in all `init` calls.

