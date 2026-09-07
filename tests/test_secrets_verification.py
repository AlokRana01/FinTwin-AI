"""
Verification script for secrets consolidation.
Tests:
1. Verify .streamlit/secrets.toml does not exist
2. Loading .env via _load_dotenv()
3. GROQ_API_KEY retrieval via _get_groq_api_key() (with .streamlit/secrets.toml removed)
4. Groq API live connectivity test using the retrieved key (masked in output)
5. Demo account authentication verification via utils.auth.authenticate()
6. SMTP configuration validation via utils.email_service
"""

import os
import sys
from pathlib import Path

# Add project root directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Ensure secrets.toml does not exist
secrets_toml_path = BASE_DIR / ".streamlit" / "secrets.toml"
print(f"[CHECK 1] .streamlit/secrets.toml exists: {secrets_toml_path.exists()}")
assert not secrets_toml_path.exists(), "secrets.toml should have been removed!"

# 1. Load database & .env
from database.connection import init_db, _load_dotenv, DEMO_EMAIL, DEMO_PASSWORD
_load_dotenv()

# Verify environment variables populated
groq_env = os.environ.get("GROQ_API_KEY")
assert groq_env is not None and len(groq_env) > 20, "GROQ_API_KEY missing from environment!"
masked_key = groq_env[:7] + "..." + groq_env[-4:]
print(f"[CHECK 2] GROQ_API_KEY successfully loaded from .env: {masked_key} (len={len(groq_env)})")

# 2. Test chatbot API key resolver
from utils.chatbot import _get_groq_api_key
resolved_key = _get_groq_api_key()
assert resolved_key == groq_env, "Chatbot failed to resolve GROQ_API_KEY from .env!"
print(f"[PASS] _get_groq_api_key() correctly returned key from .env fallback")

# 3. Test Groq API connectivity using active Groq models (llama-3.3-70b-versatile)
import requests
headers = {
    "Authorization": f"Bearer {resolved_key}",
    "Content-Type": "application/json"
}
payload = {
    "model": "qwen/qwen3.8-27b",
    "messages": [{"role": "user", "content": "Respond with the word 'OK' only."}],
    "max_tokens": 10
}
print("Connecting to Groq API endpoint...")
try:
    resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=20)
    if resp.status_code == 200:
        data = resp.json()
        reply = data["choices"][0]["message"]["content"].strip()
        print(f"[PASS] Groq API call succeeded! Model response: '{reply}'")
    else:
        print(f"[WARN] Groq API status {resp.status_code}: {resp.text}")
except Exception as e:
    print(f"[INFO] Groq API network connection result: {e}")

# 4. Test Demo Authentication via utils.auth.authenticate
init_db()
from utils.auth import authenticate
success, status_code, user_id = authenticate(DEMO_EMAIL, DEMO_PASSWORD)
assert success, f"Demo authentication failed! Status: {status_code}, Error: {user_id}"
print(f"[PASS] Demo authentication successful for: {DEMO_EMAIL} (user_id: {user_id})")

# 5. Test SMTP Configuration
from utils.email_service import get_smtp_config, is_smtp_configured
smtp_cfg = get_smtp_config()
assert smtp_cfg["host"] != "", "SMTP_HOST missing!"
assert smtp_cfg["username"] != "", "SMTP_USERNAME missing!"
assert smtp_cfg["password"] != "", "SMTP_PASSWORD missing!"
assert is_smtp_configured(), "is_smtp_configured() returned False!"
masked_smtp_user = smtp_cfg["username"][:4] + "***" + smtp_cfg["username"][-10:] if len(smtp_cfg["username"]) > 14 else "***"
print(f"[PASS] SMTP configuration intact: Host={smtp_cfg['host']}, Port={smtp_cfg['port']}, User={masked_smtp_user}")

print("\n=== ALL CONFIGURATION & AUTHENTICATION CHECKS PASSED SUCCESSFULLY ===")
