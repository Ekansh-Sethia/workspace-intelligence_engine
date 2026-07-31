import pytest
import os
import shutil
import zipfile
from pathlib import Path

# Import all models to ensure SQLAlchemy mappers initialize correctly
import authentication.models
from workspaces.utils import is_safe_path, secure_extract, get_file_hash, scan_and_process_workspace
from workspaces.models import File, FileStatus
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def temp_workspace_dir(tmp_path):
    """Fixture to provide a temporary directory for workspace tests"""
    workspace_dir = tmp_path / "workspace_test"
    workspace_dir.mkdir()
    yield workspace_dir

@pytest.mark.parametrize("target_path, expected_is_safe", [
    ("safe_file.txt", True),
    ("nested/safe_file.txt", True),
    ("nested/deeply/safe_file.pdf", True),
    ("../malicious.txt", False),
    ("../../etc/passwd", False),
    ("../../../windows/system32", False),
    (r"..\..\malicious.exe", False) if os.name == 'nt' else ("../../malicious.exe", False),
    ("C:\\malicious.txt" if os.name == 'nt' else "/etc/passwd", False),
])
def test_is_safe_path(temp_workspace_dir, target_path, expected_is_safe):
    """Generalized test for Zip Slip path traversal prevention"""
    assert is_safe_path(temp_workspace_dir, target_path) == expected_is_safe

def test_secure_extract(temp_workspace_dir):
    """Test safe extraction of a normal zip file"""
    zip_path = temp_workspace_dir / "test.zip"
    extract_dir = temp_workspace_dir / "extracted"
    extract_dir.mkdir()
    
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr("file1.txt", "content 1")
        zf.writestr("nested/file2.txt", "content 2")
        
    secure_extract(zip_path, extract_dir)
    assert (extract_dir / "file1.txt").exists()
    assert (extract_dir / "nested" / "file2.txt").exists()

@pytest.mark.parametrize("malicious_path", [
    "../escaped.txt",
    "../../etc/passwd",
    "nested/../../../root.txt",
    "/absolute/path/test.txt" if os.name != 'nt' else "C:\\absolute\\path\\test.txt"
])
def test_secure_extract_malicious(temp_workspace_dir, malicious_path):
    """Generalized test for secure_extract blocking malicious zip files"""
    zip_path = temp_workspace_dir / "malicious.zip"
    extract_dir = temp_workspace_dir / "extracted_malicious"
    extract_dir.mkdir()
    
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr(malicious_path, "malicious content")
        
    with pytest.raises(ValueError, match="Malicious path detected"):
        secure_extract(zip_path, extract_dir)

@pytest.mark.parametrize("content, expected_hash", [
    ("hello world", "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"),
    ("", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    ("Workspace Intelligence", "47f90192edd007c7af9cb6af445fdf109d5e8ee7806f128d0ed51f137248862b")
])
def test_get_file_hash(temp_workspace_dir, content, expected_hash):
    """Generalized test for SHA-256 file hashing"""
    test_file = temp_workspace_dir / "hash_test.txt"
    test_file.write_text(content)
    assert get_file_hash(test_file) == expected_hash

@pytest.mark.anyio
@pytest.mark.parametrize("test_files, expected_valid_count, expected_ignored_paths", [
    # Scenario 1: Basic valid vs invalid extensions
    (
        {"valid.txt": "t", "valid.pdf": "p", "invalid.exe": "e", "invalid.dll": "d"},
        2, 
        ["invalid.exe", "invalid.dll"]
    ),
    # Scenario 2: Hidden files and ignored directories
    (
        {".hidden.txt": "h", ".git/config": "g", "node_modules/pkg.json": "n", "valid.md": "m"},
        1,
        [".hidden.txt", ".git/config", "node_modules/pkg.json"]
    ),
    # Scenario 3: Deeply nested files
    (
        {"nested/deeply/valid.docx": "d", "nested/deeply/invalid.bin": "b"},
        1,
        ["nested/deeply/invalid.bin"]
    )
])
async def test_scan_and_process_workspace_generalized(
    temp_workspace_dir, test_files, expected_valid_count, expected_ignored_paths
):
    """Generalized test for recursive traversal, filtering, and DB record creation"""
    extract_dir = temp_workspace_dir / "extracted_scan"
    extract_dir.mkdir()
    
    # Setup files based on parametrized dictionary
    for rel_path, content in test_files.items():
        full_path = extract_dir / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        
    mock_db = MagicMock()
    mock_db.commit = AsyncMock()
    
    await scan_and_process_workspace(workspace_id=1, extract_dir=extract_dir, db=mock_db)
    
    # If there are expected valid files, ensure add_all was called
    if expected_valid_count > 0:
        assert mock_db.add_all.called
        files_added = mock_db.add_all.call_args[0][0]
        assert len(files_added) == expected_valid_count
        
        # Verify ignored paths are NOT in the database records
        added_paths = [f.relative_path.replace("\\", "/") for f in files_added]
        for ignored_path in expected_ignored_paths:
            assert ignored_path not in added_paths
            
    # Verify that invalid files were actually deleted from the disk
    for rel_path in expected_ignored_paths:
        # Note: ignored directories (.git, node_modules) aren't deleted by the function,
        # they are just skipped. Unsupported file extensions ARE deleted.
        full_path = extract_dir / rel_path
        if not any(ignored_dir in rel_path for ignored_dir in [".git", "node_modules"]) and not rel_path.startswith("."):
            assert not full_path.exists()
