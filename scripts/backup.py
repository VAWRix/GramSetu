#!/usr/bin/env python3
"""
GramSetu Local Logical Backup Utility

Executes a PostgreSQL-consistent logical backup using least-privilege role 'gramsetu_backup':
1. Executes pg_dump non-interactively (without pseudo-terminal -t) to a temporary file.
2. Validates process exit status.
3. Validates file existence and minimum size floor.
4. Validates archive structural integrity via 'pg_restore --list'.
5. Computes SHA-256 cryptographic checksum.
6. Atomically commits the backup by renaming from .tmp to .dump.
7. Generates a .sha256 checksum verification file.
"""

import os
import sys
import hashlib
import datetime
import subprocess
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

BACKUP_USER = os.getenv('BACKUP_DB_USER', 'gramsetu_backup')
BACKUP_PASSWORD = os.getenv('BACKUP_DB_PASSWORD')
DEV_DB_NAME = os.getenv('DEV_DB_NAME', 'gramsetu_dev')
HOST_BACKUP_DIR = BASE_DIR / 'backups'

if not BACKUP_PASSWORD:
    sys.exit("CRITICAL ERROR: 'BACKUP_DB_PASSWORD' is not defined in .env")

HOST_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
dump_filename = f"{DEV_DB_NAME}_{timestamp}.dump"
tmp_filename = f"{dump_filename}.tmp"

container_tmp_path = f"/var/backups/postgres/{tmp_filename}"
container_final_path = f"/var/backups/postgres/{dump_filename}"
host_tmp_path = HOST_BACKUP_DIR / tmp_filename
host_final_path = HOST_BACKUP_DIR / dump_filename
host_checksum_path = HOST_BACKUP_DIR / f"{dump_filename}.sha256"

print(f">>> [GramSetu Backup] Starting logical backup for '{DEV_DB_NAME}'...")

# 1. Execute pg_dump non-interactively to temporary path
dump_cmd = [
    'docker', 'exec', '-i',
    '-e', f'PGPASSWORD={BACKUP_PASSWORD}',
    'gramsetu-postgres',
    'pg_dump',
    '-U', BACKUP_USER,
    '-d', DEV_DB_NAME,
    '-Fc',
    '-f', container_tmp_path
]

res = subprocess.run(dump_cmd, capture_output=True, text=True)
if res.returncode != 0:
    print(f"FAILED: pg_dump exited with code {res.returncode}:\n{res.stderr}", file=sys.stderr)
    if host_tmp_path.exists():
        host_tmp_path.unlink()
    sys.exit(1)

# 2. Verify file existence and non-zero size
if not host_tmp_path.exists() or host_tmp_path.stat().st_size < 1024:
    print("FAILED: Output dump file does not exist or is smaller than 1KB threshold.", file=sys.stderr)
    if host_tmp_path.exists():
        host_tmp_path.unlink()
    sys.exit(1)

# 3. Verify archive catalog structure via pg_restore --list
verify_cmd = [
    'docker', 'exec', '-i',
    'gramsetu-postgres',
    'pg_restore', '--list', container_tmp_path
]

res_verify = subprocess.run(verify_cmd, capture_output=True, text=True)
if res_verify.returncode != 0 or len(res_verify.stdout.strip()) == 0:
    print(f"FAILED: Archive header validation failed:\n{res_verify.stderr}", file=sys.stderr)
    if host_tmp_path.exists():
        host_tmp_path.unlink()
    sys.exit(1)

entry_count = len(res_verify.stdout.strip().splitlines())
print(f"PASS: Archive structure validated successfully ({entry_count} catalog entries).")

# 4. Calculate SHA-256 checksum
sha256 = hashlib.sha256()
with open(host_tmp_path, 'rb') as f:
    while chunk := f.read(65536):
        sha256.update(chunk)
digest = sha256.hexdigest()
print(f"PASS: SHA-256 computed: {digest}")

# 5. Atomic rename to final path
if host_final_path.exists():
    host_final_path.unlink()
host_tmp_path.rename(host_final_path)

# 6. Save checksum file
with open(host_checksum_path, 'w', encoding='utf-8') as f:
    f.write(f"{digest}  {dump_filename}\n")

print(f">>> [GramSetu Backup] SUCCESS! Backup completed: {host_final_path}")
print(f"    Size: {host_final_path.stat().st_size} bytes")
