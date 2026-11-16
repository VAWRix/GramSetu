"""
Protected Document Storage utilities for GramSetu platform.

Implements private-by-default decoupled storage, unguessable storage identifiers,
path traversal defenses, file size validation, and SHA-256 integrity verification
in accordance with ADR 0004 and docs/data-model.md Section 7.
"""

import hashlib
import os
import re
from pathlib import Path
from django.conf import settings
from django.core.exceptions import ValidationError, SuspiciousOperation
from apps.core.utils import generate_uuid7

# Maximum permitted file size: 50 MB hard cap (52,428,800 bytes)
MAX_FILE_SIZE_BYTES = 52428800  # 50 * 1024 * 1024

# Permitted MIME types for official government documents
ALLOWED_MIME_TYPES = {
    'application/pdf',
    'image/jpeg',
    'image/png',
    'image/webp',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'text/plain',
    'text/csv',
    'application/zip',
    'application/x-zip-compressed',
    'application/octet-stream',  # fallback when generic binary provided
}

ALLOWED_EXTENSIONS = {
    '.pdf', '.jpg', '.jpeg', '.png', '.webp',
    '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.txt', '.csv', '.zip'
}


def sanitize_filename(filename: str) -> str:
    """
    Sanitizes user-provided original filenames to prevent path traversal,
    header injection, and control characters in Content-Disposition headers.
    """
    if not filename:
        return 'document.dat'
    # Extract basename to strip directory paths
    base = os.path.basename(filename)
    # Remove null bytes and control chars
    base = re.sub(r'[\x00-\x1f\x7f]', '', base)
    # Strip dangerous characters for headers/filenames
    base = re.sub(r'[\\/:*?"<>|]', '_', base)
    # Strip leading/trailing dots or spaces
    base = base.strip('. ')
    return base or 'document.dat'


def get_private_storage_dir() -> Path:
    """
    Returns the resolved Path for protected documents storage directory.
    Ensures directory exists on disk.
    """
    storage_dir = getattr(settings, 'PRIVATE_DOCUMENTS_DIR', settings.BASE_DIR / 'private_docs')
    storage_dir = Path(storage_dir).resolve()
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


def resolve_private_file_path(storage_path: str) -> Path:
    """
    Resolves an internal storage path and enforces strict path traversal defense.
    Raises SuspiciousOperation if the resolved path is outside PRIVATE_DOCUMENTS_DIR.
    """
    if not storage_path:
        raise SuspiciousOperation("Empty storage path.")

    # Guard against obvious path traversal tokens
    if '..' in storage_path or storage_path.startswith('/') or storage_path.startswith('\\'):
        # Extract filename if full path or traversal attempt was passed
        filename = os.path.basename(storage_path)
    else:
        filename = storage_path

    storage_dir = get_private_storage_dir()
    resolved_path = (storage_dir / filename).resolve()

    try:
        resolved_path.relative_to(storage_dir)
    except ValueError:
        raise SuspiciousOperation(f"Path traversal detected for storage path: '{storage_path}'.")

    return resolved_path


def verify_file_integrity(file_path: Path, expected_sha256: str) -> bool:
    """
    Reads physical file from disk in 64 KB chunks and verifies its SHA-256 digest
    matches the expected database checksum.
    """
    if not file_path.exists() or not file_path.is_file():
        return False

    hasher = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while chunk := f.read(65536):
            hasher.update(chunk)

    return hasher.hexdigest().lower() == expected_sha256.lower()


def save_private_document(uploaded_file, custom_uuid=None) -> tuple[str, int, str]:
    """
    Streams an uploaded file into protected private storage:
    - Calculates SHA-256 checksum on the fly.
    - Measures exact byte size.
    - Enforces 50 MB hard cap and non-zero size.
    - Saves using an unguessable UUIDv7 filename (<uuid>.dat).
    
    Returns:
        tuple (storage_path_filename, file_size_bytes, checksum_sha256)
    """
    doc_uuid = custom_uuid or generate_uuid7()
    filename = f"{doc_uuid}.dat"
    storage_dir = get_private_storage_dir()
    destination_path = storage_dir / filename

    hasher = hashlib.sha256()
    total_bytes = 0

    # Ensure file pointer is at beginning
    if hasattr(uploaded_file, 'seek'):
        uploaded_file.seek(0)

    with open(destination_path, 'wb') as dest:
        if hasattr(uploaded_file, 'chunks'):
            for chunk in uploaded_file.chunks():
                total_bytes += len(chunk)
                if total_bytes > MAX_FILE_SIZE_BYTES:
                    # Clean up partial file
                    dest.close()
                    if destination_path.exists():
                        destination_path.unlink()
                    raise ValidationError(
                        f"File size exceeds maximum permitted limit of 50 MB ({MAX_FILE_SIZE_BYTES} bytes)."
                    )
                hasher.update(chunk)
                dest.write(chunk)
        else:
            data = uploaded_file.read()
            total_bytes = len(data)
            if total_bytes > MAX_FILE_SIZE_BYTES:
                dest.close()
                if destination_path.exists():
                    destination_path.unlink()
                raise ValidationError(
                    f"File size exceeds maximum permitted limit of 50 MB ({MAX_FILE_SIZE_BYTES} bytes)."
                )
            hasher.update(data)
            dest.write(data)

    if total_bytes <= 0:
        if destination_path.exists():
            destination_path.unlink()
        raise ValidationError("Uploaded file is empty (0 bytes).")

    checksum_sha256 = hasher.hexdigest()
    return filename, total_bytes, checksum_sha256
