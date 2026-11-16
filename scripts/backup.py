#!/usr/bin/env python3
"""
GramSetu Local Logical Backup Utility

Executes a PostgreSQL-consistent logical backup using least-privilege roles:
- Targets 'dev' (default) via role 'gramsetu_backup' on database 'gramsetu_dev'.
- Targets 'test' via role 'gramsetu_test_runner' on database 'gramsetu_test'.

Pipeline:
1. Executes pg_dump non-interactively (without pseudo-terminal -t) directly to a temporary file in host-mounted volume.
2. Validates process exit status (must be 0).
3. Validates file existence and minimum size floor (> 1024 bytes).
4. Validates archive structural integrity via 'pg_restore --list' on temporary file.
5. Computes SHA-256 cryptographic checksum.
6. Atomically commits the backup by renaming from .tmp to final .dump file.
7. Re-verifies archive structural integrity on the final retained file.
8. Generates a .sha256 checksum verification file.
9. Enforces clean error termination: any failure aborts with non-zero exit code, unlinks temporary artifacts, and never modifies previous known-good backups.
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

target = sys.argv[1].lower() if len(sys.argv) > 1 else 'dev'
if target == 'test':
    DB_NAME = os.getenv('TEST_DB_NAME', 'gramsetu_test')
    BACKUP_USER = os.getenv('TEST_DB_USER', 'gramsetu_test_runner')
    BACKUP_PASSWORD = os.getenv('TEST_DB_PASSWORD')
    if not BACKUP_PASSWORD:
        sys.exit("CRITICAL ERROR: 'TEST_DB_PASSWORD' is not defined in .env")
elif target == 'dev':
    DB_NAME = os.getenv('DEV_DB_NAME', 'gramsetu_dev')
    BACKUP_USER = os.getenv('BACKUP_DB_USER', 'gramsetu_backup')
    BACKUP_PASSWORD = os.getenv('BACKUP_DB_PASSWORD')
    if not BACKUP_PASSWORD:
        sys.exit("CRITICAL ERROR: 'BACKUP_DB_PASSWORD' is not defined in .env")
else:
    sys.exit(f"CRITICAL ERROR: Unknown backup target '{target}'. Permitted targets are 'dev' or 'test'.")

HOST_BACKUP_DIR = BASE_DIR / 'backups'
HOST_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
dump_filename = f"{DB_NAME}_{timestamp}.dump"
tmp_filename = f"{dump_filename}.tmp"

container_tmp_path = f"/var/backups/postgres/{tmp_filename}"
container_final_path = f"/var/backups/postgres/{dump_filename}"
host_tmp_path = HOST_BACKUP_DIR / tmp_filename
host_final_path = HOST_BACKUP_DIR / dump_filename
host_checksum_path = HOST_BACKUP_DIR / f"{dump_filename}.sha256"

print(f">>> [GramSetu Backup] Initiating logical backup for '{DB_NAME}' using role '{BACKUP_USER}'...")

backup_committed = False

try:
    # 1. Execute pg_dump non-interactively without pseudo-terminal (-t)
    dump_cmd = [
        'docker', 'exec', '-i',
        '-e', f'PGPASSWORD={BACKUP_PASSWORD}',
        'gramsetu-postgres',
        'pg_dump',
        '-U', BACKUP_USER,
        '-d', DB_NAME,
        '-Fc',
        '-f', container_tmp_path
    ]

    res = subprocess.run(dump_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"FAILED: pg_dump exited with error code {res.returncode}:\n{res.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    # 2. Verify temporary file existence and minimum size
    if not host_tmp_path.exists():
        print(f"FAILED: Expected temporary backup file does not exist: {host_tmp_path}", file=sys.stderr)
        sys.exit(1)

    tmp_size = host_tmp_path.stat().st_size
    if tmp_size < 1024:
        print(f"FAILED: Backup file size ({tmp_size} bytes) is below minimum threshold (1024 bytes).", file=sys.stderr)
        sys.exit(1)

    # 3. Verify archive catalog structure via pg_restore --list on temporary file
    verify_tmp_cmd = [
        'docker', 'exec', '-i',
        'gramsetu-postgres',
        'pg_restore', '--list', container_tmp_path
    ]
    res_verify = subprocess.run(verify_tmp_cmd, capture_output=True, text=True)
    if res_verify.returncode != 0 or len(res_verify.stdout.strip()) == 0:
        print(f"FAILED: Archive catalog verification failed:\n{res_verify.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    toc_entries = len(res_verify.stdout.strip().splitlines())
    print(f"PASS: Temporary archive TOC verified ({toc_entries} catalog entries).")

    # 4. Compute SHA-256 checksum on temporary file
    sha256 = hashlib.sha256()
    with open(host_tmp_path, 'rb') as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    digest = sha256.hexdigest()
    print(f"PASS: SHA-256 digest computed: {digest}")

    # 5. Atomically commit backup by renaming .tmp to final .dump
    if host_final_path.exists():
        print(f"FAILED: Target backup destination already exists: {host_final_path}", file=sys.stderr)
        sys.exit(1)

    host_tmp_path.rename(host_final_path)
    backup_committed = True

    # 6. Re-verify archive catalog on the final retained file
    verify_final_cmd = [
        'docker', 'exec', '-i',
        'gramsetu-postgres',
        'pg_restore', '--list', container_final_path
    ]
    res_final_verify = subprocess.run(verify_final_cmd, capture_output=True, text=True)
    if res_final_verify.returncode != 0:
        print(f"FAILED: Final archive verification failed on retained file:\n{res_final_verify.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    # 7. Write checksum file
    with open(host_checksum_path, 'w', encoding='utf-8') as f:
        f.write(f"{digest}  {dump_filename}\n")

    print(f">>> [GramSetu Backup] SUCCESS: Backup successfully committed and verified.")
    print(f"    File: {host_final_path}")
    print(f"    Size: {host_final_path.stat().st_size} bytes")
    print(f"    SHA-256: {digest}")

finally:
    # Ensure temporary files are cleaned up if backup was not committed
    if not backup_committed and host_tmp_path.exists():
        try:
            host_tmp_path.unlink()
            print(f">>> [GramSetu Backup] Cleaned up temporary artifact: {host_tmp_path}")
        except Exception as e:
            print(f"WARNING: Could not remove temporary file {host_tmp_path}: {e}", file=sys.stderr)
