#!/usr/bin/env python3
"""
SENTINEL AWS Diagnostics
========================
Verifica la configuración de AWS CLI, credenciales y recursos existentes.
Ejecutar: python3 aws_diagnostics.py
"""

import subprocess
import sys
import os
import json

DIVIDER = "=" * 60
REGIONS_TO_CHECK = ["us-east-1", "us-east-2"]

def run(cmd, timeout=10):
    """Run a shell command with timeout."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT", -1

def section(title):
    print(f"\n{DIVIDER}")
    print(f"  {title}")
    print(DIVIDER)

def check_aws_cli():
    section("1. AWS CLI Installation")
    stdout, stderr, code = run("aws --version")
    if code == 0:
        print(f"  ✅ AWS CLI installed: {stdout}")
        return True
    else:
        print(f"  ❌ AWS CLI NOT found or error: {stderr}")
        print("  💡 Install: curl 'https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip' -o awscliv2.zip")
        print("              unzip awscliv2.zip && sudo ./aws/install")
        return False

def check_credentials():
    section("2. AWS Credentials")
    
    # Check config files
    aws_dir = os.path.expanduser("~/.aws")
    creds_file = os.path.join(aws_dir, "credentials")
    config_file = os.path.join(aws_dir, "config")
    
    if os.path.exists(creds_file):
        print(f"  ✅ Credentials file exists: {creds_file}")
    else:
        print(f"  ❌ No credentials file at {creds_file}")
        
    if os.path.exists(config_file):
        print(f"  ✅ Config file exists: {config_file}")
    else:
        print(f"  ❌ No config file at {config_file}")
    
    # Check env vars
    env_vars = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION"]
    for var in env_vars:
        val = os.environ.get(var)
        if val:
            masked = val[:4] + "****" + val[-4:] if len(val) > 8 else "****"
            print(f"  ✅ {var} = {masked}")
        else:
            print(f"  ⚠️  {var} not set in environment")
    
    # Try sts get-caller-identity
    stdout, stderr, code = run("aws sts get-caller-identity --output json", timeout=10)
    if code == 0:
        identity = json.loads(stdout)
        print(f"\n  ✅ Authenticated as:")
        print(f"     Account:  {identity.get('Account', 'N/A')}")
        print(f"     ARN:      {identity.get('Arn', 'N/A')}")
        print(f"     UserId:   {identity.get('UserId', 'N/A')}")
        return True
    else:
        print(f"\n  ❌ Cannot authenticate: {stderr}")
        print("\n  💡 Fix: Run 'aws configure' and enter your Access Key, Secret Key, and region (us-east-1)")
        return False

def check_boto3():
    section("3. Python boto3 SDK")
    try:
        import boto3
        print(f"  ✅ boto3 version: {boto3.__version__}")
        return True
    except ImportError:
        print("  ❌ boto3 NOT installed")
        print("  💡 Install: pip3 install boto3")
        return False

def audit_ec2(region):
    """Check for running/stopped EC2 instances."""
    print(f"\n  --- EC2 Instances ({region}) ---")
    stdout, stderr, code = run(
        f"aws ec2 describe-instances --region {region} "
        f"--filters 'Name=instance-state-name,Values=running,stopped' "
        f"--query 'Reservations[].Instances[].{{ID:InstanceId,State:State.Name,Type:InstanceType,IP:PublicIpAddress,Name:Tags[?Key==`Name`].Value|[0]}}' "
        f"--output json",
        timeout=15
    )
    if code == 0 and stdout:
        instances = json.loads(stdout)
        if instances:
            for inst in instances:
                status_icon = "🟢" if inst.get("State") == "running" else "🟡"
                print(f"  {status_icon} {inst.get('ID', 'N/A')} | {inst.get('State', 'N/A')} | "
                      f"{inst.get('Type', 'N/A')} | IP: {inst.get('IP', 'N/A')} | "
                      f"Name: {inst.get('Name', 'N/A')}")
        else:
            print("  (no instances found)")
    elif stderr == "TIMEOUT":
        print("  ⏱️ Timeout querying EC2")
    else:
        print(f"  ⚠️ Error: {stderr}")

def audit_s3():
    """Check S3 buckets."""
    print(f"\n  --- S3 Buckets ---")
    stdout, stderr, code = run("aws s3 ls --output text", timeout=15)
    if code == 0:
        if stdout:
            for line in stdout.split("\n"):
                if "sentinel" in line.lower():
                    print(f"  🪣 {line}  ← SENTINEL bucket")
                else:
                    print(f"  🪣 {line}")
        else:
            print("  (no buckets found)")
    elif stderr == "TIMEOUT":
        print("  ⏱️ Timeout listing S3")
    else:
        print(f"  ⚠️ Error: {stderr}")

def audit_iam():
    """Check IAM roles related to sentinel."""
    print(f"\n  --- IAM Roles (sentinel-related) ---")
    stdout, stderr, code = run(
        "aws iam list-roles --query 'Roles[?contains(RoleName, `sentinel`)].{Name:RoleName,Created:CreateDate}' --output json",
        timeout=15
    )
    if code == 0 and stdout:
        roles = json.loads(stdout)
        if roles:
            for role in roles:
                print(f"  👤 {role.get('Name', 'N/A')} | Created: {role.get('Created', 'N/A')}")
        else:
            print("  (no sentinel-related roles found)")
    elif stderr == "TIMEOUT":
        print("  ⏱️ Timeout querying IAM")

def audit_resources(authenticated):
    section("4. AWS Resources Audit")
    if not authenticated:
        print("  ⚠️ Skipping audit — not authenticated")
        return
    
    for region in REGIONS_TO_CHECK:
        audit_ec2(region)
    audit_s3()
    audit_iam()

def check_local_files():
    section("5. Local Project Files")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    key_file = os.path.join(script_dir, "sentinel-hft-key.pem")
    env_file = os.path.join(script_dir, ".env")
    
    if os.path.exists(key_file):
        perms = oct(os.stat(key_file).st_mode)[-3:]
        print(f"  ✅ Key file exists: sentinel-hft-key.pem (permissions: {perms})")
        if perms != "400":
            print(f"     ⚠️ Permissions should be 400, run: chmod 400 {key_file}")
    else:
        print("  ❌ Key file NOT found: sentinel-hft-key.pem")
    
    if os.path.exists(env_file):
        print(f"  ✅ .env file exists")
        from dotenv import load_dotenv
        load_dotenv(env_file)
        keys = ["BINANCE_API_KEY", "BINANCE_SECRET_KEY", "HF_TOKEN", "KAGGLE_USERNAME", "KAGGLE_KEY"]
        for key in keys:
            val = os.getenv(key)
            if val:
                masked = val[:4] + "****"
                print(f"     ✅ {key} = {masked}")
            else:
                print(f"     ❌ {key} is MISSING")
    else:
        print("  ❌ .env file NOT found")
    
    # Check data directories
    data_dirs = [
        ("data/market/raw", "Market price data"),
        ("data/sentimental/raw", "Sentiment data"),
        ("cortex/gym", "Gym config"),
    ]
    print()
    for rel_path, desc in data_dirs:
        full_path = os.path.join(script_dir, rel_path)
        if os.path.exists(full_path):
            count = len(os.listdir(full_path))
            print(f"  ✅ {rel_path}/ ({count} items) — {desc}")
        else:
            print(f"  ❌ {rel_path}/ MISSING — {desc}")

def print_summary(cli_ok, creds_ok, boto3_ok):
    section("📋 SUMMARY & NEXT STEPS")
    
    if cli_ok and creds_ok and boto3_ok:
        print("  🎉 Everything is configured! You can proceed with:")
        print("     python3 deploy_sentinel_cloud.py")
    else:
        print("  Things to fix:")
        if not cli_ok:
            print("  1. Install AWS CLI:")
            print('     curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip')
            print("     unzip awscliv2.zip && sudo ./aws/install")
        if not creds_ok:
            print("  2. Configure credentials:")
            print("     aws configure")
            print("     → Access Key ID:     [your key]")
            print("     → Secret Access Key: [your secret]")
            print("     → Region:            us-east-1")
            print("     → Output format:     json")
        if not boto3_ok:
            print("  3. Install boto3:")
            print("     pip3 install boto3")

def main():
    print("\n🛡️  SENTINEL AWS Diagnostics Tool")
    print(f"    Date: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    cli_ok = check_aws_cli()
    creds_ok = check_credentials() if cli_ok else False
    boto3_ok = check_boto3()
    check_local_files()
    audit_resources(creds_ok)
    print_summary(cli_ok, creds_ok, boto3_ok)
    print()

if __name__ == "__main__":
    main()
