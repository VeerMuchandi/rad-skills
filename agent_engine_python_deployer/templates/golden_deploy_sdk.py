import os
import vertexai
from vertexai.preview.reasoning_engines import A2aAgent
from google.genai import types
from google.auth import default

def main():
    project_id = "your-project-id"
    location = "us-central1"
    storage = "gs://your-staging-bucket"
    existing_engine_id = os.environ.get("EXISTING_ENGINE_ID") # Set if updating
    
    vertexai.init(project=project_id, location=location, staging_bucket=storage)
    
    client = vertexai.Client(project=project_id, location=location)
    
    # Note: You must define 'a2a_agent' before using it.
    # a2a_agent = A2aAgent(...)

    config = {
        "display_name": "My Agent",
        "agent_framework": "google-adk",
        "requirements": [
            "google-adk>=1.16.0",
            "google-cloud-aiplatform[agent_engines,adk]>=1.143.0",
            "a2a-sdk>=0.3.4",
            "pydantic==2.12.5",
            "cloudpickle==3.1.2"
        ],
        "env_vars": {
            "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true",
        },
        "extra_packages": [
            "agent_executor.py",
            "tools.py",
            "agent.py",
            "a2ui_examples.py",
            "a2ui_schema.py" # Vendor all local imports
        ]
    }

    if existing_engine_id:
        engine_name = f"projects/{project_id}/locations/{location}/reasoningEngines/{existing_engine_id}"
        print(f"Applying inplace update to: {existing_engine_id}")
        remote_agent = client.agent_engines.update(name=engine_name, agent=a2a_agent, config=config)
    else:
        print("Spinning up fresh create instance...")
        remote_agent = client.agent_engines.create(agent=a2a_agent, config=config)
        
    print(f"✓ Process settlement: {remote_agent.name}")

if __name__ == "__main__":
    main()
