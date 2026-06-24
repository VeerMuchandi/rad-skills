#!/usr/bin/env python3
import os
import sys
import subprocess
import argparse
import shutil
import json

def check_terraform():
    if not shutil.which("terraform"):
        print("Error: terraform CLI is not installed or not in PATH.", file=sys.stderr)
        sys.exit(1)

def run_cmd(args, cwd=None):
    print(f"Running command: {' '.join(args)} (in {cwd or '.'})")
    result = subprocess.run(args, cwd=cwd, capture_output=False, text=True)
    if result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)

def main():
    parser = argparse.ArgumentParser(description="Helper script to deploy Cloud Scheduler Job via Terraform.")
    parser.add_argument("--project", required=True, help="GCP Project ID")
    parser.add_argument("--region", default="us-central1", help="GCP Region")
    parser.add_argument("--job-name", required=True, help="Cloud Scheduler Job Name")
    parser.add_argument("--schedule", required=True, help="Cron schedule (e.g. '0 9 * * *')")
    parser.add_argument("--time-zone", default="America/New_York", help="Scheduler Time Zone")
    parser.add_argument("--target-uri", required=True, help="HTTP Target URI")
    parser.add_argument("--service-account", required=True, help="Service Account email for token Auth")
    parser.add_argument("--auth-type", choices=["OAUTH", "OIDC", "NONE"], default="OAUTH", help="Authentication type (OAUTH or OIDC)")
    parser.add_argument("--oauth-scope", default="https://www.googleapis.com/auth/cloud-platform", help="OAuth Scope (only for OAUTH)")
    parser.add_argument("--body", default="", help="JSON string payload to send with request")
    parser.add_argument("--work-dir", default="deploy_scheduler", help="Working directory for Terraform files")
    parser.add_argument("--destroy", action="store_true", help="Destroy the scheduler job instead of creating it")
    
    args = parser.parse_args()
    
    check_terraform()
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    templates_dir = os.path.abspath(os.path.join(script_dir, "..", "resources", "templates"))
    work_dir = os.path.abspath(args.work_dir)
    
    # Initialize workspace directory
    if not os.path.exists(work_dir):
        print(f"Creating directory: {work_dir}")
        os.makedirs(work_dir)
    
    # Copy template files to workspace directory
    for item in os.listdir(templates_dir):
        s = os.path.join(templates_dir, item)
        d = os.path.join(work_dir, item)
        if os.path.isfile(s):
            shutil.copy2(s, d)
            
    # Generate terraform.tfvars
    tfvars_path = os.path.join(work_dir, "terraform.tfvars")
    print(f"Writing Terraform variables to: {tfvars_path}")
    
    # Escape body quotes for HCL
    escaped_body = args.body.replace('"', '\\"')
    
    with open(tfvars_path, "w") as f:
        f.write(f'project_id            = "{args.project}"\n')
        f.write(f'region                = "{args.region}"\n')
        f.write(f'job_name              = "{args.job_name}"\n')
        f.write(f'schedule              = "{args.schedule}"\n')
        f.write(f'time_zone             = "{args.time_zone}"\n')
        f.write(f'target_uri            = "{args.target_uri}"\n')
        f.write(f'service_account_email = "{args.service_account}"\n')
        f.write(f'auth_type             = "{args.auth_type}"\n')
        f.write(f'oauth_scope           = "{args.oauth_scope}"\n')
        f.write(f'body                  = "{escaped_body}"\n')

    # Run Terraform Init
    run_cmd(["terraform", "init"], cwd=work_dir)
    
    if args.destroy:
        print("Starting Terraform Destroy...")
        run_cmd(["terraform", "destroy", "-auto-approve"], cwd=work_dir)
        print("==================================================")
        print("CLOUD SCHEDULER JOB DESTROYED SUCCESSFULLY")
        print("==================================================")
    else:
        print("Starting Terraform Apply...")
        run_cmd(["terraform", "apply", "-auto-approve"], cwd=work_dir)
        
        # Read outputs
        output_res = subprocess.run(["terraform", "output", "-json"], cwd=work_dir, capture_output=True, text=True)
        if output_res.returncode == 0:
            outputs = json.loads(output_res.stdout)
            job_id = outputs.get("job_id", {}).get("value", "N/A")
            state = outputs.get("job_state", {}).get("value", "N/A")
            print("==================================================")
            print("CLOUD SCHEDULER JOB CREATED SUCCESSFULLY")
            print("==================================================")
            print(f"Job ID: {job_id}")
            print(f"State:  {state}")
            print("==================================================")
        else:
            print("Warning: Could not fetch Terraform outputs.", file=sys.stderr)

if __name__ == "__main__":
    main()
