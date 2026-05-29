import json, logging, re
from a2a import types, utils
from a2a.server import agent_execution, events, tasks
from google.adk import runners
from google.adk.sessions import in_memory_session_service
from google.genai import types as genai_types
from agent import root_agent

logger = logging.getLogger(__name__)

class AdkAgentToA2AExecutor(agent_execution.AgentExecutor):
    def __init__(self):
        self._runner = runners.Runner(
            app_name="A2UIAgent",
            agent=root_agent,
            session_service=in_memory_session_service.InMemorySessionService(),
        )

    async def execute(self, context: agent_execution.RequestContext, event_queue: events.EventQueue) -> None:
        query = context.get_user_input()
        task = context.current_task
        session_id = context.context_id or (task.context_id if task else "default")
        
        # 1. SESSION RECOVERY: Extract state from A2UI payload
        try:
            if hasattr(context, 'message') and context.message:
                for part in context.message.parts:
                    if hasattr(part, 'root') and hasattr(part.root, 'data'):
                        data = part.root.data
                        if isinstance(data, dict) and 'userAction' in data:
                            action_ctx = data['userAction'].get('context', {})
                            query = action_ctx.get('message', query)
                            # Recover Form Inputs
                            for item in data['userAction'].get('inputs', []):
                                if item.get('id'): context.metadata[item['id']] = item['value']
        except Exception as e: logger.warning(f"Recovery failed: {e}")

        # 2. STATE INJECTION: Persist state via prompt (Transcript Echoing)
        state_str = "|".join([f"{k}={v}" for k, v in context.metadata.items()])
        if state_str: query = f"{query} [State: {state_str}]"

        # 3. EXECUTION: Run ADK Runner with correct types
        updater = tasks.TaskUpdater(event_queue, task.id, task.context_id)
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
