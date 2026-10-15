"""Seal the existing model key directly to the private repository's GitHub key.

Only GitHub can decrypt this ciphertext. No plaintext credential leaves the job.
"""
import base64
import json
import os
from pathlib import Path
from nacl.public import PublicKey, SealedBox

recipient = json.loads(Path("deploy/credentials-recipient.json").read_text())
assert recipient["repository"] == "YoungY620/babel-runner"
value = os.environ["OPENAI_API_KEY"]
assert value, "The source model credential is missing"
sealed = SealedBox(PublicKey(base64.b64decode(recipient["key"]))).encrypt(value.encode())
Path("sealed-credential.json").write_text(json.dumps({
    "key_id": recipient["key_id"],
    "encrypted_value": base64.b64encode(sealed).decode(),
}))
