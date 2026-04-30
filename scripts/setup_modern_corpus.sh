#!/usr/bin/env bash
# Clone the non-VistA modern M corpus seed into ~/projects/m-modern-corpus/
# (or the path passed as $1). Idempotent: skips repos that are already cloned.
#
# Catalogued and justified in docs/m-corpus-catalog.md. The seed below is
# the "Recommended seed for `make lint-modern`" three plus the two Tier-1
# supplementary picks; all are pure-`.m` (no `.cls` ObjectScript).

set -euo pipefail

ROOT="${1:-$HOME/projects/m-modern-corpus}"
mkdir -p "$ROOT"
cd "$ROOT"

# Each entry: subdir<TAB>repo URL<TAB>(optional) sparse-checkout subpath
# Sparse subpath: when set, only that subtree is materialized (used for
# YDBOcto where we want src/aux but not the C-language SQL parser).
clone_or_skip() {
    local subdir="$1"
    local url="$2"
    local sparse="${3:-}"
    if [[ -d "$subdir/.git" ]]; then
        echo "[skip]  $subdir (already cloned)"
        return
    fi
    echo "[clone] $subdir <- $url"
    if [[ -n "$sparse" ]]; then
        git clone --depth 1 --filter=blob:none --sparse "$url" "$subdir"
        ( cd "$subdir" && git sparse-checkout set "$sparse" )
    else
        git clone --depth 1 "$url" "$subdir"
    fi
}

# --- Tier 1 anchors ---------------------------------------------------
clone_or_skip ydbtest      https://github.com/YottaDB/YDBTest
clone_or_skip mgsql        https://github.com/chrisemunt/mgsql
clone_or_skip ydbocto-aux  https://github.com/YottaDB/YDBOcto         src/aux

# --- Tier 1 supplements (optional; skip-on-fail) ----------------------
clone_or_skip ewd          https://github.com/robtweed/EWD || true
clone_or_skip m-web-server https://github.com/shabiel/M-Web-Server     || true

cat <<EOF

Modern corpus setup complete at: $ROOT

Cloned subdirs (only those with .git):
$(find "$ROOT" -mindepth 2 -maxdepth 2 -name .git -printf '  %h\n' | sort)

Run the regression gate with:
    make lint-modern

To refresh the baseline (after a deliberate rule change):
    make lint-modern-baseline
EOF
