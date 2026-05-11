import os
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.genai import types

# Import the tool function from the template
from tools_template import search_records

load_dotenv()

MODEL = "gemini-2.5-flash"
AGENT_APP_NAME = 'generic_datastore_assistant'

instruction_prompt = """
You are a helpful assistant that answers user questions by searching a secure corporate datastore.
When a user asks a question, you MUST use the `search_records` tool to search the datastore for relevant information.
Synthesize the results from the datastore into a clear, concise answer.
"""

# Note: This is a simple single-agent example.
# The agent architecture (single vs multi-agent) depends on the end-user use case.
# The ADK developer skill covers building complex agent structures.

root_agent = Agent(
        model=MODEL,
        name=AGENT_APP_NAME,
        description="An agent that searches a secure corporate datastore to answer questions.",
        instruction=instruction_prompt,
        generate_content_config=types.GenerateContentConfig(temperature=0.2),
        tools=[search_records]
)
