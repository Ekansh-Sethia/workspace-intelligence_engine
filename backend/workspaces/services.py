import os
import shutil
import zipfile
from pathlib import Path
from fastapi import UploadFile, HTTPException, status
from utils.logger import logger

STORAGE_DIR = Path("local_storage")

async def save_and_extract_workspace(workspace_id: int, file: UploadFile):
    # Create workspace directory
    ws_dir = STORAGE_DIR / str(workspace_id)
    raw_dir = ws_dir / "raw"
    
    os.makedirs(raw_dir, exist_ok=True)
    
    zip_path = ws_dir / "archive.zip"
    
    # 1. Save ZIP
    try:
        with open(zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Failed to save zip for workspace {workspace_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save uploaded file")
        
    # 2. Basic Validation & Extraction
    try:
        if not zipfile.is_zipfile(zip_path):
            raise ValueError("Uploaded file is not a valid ZIP archive")
            
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Check for empty zip
            if len(zip_ref.namelist()) == 0:
                raise ValueError("ZIP archive is empty")
                
            zip_ref.extractall(raw_dir)
            
    except ValueError as ve:
        # Clean up on validation failure
        shutil.rmtree(ws_dir)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to extract zip for workspace {workspace_id}: {e}")
        shutil.rmtree(ws_dir)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to extract archive")

def delete_workspace_storage(workspace_id: int):
    ws_dir = STORAGE_DIR / str(workspace_id)
    if ws_dir.exists():
        shutil.rmtree(ws_dir, ignore_errors=True)
