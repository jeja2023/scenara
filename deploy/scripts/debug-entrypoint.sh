#!/bin/sh
set -eu

if [ -n "${SCENARA_DEBUG_SECRET_ENCRYPTION_KEY:-}" ]; then
  SCENARA_SECRET_ENCRYPTION_KEY="$SCENARA_DEBUG_SECRET_ENCRYPTION_KEY"
else
  SCENARA_SECRET_ENCRYPTION_KEY="$(python3 -c 'import base64, hashlib; print(base64.urlsafe_b64encode(hashlib.sha256(b"scenara-debug-local").digest()).decode("ascii"))')"
fi
export SCENARA_SECRET_ENCRYPTION_KEY

exec python3 -m uvicorn scenara.server:app \
  --host 0.0.0.0 \
  --port 8000 \
  --proxy-headers
