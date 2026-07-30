"""Quick connectivity check for DEE-5. Run after `docker compose up -d`."""
import os
import sys

from dotenv import load_dotenv
import psycopg2

load_dotenv()

url = os.getenv("DATABASE_URL")
if not url:
    print("ERROR: DATABASE_URL not set in environment / .env")
    sys.exit(1)

try:
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute("SELECT version();")
    version = cur.fetchone()[0]
    cur.close()
    conn.close()
    print(f"OK: connected to {version}")
except Exception as exc:
    print(f"FAIL: {exc}")
    sys.exit(1)
