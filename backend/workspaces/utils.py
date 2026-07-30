import os
import shutil
import zipfile
import hashlib
import mimetypes
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from workspaces.models import File, FileStatus

# List of extensions we support
SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".txt", ".md", ".markdown", ".pptx",
    ".jpg", ".jpeg", ".png", ".gif", ".webp"
}

# Directories we should always ignore
IGNORED_DIRS = {".git", ".DS_Store", "__pycache__", "node_modules", ".idea", ".vscode"}

def is_safe_path(base_dir: Path, target_path: str) -> bool:
    """
    Prevents Zip Slip attacks by ensuring the target path is strictly within the base directory.
    """
    resolved_target = (base_dir / target_path).resolve()
    resolved_base = base_dir.resolve()
    return str(resolved_target).startswith(str(resolved_base))

def secure_extract(zip_path: Path, extract_dir: Path):
    """
    Extracts a ZIP file securely, protecting against Zip Slip path traversal.
    """
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        for member in zip_ref.namelist():
            if not is_safe_path(extract_dir, member):
                raise ValueError(f"Malicious path detected in ZIP: {member}")
            zip_ref.extract(member, extract_dir)

def get_file_hash(filepath: Path) -> str:
    """
    Calculates the SHA-256 hash of a file.
    """
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        # Read in chunks for large files
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

async def scan_and_process_workspace(workspace_id: int, extract_dir: Path, db: AsyncSession):
    """
    Recursively scans the extracted directory, ignores junk/unsupported files, 
    calculates hashes, and saves File records to the database.
    """
    files_to_create = []
    
    for root, dirs, files in os.walk(extract_dir):
        # Modify dirs in-place to prevent os.walk from traversing ignored directories
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
        
        for file in files:
            # Ignore hidden files
            if file.startswith("."):
                continue
                
            filepath = Path(root) / file
            ext = filepath.suffix.lower()
            
            # If unsupported, delete it to save space
            if ext not in SUPPORTED_EXTENSIONS:
                os.remove(filepath)
                continue
                
            # Get relative path for the DB
            rel_path = filepath.relative_to(extract_dir).as_posix()
            
            # Hash file
            file_hash = get_file_hash(filepath)
            
            # Size
            size = filepath.stat().st_size
            
            # Mime type
            mime_type, _ = mimetypes.guess_type(filepath)
            if mime_type is None:
                mime_type = "application/octet-stream"
                
            new_file = File(
                workspace_id=workspace_id,
                relative_path=rel_path,
                file_hash=file_hash,
                mime_type=mime_type,
                size=size,
                status=FileStatus.EXTRACTED
            )
            files_to_create.append(new_file)
            
    if files_to_create:
        db.add_all(files_to_create)
        await db.commit()
