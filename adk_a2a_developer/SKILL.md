---
name: ADK A2A Developer
description: Expert guide for making ADK agents A2A compatible and testing them on Agent Engine.
---

# ADK A2A Developer Skill

This skill equips you with the knowledge to take a standard ADK agent, make it A2A (Agent-to-Agent) compatible, and deploy it to Vertex AI Agent Engine.

## A2A Protocol

A2A (Agent-to-Agent) is a protocol for communication between agents or between a client and an agent using structured messages (usually JSON-RPC). It handles message routing, sessions, and tasks. This guide focuses on deploying agents that exchange text messages and structured data via A2A.

## Step 1: Create a Custom Agent Executor

To make an ADK agent A2A compatible on Vertex AI Agent Engine, you need to override the default execution loop with a custom `AgentExecutor`.

Create a file named `agent_executor.py` in your agent directory.

Here is a template for an A2A executor:

```python
"""Agent executor for ADK agents adapted for A2A compatibility."""

import json
import logging
from a2a import types
from a2a import utils
from a2a.server import agent_execution
from a2a.server import events
from a2a.server import tasks
from a2a.utils import errors as a2a_errors

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

import agent # Import your ADK agent
from google.adk import runners
from google.adk.artifacts import in_memory_artifact_service
from google.adk.memory import in_memory_memory_service
from google.adk.sessions import in_memory_session_service
from google.genai import types as genai_types

logger = logging.getLogger(__name__)

class AdkAgentToA2AExecutor(agent_execution.AgentExecutor):
  """An agent executor for ADK agents to make them A2A compatible."""

  _runner: runners.Runner

  def __init__(self):
    self._agent = agent.root_agent
    self._runner = runners.Runner(
        app_name=self._agent.name,
        agent=self._agent,
        session_service=in_memory_session_service.InMemorySessionService(),
        artifact_service=in_memory_artifact_service.InMemoryArtifactService(),
        memory_service=in_memory_memory_service.InMemoryMemoryService(),
    )
    self._user_id = "remote_agent"

  async def execute(
      self,
      context: agent_execution.RequestContext,
      event_queue: events.EventQueue,
  ) -> None:
    query = context.get_user_input()
    task = context.current_task
    logger.info("[DEBUG] Query: %s", query)

    if not task:
      if not context.message:
        return

      task = utils.new_task(context.message)
      await event_queue.enqueue_event(task)

    updater = tasks.TaskUpdater(event_queue, task.id, task.context_id)
    session_id = task.context_id

    session = await self._runner.session_service.get_session(
        app_name=self._agent.name,
        user_id=self._user_id,
        session_id=session_id,
    )
    if session is None:
      session = await self._runner.session_service.create_session(
          app_name=self._agent.name,
          user_id=self._user_id,
          state={},
          session_id=session_id,
      )

    # 1. Action and Context Extraction (Button clicks / userAction)
    action_context = {}
    action_query = None
    try:
      if hasattr(context, 'message') and context.message and hasattr(context.message, 'parts'):
        for part in context.message.parts:
          if hasattr(part, 'root') and hasattr(part.root, 'data'):
            data = part.root.data
            if hasattr(part.root, 'metadata') and part.root.metadata and part.root.metadata.get('mimeType') == 'application/json+a2ui':
              if isinstance(data, dict) and "data" in data:
                data = data["data"]
              action_data = None
              if isinstance(data, dict):
                if "action" in data:
                  action_data = data["action"]
                elif "userAction" in data:
                  action_data = data["userAction"]
              if isinstance(action_data, dict):
                if "event" in action_data and isinstance(action_data["event"], dict):
                  action_data = action_data["event"]
                ctx = action_data.get("context", {})
                if isinstance(ctx, dict):
                  if "message" in ctx:
                    action_query = ctx["message"]
                  action_context.update(ctx)
      if action_query:
        query = action_query
      for k, v in action_context.items():
        if k != 'message':
          session.state[k] = v
      state_vars = [f"{k}={v}" for k, v in session.state.items()]
      if state_vars:
        query = f"{query} [State: {', '.join(state_vars)}]"
        logger.info("[DEBUG] Injected state into query: %s", query)
    except Exception as e:
      logger.warning("Failed to extract action context: %s", e)

    await updater.start_work()

    content = genai_types.Content(
        role="user", parts=[{"text": query}]
    )

    final_response_content = ""

    try:
      async for event in self._runner.run_async(
          user_id=self._user_id, session_id=session.id, new_message=content
      ):
        if event.is_final_response():
          if (
              event.content
              and event.content.parts
              and event.content.parts[0].text
          ):
            final_response_content += event.content.parts[0].text

    except Exception as e:
      await updater.failed(
          message=utils.new_agent_text_message(
              f"Task failed with error: {str(e)}"
          )
      )
      return

    if not final_response_content:
        await updater.failed(
            message=utils.new_agent_text_message("No response generated.")
        )
        return

    # Yield the text response as a standard A2A TextPart
    parts = [types.Part(root=types.TextPart(text=final_response_content))]
    await updater.add_artifact(parts, name="response")
    await updater.complete()

  async def cancel(
      self,
      context: agent_execution.RequestContext,
      event_queue: events.EventQueue,
  ) -> None:
    raise a2a_errors.ServerError(error=types.UnsupportedOperationError())
```

## Step 2: Deploy Using Python SDK

Use the `vertexai.Client` to deploy your agent using the `A2aAgent` template.

Create a file named `deploy_ae.py` in your agent directory:

```python
import os
import vertexai
from vertexai.preview.reasoning_engines import A2aAgent
from vertexai.preview.reasoning_engines.templates.a2a import create_agent_card
from a2a.types import AgentSkill
from dotenv import load_dotenv
from google.genai import types

import agent_executor

def deploy():
    load_dotenv()
    
    project_id = os.environ.get("PROJECT_ID")
    location = os.environ.get("LOCATION") or "us-central1"
    storage = os.environ.get("STORAGE_BUCKET")
    
    vertexai.init(
        project=project_id,
        location=location,
        staging_bucket=storage,
    )

    # 1. Define Skills & Agent Card
    agent_skill = AgentSkill(
        id="your_agent_id",
        name="Your Agent Name",
        description="Description of your agent",
        tags=["Tag1", "Tag2"],
        examples=[
            "Example query 1",
            "Example query 2",
        ],
    )

    pp_agent_card = create_agent_card(
        agent_name="Your Agent Name",
        description="Description of your agent",
        skills=[agent_skill],
    )
    
    # 2. Instantiate local A2aAgent
    a2a_agent = A2aAgent(
        agent_card=pp_agent_card,
        agent_executor_builder=agent_executor.AdkAgentToA2AExecutor,
    )

    client = vertexai.Client(
        project=project_id,
        location=location,
        http_options=types.HttpOptions(api_version="v1beta1"),
    )

    # 3. Create Config
    config = {
        "display_name": "Your Agent Name",
        "description": "Description of your agent",
        "agent_framework": "google-adk",
        "staging_bucket": storage,
        "requirements": [
            "google-adk==1.28.1",
            "google-cloud-aiplatform[agent_engines,adk]==1.143.0",
            "a2a-sdk==0.3.22", # Match your local environment version
            "pydantic==2.12.5",
            "cloudpickle==3.1.2",
            "protobuf==6.33.6",
            "jsonschema==4.26.0",
        ],
        "http_options": {
            "api_version": "v1beta1",
        },
        "max_instances": 1,
        "extra_packages": [
            "agent_executor.py",
            "agent.py",
            "tools.py",
        ],
        "env_vars": {
            "NUM_WORKERS": "1",
        },
    }

    print("Spinning up fresh create instance...")
    remote_agent = client.agent_engines.create(agent=a2a_agent, config=config)
    print(f"✓ Agent created: {remote_agent.api_resource.name}")

if __name__ == "__main__":
    deploy()
```

## Step 3: Test the A2A Agent

To test the deployed A2A agent, you can send a raw HTTP POST request to the message endpoint. Note that the payload must match the exact Protobuf schema expected by the A2A server, which may differ from the Pydantic models in some versions.

Here is the working payload structure for `message/send`:

```json
{
  "request": {
    "message_id": "unique-msg-id",
    "role": "ROLE_USER",
    "content": [
      {
        "text": "Your message here"
      }
    ]
  },
  "configuration": {
    "blocking": true
  }
}
```

- Use `request` instead of `message` at the top level.
- Use `content` instead of `parts` inside the message object.
- Use `ROLE_USER` as the role string.
- Set `blocking: true` in configuration to wait for the agent's response synchronously.

## Troubleshooting

### 1. Requirement Incompatibility
Ensure that the version of `a2a-sdk` in your `requirements` list matches the version installed in your local environment. Mismatches can cause unpickling errors during deployment.

### 2. GCS Bucket Permissions
Ensure your user or service account has `storage.buckets.get` and `storage.objects.create` access to the staging bucket used for deployment.

### 3. Protobuf KeyError 'serialized'
If you encounter `KeyError: 'serialized'` in `google/protobuf/message.py` on Python 3.13, apply the following monkey-patch at the very top of your `agent_executor.py`:

```python
try:
    from google.protobuf.message import Message
    original_setstate = Message.__setstate__
    def patched_setstate(self, state):
        if 'serialized' not in state:
             state['serialized'] = b''
        return original_setstate(self, state)
    Message.__setstate__ = patched_setstate
except Exception as e:
    pass
```
