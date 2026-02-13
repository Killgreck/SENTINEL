#!/usr/bin/env python3
"""
SENTINEL — Sync local data to S3 Data Lake
═══════════════════════════════════════════
Usage: python3 sync_to_s3.py [--bucket BUCKET_NAME] [--dry-run]

Uploads local data/ directory to S3 following the Data Lake structure:
  s3://BUCKET/raw/prices/      ← Parquet files from yfinance
  s3://BUCKET/raw/sentiment/   ← CSV files from HuggingFace
"""

import boto3
import os
import sys
import argparse
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Known sentinel buckets from deploy history
KNOWN_BUCKETS = [
    "sentinel-hft-datalake-1767753665",
    "sentinel-hft-datalake-1767754483",
]


def find_sentinel_bucket(s3_client):
    """Auto-detect the sentinel S3 bucket."""
    try:
        response = s3_client.list_buckets()
        buckets = [b["Name"] for b in response["Buckets"]]
        sentinel_buckets = [b for b in buckets if "sentinel" in b.lower()]
        
        if sentinel_buckets:
            # Use the most recent one
            bucket = sorted(sentinel_buckets)[-1]
            print(f"  🪣 Auto-detected bucket: {bucket}")
            return bucket
        
        # Check known buckets
        for known in KNOWN_BUCKETS:
            if known in buckets:
                print(f"  🪣 Found known bucket: {known}")
                return known
        
        print("  ❌ No sentinel bucket found. Create one with:")
        print("     aws s3 mb s3://sentinel-hft-datalake")
        return None
    except Exception as e:
        print(f"  ❌ Error listing buckets: {e}")
        return None


def sync_directory(s3_client, local_dir, bucket, s3_prefix, dry_run=False):
    """Upload files from local_dir to s3://bucket/s3_prefix/"""
    if not os.path.exists(local_dir):
        print(f"  ⚠️  Directory not found: {local_dir}")
        return 0
    
    uploaded = 0
    for root, dirs, files in os.walk(local_dir):
        for filename in files:
            local_path = os.path.join(root, filename)
            # Build S3 key preserving subdirectory structure
            relative_path = os.path.relpath(local_path, local_dir)
            s3_key = f"{s3_prefix}/{relative_path}"
            
            file_size = os.path.getsize(local_path)
            size_mb = file_size / (1024 * 1024)
            
            if dry_run:
                print(f"  [DRY-RUN] Would upload: {relative_path} → s3://{bucket}/{s3_key} ({size_mb:.2f} MB)")
            else:
                print(f"  ⬆️  Uploading: {relative_path} ({size_mb:.2f} MB)...", end=" ", flush=True)
                try:
                    s3_client.upload_file(local_path, bucket, s3_key)
                    print("✅")
                except Exception as e:
                    print(f"❌ {e}")
            uploaded += 1
    
    return uploaded


def main():
    parser = argparse.ArgumentParser(description="Sync SENTINEL data to S3")
    parser.add_argument("--bucket", help="S3 bucket name (auto-detected if omitted)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be uploaded without uploading")
    args = parser.parse_args()
    
    print("\n🛡️  SENTINEL — Data Sync to S3")
    print(f"    Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"    Mode: {'DRY RUN' if args.dry_run else 'LIVE UPLOAD'}")
    print()
    
    s3_client = boto3.client("s3")
    
    # Determine bucket
    bucket = args.bucket or find_sentinel_bucket(s3_client)
    if not bucket:
        sys.exit(1)
    
    print(f"\n  Target: s3://{bucket}/\n")
    
    # Sync price data
    print("  ── Precio (Market Data) ──")
    prices_dir = os.path.join(SCRIPT_DIR, "data", "market", "raw")
    count_prices = sync_directory(s3_client, prices_dir, bucket, "raw/prices", args.dry_run)
    
    # Sync sentiment data
    print("\n  ── Sentimiento ──")
    sentiment_dir = os.path.join(SCRIPT_DIR, "data", "sentimental", "raw")
    count_sentiment = sync_directory(s3_client, sentiment_dir, bucket, "raw/sentiment", args.dry_run)
    
    # Summary
    total = count_prices + count_sentiment
    action = "would upload" if args.dry_run else "uploaded"
    print(f"\n  📊 Total: {action} {total} files ({count_prices} prices + {count_sentiment} sentiment)")
    
    if args.dry_run and total > 0:
        print("\n  💡 Run without --dry-run to actually upload:")
        print(f"     python3 sync_to_s3.py --bucket {bucket}")
    
    print()


if __name__ == "__main__":
    main()
