#!/usr/bin/env python3
import os
import sys
import subprocess
import argparse
import shutil

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

def init_db(project_id, secret_prefix, sql_file_path, flavor):
    try:
        from google.cloud import secretmanager
        from google.cloud.sql.connector import Connector, IPTypes
        import sqlalchemy
    except ImportError as e:
        print(f"Error: Required Python packages are missing ({e}). Please run: pip install sqlalchemy cloud-sql-python-connector[pg8000] google-cloud-secret-manager", file=sys.stderr)
        sys.exit(1)

    print("Fetching connection secrets from Secret Manager...")
    client = secretmanager.SecretManagerServiceClient()
    
    def get_secret(secret_id):
        name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")

    instance_connection_name = get_secret(f"{secret_prefix}db_connection_name")
    db_user = get_secret(f"{secret_prefix}db_user")
    db_pass = get_secret(f"{secret_prefix}db_password")
    db_name = get_secret(f"{secret_prefix}db_name")

    connector = Connector()

    if flavor == "postgres":
        def getconn():
            return connector.connect(
                instance_connection_name,
                "pg8000",
                user=db_user,
                password=db_pass,
                db=db_name,
                ip_type=IPTypes.PUBLIC,
            )
        pool = sqlalchemy.create_engine(
            "postgresql+pg8000://",
            creator=getconn,
        )
    elif flavor == "mysql":
        try:
            import pymysql
        except ImportError:
            print("Error: PyMySQL is required to initialize a MySQL database. Run: pip install pymysql", file=sys.stderr)
            sys.exit(1)
            
        def getconn():
            return connector.connect(
                instance_connection_name,
                "pymysql",
                user=db_user,
                password=db_pass,
                db=db_name,
                ip_type=IPTypes.PUBLIC,
            )
        pool = sqlalchemy.create_engine(
            "mysql+pymysql://",
            creator=getconn,
        )
    else:
        raise ValueError(f"Unsupported flavor: {flavor}")

    print(f"Reading SQL file: {sql_file_path}")
    with open(sql_file_path, "r") as f:
        sql_content = f.read()

    # Simple statement splitter by semicolon
    statements = []
    current_statement = []
    for line in sql_content.splitlines():
        if line.strip().startswith("--") or line.strip().startswith("#"):
            continue
        current_statement.append(line)
        if ";" in line:
            statements.append("\n".join(current_statement))
            current_statement = []
    if current_statement:
        rem = "\n".join(current_statement).strip()
        if rem:
            statements.append(rem)

    print("Connecting to database and executing initialization schema...")
    with pool.connect() as conn:
        for stmt in statements:
            stmt = stmt.strip()
            if not stmt:
                continue
            print(f"Executing: {stmt.replace(chr(10), ' ')}")
            conn.execute(sqlalchemy.text(stmt))
        conn.commit()
    print("Database tables initialized successfully!")

def main():
    parser = argparse.ArgumentParser(description="Helper script to deploy Cloud SQL via Terraform.")
    parser.add_argument("--project", required=True, help="GCP Project ID")
    parser.add_argument("--region", default="us-central1", help="GCP Region")
    parser.add_argument("--instance-prefix", default="adk-db", help="Instance name prefix")
    parser.add_argument("--database", default="adk_database", help="Database name")
    parser.add_argument("--username", default="adk_user", help="Database username")
    parser.add_argument("--secret-prefix", default="adk_", help="Secret ID prefix")
    parser.add_argument("--flavor", choices=["postgres", "mysql"], default="postgres", help="Database flavor (postgres or mysql)")
    parser.add_argument("--version", default=None, help="Database version (defaults to POSTGRES_15 or MYSQL_8_0)")
    parser.add_argument("--work-dir", default="deploy_db", help="Working directory for Terraform files")
    parser.add_argument("--sql-file", default=None, help="Path to a SQL file to run after database creation")
    parser.add_argument("--destroy", action="store_true", help="Destroy the resources instead of creating them")
    
    args = parser.parse_args()
    
    # Check SQL file existence if specified
    if args.sql_file and not os.path.exists(args.sql_file):
        print(f"Error: SQL file not found at: {args.sql_file}", file=sys.stderr)
        sys.exit(1)
        
    # Set default database version based on flavor if not specified
    db_version = args.version
    if not db_version:
        db_version = "POSTGRES_15" if args.flavor == "postgres" else "MYSQL_8_0"
        
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
            
    # Create terraform.tfvars
    tfvars_path = os.path.join(work_dir, "terraform.tfvars")
    with open(tfvars_path, "w") as f:
        f.write(f'project_id           = "{args.project}"\n')
        f.write(f'region               = "{args.region}"\n')
        f.write(f'instance_name_prefix = "{args.instance_prefix}"\n')
        f.write(f'database_flavor      = "{args.flavor}"\n')
        f.write(f'database_version     = "{db_version}"\n')
        f.write(f'database_name        = "{args.database}"\n')
        f.write(f'db_username          = "{args.username}"\n')
        f.write(f'secret_prefix        = "{args.secret_prefix}"\n')
        f.write('deletion_protection  = false\n')
        
    print(f"Configured terraform.tfvars in {work_dir}")
    
    # Run terraform init
    run_cmd(["terraform", "init"], cwd=work_dir)
    
    # Run terraform apply or destroy
    if args.destroy:
        print("Starting Terraform Destroy...")
        run_cmd(["terraform", "destroy", "-auto-approve"], cwd=work_dir)
    else:
        print("Starting Terraform Apply...")
        run_cmd(["terraform", "apply", "-auto-approve"], cwd=work_dir)
        
        # Get outputs
        output_res = subprocess.run(["terraform", "output", "-json"], cwd=work_dir, capture_output=True, text=True)
        if output_res.returncode == 0:
            print("\n" + "="*50)
            print("DEPLOYMENT SUCCESSFUL")
            print("="*50)
            print(output_res.stdout)
            print("="*50)
            
            # Initialize database if sql-file is provided
            if args.sql_file:
                print("Starting database schema initialization...")
                init_db(
                    project_id=args.project,
                    secret_prefix=args.secret_prefix,
                    sql_file_path=os.path.abspath(args.sql_file),
                    flavor=args.flavor
                )
        else:
            print("Failed to fetch terraform outputs.", file=sys.stderr)

if __name__ == "__main__":
    main()
