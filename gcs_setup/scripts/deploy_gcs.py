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
    parser = argparse.ArgumentParser(description="Helper script to deploy GCS Buckets via Terraform.")
    parser.add_argument("--project", required=True, help="GCP Project ID")
    parser.add_argument("--region", default="us-central1", help="GCP Region")
    parser.add_argument("--buckets", required=True, help="Comma-separated list of bucket names to create")
    parser.add_argument("--work-dir", default="deploy_gcs", help="Working directory for Terraform files")
    parser.add_argument("--force-destroy", type=bool, default=True, help="Allow deleting buckets containing objects on destroy")
    parser.add_argument("--destroy", action="store_true", help="Destroy the buckets instead of creating them")
    
    args = parser.parse_args()
    
    check_terraform()
    
    bucket_list = [b.strip() for b in args.buckets.split(",") if b.strip()]
    if not bucket_list:
        print("Error: No bucket names specified.", file=sys.stderr)
        sys.exit(1)
        
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
    with open(tfvars_path, "w") as f:
        f.write(f'project_id    = "{args.project}"\n')
        f.write(f'region        = "{args.region}"\n')
        
        # Format the list of strings for HCL
        buckets_hcl = ", ".join([f'"{b}"' for b in bucket_list])
        f.write(f'bucket_names  = [{buckets_hcl}]\n')
        f.write(f'force_destroy = {str(args.force_destroy).lower()}\n')

    # Run Terraform Init
    run_cmd(["terraform", "init"], cwd=work_dir)
    
    if args.destroy:
        print("Starting Terraform Destroy...")
        run_cmd(["terraform", "destroy", "-auto-approve"], cwd=work_dir)
        print("==================================================")
        print("GCS BUCKETS DESTROYED SUCCESSFULLY")
        print("==================================================")
    else:
        print("Starting Terraform Apply...")
        run_cmd(["terraform", "apply", "-auto-approve"], cwd=work_dir)
        
        # Read outputs
        output_res = subprocess.run(["terraform", "output", "-json"], cwd=work_dir, capture_output=True, text=True)
        if output_res.returncode == 0:
            outputs = json.loads(output_res.stdout)
            urls = outputs.get("bucket_urls", {}).get("value", {})
            print("==================================================")
            print("GCS BUCKETS CREATED SUCCESSFULLY")
            print("==================================================")
            for name, url in urls.items():
                print(f"Bucket: {name} -> {url}")
            print("==================================================")
        else:
            print("Warning: Could not fetch Terraform outputs.", file=sys.stderr)

if __name__ == "__main__":
    main()
