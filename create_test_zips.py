import zipfile
import os

def create_normal_zip():
    with zipfile.ZipFile("test_workspace.zip", "w") as zf:
        # Valid files
        zf.writestr("notes.txt", "This is a valid text file.")
        zf.writestr("nested/folder/report.pdf", b"%PDF-1.4...")
        zf.writestr("nested/folder/data.csv", "id,name\n1,test") # Unsupported (CSV not in set)
        
        # Hidden files
        zf.writestr(".git/config", "hidden git config")
        zf.writestr("nested/.DS_Store", "hidden mac file")
        
        # Duplicates (same content)
        zf.writestr("notes_duplicate.txt", "This is a valid text file.")

def create_malicious_zip():
    with zipfile.ZipFile("malicious_workspace.zip", "w") as zf:
        zf.writestr("../../../../windows/system32/hacked.txt", "zip slip attack")
        zf.writestr("normal.txt", "this is fine")

if __name__ == "__main__":
    create_normal_zip()
    create_malicious_zip()
    print("Created test_workspace.zip and malicious_workspace.zip")
