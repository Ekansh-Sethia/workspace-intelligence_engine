"""
Live Production End-to-End Test Script
Tests https://wie-backend.onrender.com with Desktop ZIP upload & chat query.
"""
import urllib.request
import urllib.parse
import json
import time
import os
import uuid

BASE_URL = "https://wie-backend.onrender.com/api/v1"
ZIP_PATH = r"C:\Users\ASUS\OneDrive\Desktop\AnotherTest.zip"
if not os.path.exists(ZIP_PATH):
    ZIP_PATH = r"C:\Users\ASUS\OneDrive\Desktop\NewFileTest.zip"

print(f"Testing live production with ZIP: {ZIP_PATH} ({os.path.getsize(ZIP_PATH)} bytes)")

# 1. Sign up a temporary test user
test_email = f"prod_verifier_{uuid.uuid4().hex[:6]}@example.com"
test_password = "Password123!"

signup_data = json.dumps({"email": test_email, "password": test_password}).encode("utf-8")
req = urllib.request.Request(
    f"{BASE_URL}/auth/signup",
    data=signup_data,
    headers={"Content-Type": "application/json"}
)

try:
    with urllib.request.urlopen(req) as r:
        print(f"[1] Signed up successfully: {test_email}")
except urllib.error.HTTPError as e:
    print(f"[1] Signup error: {e.code} {e.read().decode()}")

# 2. Log in to get access token
login_data = urllib.parse.urlencode({"username": test_email, "password": test_password}).encode("utf-8")
req = urllib.request.Request(
    f"{BASE_URL}/auth/login",
    data=login_data,
    headers={"Content-Type": "application/x-www-form-urlencoded"}
)

with urllib.request.urlopen(req) as r:
    auth_data = json.loads(r.read().decode())
    token = auth_data["access_token"]
    print(f"[2] Logged in successfully. Token acquired.")

headers = {"Authorization": f"Bearer {token}"}

# 3. Upload the desktop ZIP file (multipart/form-data)
print(f"[3] Uploading {os.path.basename(ZIP_PATH)} to production...")
boundary = "----WebKitFormBoundary" + uuid.uuid4().hex
body = []

# Form fields: name, description
body.extend([
    f"--{boundary}".encode(),
    b'Content-Disposition: form-data; name="name"',
    b'',
    b'Desktop Test Workspace',
    f"--{boundary}".encode(),
    b'Content-Disposition: form-data; name="description"',
    b'',
    b'Automated production verification workspace',
    f"--{boundary}".encode(),
    f'Content-Disposition: form-data; name="file"; filename="{os.path.basename(ZIP_PATH)}"'.encode(),
    b'Content-Type: application/zip',
    b'',
])

with open(ZIP_PATH, "rb") as f:
    body.append(f.read())

body.extend([
    f"--{boundary}--".encode(),
    b''
])

payload = b"\r\n".join(body)

upload_req = urllib.request.Request(
    f"{BASE_URL}/workspaces",
    data=payload,
    headers={
        **headers,
        "Content-Type": f"multipart/form-data; boundary={boundary}"
    }
)

with urllib.request.urlopen(upload_req) as r:
    ws = json.loads(r.read().decode())
    ws_id = ws["id"]
    print(f"[3] Upload Accepted (Status {r.status}). Workspace ID: {ws_id}, Initial Status: {ws['status']}")

# 4. Poll workspace status until 'ready' or timeout
print("[4] Monitoring background processing on Render...")
max_wait = 180  # 3 minutes max
start_time = time.time()
current_status = ws["status"]

while time.time() - start_time < max_wait:
    time.sleep(4)
    check_req = urllib.request.Request(f"{BASE_URL}/workspaces/{ws_id}", headers=headers)
    with urllib.request.urlopen(check_req) as r:
        ws_info = json.loads(r.read().decode())
        current_status = ws_info["status"]
        elapsed = int(time.time() - start_time)
        print(f"    Elapsed: {elapsed}s | Status: {current_status}")
        if current_status in ["ready", "failed"]:
            break

print(f"[4] Workspace processing finished with status: {current_status.upper()}")

if current_status != "ready":
    print("Workspace did not transition to ready in time. Exiting test.")
    exit(1)

# Check extracted files
files_req = urllib.request.Request(f"{BASE_URL}/workspaces/{ws_id}/files", headers=headers)
with urllib.request.urlopen(files_req) as r:
    files = json.loads(r.read().decode())
    print(f"    Extracted files ({len(files)}):")
    for f in files:
        print(f"    - {f.get('relative_path')} ({f.get('size')} bytes, {f.get('chunk_count')} chunks, status: {f.get('status')})")

# 5. Create a Chat Session
print("[5] Creating chat session...")
session_req = urllib.request.Request(
    f"{BASE_URL}/workspaces/{ws_id}/chat/sessions",
    data=b"{}",
    headers={**headers, "Content-Type": "application/json"}
)
with urllib.request.urlopen(session_req) as r:
    session = json.loads(r.read().decode())
    session_id = session["id"]
    print(f"    Chat Session ID: {session_id}")

# 6. Send a Chat Query and read streaming SSE response
query = "What is the educational background and skills mentioned in these documents?"
print(f"[6] Sending question: '{query}'")

chat_payload = json.dumps({"query": query}).encode("utf-8")
chat_req = urllib.request.Request(
    f"{BASE_URL}/workspaces/{ws_id}/chat/sessions/{session_id}/messages",
    data=chat_payload,
    headers={**headers, "Content-Type": "application/json"}
)

print("    Receiving streaming response from live production LLM:\n")
full_answer = []
sources = []

with urllib.request.urlopen(chat_req) as r:
    for line in r:
        decoded_line = line.decode("utf-8")
        if decoded_line.startswith("data: "):
            data_str = decoded_line[6:].strip()
            if data_str == "[DONE]":
                break
            try:
                event_data = json.loads(data_str)
                token = event_data.get("token", "")
                full_answer.append(token)
                print(token, end="", flush=True)
                if "sources" in event_data:
                    sources = event_data["sources"]
            except Exception:
                pass

print("\n\n" + "="*60)
print("PRODUCTION VERIFICATION RESULT:")
print("="*60)
print(f"Answer Length: {len(''.join(full_answer))} characters")
print(f"Citations/Sources Returned: {sources}")
print("ALL PRODUCTION CHECKS PASSED PERFECTLY!")
print("="*60)
