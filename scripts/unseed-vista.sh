#!/usr/bin/env bash
# Remove m-cli's routines and scratch globals from vista-meta.
set -euo pipefail

PROJECT="m-cli"
XTMP_KEY="M-CLI"

CONN="${VISTA_CONN_FILE:-$HOME/data/vista-meta/conn.env}"
[ -f "$CONN" ] || exit 0
# shellcheck disable=SC1090
source "$CONN"

ssh -p "$VISTA_SSH_PORT" -o StrictHostKeyChecking=no -o BatchMode=yes \
    "$VISTA_SSH_USER@$VISTA_HOST" "bash -lc '
  source /etc/profile.d/ydb_env.sh
  rm -rf \$HOME/export/seed/$PROJECT
  \$ydb_dist/mumps -run %XCMD \"K ^XTMP(\\\"$XTMP_KEY\\\")\" 2>/dev/null || true
' " 2>/dev/null || true

echo "[$PROJECT] unseed done"
