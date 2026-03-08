#!/usr/bin/env python3
"""One-time migration: encrypt plaintext stark_private_key and ai_api_key in SQLite."""
import os, sys, sqlite3, hashlib, base64

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "edgex_agent.db")
if not os.path.exists(DB_PATH):
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "edgex_agent.db")

token = os.getenv("TELEGRAM_BOT_TOKEN", "")
if not token:
    print("ERROR: TELEGRAM_BOT_TOKEN not set"); sys.exit(1)

from cryptography.fernet import Fernet
key_bytes = hashlib.sha256(token.encode()).digest()
f = Fernet(base64.urlsafe_b64encode(key_bytes))

def encrypt(val):
    if not val or val.startswith("enc:"):
        return val
    return "enc:" + f.encrypt(val.encode()).decode()

conn = sqlite3.connect(DB_PATH)
rows = conn.execute("SELECT tg_user_id, stark_private_key, ai_api_key FROM users").fetchall()

total = len(rows)
migrated_spk = 0
migrated_aik = 0
already_enc = 0
skipped = 0

for uid, spk, aik in rows:
    updates = {}
    if spk and not spk.startswith("enc:"):
        updates["stark_private_key"] = encrypt(spk)
        migrated_spk += 1
    elif spk and spk.startswith("enc:"):
        already_enc += 1

    if aik and not aik.startswith("enc:"):
        updates["ai_api_key"] = encrypt(aik)
        migrated_aik += 1
    elif aik and aik.startswith("enc:"):
        already_enc += 1

    if updates:
        sets = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE users SET {sets} WHERE tg_user_id = ?", list(updates.values()) + [uid])
    else:
        skipped += 1

conn.commit()

# Verify
verified = 0
for uid, spk, aik in conn.execute("SELECT tg_user_id, stark_private_key, ai_api_key FROM users").fetchall():
    if spk and not spk.startswith("enc:"):
        print(f"  WARNING: user {uid} stark_private_key still plaintext!")
    elif spk:
        verified += 1
    if aik and not aik.startswith("enc:"):
        print(f"  WARNING: user {uid} ai_api_key still plaintext!")
    elif aik:
        verified += 1

conn.close()
print(f"\n=== Encryption Migration Report ===")
print(f"Total users: {total}")
print(f"stark_private_key migrated: {migrated_spk}")
print(f"ai_api_key migrated: {migrated_aik}")
print(f"Already encrypted: {already_enc}")
print(f"Verified enc: fields: {verified}")
print(f"Done.")
