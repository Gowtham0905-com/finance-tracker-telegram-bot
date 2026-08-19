import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

try:
    conn = psycopg2.connect(DATABASE_URL)

    cursor = conn.cursor()

    cursor.execute("SELECT version();")

    version = cursor.fetchone()

    print("✅ PostgreSQL connection successful!")
    print(version[0])

    cursor.close()
    conn.close()

except Exception as e:
    print("❌ Connection failed:")
    print(e)
