#!/usr/bin/env python3
"""Helper script to deploy A2UI ADK agents cleanly to Google Cloud Run."""

import argparse
import os
import shutil
import subprocess
import sys


def parse_args():
  parser = argparse.ArgumentParser(
      description="Deploy an A2UI ADK agent cleanly to Google Cloud Run."
  )
  parser.add_argument(
      "--project", required=True, help="Google Cloud Project ID."
  )
  parser.add_argument(
      "--region", default="us-central1", help="GCP region (default: us-central1)."
  )
  parser.add_argument(
      "--agent_dir",
      required=True,
      help="Path to the agent directory to deploy.",
  )
  parser.add_argument(
      "--service_name",
      help="Cloud Run service name. Defaults to agent directory name.",
  )
  parser.add_argument(
      "--port", type=int, default=8000, help="Container port (default: 8000)."
  )
  parser.add_argument(
      "--google_adk_version",
      default="1.28.1",
      help="google-adk package version (default: 1.28.1).",
  )
  return parser.parse_args()


def clean_requirements(src_path, dest_path):
  """Cleans requirements.txt to strip local wheel and Git references."""
  if not os.path.exists(src_path):
    print(f"Creating empty requirements.txt at {dest_path}")
    with open(dest_path, "w", encoding="utf-8") as f:
      f.write("jsonschema\na2ui-agent-sdk\n")
    return

  print(f"Cleaning requirements.txt from {src_path} to {dest_path}")
  with open(src_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

  cleaned_lines = []
  has_a2ui_sdk = False
  for line in lines:
    line_stripped = line.strip()
    if not line_stripped or line_stripped.startswith("#"):
      continue
    # If it refers to local wheel or git URL for a2ui agent sdk, simplify it
    if "a2ui_agent_sdk" in line_stripped or "A2UI.git" in line_stripped:
      if not has_a2ui_sdk:
        cleaned_lines.append("a2ui-agent-sdk\n")
        has_a2ui_sdk = True
    elif line_stripped == "a2ui-agent-sdk":
      if not has_a2ui_sdk:
        cleaned_lines.append("a2ui-agent-sdk\n")
        has_a2ui_sdk = True
    else:
      cleaned_lines.append(line)

  if not has_a2ui_sdk:
    cleaned_lines.append("a2ui-agent-sdk\n")

  with open(dest_path, "w", encoding="utf-8") as f:
    f.writelines(cleaned_lines)


def run_cmd(cmd, cwd=None):
  print(f"Running: {' '.join(cmd)}")
  result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
  if result.returncode != 0:
    print(f"Error executing command: {' '.join(cmd)}")
    print(f"Stdout:\n{result.stdout}")
    print(f"Stderr:\n{result.stderr}")
    sys.exit(result.returncode)
  return result.stdout


def main():
  args = parse_args()

  agent_dir = os.path.abspath(args.agent_dir)
  agent_name = os.path.basename(agent_dir)
  if not args.service_name:
    args.service_name = agent_name.replace("_", "-")

  if not os.path.isdir(agent_dir):
    print(f"Error: {agent_dir} is not a directory.")
    sys.exit(1)

  # 1. Setup Staging Area
  workspace_root = os.getcwd()
  staging_dir = os.path.join(workspace_root, "scratch", "deploy_run")
  staging_agent_dir = os.path.join(
      staging_dir, "agents", agent_name
  )

  print(f"Setting up staging area in: {staging_dir}")
  if os.path.exists(staging_dir):
    shutil.rmtree(staging_dir)
  os.makedirs(staging_agent_dir)

  # 2. Copy only necessary files (excluding build artifacts)
  for item in os.listdir(agent_dir):
    item_path = os.path.join(agent_dir, item)
    if os.path.isfile(item_path):
      if item.endswith(".py") or item.endswith(".json"):
        shutil.copy2(item_path, staging_agent_dir)

  # Clean and copy requirements.txt
  clean_requirements(
      os.path.join(agent_dir, "requirements.txt"),
      os.path.join(staging_agent_dir, "requirements.txt"),
  )

  # 3. Generate Dockerfile
  dockerfile_content = f"""FROM python:3.11-slim
WORKDIR /app

RUN adduser --disabled-password --gecos "" myuser
USER myuser
ENV PATH="/home/myuser/.local/bin:$PATH"
ENV GOOGLE_GENAI_USE_VERTEXAI=1
ENV GOOGLE_CLOUD_PROJECT={args.project}
ENV GOOGLE_CLOUD_LOCATION={args.region}

RUN pip install google-adk=={args.google_adk_version}

COPY --chown=myuser:myuser "agents/{agent_name}/" "/app/agents/{agent_name}/"
RUN pip install -r "/app/agents/{agent_name}/requirements.txt"

EXPOSE {args.port}
CMD ["adk", "api_server", "--port={args.port}", "--host=0.0.0.0", "--a2a", "/app/agents"]
"""
  dockerfile_path = os.path.join(staging_dir, "Dockerfile")
  with open(dockerfile_path, "w", encoding="utf-8") as f:
    f.write(dockerfile_content)
  print(f"Generated Dockerfile at: {dockerfile_path}")

  # 4. Trigger Cloud Build
  image_uri = (
      f"us-central1-docker.pkg.dev/{args.project}/cloud-run-source-deploy/{args.service_name}:latest"
  )
  print(f"Triggering Cloud Build for image: {image_uri}")
  build_cmd = [
      "gcloud",
      "builds",
      "submit",
      "--tag",
      image_uri,
      "--project",
      args.project,
      "--region",
      args.region,
  ]
  run_cmd(build_cmd, cwd=staging_dir)
  print("Cloud Build completed successfully!")

  # 5. Cloud Run Deploy
  print(f"Deploying to Cloud Run service: {args.service_name}")
  deploy_cmd = [
      "gcloud",
      "run",
      "deploy",
      args.service_name,
      "--image",
      image_uri,
      "--project",
      args.project,
      "--region",
      args.region,
      "--port",
      str(args.port),
      "--allow-unauthenticated",
  ]
  run_cmd(deploy_cmd)
  print("Cloud Run deployment completed successfully!")

  # Get URL
  get_url_cmd = [
      "gcloud",
      "run",
      "services",
      "describe",
      args.service_name,
      "--project",
      args.project,
      "--region",
      args.region,
      "--format",
      "value(status.url)",
  ]
  service_url = run_cmd(get_url_cmd).strip()
  namespaced_url = f"{service_url}/a2a/{agent_name}"

  print("\n==================================================")
  print("DEPLOYMENT SUCCESSFUL")
  print(f"Service URL: {service_url}")
  print(f"A2A Namespaced URL: {namespaced_url}")
  print(f"Agent Card: {namespaced_url}/.well-known/agent-card.json")
  print("==================================================")


if __name__ == "__main__":
  main()
