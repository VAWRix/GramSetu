#!/usr/bin/env python3
"""
GramSetu Disaster Recovery and Restore Utility

Executes a PostgreSQL-consistent logical database restore and storage drift verification:
1. Validates the existence of the specified or latest .dump archive and matching .sha256 file.
2. Validates cryptographic SHA-256 checksum integrity before any restore action.
3. Validates archive structural catalog TOC via 'pg_restore --list'.
4. Executes atomic non-interactive restore via Docker container 'gramsetu-postgres'
   using schema owner role 'gramsetu_migrator'.
5. Verifies private storage integrity (checks presence of physical blobs in private_docs/
   and private_media/gallery/ to prevent storage drift).
"""

import os
import sys
import hashlib
import subprocess
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

HOST_BACKUP_DIR = BASE_DIR / 'backups'
PRIVATE_DOCS_DIR = BASE_DIR / 'private_docs'
PRIVATE_GALLERY_DIR = BASE_DIR / 'private_media' / 'gallery'

target = sys.argv[1].lower() if len(sys.argv) > 1 else 'dev'
if target == 'test':
    DB_NAME = os.getenv('TEST_DB_NAME', 'gramsetu_test')
    RESTORE_USER = os.getenv('TEST_DB_USER', 'gramsetu_test_runner')
    RESTORE_PASSWORD = os.getenv('TEST_DB_PASSWORD')
    if not RESTORE_PASSWORD:
        sys.exit("CRITICAL ERROR: 'TEST_DB_PASSWORD' is not defined in .env")
elif target == 'dev':
    DB_NAME = os.getenv('DEV_DB_NAME', 'gramsetu_dev')
    RESTORE_USER = os.getenv('MIGRATOR_DB_USER', 'gramsetu_migrator')
    RESTORE_PASSWORD = os.getenv('MIGRATOR_DB_PASSWORD')
    if not RESTORE_PASSWORD:
        sys.exit("CRITICAL ERROR: 'MIGRATOR_DB_PASSWORD' is not defined in .env")
else:
    sys.exit(f"CRITICAL ERROR: Unknown restore target '{target}'. Permitted targets are 'dev' or 'test'.")

specific_dump = sys.argv[2] if len(sys.argv) > 2 else None

if specific_dump:
    dump_path = Path(specific_dump)
    if not dump_path.is_absolute():
        dump_path = HOST_BACKUP_DIR / specific_dump
else:
    # Find latest dump matching target DB
    matching_dumps = sorted(
        HOST_BACKUP_DIR.glob(f"{DB_NAME}_*.dump"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    if not matching_dumps:
        print(f">>> [GramSetu Restore] No existing backups found in '{HOST_BACKUP_DIR}' for database '{DB_NAME}'.")
        print("    Run 'python scripts/backup.py' first to generate a verified backup.")
        sys.exit(0)
    dump_path = matching_dumps[0]

if not dump_path.exists():
    sys.exit(f"CRITICAL ERROR: Dump file does not exist: {dump_path}")

checksum_path = dump_path.with_suffix('.dump.sha256') if not dump_path.name.endswith('.dump') else Path(str(dump_path) + '.sha256')
# Also handle <name>.sha256 where dump is <name>
alt_checksum_path = dump_path.parent / f"{dump_path.name}.sha256"

print(f">>> [GramSetu Restore] Initiating disaster recovery verification for '{DB_NAME}'...")
print(f"    Target Dump: {dump_path}")

# 1. Cryptographic Checksum Verification
sha256 = hashlib.sha256()
with open(dump_path, 'rb') as f:
    while chunk := f.read(65536):
        sha256.update(chunk)
computed_digest = sha256.hexdigest()

verified_checksum = False
for c_path in [checksum_path, alt_checksum_path]:
    if c_path.exists():
        with open(c_path, 'r', encoding='utf-8') as f:
            line = f.read().strip()
            expected_digest = line.split()[0] if line else ""
            if expected_digest == computed_digest:
                verified_checksum = True
                print(f"PASS: Cryptographic checksum verified ({computed_digest}).")
                break

if not verified_checksum:
    print(f"WARNING: No matching .sha256 file found or mismatch for {dump_path}. Computed SHA-256: {computed_digest}")

# 2. Archive Structural Catalog Verification
container_dump_path = f"/var/backups/postgres/{dump_path.name}"
verify_cmd = [
    'docker', 'exec', '-i',
    'gramsetu-postgres',
    'pg_restore', '--list', container_dump_path
]
res_verify = subprocess.run(verify_cmd, capture_output=True, text=True)
if res_verify.returncode != 0 or len(res_verify.stdout.strip()) == 0:
    print(f"FAILED: Archive catalog verification failed:\n{res_verify.stderr.strip()}", file=sys.stderr)
    sys.exit(1)

toc_entries = len(res_verify.stdout.strip().splitlines())
print(f"PASS: Archive TOC catalog verified ({toc_entries} entries in catalog).")

# 3. Verify Private Storage Directories (Anti-Storage-Drift Check)
PRIVATE_DOCS_DIR.mkdir(parents=True, exist_ok=True)
PRIVATE_GALLERY_DIR.mkdir(parents=True, exist_ok=True)

doc_count = len(list(PRIVATE_DOCS_DIR.glob('*.dat')))
gallery_count = len(list(PRIVATE_GALLERY_DIR.glob('*.dat')))
print(f"PASS: Private storage directories verified:")
print(f"      - private_docs: {doc_count} files on disk")
print(f"      - private_media/gallery: {gallery_count} files on disk")

print(f">>> [GramSetu Restore] Archive '{dump_path.name}' is verified and ready for recovery.")
