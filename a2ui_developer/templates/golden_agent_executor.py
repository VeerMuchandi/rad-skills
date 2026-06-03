import json, logging, re, sys
import google.protobuf.json_format as json_format
from a2a import types, utils
from a2a.server import agent_execution, events, tasks
from google.adk import runners
from google.adk.sessions import in_memory_session_service
from google.genai import types as genai_types
try:
    from .agent import root_agent
except ImportError:
    from agent import root_agent

logger = logging.getLogger(__name__)

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
                if "content" in d and isinstance(d["content"], list):
                    for part in d["content"]:
                        if isinstance(part, dict) and "data" in part:
                            part_data = part["data"]
                            if isinstance(part_data, dict) and "data" not in part_data:
                                part["data"] = {"data": part_data}
                for k, v in list(d.items()):
                    if isinstance(v, dict):
                        fix_a2a_payload(v)
                    elif isinstance(v, list):
                        for item in v:
                            if isinstance(item, dict):
                                fix_a2a_payload(item)
                return d
                
            fixed_data = fix_a2a_payload(data)
            text = json.dumps(fixed_data)
        except Exception as e:
            logger.warning(f"Patched Parse failed to preprocess A2A payload: {e}")
            
    return original_parse(text, message, *args, **kwargs)

def apply_monkey_patch():
    json_format.Parse = patched_parse
    # Also patch directly in rest_handler if imported/importable
    try:
        import a2a.server.request_handlers.rest_handler as rest_handler
        rest_handler.Parse = patched_parse
        logger.info("Successfully patched rest_handler.Parse")
    except Exception as ex:
        logger.warning(f"Could not import rest_handler during patch: {ex}")
    # Propagate patched parser to already-loaded A2A modules
    for mod_name, mod in list(sys.modules.items()):
        if mod and mod_name.startswith('a2a') and hasattr(mod, 'Parse'):
            try:
                mod.Parse = patched_parse
            except:
                pass

apply_monkey_patch()


class AdkAgentToA2AExecutor(agent_execution.AgentExecutor):
    def __init__(self):
        apply_monkey_patch()
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
        
        # Accumulate recovered metadata keys.
        # RequestContext.metadata properties return transient dictionaries when underlying _params.metadata is None.
        metadata_dict = {}
        if hasattr(context, 'metadata') and context.metadata:
            try:
                metadata_dict.update(context.metadata)
            except:
                pass
        
        # 1. SESSION RECOVERY: Extract state from A2UI payload
        try:
            if hasattr(context, 'message') and context.message:
                parts = []
                if hasattr(context.message, 'parts'):
                    parts = context.message.parts
                elif isinstance(context.message, dict):
                    parts = context.message.get('parts', [])
                
                for part in parts:
                    data = None
                    if hasattr(part, 'data') and part.data:
                        data = part.data
                    elif isinstance(part, dict) and 'data' in part:
                        data = part['data']
                    elif hasattr(part, 'root') and hasattr(part.root, 'data'):
                        data = part.root.data
                        
                    if data:
                        # Convert protobuf Struct to dict if it's a Protobuf message
                        if not isinstance(data, dict):
                            try:
                                from google.protobuf.json_format import MessageToDict
                                data = MessageToDict(data)
                            except Exception as ex:
                                logger.warning(f"Struct conversion failed: {ex}")
                                
                        if isinstance(data, dict) and 'data' in data:
                            data = data['data']
                        if isinstance(data, dict) and 'userAction' in data:
                            user_action = data['userAction']
                            action_ctx = user_action.get('context', {})
                            query = action_ctx.get('message', query)
                            # Recover Form Inputs
                            for item in user_action.get('inputs', []):
                                if item.get('id'): 
                                    metadata_dict[item['id']] = item['value']
                            # Also recover directly from context keys (e.g. for remote_tester compatibility)
                            for k, v in action_ctx.items():
                                if k != 'message':
                                    path_key = f"/trip/{k}" if not k.startswith('/') else k
                                    metadata_dict[path_key] = v
                            
                            # Server-side address syncing for Same as starting address checkbox
                            if metadata_dict.get('/trip/same_as_start') is True or metadata_dict.get('same_as_start') is True:
                                start_val = metadata_dict.get('/trip/start_location') or metadata_dict.get('start_location')
                                if start_val:
                                    metadata_dict['/trip/end_location'] = start_val
                                    metadata_dict['end_location'] = start_val
        except Exception as e: logger.warning(f"Recovery failed: {e}")

        # Write metadata back to context._params so it persists in RequestContext
        if hasattr(context, '_params') and context._params:
            context._params.metadata = metadata_dict
        elif hasattr(context, 'metadata') and hasattr(context.metadata, 'update'):
            try:
                context.metadata.update(metadata_dict)
            except:
                pass

        # Get or create runner session to directly populate session state (mirroring local tester behavior)
        try:
            service = self._runner.session_service
            # Direct storage modification for InMemorySessionService
            if hasattr(service, 'sessions'):
                app_sessions = service.sessions.setdefault("A2UIAgent", {})
                user_sessions = app_sessions.setdefault("user", {})
                if session_id not in user_sessions:
                    from google.adk.sessions.session import Session
                    import time
                    user_sessions[session_id] = Session(
                        app_name="A2UIAgent",
                        user_id="user",
                        id=session_id,
                        state={},
                        last_update_time=time.time(),
                    )
                # Mutate the state of the session directly in the service storage
                for k, v in metadata_dict.items():
                    key = k.replace('/trip/', '').replace('/', '')
                    user_sessions[session_id].state[key] = v
                logger.info(f"[DEBUG] Mutated storage session state directly: {user_sessions[session_id].state}")
            
            # Fallback for get_session / update_session for other implementations
            session = await service.get_session(
                app_name="A2UIAgent",
                user_id="user",
                session_id=session_id,
            )
            if session:
                state = session.state if session.state else {}
                for k, v in metadata_dict.items():
                    key = k.replace('/trip/', '').replace('/', '')
                    state[key] = v
                session.state = state
                if hasattr(service, 'update_session'):
                    await service.update_session(session)
                logger.info(f"[DEBUG] Successfully injected session state into copy of runner: {state}")
        except Exception as e:
            logger.warning(f"Session injection failed: {e}", exc_info=True)

        # 2. STATE INJECTION: Persist state via prompt (Transcript Echoing)
        state_parts = []
        for k, v in metadata_dict.items():
            # Clean A2UI path prefixes (like '/trip/') to leave raw parameter names
            key = k.replace('/trip/', '').replace('/', '')
            state_parts.append(f"[State: {key}={v}]")
        if state_parts:
            query = f"{query} " + " ".join(state_parts)

        # 3. EXECUTION: Run ADK Runner with correct types
        updater = tasks.TaskUpdater(event_queue, task_id, context_id)
        await updater.start_work()
        
        full_text = ""
        async for event in self._runner.run_async(
            user_id="user", 
            session_id=session_id, 
            new_message=genai_types.Content(parts=[genai_types.Part(text=query)])
        ):
            if event.content and event.content.parts:
                for p in event.content.parts:
                    if hasattr(p, 'text') and p.text:
                        full_text += p.text

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
