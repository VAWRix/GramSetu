"""
Protected Gallery Image Storage utilities for GramSetu platform.

Implements private-by-default decoupled storage, unguessable storage identifiers,
path traversal defenses, file size validation, magic-byte MIME verification,
and SHA-256 integrity verification in accordance with docs/data-model.md Section 4.9 & 7.
"""

import hashlib
import ipaddress
import os
import re
import socket
import urllib.parse
from pathlib import Path
from django.conf import settings
from django.core.exceptions import ValidationError, SuspiciousOperation
from apps.core.utils import generate_uuid7

# Maximum permitted image size: 15 MB (15,728,640 bytes)
MAX_IMAGE_SIZE_BYTES = 15728640  # 15 * 1024 * 1024

# Permitted MIME types for official Panchayat photographs
ALLOWED_IMAGE_MIME_TYPES = {
    'image/jpeg',
    'image/png',
    'image/webp',
}

ALLOWED_IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.webp',
}


def sanitize_filename(filename: str) -> str:
    """
    Sanitizes user-provided original filenames to prevent path traversal,
    header injection, and control characters in Content-Disposition headers.
    """
    if not filename:
        return 'image.jpg'
    base = os.path.basename(filename)
    base = re.sub(r'[\x00-\x1f\x7f]', '', base)
    base = re.sub(r'[\\/:*?"<>|]', '_', base)
    base = base.strip('. ')
    return base or 'image.jpg'


def get_private_gallery_dir() -> Path:
    """
    Returns the resolved Path for protected gallery storage directory.
    Ensures directory exists on disk.
    """
    storage_dir = getattr(settings, 'PRIVATE_GALLERY_DIR', settings.BASE_DIR / 'private_media' / 'gallery')
    storage_dir = Path(storage_dir).resolve()
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


def resolve_private_gallery_path(storage_path: str) -> Path:
    """
    Resolves an internal storage path and enforces strict path traversal defense.
    Raises SuspiciousOperation if the resolved path is outside PRIVATE_GALLERY_DIR.
    """
    if not storage_path:
        raise SuspiciousOperation("Empty storage path.")

    # Guard against obvious path traversal tokens
    if '..' in storage_path or storage_path.startswith('/') or storage_path.startswith('\\'):
        filename = os.path.basename(storage_path)
    else:
        filename = storage_path

    storage_dir = get_private_gallery_dir()
    resolved_path = (storage_dir / filename).resolve()

    try:
        resolved_path.relative_to(storage_dir)
    except ValueError:
        raise SuspiciousOperation(f"Path traversal detected for storage path: '{storage_path}'.")

    return resolved_path


def detect_image_mime(header: bytes) -> str | None:
    """
    Inspects leading bytes (magic numbers) of file stream to determine image MIME type.
    """
    if len(header) >= 3 and header[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if len(header) >= 8 and header[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if len(header) >= 12 and header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return 'image/webp'
    return None


def validate_image_file(file_obj, filename: str = ""):
    """
    Validates uploaded image file against size cap, extension whitelist,
    and magic byte header verification.
    """
    # 1. Size check
    file_size = file_obj.size if hasattr(file_obj, 'size') else 0
    if file_size <= 0:
        raise ValidationError("Uploaded file is empty (0 bytes).")
    if file_size > MAX_IMAGE_SIZE_BYTES:
        raise ValidationError(
            f"Image file size ({file_size} bytes) exceeds maximum limit of 15 MB."
        )

    # 2. Extension check
    name_to_check = filename or getattr(file_obj, 'name', '')
    ext = os.path.splitext(name_to_check)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(
            f"Image extension '{ext}' is not permitted. Allowed: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}."
        )

    # 3. Magic bytes inspection
    pos = file_obj.tell() if hasattr(file_obj, 'tell') else 0
    header = file_obj.read(32)
    if hasattr(file_obj, 'seek'):
        file_obj.seek(pos)

    detected_mime = detect_image_mime(header)
    if not detected_mime or detected_mime not in ALLOWED_IMAGE_MIME_TYPES:
        raise ValidationError(
            "File header verification failed: file is not a valid JPEG, PNG, or WebP image."
        )

    return detected_mime


def save_gallery_image(file_obj, original_filename: str = "") -> tuple[str, str, int, str, str]:
    """
    Saves an uploaded image binary to protected disk storage under an unguessable UUID filename.
    Computes cryptographic SHA-256 hash.
    Returns: (storage_path, sanitized_filename, file_size_bytes, mime_type, checksum_sha256)
    """
    clean_name = sanitize_filename(original_filename or getattr(file_obj, 'name', 'photo.jpg'))
    detected_mime = validate_image_file(file_obj, clean_name)

    storage_dir = get_private_gallery_dir()
    storage_uuid = generate_uuid7()
    ext = os.path.splitext(clean_name)[1].lower() or '.jpg'
    storage_filename = f"{storage_uuid}{ext}.dat"
    dest_path = storage_dir / storage_filename

    sha256 = hashlib.sha256()
    bytes_written = 0

    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)

    with open(dest_path, 'wb') as dest:
        for chunk in file_obj.chunks() if hasattr(file_obj, 'chunks') else [file_obj.read()]:
            if not chunk:
                break
            sha256.update(chunk)
            dest.write(chunk)
            bytes_written += len(chunk)

    checksum = sha256.hexdigest()
    return storage_filename, clean_name, bytes_written, detected_mime, checksum


def verify_gallery_image_integrity(storage_path: str, expected_sha256: str) -> bool:
    """
    Verifies disk image integrity against expected SHA-256 checksum.
    """
    try:
        resolved = resolve_private_gallery_path(storage_path)
    except SuspiciousOperation:
        return False

    if not resolved.exists() or not resolved.is_file():
        return False

    sha256 = hashlib.sha256()
    with open(resolved, 'rb') as f:
        while chunk := f.read(65536):
            sha256.update(chunk)

    return sha256.hexdigest() == expected_sha256


def delete_private_gallery_file(storage_path: str) -> bool:
    """
    Safely deletes a private gallery image file from disk.
    """
    try:
        resolved = resolve_private_gallery_path(storage_path)
        if resolved.exists() and resolved.is_file():
            resolved.unlink()
            return True
    except (SuspiciousOperation, OSError):
        pass
    return False


def convert_and_validate_image_url(raw_url: str) -> tuple[str, str | None]:
    """
    Validates an external image URL for SSRF vulnerabilities and translates
    Google Drive share links to direct image stream URLs.
    """
    if not raw_url or not isinstance(raw_url, str):
        return "", "Invalid URL provided."

    url = raw_url.strip()

    # Reject unsupported Google Drive links (e.g. folders, documents, spreadsheets)
    if 'drive.google.com/drive/' in url and ('folders/' in url or 'my-drive' in url):
        return "", "Google Drive folder links cannot be rendered as photographs. Please provide a direct share link to an individual image file."
    if 'docs.google.com' in url:
        return "", "Google Docs or Sheets links cannot be displayed as images. Please provide a direct image file link."

    # Convert Google Drive links:
    # Pattern 1: https://drive.google.com/file/d/<ID>/view...
    drive_file_match = re.search(r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)', url)
    if drive_file_match:
        file_id = drive_file_match.group(1)
        url = f"https://drive.google.com/uc?export=view&id={file_id}"
    else:
        # Pattern 2: https://drive.google.com/open?id=<ID>
        drive_id_match = re.search(r'drive\.google\.com/(?:open|uc)\?(?:[^&]*&)*id=([a-zA-Z0-9_-]+)', url)
        if drive_id_match:
            file_id = drive_id_match.group(1)
            url = f"https://drive.google.com/uc?export=view&id={file_id}"

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in ('http', 'https'):
        return "", "Only http and https protocols are permitted."

    hostname = parsed.hostname
    if not hostname:
        return "", "URL must include a valid hostname."

    # Prevent loopback and local names directly
    if hostname.lower() in ('localhost', '127.0.0.1', '::1', '0.0.0.0', 'local', 'test'):
        return "", "Access to localhost or loopback addresses is forbidden."

    # Resolve IP and check for private, loopback, link-local, multicast addresses (SSRF defense)
    try:
        addr_info = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == 'https' else 80))
        for res in addr_info:
            ip_str = res[4][0]
            ip_obj = ipaddress.ip_address(ip_str)
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_multicast or ip_obj.is_reserved:
                return "", f"Security policy violation: Access to private or internal IP ({ip_str}) is blocked."
    except socket.gaierror:
        # If hostname resolution fails: fail closed
        return "", f"Could not resolve hostname '{hostname}'. Please provide an accessible public URL."
    except Exception as e:
        return "", f"URL validation failed: {str(e)}"

    return url, None
