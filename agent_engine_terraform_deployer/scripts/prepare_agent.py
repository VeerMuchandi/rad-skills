#!/usr/bin/env python3
import os
import sys
import subprocess
import json

def get_project_id():
    """Attempts to retrieve the active GCP project ID from gcloud config."""
    try:
        return subprocess.check_output("gcloud config get-value project", shell=True, stderr=subprocess.DEVNULL).decode().strip()
    except:
        return None

def get_llm_ignores(files, project_id):
    """Uses Vertex AI to recommend files to ignore."""
    try:
        import vertexai
        from vertexai.generative_models import GenerativeModel
        
        print(f"Connecting to Vertex AI (Project: {project_id})...")
        vertexai.init(project=project_id, location="us-central1") # Defaulting to us-central1 for Ops
        model = GenerativeModel("gemini-1.5-flash")
        
        prompt = f"""
        You are an expert in Python and Docker deployments. I am deploying a Python agent to Vertex AI Agent Engine.
        There is a 256MB source limit. I need to create a .ae_ignore file (similar to .dockerignore).
        
        Here is the list of files and directories in my root:
        {json.dumps(files)}
        
        Identify specific file or directory names from this list that should likely be EXCLUDED.
        Common candidates: venvs, git folders, test caches, deployment configs, large data files, temp files.
        Retain application code, requirements.txt, and strict config files.
        
        Return ONLY a raw list of names to ignore, one per line. No markdown formatting.
        """
        
        response = model.generate_content(prompt)
        text = response.text.strip()
        # Clean up any markdown code blocks if the model hallucinates them
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        clean_lines = []
        for line in lines:
            if line.startswith("```"): continue
            clean_lines.append(line)
            
        print(f"[AI] Recommended {len(clean_lines)} exclusions.")
        return set(clean_lines)
        
    except Exception as e:
        print(f"[WARN] Failed to use LLM for ignore analysis: {e}")
        return set()

def prepare_agent(agent_dir):
    """
    Intelligently prepares an agent using Hybrid (LLM + Rule) logic.
    """
    print(f"Preparing agent in: {agent_dir}")
    
    # List top-level files
    try:
        files = os.listdir(agent_dir)
    except FileNotFoundError:
        print(f"Error: Directory '{agent_dir}' not found.")
        return

    # 1. Handle .ae_ignore
    ignore_path = os.path.join(agent_dir, ".ae_ignore")
    
    # Rule-Based Baseline (Always safe)
    baseline_ignores = {
        "__pycache__", "*.pyc", ".git", ".venv", "deploy", ".ds_store", 
        ".terraform", ".terraform.lock.hcl", "venv", "env", ".idea", ".vscode",
        "*.zip", "*.pkl", "schema.json"
    }
    
    # LLM-Based Insights
    llm_ignores = set()
    project_id = get_project_id()
    
    if project_id:
        try:
            # Check if vertexai is installed
            import vertexai
            llm_ignores = get_llm_ignores(files, project_id)
        except ImportError:
            print("[INFO] 'vertexai' library not found. Using standard rules. (Pip install google-cloud-aiplatform for AI features)")
    else:
        print("[INFO] No active GCP project found. Using standard rules.")
        
    final_ignores = baseline_ignores.union(llm_ignores)
    
    current_ignores = set()
    if os.path.exists(ignore_path):
        with open(ignore_path, "r") as f:
            current_ignores = {line.strip() for line in f if line.strip() and not line.startswith("#")}
    
    missing_ignores = final_ignores - current_ignores
    
    if missing_ignores:
        print(f"Adding {len(missing_ignores)} patterns to .ae_ignore...")
        with open(ignore_path, "a") as f:
            if current_ignores: f.write("\n")
            f.write("# Added by Agent Engine Deployer Skill (Hybrid Analysis)\n")
            for item in sorted(missing_ignores):
                f.write(f"{item}\n")
    else:
        print(".ae_ignore is already up to date.")

    # 2. Handle requirements.txt
    req_path = os.path.join(agent_dir, "requirements.txt")
    mandatory_dep = "google-cloud-aiplatform[agent_engines,adk]"
    
    has_dep = False
    if os.path.exists(req_path):
        with open(req_path, "r") as f:
            content = f.read()
            if "google-cloud-aiplatform" in content and "agent_engines" in content:
                has_dep = True
    
    if not has_dep:
        print(f"Adding mandatory dependency '{mandatory_dep}' to requirements.txt...")
        with open(req_path, "a") as f:
            f.write(f"\n# Mandatory for Agent Engine\n{mandatory_dep}\n")
    else:
        print("requirements.txt already correctly configured.")

    # 3. Handle .env
    env_path = os.path.join(agent_dir, ".env")
    telemetry_vars = {
        "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true"
    }
    
    existing_vars = {}
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    key, val = line.split("=", 1)
                    existing_vars[key.strip()] = val.strip()
    
    new_vars = {}
    for key, val in telemetry_vars.items():
        if key not in existing_vars:
            new_vars[key] = val
            
    if new_vars:
        print(f"Adding {len(new_vars)} telemetry variables to .env...")
        with open(env_path, "a") as f:
            f.write("\n# Added by Agent Engine Deployer Skill\n")
            for key, val in new_vars.items():
                f.write(f"{key}={val}\n")
    else:
        print(".env is already correctly configured.")

    print("\n[SUCCESS] Agent is ready for deployment configuration!")

if __name__ == "__main__":
    target_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    prepare_agent(target_dir)
