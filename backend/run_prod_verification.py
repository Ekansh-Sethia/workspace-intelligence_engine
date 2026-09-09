"""
Comprehensive Production End-to-End Test Script
Tests both ZIP files (< 5MB) on live production:
https://wie-backend.onrender.com

Verifies:
- User signup and login
- ZIP file upload & status transition to READY
- Ingestion memory stability (monitored via /api/v1/health)
- Chat session creation
- Multi-question Q&A streaming with Gemini LLM & FastEmbed vector search
- Ground-truth validation (expected vs actual)
- Source citations
- Full cleanup (workspace deletion)
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

def get_health_memory():
    try:
        req = urllib.request.Request(f"{BASE_URL}/health")
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
            return data.get("memory", {})
    except Exception as e:
        return {"error": str(e)}

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
    with urllib.request.urlopen(req, timeout=15) as r:
        pass
        
    # 2. Login
    login_data = urllib.parse.urlencode({"username": test_email, "password": test_password}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/auth/login",
        data=login_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
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
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def wait_for_ready(token, workspace_id, timeout=240):
    start = time.time()
    headers = {"Authorization": f"Bearer {token}"}
    last_status = None
    while time.time() - start < timeout:
        req = urllib.request.Request(f"{BASE_URL}/workspaces/{workspace_id}", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())
                status = data["status"]
                elapsed = int(time.time() - start)
                if status != last_status:
                    print(f"    [{elapsed}s] Workspace {workspace_id} status: {status}")
                    last_status = status
                if status == "ready":
                    return True, data
                elif status == "failed":
                    return False, data
        except urllib.error.HTTPError as e:
            print(f"    [HTTP {e.code}] Error during polling: {e.read().decode()}")
            if e.code == 502:
                return False, {"error": "502 Bad Gateway (OOM)"}
        except Exception as exc:
            elapsed = int(time.time() - start)
            print(f"    [{elapsed}s] Polling network retry: {type(exc).__name__}")
        time.sleep(4)
    return False, {"error": "Timeout"}

def ask_question(token, workspace_id, session_id, question):
    print(f"\n  [Question]: {question}")
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
    print("  [Response]: ", end="", flush=True)
    with urllib.request.urlopen(req, timeout=60) as r:
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
    print(f"  [Sources]: {sources}")
    return full_answer, sources

def test_workspace(zip_path, title, test_cases):
    print("\n" + "=" * 75)
    print(f"STARTING TEST: {title}")
    print(f"File: {zip_path} ({os.path.getsize(zip_path):,} bytes)")
    print("=" * 75)
    
    mem_before = get_health_memory()
    print(f"[Memory Before] VmRSS: {mem_before.get('VmRSS', 'N/A')}, VmHWM: {mem_before.get('VmHWM', 'N/A')}")
    
    token, email = create_auth_session()
    print(f"[1] Authenticated test user: {email}")
    
    t0 = time.time()
    ws = upload_workspace(token, zip_path, title, f"Production verification for {title}")
    ws_id = ws["id"]
    print(f"[2] Upload accepted. Workspace ID: {ws_id}, Initial Status: {ws['status']}")
    
    print("[3] Monitoring background ingestion (Parsing -> FastEmbed -> Summarizing -> Ready)...")
    success, ws_data = wait_for_ready(token, ws_id)
    duration = int(time.time() - t0)
    
    if not success:
        print(f"FAILED! Workspace {ws_id} did not reach ready. Details: {ws_data}")
        return False, []
        
    print(f"[SUCCESS] Reached READY in {duration}s!")
    print(f"    Summary: {ws_data.get('summary', '')[:100]}...")
    print(f"    Keywords: {ws_data.get('keywords')}")
    print(f"    Chunks: {ws_data.get('total_chunk_count')}")
    
    mem_after_ingest = get_health_memory()
    print(f"[Memory After Ingest] VmRSS: {mem_after_ingest.get('VmRSS', 'N/A')}, VmHWM: {mem_after_ingest.get('VmHWM', 'N/A')}")
    
    # Create chat session
    s_req = urllib.request.Request(
        f"{BASE_URL}/workspaces/{ws_id}/chat/sessions",
        data=b"{}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(s_req, timeout=15) as r:
        session = json.loads(r.read().decode())
        session_id = session["id"]
    print(f"[4] Chat session initialized: {session_id}")
    
    results = []
    try:
        print(f"[5] Running Q&A verification ({len(test_cases)} questions)...")
        for tc in test_cases:
            q = tc["question"]
            expected = tc["expected"]
            keywords = tc["must_contain"]
            
            actual_answer, sources = ask_question(token, ws_id, session_id, q)
            
            # Check keyword presence in actual answer
            matched_kw = [k for k in keywords if k.lower() in actual_answer.lower()]
            match_rate = len(matched_kw) / len(keywords) if keywords else 1.0
            passed = match_rate >= 0.5 and len(actual_answer) > 20
            
            results.append({
                "question": q,
                "expected": expected,
                "actual": actual_answer,
                "sources": sources,
                "passed": passed,
                "matched_keywords": matched_kw,
                "all_keywords": keywords,
            })
            time.sleep(12)
    finally:
        # Cleanup workspace
        print(f"\n[6] Cleanup: Deleting test workspace {ws_id}...")
        del_req = urllib.request.Request(
            f"{BASE_URL}/workspaces/{ws_id}",
            headers={"Authorization": f"Bearer {token}"},
            method="DELETE"
        )
        try:
            with urllib.request.urlopen(del_req, timeout=15) as r:
                print(f"    Workspace {ws_id} deleted successfully (HTTP {r.status})")
        except Exception as e:
            print(f"    Warning deleting workspace {ws_id}: {e}")
            
    mem_after_test = get_health_memory()
    print(f"[Memory After Test & Cleanup] VmRSS: {mem_after_test.get('VmRSS', 'N/A')}, VmHWM: {mem_after_test.get('VmHWM', 'N/A')}")
    
    return True, results

if __name__ == "__main__":
    print("=" * 75)
    print("PRODUCTION END-TO-END VERIFICATION (< 5MB LIMIT)")
    print("Backend URL: https://wie-backend.onrender.com")
    print("=" * 75)
    
    # Test Suite 1: AnotherTest.zip (0.86 MB)
    test_cases_1 = [
        {
            "question": "What company and role did Ekansh Sethia apply for in his cover letter, and what university is he attending?",
            "expected": "Applied to Goldman Sachs for the Engineering Summer Analyst (Summer Analyst - Engineering Division) role. University is Sri G.S. Institute of Technology and Science (SGSITS), Indore.",
            "must_contain": ["Goldman", "Analyst", "SGSITS"]
        },
        {
            "question": "In the FINPULSE interview questions, why was FastAPI selected over Django or Flask for the backend?",
            "expected": "FastAPI was selected for performance (Starlette/Pydantic, fast processing of historical financial data), native async support (async def for network/Yahoo Finance and DB I/O), automatic validation with Pydantic, and automatic Swagger UI (/docs). Django was considered too heavyweight.",
            "must_contain": ["FastAPI", "async", "Pydantic"]
        },
        {
            "question": "What academic program and semester result is documented in Till 4th Sem.pdf, and what are some of the subjects listed?",
            "expected": "B.Tech in Information Technology at SGSITS (Semester III / session 2025-26, Ekansh Sethia). Subjects include Computer Organization & Architecture, Data Structures, Digital Electronics.",
            "must_contain": ["Information Technology", "Computer Organization", "Data Structures"]
        }
    ]
    
    # Test Suite 2: LargeTestWorkspace.zip (1.42 MB)
    test_cases_2 = [
        {
            "question": "In the OS Lab Assignment 1 document, what folder creation commands and folder names are specified?",
            "expected": "Creating 'OS_lab' folder via 'mkdir OS_lab', and creating subfolders 'Assignment_1', 'Assignment_2', 'Programs', and 'Backup' via 'mkdir Assignment_1 Assignment_2 Programs Backup'.",
            "must_contain": ["OS_lab", "Assignment_1", "mkdir"]
        },
        {
            "question": "In the Spotify Class Diagram document, what classes/entities and key methods are described?",
            "expected": "Classes include Account (methods: login, changePswd, logout, etc.), Playlist (methods: playSong, deleteSong, addSong, shuffle, etc.), and Song.",
            "must_contain": ["Account", "Playlist", "Song"]
        },
        {
            "question": "What examination paper is included in the workspace, what is the subject, and what was the exam duration?",
            "expected": "GATE 2013 Question Booklet Code CS-A, Subject: Computer Science and Information Technology (CS), Duration: Three Hours.",
            "must_contain": ["GATE", "Computer Science", "Three Hours"]
        }
    ]
    
    ok1, results1 = test_workspace(ZIP1_PATH, "AnotherTest (0.86 MB)", test_cases_1)
    time.sleep(3)
    ok2, results2 = test_workspace(ZIP2_PATH, "LargeTestWorkspace (1.42 MB)", test_cases_2)
    
    # Output final summary
    print("\n" + "=" * 75)
    print("FINAL SUMMARY REPORT")
    print("=" * 75)
    
    all_results = [("AnotherTest.zip", ok1, results1), ("LargeTestWorkspace.zip", ok2, results2)]
    for name, ok, res in all_results:
        print(f"\n--- {name} ({'SUCCESS' if ok else 'FAILED'}) ---")
        for i, r in enumerate(res, 1):
            status_str = "MATCHED (PASS)" if r["passed"] else "UNMATCHED (FAIL)"
            print(f"\n  [Q{i}]: {r['question']}")
            print(f"  [Expected]: {r['expected']}")
            print(f"  [Actual]: {r['actual'][:250]}...")
            print(f"  [Sources]: {r['sources']}")
            print(f"  [Matched Keywords]: {r['matched_keywords']}/{r['all_keywords']}")
            print(f"  [Status]: {status_str}")
            
    final_mem = get_health_memory()
    print("\n" + "=" * 75)
    print(f"FINAL RENDER MEMORY: VmRSS={final_mem.get('VmRSS')}, VmHWM={final_mem.get('VmHWM')}")
    print("=" * 75)
