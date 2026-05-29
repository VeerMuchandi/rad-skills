import os, vertexai, json, requests
from vertexai.preview.reasoning_engines import A2aAgent
from google.genai import types

# STABLE VERSIONS FOR PYTHON 3.13 / A2UI
VERSIONS = [
    "google-adk==1.28.1", "a2a-sdk==0.3.25", "pydantic==2.12.5", 
    "cloudpickle==3.1.2", "protobuf==6.33.6",
    "a2ui-agent-sdk @ git+https://github.com/google/A2UI.git#subdirectory=agent_sdks/python"
]

def main():
    existing_id = os.environ.get("EXISTING_ENGINE_ID")
    vertexai.init(project=os.environ["PROJECT_ID"], location="us-central1", staging_bucket=os.environ["BUCKET"])
    client = vertexai.Client(project=os.environ["PROJECT_ID"], location="us-central1")
    
    # Note: You must define 'my_card' and 'AdkAgentToA2AExecutor' before using them.
    # my_card = ...
    # from agent_executor import AdkAgentToA2AExecutor
    
    a2a_agent = A2aAgent(agent_card=my_card, agent_executor_builder=AdkAgentToA2AExecutor)
    config = {
        "requirements": VERSIONS, 
        "extra_packages": ["agent_executor.py", "agent.py", "tools.py"]
    }

    if existing_id:
        name = f"projects/{os.environ['PROJECT_ID']}/locations/us-central1/reasoningEngines/{existing_id}"
        remote = client.agent_engines.update(name=name, agent=a2a_agent, config=config)
    else:
        remote = client.agent_engines.create(agent=a2a_agent, config=config)
    
    print(f"Deploy complete: {remote.name}")

if __name__ == "__main__":
    main()
