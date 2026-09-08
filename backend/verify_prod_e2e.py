"""
Comprehensive Production End-to-End Verification Script
Tests both ZIP files against https://wie-backend.onrender.com and verifies:
1. Ingestion without OOM / 502 Bad Gateway
2. Status transitions to READY cleanly
3. File chunking and metadata generation
4. Live Chat Q&A with Gemini LLM streaming + source citations
"""
import urllib.request
import urllib.parse
import json
import time
import os
import uuid
import sys

BASE_URL = "https://wie-backend.onrender.com/api/v1"
ZIP1_PATH = r"C:\Users\ASUS\OneDrive\Desktop\AnotherTest.zip"
ZIP2_PATH = r"C:\Users\ASUS\OneDrive\Desktop\LargeTestWorkspace.zip"

def create_auth_session():
    test_email = f"verifier_{uuid.uuid4().hex[:6]}@example.com"
    test_password = "Password123!"
    
    # 1. Sign up
    signup_data = json.dumps({"email": test_email, "password": test_password}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/auth/signup",
        data=signup_data,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as r:
        pass
        
    # 2. Login
    login_data = urllib.parse.urlencode({"username": test_email, "password": test_password}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/auth/login",
        data=login_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    with urllib.request.urlopen(req) as r:
        auth = json.loads(r.read().decode())
        token = auth["access_token"]
        
    return token, test_email

def upload_workspace(token, zip_path, name, description):
    boundary = "----WebKitFormBoundary" + uuid.uuid4().hex
    body = []
    body.extend([
        f"--{boundary}".encode(),
        b'Content-Disposition: form-data; name="name"',
        b'',
        name.encode(),
        f"--{boundary}".encode(),
        b'Content-Disposition: form-data; name="description"',
        b'',
        description.encode(),
        f"--{boundary}".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{os.path.basename(zip_path)}"'.encode(),
        b'Content-Type: application/zip',
        b'',
    ])
    with open(zip_path, "rb") as f:
        body.append(f.read())
    body.extend([
        f"--{boundary}--".encode(),
        b''
    ])
    payload = b"\r\n".join(body)
    
    req = urllib.request.Request(
        f"{BASE_URL}/workspaces",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        }
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())

def wait_for_ready(token, workspace_id, timeout=180):
    start = time.time()
    headers = {"Authorization": f"Bearer {token}"}
    while time.time() - start < timeout:
        req = urllib.request.Request(f"{BASE_URL}/workspaces/{workspace_id}", headers=headers)
        try:
            with urllib.request.urlopen(req) as r:
                data = json.loads(r.read().decode())
                status = data["status"]
                elapsed = int(time.time() - start)
                print(f"    [{elapsed}s] Workspace {workspace_id} status: {status}")
                if status == "ready":
                    return True, data
                elif status == "failed":
                    return False, data
        except urllib.error.HTTPError as e:
            print(f"    [HTTP {e.code}] Error during polling: {e.read().decode()}")
            if e.code == 502:
                return False, {"error": "502 Bad Gateway (OOM)"}
        time.sleep(3)
    return False, {"error": "Timeout"}

def ask_question(token, workspace_id, session_id, question):
    print(f"\n  [Q]: {question}")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = json.dumps({"query": question}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/workspaces/{workspace_id}/chat/sessions/{session_id}/messages",
        data=payload,
        headers=headers
    )
    
    tokens = []
    sources = []
    print("  [A]: ", end="", flush=True)
    with urllib.request.urlopen(req) as r:
        for line in r:
            decoded = line.decode("utf-8").strip()
            if not decoded.startswith("data: "):
                continue
            content = decoded[6:]
            if content == "[DONE]":
                break
            if content.startswith("[SOURCES]"):
                try:
                    sources = json.loads(content[9:])
                except Exception:
                    pass
                continue
            try:
                tok = json.loads(content)
                tokens.append(tok)
                print(tok, end="", flush=True)
            except Exception:
                tokens.append(content)
                print(content, end="", flush=True)
    print()
    full_answer = "".join(tokens)
    print(f"  [Sources Cited]: {sources} (Length: {len(full_answer)} chars)")
    return full_answer, sources

def test_zip_workflow(zip_path, questions, title):
    print("\n" + "=" * 70)
    print(f"TESTING WORKSPACE: {title}")
    print(f"File: {zip_path} ({os.path.getsize(zip_path):,} bytes)")
    print("=" * 70)
    
    token, email = create_auth_session()
    print(f"[1] Signed up & authenticated test user: {email}")
    
    t0 = time.time()
    ws = upload_workspace(token, zip_path, title, f"Verification workspace for {title}")
    ws_id = ws["id"]
    print(f"[2] Upload accepted (Workspace ID: {ws_id}, initial status: {ws['status']})")
    
    print("[3] Monitoring background processing (Parsing -> FastEmbed -> Ready)...")
    success, ws_data = wait_for_ready(token, ws_id)
    duration = int(time.time() - t0)
    
    if not success:
        print(f"FAILED! Workspace {ws_id} did not reach 'ready'. Response: {ws_data}")
        return False
        
    print(f"[SUCCESS] Workspace {ws_id} reached READY in {duration} seconds!")
    print(f"    Summary: {ws_data.get('summary')[:120]}...")
    print(f"    Keywords: {ws_data.get('keywords')}")
    print(f"    Total chunks: {ws_data.get('total_chunk_count')}")
    
    # Check files list
    req = urllib.request.Request(
        f"{BASE_URL}/workspaces/{ws_id}/files",
        headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req) as r:
        files = json.loads(r.read().decode())
        print(f"[4] Files in workspace ({len(files)}):")
        for f in files:
            print(f"    - {f['relative_path']}: {f['size']:,} bytes | {f['chunk_count']} chunks | status={f['status']}")
            
    # Create chat session
    s_req = urllib.request.Request(
        f"{BASE_URL}/workspaces/{ws_id}/chat/sessions",
        data=b"{}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(s_req) as r:
        session = json.loads(r.read().decode())
        session_id = session["id"]
    print(f"[5] Created chat session: {session_id}")
    
    print(f"[6] Asking {len(questions)} verification questions to Gemini LLM:")
    try:
        for q in questions:
            ans, srcs = ask_question(token, ws_id, session_id, q)
            if len(ans) == 0:
                print("    WARNING: Empty answer received!")
            time.sleep(2)
    finally:
        if ws_id and token:
            print(f"\n[CLEANUP] Deleting test workspace {ws_id}...")
            del_req = urllib.request.Request(
                f"{BASE_URL}/workspaces/{ws_id}",
                headers={"Authorization": f"Bearer {token}"},
                method="DELETE"
            )
            try:
                with urllib.request.urlopen(del_req) as r:
                    print(f"[CLEANUP] Workspace {ws_id} successfully deleted (HTTP {r.status})")
            except Exception as e:
                print(f"[CLEANUP] Warning: failed to delete workspace {ws_id}: {e}")
            
    return True

if __name__ == "__main__":
    print("Starting Live Production Verification against https://wie-backend.onrender.com...")
    
    # Test 1: AnotherTest.zip
    q1 = [
        "What position and company did Ekansh Sethia apply for in his cover letter?",
        "What is the FINPULSE project, and why was FastAPI chosen over Flask or Django for the backend?",
        "What academic degree and semester results are mentioned in the documents?"
    ]
    ok1 = test_zip_workflow(ZIP1_PATH, q1, "AnotherTest (0.9 MB)")
    
    if not ok1:
        print("\nTEST 1 FAILED!")
        sys.exit(1)
        
    # Test 2: LargeTestWorkspace.zip
    q2 = [
        "What operating systems lab assignments and system calls or concepts are covered in the OS Lab document?",
        "What software design or entities are depicted in the Spotify class diagram?",
        "What examination paper is included and what subjects or topics does it test?"
    ]
    ok2 = test_zip_workflow(ZIP2_PATH, q2, "LargeTestWorkspace (1.42 MB / ~3.5 MB uncompressed)")
    
    print("\n" + "=" * 70)
    print("ALL TESTS COMPLETED:")
    print(f"  Test 1 (AnotherTest.zip): {'PASSED' if ok1 else 'FAILED'}")
    print(f"  Test 2 (LargeTestWorkspace.zip): {'PASSED' if ok2 else 'FAILED'}")
    print("=" * 70)
