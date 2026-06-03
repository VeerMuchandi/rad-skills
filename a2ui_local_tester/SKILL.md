---
name: A2UI Local Tester
description: Specialized role for setting up and performing local testing of A2UI agents using the A2A / JSON-RPC protocol.
mode: manual
---

# A2UI Local Tester Skill

You are the **A2UI Local Tester**. Your primary responsibility is to set up a local testing harness for A2UI agents, allowing developers to verify component rendering and interaction flow without deploying to Vertex AI Agent Engine or Gemini Enterprise.

## Core Responsibilities
1.  **Local Server Setup**: Create a local server (e.g., using FastAPI) that mimics the A2A protocol.
2.  **A2A Protocol Emulation**: Handle JSON-RPC 2.0 requests and bridge them to the agent's executor.
3.  **Isolation**: Ensure all local testing code is kept in a separate sub-folder under the agent and is excluded from deployment.

## Mandatory Workflow
1. **Isolation**: Implement the A2UI agent in a separate folder from the reference agent (e.g., `[agent_name]_a2ui`).
2. **Local First**: Always verify the agent using this local tester skill before suggesting or attempting deployment.
3. **Explicit Permission**: Deploy to runtime environments only when explicitly instructed by the user after successful local testing.

## Implementation Guide (Option 2: A2A / JSON-RPC)

If the agent is built as an A2A / JSON-RPC service (e.g., using `AdkAgentToA2AExecutor`), follow these steps to set up local testing:

### Step 1: Create a Local Tester Sub-folder
Create a folder named `local_tester` (or similar) directly under the agent's root directory.
Ensure this folder is added to the project's `.gitignore` to prevent it from being included in deployment packages.

### Step 2: Implement the Local Server
Create a Python script (e.g., `server.py`) inside the `local_tester` folder. This script should use FastAPI to expose the endpoints and serve the mock client.

Here is the complete template for `server.py`:

```python
import os
import sys
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
import logging
from dotenv import load_dotenv

# Add parent directory to path to import agent and tools
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)

# Load environment variables from .env file in parent directory
load_dotenv(os.path.join(parent_dir, '.env'))

import agent
from google.adk import runners
from google.adk.sessions import in_memory_session_service
from google.adk.artifacts import in_memory_artifact_service
from google.adk.memory import in_memory_memory_service
from google.genai import types as genai_types

app = FastAPI()

# Enable CORS for local testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Initialize ADK Runner
adk_agent = agent.root_agent
runner = runners.Runner(
    app_name=adk_agent.name,
    agent=adk_agent,
    session_service=in_memory_session_service.InMemorySessionService(),
    artifact_service=in_memory_artifact_service.InMemoryArtifactService(),
    memory_service=in_memory_memory_service.InMemoryMemoryService(),
)

@app.get("/.well-known/agent-card.json")
async def get_agent_card():
    return {
        "capabilities": {
            "streaming": False,
            "extensions": [{"uri": "https://a2ui.org/a2a-extension/a2ui/v0.8", "required": False}]
        },
        "name": adk_agent.name,
        "url": "/jsonrpc",
        "version": "1.0.0"
    }

@app.get("/")
async def get_index():
    return FileResponse(os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"))

@app.post("/jsonrpc")
async def handle_jsonrpc(request: Request):
    body = await request.json()
    logger.info(f"Received JSON-RPC request: {body}")
    
    if body.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request"}, "id": body.get("id")}
        
    method = body.get("method")
    params = body.get("params", {})
    request_id = body.get("id")
    
    if method == "message/send":
        message = params.get("message", {})
        query = message.get("text", "")
        parts = message.get("parts", [])
        session_id = params.get("session_id", "local_session")
        
        # Extract userAction from DataPart
        user_action = None
        for part in parts:
            if part.get("metadata", {}).get("mimeType") == "application/json+a2ui":
                data = part.get("data")
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except:
                        pass
                if isinstance(data, dict) and 'userAction' in data:
                    user_action = data['userAction']
                    break
        
        # Get session
        session = await runner.session_service.get_session(
            app_name=adk_agent.name,
            user_id="local_user",
            session_id=session_id,
        )
        if not session:
            session = await runner.session_service.create_session(
                app_name=adk_agent.name,
                user_id="local_user",
                state={},
                session_id=session_id,
            )
            
        state = session.state if session.state else {}
        
        # Inject userAction context into session state
        if user_action:
            action_context = user_action.get('context', {})
            for key, value in action_context.items():
                state[key] = value
                if key == 'message':
                    query = value # Override query with message from context
            session.state = state # Update in-memory object
            
        # Append state to query to maintain context
        state_str = " ".join([f"[State: {k}={v}]" for k, v in state.items() if k not in ['message']])
        if state_str:
            query = f"{query} {state_str}"
            logger.info(f"Injected state into query: {query}")
            
        content = genai_types.Content(role="user", parts=[{"text": query}])
        
        final_response_content = None
        async for event in runner.run_async(
            user_id="local_user", session_id=session.id, new_message=content
        ):
            if event.is_final_response():
                if event.content and event.content.parts and event.content.parts[0].text:
                    final_response_content = "\n".join([p.text for p in event.content.parts if p.text])
                    
        if not final_response_content:
            return {"jsonrpc": "2.0", "result": {"message": {"text": "No response from agent"}}, "id": request_id}
            
        # Split A2UI JSON
        text_part = final_response_content
        json_string_cleaned = "[]"
        
        if "---a2ui_JSON---" in final_response_content:
            text_part, json_string = final_response_content.split("---a2ui_JSON---", 1)
            json_string_cleaned = json_string.strip().lstrip("```json").rstrip("```").strip()
            if not json_string_cleaned:
                json_string_cleaned = "[]"
                
        try:
            ui_data = json.loads(json_string_cleaned)
        except Exception as e:
            logger.error(f"Failed to parse UI JSON: {e}")
            ui_data = []
            
        parts = []
        if text_part.strip():
            parts.append({"text": text_part.strip()})
            
        # Load schema
        schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_to_client_with_standard_catalog.json")
        schema = None
        if os.path.exists(schema_path):
            try:
                with open(schema_path, "r") as f:
                    schema = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load schema from {schema_path}: {e}")

        # Wrap A2UI messages in DataPart
        if isinstance(ui_data, list):
            messages = ui_data
        elif isinstance(ui_data, dict) and "a2ui_messages" in ui_data:
            messages = ui_data["a2ui_messages"]
        else:
            messages = [ui_data] if ui_data else []
            
        for msg in messages:
            if schema:
                try:
                    import jsonschema
                    jsonschema.validate(instance=msg, schema=schema)
                    logger.info("A2UI payload message successfully validated against schema.")
                except jsonschema.ValidationError as e:
                    logger.critical(f"A2UI STRICT SCHEMA VALIDATION FAILED: {e.message}")
                    logger.critical(f"Invalid Message: {json.dumps(msg, indent=2)}")
                    raise ValueError(f"A2UI Schema Validation Error: {e.message}") from e
            parts.append({
                "data": msg,
                "metadata": {"mimeType": "application/json+a2ui"}
            })
            
        return {
            "jsonrpc": "2.0",
            "result": {
                "message": {
                    "parts": parts
                }
            },
            "id": request_id
        }
        
    return {"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}, "id": request_id}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```


### Step 3: Generate an Interactive Mock Client
To test the agent without cloning the full A2UI repository, you can generate an interactive HTML client inside the `local_tester` folder. This client uses `fetch` to communicate with your local server and renders a basic visual representation of the A2UI components (Cards, Buttons, Dropdowns) rather than just dumping JSON.

Key Features of this Mock Client:
*   **Recursive Rendering**: Designed to render A2UI components gracefully. It provides specific renderers for core components like `Card`, `Column`, `Row`, `Text`, `Button`, `MultipleChoice`, `DateTimeInput`, `CheckBox`, `Slider`, and `TextField`, and falls back gracefully for others.
*   **State Management**: Maintains a local `dataModel` object and handles `dataModelUpdate` from the server.
*   **Interactive Buttons**: Button clicks construct the full `userAction` payload with context, resolving paths against the local `dataModel`.
*   **JSON Toggle**: Hides the raw JSON payload by default in a collapsible section.
*   **Session Management**: Displays current session ID and allows starting a new session.
*   **Keyboard Support**: Pressing Enter in the input field sends the message.

Create `index.html` in the `local_tester` folder:
```html
<!DOCTYPE html>
<html>
<head>
    <title>A2UI Local Tester</title>
    <style>
        body { font-family: sans-serif; margin: 20px; background: #f0f2f5; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .chat-box { border: 1px solid #ccc; padding: 10px; height: 400px; overflow-y: scroll; margin-bottom: 10px; background: #fafafa; }
        .card { border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 8px; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
        .button { background: #007bff; color: white; padding: 8px 15px; border: none; border-radius: 4px; cursor: pointer; margin-right: 5px; }
        .button:hover { background: #0056b3; }
        .input-group { display: flex; gap: 10px; }
        input[type="text"] { flex-grow: 1; padding: 8px; border: 1px solid #ccc; border-radius: 4px; }
        select { padding: 8px; border: 1px solid #ccc; border-radius: 4px; }
        pre { background: #f8f9fa; padding: 10px; border-radius: 4px; border: 1px solid #e9ecef; overflow-x: auto; }
        details { margin-top: 10px; }
        summary { cursor: pointer; color: #007bff; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        .session-info { font-size: 0.9em; color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>A2UI Local Tester</h1>
            <div class="session-info">
                <span id="session-id-display"></span>
                <button onclick="startNewSession()" class="button" style="background: #dc3545; margin-left: 10px;">New Session</button>
            </div>
        </div>
        
        <div class="chat-box" id="chat"></div>
        <div class="input-group">
            <input type="text" id="input" placeholder="Type a message...">
            <button onclick="sendMessage()" class="button">Send</button>
        </div>
        
        <details>
            <summary>Show Raw UI JSON</summary>
            <pre id="json-dump">No UI data yet.</pre>
        </details>
    </div>

    <script>
        let dataModel = {};
        let sessionId = generateSessionId();

        function generateSessionId() {
            return 'session_' + Math.random().toString(36).substr(2, 9);
        }

        function updateSessionDisplay() {
            document.getElementById('session-id-display').innerText = `Session: ${sessionId}`;
        }

        function startNewSession() {
            sessionId = generateSessionId();
            updateSessionDisplay();
            dataModel = {};
            document.getElementById('chat').innerHTML = '';
            appendMessage('System', 'Started a new session.');
            document.getElementById('json-dump').innerText = 'No UI data yet.';
        }

        // Call on load
        updateSessionDisplay();

        // Enter key listener
        document.getElementById('input').addEventListener('keypress', function (e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });

        async function sendMessage() {
            const input = document.getElementById('input');
            const text = input.value;
            if (!text.trim()) return;
            input.value = '';
            
            appendMessage('User', text);
            
            await sendPayload({ message: { text: text } });
        }

        async function sendUserAction(userAction, messageText) {
            appendMessage('User', messageText);
            
            const payload = {
                message: {
                    text: messageText,
                    parts: [
                        {
                            data: { userAction: userAction },
                            metadata: { mimeType: 'application/json+a2ui' }
                        }
                    ]
                }
            };
            
            await sendPayload(payload);
        }

        async function sendPayload(params) {
            const loadingDiv = appendMessage('System', 'Agent is thinking...');
            try {
                const response = await fetch('/jsonrpc', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        jsonrpc: '2.0',
                        method: 'message/send',
                        params: { ...params, session_id: sessionId },
                        id: Date.now()
                    })
                });
                
                const data = await response.json();
                loadingDiv.remove();
                handleResponse(data);
            } catch (error) {
                loadingDiv.remove();
                appendMessage('Error', `Failed to connect to server: ${error.message}`);
            }
        }

        function appendMessage(sender, text) {
            const chat = document.getElementById('chat');
            const div = document.createElement('div');
            div.style.marginBottom = '10px';
            div.innerHTML = `<strong>${sender}:</strong> ${text}`;
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
            return div;
        }

        let currentRootId = null;

        function handleResponse(data) {
            if (data.error) {
                appendMessage('Error', data.error.message);
                return;
            }
            
            const parts = data.result.message.parts;
            
            // First pass to find beginRendering and extract root ID
            for (const part of parts) {
                if (part.data && part.metadata && part.metadata.mimeType === 'application/json+a2ui') {
                    const uiData = part.data;
                    if (uiData.beginRendering) {
                        currentRootId = uiData.beginRendering.root;
                    }
                }
            }
            
            for (const part of parts) {
                if (part.text) {
                    appendMessage('Agent', part.text);
                }
                if (part.data && part.metadata && part.metadata.mimeType === 'application/json+a2ui') {
                    const uiData = part.data;
                    console.log("Received UI Data:", uiData);
                    
                    // Handle Data Model Updates
                    if (uiData.dataModelUpdate) {
                        const contents = uiData.dataModelUpdate.contents || [];
                        for (const item of contents) {
                            dataModel[item.key] = item.valueString || item.valueNumber || item.valueBoolean;
                        }
                    }
                    
                    // Handle Surface Updates (Rendering)
                    if (uiData.surfaceUpdate) {
                        document.getElementById('json-dump').innerText = JSON.stringify(uiData, null, 2);
                        const rootToUse = uiData.surfaceUpdate.root || currentRootId;
                        renderUI(uiData.surfaceUpdate, rootToUse);
                    }
                }
            }
        }

        function renderUI(surfaceUpdate, rootId) {
            const chat = document.getElementById('chat');
            const div = document.createElement('div');
            div.className = 'card';
            div.innerHTML = '<h4>Rich UI View</h4>';
            
            const components = surfaceUpdate.components;
            
            if (rootId && components) {
                const rendered = renderComponent(rootId, components);
                if (rendered) {
                    div.appendChild(rendered);
                }
            }
            
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
        }

        function renderComponent(componentId, components) {
            console.log("Rendering component:", componentId);
            const compWrapper = components.find(c => c.id === componentId);
            if (!compWrapper) {
                console.warn("Component not found:", componentId);
                return document.createTextNode(`[Missing: ${componentId}]`);
            }
            
            const comp = compWrapper.component;
            console.log("Component data:", comp);
            
            if (comp.Text) {
                const div = document.createElement('div');
                div.innerText = comp.Text.text.literalString || "";
                if (comp.Text.usageHint === 'h1') div.style.fontSize = '1.8em';
                if (comp.Text.usageHint === 'h2') div.style.fontSize = '1.4em';
                if (comp.Text.usageHint === 'h3') div.style.fontSize = '1.2em';
                div.style.marginBottom = '5px';
                return div;
            }
            
            if (comp.Card) {
                const div = document.createElement('div');
                div.style.border = '1px solid #ccc';
                div.style.padding = '10px';
                div.style.borderRadius = '5px';
                div.style.background = '#fff';
                div.style.marginBottom = '10px';
                if (comp.Card.child) {
                    div.appendChild(renderComponent(comp.Card.child, components));
                }
                return div;
            }
            
            if (comp.Column) {
                const div = document.createElement('div');
                div.style.display = 'flex';
                div.style.flexDirection = 'column';
                div.style.gap = '10px';
                const children = comp.Column.children.explicitList || [];
                for (const childId of children) {
                    div.appendChild(renderComponent(childId, components));
                }
                return div;
            }
            
            if (comp.Row) {
                const div = document.createElement('div');
                div.style.display = 'flex';
                div.style.flexDirection = 'row';
                div.style.gap = '10px';
                div.style.justifyContent = comp.Row.distribution === 'spaceAround' ? 'space-around' : 'flex-start';
                const children = comp.Row.children.explicitList || [];
                for (const childId of children) {
                    div.appendChild(renderComponent(childId, components));
                }
                return div;
            }
            
            if (comp.Button) {
                const btn = document.createElement('button');
                btn.className = 'button';
                if (comp.Button.child) {
                    const childComp = components.find(c => c.id === comp.Button.child);
                    if (childComp && childComp.component.Text) {
                        btn.innerText = childComp.component.Text.text.literalString;
                    } else {
                        btn.innerText = comp.Button.child;
                    }
                }
                
                if (comp.Button.action) {
                    btn.onclick = () => {
                        const context = comp.Button.action.context || [];
                        const msgItem = context.find(i => i.key === 'message');
                        let msgText = "Action triggered";
                        if (msgItem) {
                            msgText = msgItem.value.literalString || "Action triggered";
                        }
                        
                        // Construct userAction payload
                        const userAction = {
                            name: comp.Button.action.name,
                            context: {}
                        };
                        
                        if (comp.Button.action.context && comp.Button.action.context.length > 0) {
                            for (const ctxItem of comp.Button.action.context) {
                                const key = ctxItem.key;
                                let val = undefined;
                                if (ctxItem.value) {
                                    if (ctxItem.value.literalString !== undefined) {
                                        val = ctxItem.value.literalString;
                                    } else if (ctxItem.value.path !== undefined) {
                                        val = dataModel[ctxItem.value.path];
                                    }
                                }
                                userAction.context[key] = val;
                            }
                        } else {
                            // Grab values from inputs to context
                            const inputFields = document.querySelectorAll('input, select');
                            inputFields.forEach(field => {
                                if (field.id) {
                                    const path = "/" + field.id.replace("_input", "").replace("_select", "").replace("_checkbox", "").replace("_slider", "");
                                    const cleanKey = field.id.replace("_input", "").replace("_select", "").replace("_checkbox", "").replace("_slider", "");
                                    userAction.context[cleanKey] = dataModel[path] || field.value;
                                }
                            });
                        }
                        
                        sendUserAction(userAction, msgText);
                    };
                }
                return btn;
            }
            
            if (comp.MultipleChoice) {
                const mc = comp.MultipleChoice;
                const select = document.createElement('select');
                select.style.padding = '5px';
                if (mc.selections && mc.selections.path) {
                    select.id = mc.selections.path + "_select";
                }
                
                // Add empty option
                const emptyOpt = document.createElement('option');
                emptyOpt.value = "";
                emptyOpt.innerText = "Select...";
                select.appendChild(emptyOpt);
                
                for (const opt of mc.options) {
                    const option = document.createElement('option');
                    option.value = opt.value;
                    option.innerText = opt.label.literalString || opt.value;
                    select.appendChild(option);
                }
                
                // Handle selections path
                if (mc.selections && mc.selections.path) {
                    select.onchange = (e) => {
                        dataModel[mc.selections.path] = e.target.value;
                        console.log(`Updated data model: ${mc.selections.path} = ${e.target.value}`);
                    };
                }
                
                return select;
            }

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
                input.style.padding = '5px';
                
                if (comp.DateTimeInput.value && comp.DateTimeInput.value.path) {
                    const path = comp.DateTimeInput.value.path;
                    input.id = path + "_input";
                    input.value = dataModel[path] || "";
                    input.oninput = (e) => {
                        dataModel[path] = e.target.value;
                        console.log(`Updated data model: ${path} = ${e.target.value}`);
                    };
                }
                return input;
            }
            
            if (comp.CheckBox) {
                const div = document.createElement('div');
                div.style.display = 'flex';
                div.style.alignItems = 'center';
                div.style.gap = '5px';
                
                const input = document.createElement('input');
                input.type = 'checkbox';
                
                const label = document.createElement('label');
                label.innerText = comp.CheckBox.label.literalString || "";
                
                div.appendChild(input);
                div.appendChild(label);
                
                if (comp.CheckBox.value && comp.CheckBox.value.path) {
                    const path = comp.CheckBox.value.path;
                    input.id = path + "_checkbox";
                    input.checked = dataModel[path] || false;
                    input.onchange = (e) => {
                        dataModel[path] = e.target.checked;
                        console.log(`Updated data model: ${path} = ${e.target.checked}`);
                    };
                }
                return div;
            }
            
            if (comp.Slider) {
                const div = document.createElement('div');
                div.style.display = 'flex';
                div.style.flexDirection = 'column';
                
                const label = document.createElement('label');
                label.innerText = `Value: `;
                const span = document.createElement('span');
                span.innerText = dataModel[comp.Slider.value.path] || comp.Slider.minValue || 0;
                label.appendChild(span);
                
                const input = document.createElement('input');
                input.type = 'range';
                input.min = comp.Slider.minValue || 0;
                input.max = comp.Slider.maxValue || 100;
                input.value = dataModel[comp.Slider.value.path] || 0;
                
                div.appendChild(label);
                div.appendChild(input);
                
                if (comp.Slider.value && comp.Slider.value.path) {
                    const path = comp.Slider.value.path;
                    input.id = path + "_slider";
                    input.oninput = (e) => {
                        span.innerText = e.target.value;
                        dataModel[path] = parseInt(e.target.value);
                    };
                }
                return div;
            }
            
            if (comp.TextField) {
                const div = document.createElement('div');
                div.style.display = 'flex';
                div.style.flexDirection = 'column';
                
                const label = document.createElement('label');
                label.innerText = comp.TextField.label.literalString || "";
                
                const input = document.createElement('input');
                input.type = 'text';
                
                div.appendChild(label);
                div.appendChild(input);
                
                if (comp.TextField.text && comp.TextField.text.path) {
                    const path = comp.TextField.text.path;
                    input.id = path + "_input";
                    input.value = dataModel[path] || "";
                    input.oninput = (e) => {
                        dataModel[path] = e.target.value;
                        console.log(`Updated data model: ${path} = ${e.target.value}`);
                    };
                }
                return div;
            }
            
            if (type === 'Image') {
                const img = document.createElement('img');
                img.src = comp.Image.url.literalString || comp.Image.url.path || "";
                img.style.maxWidth = '100px';
                img.style.maxHeight = '100px';
                img.style.objectFit = comp.Image.fit || 'contain';
                img.style.display = 'block';
                img.style.marginBottom = '5px';
                return img;
            }
            
            if (comp.WebFrameUrl) {
                const iframe = document.createElement('iframe');
                const urlObj = comp.WebFrameUrl.url;
                let srcUrl = "";
                if (urlObj.literalString) {
                    srcUrl = urlObj.literalString;
                } else if (urlObj.path) {
                    srcUrl = dataModel[urlObj.path] || "";
                }
                iframe.src = srcUrl;
                iframe.width = "100%";
                iframe.height = (comp.WebFrameUrl.height || 450) + "px";
                iframe.style.border = "none";
                iframe.style.borderRadius = "8px";
                iframe.style.boxShadow = "0 1px 3px rgba(0,0,0,0.1)";
                iframe.style.marginTop = "10px";
                return iframe;
            }
            
            if (comp.WebFrameSrcdoc) {
                const iframe = document.createElement('iframe');
                const srcdocObj = comp.WebFrameSrcdoc.srcdoc;
                let srcdocHtml = "";
                if (srcdocObj && srcdocObj.literalString) {
                    srcdocHtml = srcdocObj.literalString;
                } else if (srcdocObj && srcdocObj.path) {
                    srcdocHtml = dataModel[srcdocObj.path] || "";
                }
                iframe.srcdoc = srcdocHtml;
                iframe.width = "100%";
                iframe.height = (comp.WebFrameSrcdoc.height || 400) + "px";
                iframe.style.border = "none";
                iframe.style.borderRadius = "8px";
                iframe.style.boxShadow = "0 1px 3px rgba(0,0,0,0.1)";
                iframe.style.marginTop = "10px";
                return iframe;
            }
            
            if (comp.Divider) {
                const hr = document.createElement('hr');
                hr.style.border = "none";
                if (comp.Divider.axis === 'vertical') {
                    hr.style.borderLeft = "1px solid #eef2f6";
                    hr.style.height = "100%";
                    hr.style.margin = "0 10px";
                    hr.style.display = "inline-block";
                } else {
                    hr.style.borderTop = "1px solid #eef2f6";
                    hr.style.width = "100%";
                    hr.style.margin = "8px 0";
                }
                return hr;
            }
            
            const fallbackDiv = document.createElement('div');
            fallbackDiv.style.border = '1px dashed #ffc107';
            fallbackDiv.style.padding = '10px';
            fallbackDiv.style.margin = '5px 0';
            fallbackDiv.style.borderRadius = '4px';
            fallbackDiv.style.background = '#fff8e1';
            fallbackDiv.style.color = '#856404';
            
            const type = Object.keys(comp)[0] || "Unknown";
            fallbackDiv.innerHTML = `<strong>[${type}]</strong> ${componentId}`;
            
            return fallbackDiv;
        }
    </script>
</body>
</html>
```

### Step 4: Run the Client via HTTP Server
To avoid CORS and file origin restrictions in the browser, it is recommended to serve the generated `index.html` over HTTP. You can use Python's built-in HTTP server:

```bash
cd local_tester
python3 -m http.server 8080
```

Then open `http://localhost:8080` in your browser to test the agent.

## Remote Tester Pattern (Proxying to Deployed Agent)

If the agent is already deployed to Vertex AI Agent Engine, you can use a remote tester to verify it. This involves running a local proxy server that forwards A2A requests to the deployed agent endpoint, while serving the interactive mock client locally.

### Step 1: Create a Remote Tester Sub-folder
Create a folder named `remote_tester` directly under the agent's root directory. Copy the `index.html` file from the `local_tester` folder into this new folder, and update the heading in it to `<h1>A2UI Remote Tester</h1>` and the title to `<title>A2UI Remote Tester</title>` to distinguish it from the local tester.

### Step 2: Implement the Proxy Server
Create a Python script (e.g., `proxy_server.py`) inside the `remote_tester` folder.

Here is the complete template for `proxy_server.py`:
```python
import os
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
import logging
import requests
import time
from google.auth import default
from google.auth.transport.requests import Request as AuthRequest

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Configure these for your deployed agent
PROJECT_ID = "your-project-id"
LOCATION = "us-central1"
ENGINE_ID = "your-engine-id"

def get_bearer_token():
    credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(AuthRequest())
    return credentials.token

@app.get("/.well-known/agent-card.json")
async def get_agent_card():
    token = get_bearer_token()
    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{ENGINE_ID}/a2a/v1/card"
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(url, headers=headers)
    return res.json()

@app.get("/")
async def get_index():
    return FileResponse(os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"))

@app.post("/jsonrpc")
async def handle_jsonrpc(request: Request):
    body = await request.json()
    logger.info(f"Received JSON-RPC request: {body}")
    
    if body.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request"}, "id": body.get("id")}
        
    method = body.get("method")
    params = body.get("params", {})
    request_id = body.get("id")
    
    if method == "message/send":
        message = params.get("message", {})
        
        token = get_bearer_token()
        url = f"https://{LOCATION}-aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{ENGINE_ID}/a2a/v1/message:send"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        payload = {"message": message}
        
        logger.info(f"Forwarding to remote agent: {url}")
        res = requests.post(url, headers=headers, json=payload)
        
        if res.status_code != 200:
            return {"jsonrpc": "2.0", "error": {"code": res.status_code, "message": res.text}, "id": request_id}
            
        remote_response = res.json()
        task_id = remote_response.get("task", {}).get("id")
        
        if task_id:
            logger.info(f"Polling Task {task_id}...")
            task_url = f"https://{LOCATION}-aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{ENGINE_ID}/a2a/v1/tasks/{task_id}"
            
            for _ in range(90):
                time.sleep(2)
                task_res = requests.get(task_url, headers=headers)
                if task_res.status_code == 404:
                    logger.warning("Task status returned 404 (not found). Syncing replica, retrying...")
                    continue
                if task_res.status_code == 200:
                    task_data = task_res.json()
                    state = task_data.get("status", {}).get("state")
                    
                    if state == "TASK_STATE_SUCCEEDED" or state == "TASK_STATE_COMPLETED":
                        artifacts = task_data.get("artifacts", [])
                        # Load schema
                        schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_to_client_with_standard_catalog.json")
                        schema = None
                        if os.path.exists(schema_path):
                            try:
                                with open(schema_path, "r") as f:
                                    schema = json.load(f)
                            except Exception as e:
                                logger.error(f"Failed to load schema from {schema_path}: {e}")

                        parts = []
                        if artifacts:
                            parts = artifacts[0].get("parts", [])
                            # Clean nested data fields in A2UI parts if needed
                            for part in parts:
                                if "data" in part and part.get("metadata", {}).get("mimeType") == "application/json+a2ui":
                                    data_field = part["data"]
                                    if isinstance(data_field, dict) and "data" in data_field:
                                        part["data"] = data_field["data"]
                                    
                                    # Validate data_field against schema
                                    if schema:
                                        try:
                                            import jsonschema
                                            jsonschema.validate(instance=part["data"], schema=schema)
                                            logger.info("A2UI payload part successfully validated against schema.")
                                        except jsonschema.ValidationError as e:
                                            logger.critical(f"A2UI STRICT SCHEMA VALIDATION FAILED: {e.message}")
                                            logger.critical(f"Invalid Message: {json.dumps(part['data'], indent=2)}")
                                            raise ValueError(f"A2UI Schema Validation Error: {e.message}") from e
                            
                        return {
                            "jsonrpc": "2.0",
                            "result": {
                                "message": {
                                    "parts": parts
                                }
                            },
                            "id": request_id
                        }
                    elif state == "TASK_STATE_FAILED":
                        return {"jsonrpc": "2.0", "error": {"code": 500, "message": "Task failed on remote agent"}, "id": request_id}
                
            return {"jsonrpc": "2.0", "error": {"code": 504, "message": "Task timeout on remote agent"}, "id": request_id}
        else:
            return {"jsonrpc": "2.0", "error": {"code": 500, "message": "No task ID returned from remote agent"}, "id": request_id}
        
    return {"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}, "id": request_id}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Step 3: Run the Proxy Server
```bash
cd remote_tester
python3 proxy_server.py
```

### Step 4: Test in Browser
Open the local URL (e.g., `http://localhost:8000`) in your browser.

## Best Practices
*   **Keep it Separate**: Do not import local tester code in your core agent files.
*   **Mocking**: If the agent relies on Gemini Enterprise specific features (like user identity or specific datastores), mock them in the local server or executor bridge.

## 🚨 Lessons Learned & Troubleshooting

### 1. Unified Origin for Remote Environments
*   **The Problem**: Serving the mock client (port 8080) and the API (port 8000) on different ports causes CORS preflight (OPTIONS) requests. In remote SSH environments using proxies (like Google's ÜberProxy), these preflight requests may be redirected to SSO login pages, which browsers block, causing fetch failures.
*   **The Solution**: **Serve the mock client directly from the FastAPI server** at the root `/` endpoint. This puts both on the same origin (e.g., `http://vmps.c.googlers.com:8000/`) and avoids CORS issues entirely.

### 2. Reliable Automation of Dropdowns (MultipleChoice)
*   **The Problem**: Simulating key presses on `<select>` elements in the mock client may not reliably trigger the `onchange` event, resulting in empty values being sent in the action context.
*   **The Solution**: Use `execute_browser_javascript` to set the value of the dropdown directly and manually dispatch a change event:
```javascript
const select = document.getElementById('your_component_id_select');
select.value = 'desired_value';
select.dispatchEvent(new Event('change'));
```

### 3. Handling Quota Exhaustion (429)
*   **Symptom**: Local server returns `500 Internal Server Error` during a request.
*   **Cause**: The underlying Gemini API might be returning `429 RESOURCE_EXHAUSTED` due to quota limits.
*   **Action**: Check the server logs for the 429 traceback. Advise the user to retry later or check quota allocations.

### 4. Key Mapping Mismatch (Slash vs No Slash)
*   **The Problem**: Data paths in A2UI often start with a slash (e.g., `/start_address`). When the client sends these in the action context, it might strip the slash or use it as the key. If the server looks strictly for one format, it will fail to find the data.
*   **The Solution**: Ensure the server state extraction and bypass logic are resilient by checking for both formats:
```python
start_addr = state.get("start_address") or state.get("/start_address")
```
