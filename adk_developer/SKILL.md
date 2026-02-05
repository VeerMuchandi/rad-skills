---
name: ADK Developer
description: Comprehensive guide to building, orchestrating, and deploying agents with the Google Agent Development Kit (ADK).
---

# ADK Developer Skill

This document serves as a long-form, comprehensive reference for building, orchestrating, and deploying AI agents using the Python Agent Development Kit (ADK). It covers every significant aspect with detailed code examples and in-depth best practices.


## 0. Skill Initialization
**CRITICAL**: This skill relies on local reference documentation that must be kept in sync with the official repository.

**When starting a new session or tasks involving ADK:**
1.  **Ask Permission**: "Shall I check for updates to the ADK references from the official global cache?"
2.  **Execute Update**: If the user agrees, run:
    ```bash
    python3 ~/.gemini/jetski/skills/adk_developer/scripts/update_skill.py
    ```
3.  **Confirm**: Report the update status before proceeding.

## 1. Golden Rules for ADK Development
> [!IMPORTANT]
> 1.  **Always use Vertex AI**: Set `GOOGLE_GENAI_USE_VERTEXAI=True`.
> 2.  **Configuration**: Ask for `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` from the user.
> 3.  **Models**: Use `gemini-2.5-flash` or higher. **NEVER** use `gemini-1.5-flash` or `gemini-1.5-pro`.
> 4.  **Directory Structure**: **NEVER** put code in the root folder. Always create specific agent subfolders (e.g., `my_agent/`).
> 5.  **Simplicity First**: **ALWAYS** start with a single `LlmAgent`. Only introduce Workflow/Multi-Agent architectures if the task complexity specifically demands it (e.g., rigid determinism, context limits). Do not over-engineer.
> 6.  **Process Boundaries**: When asked to **Design**, produce the design artifact and **STOP**. Do not implement code until explicitly requested.
> 7.  **Configuration Protocol**: **NEVER** assume values for `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, or other secrets. **ALWAYS** ask the user for these values before creating configuration files.

## Table of Contents

1.  [Core Concepts & Project Structure](#1-core-concepts--project-structure)
2.  [Agent Definitions (`LlmAgent`)](#2-agent-definitions-llmagent)
3.  [Orchestration with Workflow Agents](#3-orchestration-with-workflow-agents)
4.  [Multi-Agent Systems & Communication](#4-multi-agent-systems--communication)
5.  [Building Custom Agents (`BaseAgent`)](#5-building-custom-agents-baseagent)
6.  [Models: Gemini, LiteLLM, and Vertex AI](#6-models-gemini-litellm-and-vertex-ai)
7.  [Tools: The Agent's Capabilities](#7-tools-the-agents-capabilities)
8.  [Context, State, and Memory Management](#8-context-state-and-memory-management)
9.  [Runtime, Events, and Execution Flow](#9-runtime-events-and-execution-flow)
10. [Control Flow with Callbacks](#10-control-flow-with-callbacks)
11. [Authentication for Tools](#11-authentication-for-tools)
12. [Deployment Strategies](#12-deployment-strategies)
13. [Evaluation and Safety](#13-evaluation-and-safety)
14. [Debugging, Logging & Observability](#14-debugging-logging--observability)
15. [Streaming & Advanced I/O](#15-streaming--advanced-io)
16. [Performance Optimization](#16-performance-optimization)
17. [General Best Practices & Common Pitfalls](#17-general-best-practices--common-pitfalls)
18. [Official API & CLI References](#18-official-api--cli-references)

---

## 1. Core Concepts & Project Structure

### 1.1 ADK's Foundational Principles

*   **Modularity**: Break down complex problems into smaller, manageable agents and tools.
*   **Composability**: Combine simple agents and tools to build sophisticated systems.
*   **Observability**: Detailed event logging and tracing capabilities to understand agent behavior.
*   **Extensibility**: Easily integrate with external services, models, and frameworks.
*   **Deployment-Agnostic**: Design agents once, deploy anywhere.

### 1.2 Essential Primitives

*   **`Agent`**: The core intelligent unit. Can be `LlmAgent` (LLM-driven) or `BaseAgent` (custom/workflow).
*   **`Tool`**: Callable function/class providing external capabilities (`FunctionTool`, `OpenAPIToolset`, etc.).
*   **`Session`**: A unique, stateful conversation thread with history (`events`) and short-term memory (`state`).
*   **`State`**: Key-value dictionary within a `Session` for transient conversation data.
*   **`Memory`**: Long-term, searchable knowledge base beyond a single session (`MemoryService`).
*   **`Artifact`**: Named, versioned binary data (files, images) associated with a session or user.
*   **`Runner`**: The execution engine; orchestrates agent activity and event flow.
*   **`Event`**: Atomic unit of communication and history; carries content and side-effect `actions`.
*   **`InvocationContext`**: The comprehensive root context object holding all runtime information for a single `run_async` call.

### 1.3 Standard Project Layout

A well-structured ADK project is crucial for maintainability and leveraging `adk` CLI tools.

```text
your_project_root/
├── my_first_agent/             # Each folder is a distinct agent app
│   ├── __init__.py             # Makes `my_first_agent` a Python package (`from . import agent`)
│   ├── agent.py                # Contains `root_agent` definition and `LlmAgent`/WorkflowAgent instances
│   ├── tools.py                # Custom tool function definitions
│   ├── data/                   # Optional: static data, templates
│   └── .env                    # Environment variables (API keys, project IDs)
├── my_second_agent/
│   ├── __init__.py
│   └── agent.py
├── requirements.txt            # Project's Python dependencies (e.g., google-adk, litellm)
├── tests/                      # Unit and integration tests
│   ├── unit/
│   │   └── test_tools.py
│   └── integration/
│       └── test_my_first_agent.py
│       └── my_first_agent.evalset.json # Evaluation dataset for `adk eval`
└── main.py                     # Optional: Entry point for custom FastAPI server deployment
```
*   `adk web` and `adk run` automatically discover agents in subdirectories with `__init__.py` and `agent.py`.
*   `.env` files are automatically loaded by `adk` tools when run from the root or agent directory.

### 1.A Build Agents without Code (Agent Config)

ADK allows you to define agents, tools, and even multi-agent workflows using a simple YAML format.

#### **Core Agent Config Structure**

*   **Basic Agent (`root_agent.yaml`)**:
    ```yaml
    # yaml-language-server: $schema=https://raw.githubusercontent.com/google/adk-python/refs/heads/main/src/google/adk/agents/config_schemas/AgentConfig.json
    name: assistant_agent
    model: gemini-2.5-flash
    description: A helper agent that can answer users' various questions.
    instruction: You are an agent to help answer users' various questions.
    ```

*   **Loading Agent Config in Python**:
    ```python
    from google.adk.agents import config_agent_utils
    root_agent = config_agent_utils.from_config("{agent_folder}/root_agent.yaml")
    ```

---

## 2. Agent Definitions (`LlmAgent`)

The `LlmAgent` is the cornerstone of intelligent behavior, leveraging an LLM for reasoning and decision-making.

### 2.1 Basic `LlmAgent` Setup

```python
from google.adk.agents import Agent

def get_current_time(city: str) -> dict:
    """Returns the current time in a specified city."""
    # Mock implementation
    if city.lower() == "new york":
        return {"status": "success", "time": "10:30 AM EST"}
    return {"status": "error", "message": f"Time for {city} not available."}

my_first_llm_agent = Agent(
    name="time_teller_agent",
    model="gemini-2.5-flash", # Essential: The LLM powering the agent
    instruction="You are a helpful assistant that tells the current time in cities. Use the 'get_current_time' tool for this purpose.",
    description="Tells the current time in a specified city.", # Crucial for multi-agent delegation
    tools=[get_current_time] # List of callable functions/tool instances
)
```

### 2.2 Advanced `LlmAgent` Configuration

*   **`generate_content_config`**: Controls LLM generation parameters (temperature, token limits, safety).
    ```python
    from google.genai import types as genai_types
    from google.adk.agents import Agent

    gen_config = genai_types.GenerateContentConfig(
        temperature=0.2,            # Controls randomness (0.0-1.0), lower for more deterministic.
        top_p=0.9,                  # Nucleus sampling: sample from top_p probability mass.
        top_k=40,                   # Top-k sampling: sample from top_k most likely tokens.
        max_output_tokens=1024,     # Max tokens in LLM's response.
        stop_sequences=["## END"]   # LLM will stop generating if these sequences appear.
    )
    agent = Agent(
        # ... basic config ...
        generate_content_config=gen_config
    )
    ```

*   **`input_schema` & `output_schema`**: Define strict JSON input/output formats using Pydantic models.
    > **Warning**: Using `output_schema` forces the LLM to generate JSON and **disables** its ability to use tools or delegate to other agents.

#### **Example: Defining and Using Structured Output**

This is the most reliable way to make an LLM produce predictable, parseable JSON, which is essential for multi-agent workflows.

1.  **Define the Schema with Pydantic:**
    ```python
    from pydantic import BaseModel, Field
    from typing import Literal

    class SearchQuery(BaseModel):
        """Model representing a specific search query for web search."""
        search_query: str = Field(
            description="A highly specific and targeted query for web search."
        )

    class Feedback(BaseModel):
        """Model for providing evaluation feedback on research quality."""
        grade: Literal["pass", "fail"] = Field(
            description="Evaluation result. 'pass' if the research is sufficient, 'fail' if it needs revision."
        )
        comment: str = Field(
            description="Detailed explanation of the evaluation, highlighting strengths and/or weaknesses of the research."
        )
        follow_up_queries: list[SearchQuery] | None = Field(
            default=None,
            description="A list of specific, targeted follow-up search queries needed to fix research gaps. This should be null or empty if the grade is 'pass'."
        )
    ```

2.  **Assign the Schema to an `LlmAgent`:**
    ```python
    research_evaluator = LlmAgent(
        name="research_evaluator",
        model="gemini-2.5-pro",
        instruction="""
        You are a meticulous quality assurance analyst. Evaluate the research findings in 'section_research_findings' and be very critical.
        If you find significant gaps, assign a grade of 'fail', write a detailed comment, and generate 5-7 specific follow-up queries.
        If the research is thorough, grade it 'pass'.
        Your response must be a single, raw JSON object validating against the 'Feedback' schema.
        """,
        output_schema=Feedback, # This forces the LLM to output JSON matching the Feedback model.
        output_key="research_evaluation", # The resulting JSON object will be saved to state.
        disallow_transfer_to_peers=True, # Prevents this agent from delegating. Its job is only to evaluate.
    )
    ```

### 2.3 LLM Instruction Crafting (`instruction`)

The `instruction` is critical. It guides the LLM's behavior, persona, and tool usage.

**Example 1: Constraining Tool Use and Output Format**
```python
import datetime
from google.adk.tools import google_search   

plan_generator = LlmAgent(
    model="gemini-2.5-flash",
    name="plan_generator",
    description="Generates a 4-5 line action-oriented research plan.",
    instruction=f"""
    You are a research strategist. Your job is to create a high-level RESEARCH PLAN, not a summary.
    **RULE: Your output MUST be a bulleted list of 4-5 action-oriented research goals or key questions.**
    - A good goal starts with a verb like "Analyze," "Identify," "Investigate."
    - A bad output is a statement of fact like "The event was in April 2024."
    **TOOL USE IS STRICTLY LIMITED:**
    Your goal is to create a generic, high-quality plan *without searching*.
    Only use `google_search` if a topic is ambiguous and you absolutely cannot create a plan without it.
    You are explicitly forbidden from researching the *content* or *themes* of the topic.
    Current date: {datetime.datetime.now().strftime("%Y-%m-%d")}
    """,
    tools=[google_search],
)
```

---

## 3. Orchestration with Workflow Agents

Workflow agents (`SequentialAgent`, `ParallelAgent`, `LoopAgent`) provide deterministic control flow, combining LLM capabilities with structured execution.

### 3.1 `SequentialAgent`: Linear Execution

Executes `sub_agents` one after another in the order defined. The `InvocationContext` is passed along, allowing state changes to be visible to subsequent agents.

```python
from google.adk.agents import SequentialAgent, Agent

document_pipeline = SequentialAgent(
    name="SummaryQuestionPipeline",
    sub_agents=[summarizer, question_generator], # Order matters!
    description="Summarizes a document then generates questions."
)
```

### 3.2 `ParallelAgent`: Concurrent Execution

Executes `sub_agents` simultaneously. Useful for independent tasks to reduce overall latency. All sub-agents share the same `session.state`.

### 3.3 `LoopAgent`: Iterative Processes

Repeatedly executes its `sub_agents` (sequentially within each loop iteration) until a condition is met or `max_iterations` is reached.

**Termination**: The loop stops if `max_iterations` is reached OR any sub-agent yields an event with `actions.escalate = True`.


### 3.4 The "Sandwich" Pattern (Intake-Process-Handoff)

**CRITICAL ARCHITECTURE RULE**: When using `SequentialAgent` or other deterministic workflows, **never** start the workflow until all required information is collected.

**The Pattern**:
1.  **Intake Agent (`LlmAgent`)**:
    *   **Role**: Interactive User Interface.
    *   **Task**: Converses with the user to collect all necessary variables (arguments).
    *   **Output**: Writes valid data to `session.state`.
    *   **Transition**: Only transfers to the Workflow Agent when validation passes.
2.  **Workflow Agent (`SequentialAgent`)**:
    *   **Role**: Headless Execution.
    *   **Task**: Reads `session.state`, executes tools/sub-agents, writes results to `session.state`.
    *   **Constraint**: **NEVER** ask the user questions here. Logic must be deterministic.
3.  **Handoff Agent (`LlmAgent`)**:
    *   **Role**: Result Presentation & Follow-up.
    *   **Task**: Informative summary of the workflow's output. Handles "What next?" questions.

**Example Structure**:
```python
main_orchestrator = LlmAgent(
    name="MainApp",
    description="Orchestrator for the entire application.",
    instruction="""You are the main coordinator. 
    1. First, transfer to `intake_agent` to gather the user's requirements.
    2. Once `intake_agent` finishes and details are saved, transfer to `research_workflow` to process the data in the background. DO NOT do this yourself.
    3. After the workflow completes, transfer to `presenter_agent` to share the results with the user.
    """,
    sub_agents=[
        intake_agent,      # Interactive: "What city do you want to research?"
        research_workflow, # Headless: SequentialAgent[Search, Scrape, Summarize] -> writes to state['summary']
        presenter_agent    # Interactive: "Here is the summary for {city}. Any questions?"
    ]
)
```

---

## 4. Multi-Agent Systems & Communication

### 4.1 Agent Hierarchy

A hierarchical (tree-like) structure of parent-child relationships defined by the `sub_agents` parameter.

### 4.2 Inter-Agent Communication Mechanisms

1.  **Shared Session State (`session.state`)**: The most common and robust method. Agents read from and write to the same mutable dictionary.
2.  **LLM-Driven Delegation (`transfer_to_agent`)**: A `LlmAgent` can dynamically hand over control to another agent based on its reasoning.
3.  **Explicit Invocation (`AgentTool`)**: An `LlmAgent` can treat another `BaseAgent` instance as a callable tool.

### 4.A. Distributed Communication (A2A Protocol)

The Agent-to-Agent (A2A) Protocol enables agents to communicate over a network, even if they are written in different languages or run as separate services.

*   **Exposing an Agent**:
    ```python
    from google.adk.a2a.utils.agent_to_a2a import to_a2a
    # root_agent is your existing ADK Agent instance
    a2a_app = to_a2a(root_agent, port=8001)
    ```
*   **Consuming a Remote Agent**:
    ```python
    from google.adk.a2a.remote_a2a_agent import RemoteA2aAgent
    prime_checker_agent = RemoteA2aAgent(
        name="prime_agent",
        description="A remote agent that checks if numbers are prime.",
        agent_card="http://localhost:8001/a2a/check_prime_agent/.well-known/agent.json"
    )
    ```

---

## 5. Building Custom Agents (`BaseAgent`)

For unique orchestration logic that doesn't fit standard workflow agents, inherit directly from `BaseAgent`.

### 5.2 Implementing `_run_async_impl`

```python
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from typing import AsyncGenerator
import logging

class EscalationChecker(BaseAgent):
    """Checks research evaluation and escalates to stop the loop if grade is 'pass'."""

    def __init__(self, name: str):
        super().__init__(name=name)

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        # 1. Read from session state.
        evaluation_result = ctx.session.state.get("research_evaluation")

        # 2. Apply custom Python logic.
        if evaluation_result and evaluation_result.get("grade") == "pass":
            logging.info(f"[{self.name}] Research passed. Escalating to stop loop.")
            # 3. Yield an Event with a control Action.
            yield Event(author=self.name, actions=EventActions(escalate=True))
        else:
            logging.info(f"[{self.name}] Research failed or not found. Loop continues.")
            # Yielding an event without actions lets the flow continue.
            yield Event(author=self.name)
```

---

## 6. Models: Gemini, LiteLLM, and Vertex AI

ADK's model flexibility allows integrating various LLMs for different needs.

### 6.1 Google Gemini Models (AI Studio & Vertex AI)

**Note:** Always use `GOOGLE_GENAI_USE_VERTEXAI=True`. Ask for `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` from the user. Use `gemini-2.5-flash` or higher model.

*   **Vertex AI (Production)**:
    *   Authenticate via `gcloud auth application-default login` (recommended).
    *   Set `GOOGLE_CLOUD_PROJECT="YOUR_PROJECT_ID"`, `GOOGLE_CLOUD_LOCATION="your-region"` (environment variables).
    *   Set `GOOGLE_GENAI_USE_VERTEXAI="True"`.

### 6.2 Other Cloud & Proprietary Models via LiteLLM

`LiteLlm` provides a unified interface to 100+ LLMs (OpenAI, Anthropic, Cohere, etc.).

```python
from google.adk.models.lite_llm import LiteLlm
agent_openai = Agent(model=LiteLlm(model="openai/gpt-4o"), ...)
```

---

## 7. Tools: The Agent's Capabilities

Tools extend an agent's abilities beyond text generation.

### 7.1 Defining Function Tools: Principles & Best Practices

*   **Signature**: `def my_tool(param1: Type, param2: Type, tool_context: ToolContext) -> dict:`
*   **Parameters**: Clear names, required type hints, **NO DEFAULT VALUES**.
*   **Return Type**: **Must** be a `dict` (JSON-serializable).
*   **Docstring**: **CRITICAL**. Explain purpose, when to use, arguments, and return value structure. **AVOID** mentioning `tool_context` in docstring.

### 7.3 All Tool Types & Their Usage

1.  **Custom Function Tools**: `FunctionTool`, `LongRunningFunctionTool`, `AgentTool`.
2.  **Built-in Tools**: `google_search`, `BuiltInCodeExecutor`, `VertexAiSearchTool`, `BigQueryToolset`.
3.  **Third-Party Tool Wrappers**: `LangchainTool`, `CrewaiTool`.
4.  **OpenAPI & Protocol Tools**: `OpenAPIToolset`, `MCPToolset`.
5.  **Google Cloud Tools**: `ApiHubToolset`, `ApplicationIntegrationToolset`.

---

## 8. Context, State, and Memory Management

### 8.2 `State`: The Conversational Scratchpad

A mutable dictionary within `session.state` for short-term, dynamic data.

*   **Update Mechanism**: Always update via `context.state` (in callbacks/tools) or `LlmAgent.output_key`.
*   **Prefixes for Scope**:
    *   **(No prefix)**: Session-specific (e.g., `session.state['booking_step']`).
    *   `user:`: Persistent for a `user_id` across all their sessions.
    *   `app:`: Persistent for `app_name` across all users and sessions.
    *   `temp:`: Volatile, for the current `Invocation` turn only.

---

## 9. Runtime, Events, and Execution Flow

### 9.2 The Event Loop: Core Execution Flow

1.  User input becomes a `user` `Event`.
2.  `Runner` calls `agent.run_async(invocation_context)`.
3.  Agent `yield`s an `Event` (e.g., tool call, text response). Execution pauses.
4.  `Runner` processes the `Event` (applies state changes, etc.) and yields it to the client.
5.  Execution resumes. This cycle repeats until the agent is done.

### 9.3 `Event` Object: The Communication Backbone

*   `Event.author`: Source of the event (`'user'`, agent name, `'system'`).
*   `Event.content`: The primary payload (text, function calls, function responses).
*   `Event.actions`: Signals side effects (`state_delta`, `transfer_to_agent`, `escalate`).
*   `Event.is_final_response()`: Helper to identify the complete, displayable message.

---

## 10. Control Flow with Callbacks

Callbacks are functions that intercept and control agent execution at specific points.

### 10.2 Types of Callbacks

1.  **Agent Lifecycle**: `before_agent_callback`, `after_agent_callback`.
2.  **LLM Interaction**: `before_model_callback`, `after_model_callback`.
3.  **Tool Execution**: `before_tool_callback`, `after_tool_callback`.

### 10.3 Callback Best Practices

**Example 2: Output Transformation with `after_agent_callback`**
This callback takes an LLM's raw output (containing custom tags), uses Python to format it into markdown, and returns the modified content, overriding the original.

```python
import re
from google.adk.agents.callback_context import CallbackContext
from google.genai import types as genai_types

def citation_replacement_callback(callback_context: CallbackContext) -> genai_types.Content:
    """Replaces <cite> tags in a report with Markdown-formatted links."""
    # 1. Get raw report and sources from state.
    final_report = callback_context.state.get("final_cited_report", "")
    sources = callback_context.state.get("sources", {})

    # 2. Define a replacer function for regex substitution.
    def tag_replacer(match: re.Match) -> str:
        short_id = match.group(1)
        if not (source_info := sources.get(short_id)):
            return "" # Remove invalid tags
        title = source_info.get("title", short_id)
        return f" [{title}]({source_info['url']})"

    # 3. Use regex to find all <cite> tags and replace them.
    processed_report = re.sub(
        r'<cite\s+source\s*=\s*["\']?(src-\d+)["\']?\s*/>',
        tag_replacer,
        final_report,
    )
    processed_report = re.sub(r"\s+([.,;:])", r"\1", processed_report) # Fix spacing

    # 4. Save the new version to state and return it to override the original agent output.
    callback_context.state["final_report_with_citations"] = processed_report
    return genai_types.Content(parts=[genai_types.Part(text=processed_report)])
```

---

## 11. Authentication for Tools

### 11.2 Interactive OAuth/OIDC Flows

When a tool requires user interaction (OAuth consent), ADK pauses and signals your `Agent Client` application.

1.  **Detect Auth Request**: `runner.run_async()` yields an event with a special `adk_request_credential` function call.
2.  **Redirect User**: Extract `auth_uri` from `auth_config` in the event. Redirect user's browser.
3.  **Send Auth Result to ADK**: Your client prepares a `FunctionResponse` for `adk_request_credential` with the captured callback URL.
4.  **Resume Execution**: `runner.run_async()` is called again with this `FunctionResponse`.

---

## 12. Deployment Strategies

### 12.1 Local Development

*   **`adk web`**: Launches a local web UI. **CRITICAL**: Do not pass the agent folder name to this command (e.g., `adk web my_agent` is WRONG). Just run `adk web` from the project root; it will automatically discover available agents.
*   **`adk run`**: Command-line interactive chat.
    *   **Automated Replay Testing (Non-Interactive)**: To test an agent non-interactively with a predefined sequence of queries, use the `--replay` flag:
        ```bash
        adk run <agent_path> --replay <json_file_path>
        ```
        The JSON file must conform to this schema:
        ```json
        {
          "state": {},
          "queries": [
            "User prompt step 1",
            "User prompt step 2"
          ]
        }
        ```
*   **`adk api_server`**: Launches a local FastAPI server exposing `/run`, `/run_sse`, etc.

### 12.2 Vertex AI Agent Engine

Fully managed, scalable service for ADK agents on Google Cloud.

```python
from vertexai.preview import reasoning_engines

# Wrap your root_agent for deployment
app_for_engine = reasoning_engines.AdkApp(agent=root_agent, enable_tracing=True)

# Deploy
remote_app = agent_engines.create(
    agent_engine=app_for_engine,
    requirements=["google-cloud-aiplatform[adk,agent_engines]"],
    display_name="My Production Agent"
)
```

### 12.3 Cloud Run

Serverless container platform.

*   ADK CLI: `adk deploy cloud_run --project <id> --region <loc> ... /path/to/agent`

---

## 13. Evaluation and Safety

### 13.1 Agent Evaluation (`adk eval`)

Systematically assess agent performance using `eval_cases` defined in `.evalset.json`.

```json
{
  "eval_set_id": "weather_bot_eval",
  "eval_cases": [
    {
      "eval_id": "london_weather_query",
      "conversation": [
        {
          "user_content": {"parts": [{"text": "What's the weather in London?"}]},
          "final_response": {"parts": [{"text": "The weather in London is cloudy..."}]},
          "intermediate_data": {
            "tool_uses": [{"name": "get_weather", "args": {"city": "London"}}]
          }
        }
      ],
      "session_input": {"app_name": "weather_app", "user_id": "test_user", "state": {}}
    }
  ]
}
```

### 13.2 Safety & Guardrails

1.  **Identity**: Use User-Auth (OAuth) for tracing actions to users.
2.  **In-Tool Guardrails**: Validate model-provided arguments before execution.
3.  **Built-in Gemini Safety**: Content Safety Filters.
4.  **Sandboxed Code Execution**: Use `BuiltInCodeExecutor`.

---

## 14. Debugging, Logging & Observability

*   **`adk web` UI**: Visual trace inspector.
*   **Event Stream Logging**: Iterate `runner.run_async()` events and print relevant fields.
*   **Observability Integrations**: Supports OpenTelemetry.

---

## 15. Streaming & Advanced I/O

*   **Bidirectional Streaming**: Enables low-latency, two-way data flow (text, audio, video).
*   **Streaming Tools**: Must be an `async` function with a return type of `AsyncGenerator`.
*   **Advanced I/O**: Supports Audio (`audio/pcm`) and Vision (`image/jpeg`, `video/mp4`) inputs.

---

## 16. Performance Optimization

*   **Model Selection**: Choose the smallest model that meets requirements.
*   **Instruction Prompt Engineering**: Concise, clear instructions.
*   **Tool Use Optimization**: Design efficient tools.
*   **`include_contents='none'`**: For stateless utility agents.
*   **Streaming**: Use `StreamingMode.SSE` or `BIDI`.

---

## 17. General Best Practices & Common Pitfalls

*   **Start Simple**: Begin with `LlmAgent` and mock tools.
*   **Dependency Management**: Use `requirements.txt`.
*   **Secrets Management**: Never hardcode API keys. Use `.env`.
*   **Avoid Infinite Loops**: Use `max_iterations` and `max_llm_calls`.
*   **Testing**: Implement robust `try...except` blocks in tools and callbacks.

### Testing the output of an agent

The following script demonstrates how to programmatically test an agent's output.

```python
import asyncio
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from app.agent import root_agent
from google.genai import types as genai_types

async def main():
    """Runs the agent with a sample query."""
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name="app", user_id="test_user", session_id="test_session"
    )
    runner = Runner(
        agent=root_agent, app_name="app", session_service=session_service
    )
    query = "I want a recipe for pancakes"
    async for event in runner.run_async(
        user_id="test_user",
        session_id="test_session",
        new_message=genai_types.Content(
            role="user", 
            parts=[genai_types.Part.from_text(text=query)]
        ),
    ):
        if event.is_final_response():
            print(event.content.parts[0].text)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 18. Official API & CLI References

*   [Python API Reference](./api-reference/python/index.html)
*   [CLI Reference](./api-reference/cli/index.html)
*   [REST API Reference](./api-reference/rest/index.md)

---

## 19. Lessons Learned & Field Patterns

Real-world insights from deploying ADK agents.

### 19.1 Strict Browser Verification
**Context**: When testing E2E with `adk web` or browser automation.
*   **Problem**: Scripts often fail because they click before the UI is ready.
*   **Solution**: **Verify before interaction**.
    *   *Bad*: Type query -> Wait 2s -> Click "Select".
    *   *Good*: Type query -> Wait 5s -> **Assert** "Plan list" is visible -> Click "Select".

### 19.2 Tool Dependency Audits
**Context**: Migrating tools between agents.
*   **Problem**: Copying `tools.py` often misses external file dependencies (e.g., `data.json`).
*   **Solution**: Grep tool code for `open()`, `read()`, or `load()` to identify and copy required assets.

### 19.3 Hybrid Chat "Text-First" Rule
**Context**: Combining Conversational UI with A2UI.
*   **Rule**: Always stream **Text** before **JSON Payload**.
*   **Why**: Maintains conversational flow. Users see "Here are the plans:" (Text) immediately, while the complex "Plan Card" (JSON) renders milliseconds later.
*   **Implementation**: Enforce this in your system instructions and few-shot examples.

### 19.4 Avoid Premature Complexity
**Context**: Designing new agent architectures.
*   **Problem**: defaulting to multi-agent/sequential chains (like the "Sandwich Pattern") for simple use cases.
*   **Lesson**: The "Sandwich Pattern" is for **heavy-duty** workflows where an open-ended LLM is too risky. For standard shopping/lookup tasks, a single `LlmAgent` with well-defined tools is preferred. **YAGNI (You Aren't Gonna Need It)** applies to agents too.

### 19.5 Explicit Consent for Implementation
**Context**: User asks for "Design" or "Architecture".
*   **Rule**: output the `.md` file and **wait**. Generating implementation code immediately violates trust and wastes tokens if the design is rejected.

### 19.6 The Sandwich Pattern Root Orchestrator Pitfall
**Context**: Designing the "Sandwich Pattern" (Interactive Intake -> Headless Workflow -> Interactive Review).
*   **Problem**: Using a `SequentialAgent` as the root orchestrator. `SequentialAgent` runs its sub-agents back-to-back and does not natively halt or yield for intermediate multi-turn user inputs unless forced via explicit signals.
*   **Solution**: The master orchestrator for a Sandwich Pattern MUST be an `LlmAgent`. The `LlmAgent` can dynamically read the event stream, pause to let the user answer the Intake agent's questions, recognize when Intake is finished (state updated), and then transfer control to the headless `SequentialAgent` workflow in the background.


### 19.7 The Sequential Resume Paradox (Handoff Stall)
**Context**: In a "Sandwich Pattern" where an interactive `LlmAgent` (Intake) finishes its job and needs to return control to the parent orchestrator so a headless workflow can run.
**Problem**: The Intake agent collects the last piece of information, says "Thank you, I will process this", but the system hangs waiting for the user to reply to a completed task. The orchestrator never resumes because the Intake agent is still considered the "active" agent.
**Solution**: The interactive agent MUST explicitly yield control back to the orchestrator when its task is complete.
1. Set `disallow_transfer_to_parent=False` on the interactive agent so it is allowed to return control.
2. In the agent's `instruction`, explicitly command it to "transfer back to your parent orchestrator" once all mandatory data is collected.
3. In the final tool called by the agent to save data, inject `tool_context.state["force_end"] = True` to forcefully break out of the active interaction loop, allowing the orchestrator's event loop to detect the state change and route to the next workflow step.

### 19.8 Testing Multi-Agent Apps with `adk web`
**Context**: Running `adk web` to test a newly developed agent via the browser UI.
**Problem**: Running `adk web` from *inside* the specific agent's folder or running `adk web [agent_name]` can cause pathing issues, naming collisions, or prevent the app launcher from loading the agent correctly.
**Solution**: Always run `adk web --port 8080` from the **parent workspace directory** (the root folder containing all agent subfolders) without specifying the agent name. This allows the ADK dev server to discover all agents, present the app selector UI properly, and maintain session isolation.
