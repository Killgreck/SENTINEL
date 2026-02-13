import boto3
import time
import os
import subprocess
import json
import urllib.request

# Configuration
REGION = "us-east-1"
PROJECT_NAME = "sentinel-hft"
BUCKET_NAME = f"{PROJECT_NAME}-datalake-{int(time.time())}"
KEY_NAME = f"{PROJECT_NAME}-key"
SG_NAME = f"{PROJECT_NAME}-sg"
ROLE_NAME = f"{PROJECT_NAME}-role"
INSTANCE_TYPE = "t3.medium"
AMI_NAME_FILTER = "al2023-ami-2023*" # Amazon Linux 2023

ec2 = boto3.client("ec2", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)
iam = boto3.client("iam", region_name=REGION)

def get_my_ip():
    try:
        with urllib.request.urlopen("http://checkip.amazonaws.com") as response:
            return response.read().decode("utf-8").strip() + "/32"
    except:
        return "0.0.0.0/0"

def create_key_pair():
    print(f"Checking Key Pair '{KEY_NAME}'...")
    try:
        ec2.describe_key_pairs(KeyNames=[KEY_NAME])
        print(f"Key Pair '{KEY_NAME}' already exists.")
        # Check if we have the pem file locally
        if not os.path.exists(f"{KEY_NAME}.pem"):
             print(f"⚠️ Warning: Key Pair exists in AWS but '{KEY_NAME}.pem' not found locally. You might not be able to SSH.")
    except ec2.exceptions.ClientError:
        print(f"Creating Key Pair '{KEY_NAME}'...")
        key_pair = ec2.create_key_pair(KeyName=KEY_NAME)
        private_key = key_pair["KeyMaterial"]
        with open(f"{KEY_NAME}.pem", "w") as f:
            f.write(private_key)
        os.chmod(f"{KEY_NAME}.pem", 0o400)
        print(f"✅ Key Pair created and saved to {KEY_NAME}.pem")

def create_security_group():
    print(f"Checking Security Group '{SG_NAME}'...")
    try:
        response = ec2.describe_security_groups(GroupNames=[SG_NAME])
        sg_id = response['SecurityGroups'][0]['GroupId']
        print(f"Security Group '{SG_NAME}' already exists ({sg_id}).")
        return sg_id
    except ec2.exceptions.ClientError:
        print(f"Creating Security Group '{SG_NAME}'...")
        my_ip = get_my_ip()
        vpc_response = ec2.describe_vpcs()
        vpc_id = vpc_response['Vpcs'][0]['VpcId']
        
        sg = ec2.create_security_group(
            GroupName=SG_NAME,
            Description="Allow SSH for Sentinel",
            VpcId=vpc_id
        )
        sg_id = sg['GroupId']
        
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpRanges': [{'CidrIp': my_ip}]
                }
            ]
        )
        print(f"✅ Security Group created: {sg_id} (Allowed SSH from {my_ip})")
        return sg_id

def create_iam_role():
    print(f"Checking IAM Role '{ROLE_NAME}'...")
    try:
        iam.get_role(RoleName=ROLE_NAME)
        print(f"IAM Role '{ROLE_NAME}' already exists.")
    except iam.exceptions.NoSuchEntityException:
        print(f"Creating IAM Role '{ROLE_NAME}'...")
        assume_role_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(assume_role_policy)
        )
        iam.attach_role_policy(
            RoleName=ROLE_NAME,
            PolicyArn="arn:aws:iam::aws:policy/AmazonS3FullAccess"
        )
        # Create Instance Profile
        try:
            iam.create_instance_profile(InstanceProfileName=ROLE_NAME)
        except iam.exceptions.EntityAlreadyExistsException:
            pass
            
        iam.add_role_to_instance_profile(
            InstanceProfileName=ROLE_NAME,
            RoleName=ROLE_NAME
        )
        print(f"✅ IAM Role and Instance Profile created.")
        time.sleep(10) # Wait for propagation

def create_s3_bucket():
    print(f"Creating S3 Bucket '{BUCKET_NAME}'...")
    try:
        if REGION == "us-east-1":
            s3.create_bucket(Bucket=BUCKET_NAME)
        else:
            s3.create_bucket(
                Bucket=BUCKET_NAME,
                CreateBucketConfiguration={'LocationConstraint': REGION}
            )
        print(f"✅ S3 Bucket created: {BUCKET_NAME}")
    except Exception as e:
        print(f"⚠️ Could not create bucket (might exist): {e}")
    return BUCKET_NAME

def get_latest_ami():
    response = ec2.describe_images(
        Filters=[
            {'Name': 'name', 'Values': [AMI_NAME_FILTER]},
            {'Name': 'architecture', 'Values': ['x86_64']},
            {'Name': 'owner-alias', 'Values': ['amazon']}
        ],
        Owners=['amazon']
    )
    # Sort by creation date
    images = sorted(response['Images'], key=lambda x: x['CreationDate'], reverse=True)
    if not images:
        raise Exception("No AMI found")
    return images[0]['ImageId']

def launch_instance(sg_id):
    ami_id = get_latest_ami()
    print(f"Launching EC2 Instance ({INSTANCE_TYPE}) with AMI {ami_id}...")
    
    user_data_script = f"""#!/bin/bash
dnf update -y
dnf install -y git python3-pip
pip3 install pandas yfinance pyarrow huggingface_hub python-dotenv boto3

# Setup Directories
mkdir -p /home/ec2-user/sentinel/data/market/raw
mkdir -p /home/ec2-user/sentinel/data/sentimental/raw
chown -R ec2-user:ec2-user /home/ec2-user/sentinel
"""

    instances = ec2.run_instances(
        ImageId=ami_id,
        InstanceType=INSTANCE_TYPE,
        KeyName=KEY_NAME,
        SecurityGroupIds=[sg_id],
        MinCount=1,
        MaxCount=1,
        IamInstanceProfile={'Name': ROLE_NAME},
        UserData=user_data_script,
        TagSpecifications=[{
            'ResourceType': 'instance',
            'Tags': [{'Key': 'Name', 'Value': 'Sentinel-Ingestion-Node'}]
        }]
    )
    
    instance_id = instances['Instances'][0]['InstanceId']
    print(f"✅ Instance launched: {instance_id}")
    return instance_id

def main():
    print("🚀 Initializing Sentinel Cloud Environment...")
    
    create_key_pair()
    sg_id = create_security_group()
    create_iam_role()
    bucket = create_s3_bucket()
    
    instance_id = launch_instance(sg_id)
    
    print("Waiting for instance to be running...")
    waiter = ec2.get_waiter('instance_running')
    waiter.wait(InstanceIds=[instance_id])
    
    # Get Public DNS/IP
    desc = ec2.describe_instances(InstanceIds=[instance_id])
    public_dns = desc['Reservations'][0]['Instances'][0]['PublicDnsName']
    public_ip = desc['Reservations'][0]['Instances'][0]['PublicIpAddress']
    
    print("\n" + "="*50)
    print("✅ DEPLOYMENT COMPLETE")
    print("="*50)
    print(f"Instance ID: {instance_id}")
    print(f"Public IP:   {public_ip}")
    print(f"S3 Bucket:   {bucket}")
    print(f"Key File:    {KEY_NAME}.pem")
    print("-" * 30)
    print("To connect:")
    print(f"ssh -i {KEY_NAME}.pem ec2-user@{public_dns}")
    print("-" * 30)
    print("Next steps:")
    print("1. Upload your scripts:")
    print(f"   scp -i {KEY_NAME}.pem requirements.txt download_*.py ec2-user@{public_dns}:~/sentinel/")
    print("2. Connect and run:")
    print(f"   ssh -i {KEY_NAME}.pem ec2-user@{public_dns}")
    print("   cd sentinel")
    print("   pip3 install -r requirements.txt")
    print("   python3 download_prices_now.py")
    print("   python3 download_sentiment_history.py")
    print("   aws s3 sync data/ s3://{bucket}/raw/")

if __name__ == "__main__":
    main()
