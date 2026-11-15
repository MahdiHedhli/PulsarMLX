#!/usr/bin/env bash
# Non-interference check for the PulsarMLX Console work (spec 022).
#
# The console work must not change any file the engine track edits or hashes.
# This script checks that mechanically. It needs only bash (3.2 or later) and
# git, and it reads the repository without changing it.
#
# Usage:
#   console/tools/check-boundary.sh [--base REF] [--committed]
#   console/tools/check-boundary.sh [--base REF] [--committed] --list-paths
#
#   --base REF     The branch the work will merge into (default: origin/main).
#                  Changes are measured from merge-base(REF, HEAD).
#   --committed    Measure merge-base..HEAD only (CI). Without it the working
#                  tree is measured as well: staged, unstaged and untracked
#                  files that are not ignored (local use before a commit).
#   --list-paths   Print the changed paths, one per line, and exit. Used by
#                  check-hygiene.sh so both tools agree on what changed.
#   --print-allowlist
#                  Print the allowlist (prefixes end in /) and exit.
#
# Checks, one output line each:
#   1. allowlist       every changed path is inside the console allowlist
#   2. frozen-blobs    root Cargo.toml, Cargo.lock and .github/workflows/macos.yml
#                      are byte-identical to the merge base
#   3. ignored-files   nothing under console/ or the feature directory is
#                      ignored by git, and no path uses a .gitignore trap name
#   4. path-deps       no Cargo manifest under console/ points outside console/,
#                      and no Cargo configuration directory (.cargo/) exists
#                      under console/
#   5. reserved-names  no engine-track package or directory name is used
#
# Exit status: 0 when every check passes, 1 when any check fails, 2 on a usage
# or repository error.

set -euo pipefail
export LC_ALL=C
export GIT_PAGER=cat

# ---------------------------------------------------------------------------
# Policy (specs/022-console-serving-parity/plan.md, section Non-Interference).
# Keep in step with console/README.md.
# ---------------------------------------------------------------------------
ALLOW_PREFIXES='console/
specs/022-console-serving-parity/
docs/console/'
ALLOW_EXACT='docs/roadmap/CONSOLE_ROADMAP.md
docs/roadmap/PULSARMLX_STRATEGY.md
docs/upstream/PROJECT_MAYA.md
docs/upstream/PROJECT_MAYA_SYNC.md
docs/architecture/decisions/0008-console-serving-ahead-of-stage-f.md
NOTICE.md
README.md
CONTRIBUTING.md
.github/workflows/console.yml'
FROZEN_FILES='Cargo.toml
Cargo.lock
.github/workflows/macos.yml'
OWNED_ROOTS='console
specs/022-console-serving-parity'
RESERVED_PACKAGES='mlx-expert-ranges
mlx-expert-mlp
expert-residency-core
packed-affine-adoption
serve
pulsar-serve
pulsar-serve-synthetic'
# Directory names that the root .gitignore drops silently, plus local caches.
# A path component equal to one of these is refused even if .gitignore changes.
TRAP_DIRS='models
weights
checkpoints
logs
dist
env
venv
.venv
debug
release
target
__pycache__
.pytest_cache
.mypy_cache
.ruff_cache
.cache
.huggingface
.ssh
.agents
.claude
.gitnexus
.pulsarmlx-local
.idea
.vscode'
# File-name patterns (shell globs, matched against the lower-cased base name).
TRAP_FILES='*.log
*.key
*.pem
*.p12
*.pfx
secrets.*
credentials.json
mcp.json
mcp.local.json
*.trace
*.trace.json
*.bench.json
*.benchmark.json
*.prof*
*.perf
*.tmp
*.swp
*.rs.bk
*.rlib
*.pyc
*.pyo
*.pyd
*.gguf
*.gguf.warm
*.ctx-state
*.safetensors
*.ckpt
*.pt
*.pth
*.onnx
claude.md
agents.md
.env
.env.*
id_rsa*
id_ed25519*
.ds_store'

# ---------------------------------------------------------------------------

usage() {
    sed -n '2,34p' "$0" | sed 's/^# \{0,1\}//'
}

base_ref=origin/main
committed=0
list_only=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --base)
            [ "$#" -ge 2 ] || { echo "check-boundary: --base needs a value" >&2; exit 2; }
            base_ref=$2
            shift 2
            ;;
        --base=*) base_ref=${1#--base=}; shift ;;
        --committed) committed=1; shift ;;
        --list-paths) list_only=1; shift ;;
        --print-allowlist) printf '%s\n%s\n' "$ALLOW_PREFIXES" "$ALLOW_EXACT"; exit 0 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "check-boundary: unknown argument: $1" >&2; exit 2 ;;
    esac
done

top=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "check-boundary: not inside a git work tree" >&2
    exit 2
}
cd "$top"

case "$base_ref" in
    -*) echo "check-boundary: invalid base ref" >&2; exit 2 ;;
esac
git rev-parse --verify --quiet "$base_ref^{commit}" >/dev/null || {
    echo "check-boundary: base ref '$base_ref' is not available (fetch it first)" >&2
    exit 2
}
merge_base=$(git merge-base "$base_ref" HEAD) || {
    echo "check-boundary: no merge base between '$base_ref' and HEAD" >&2
    exit 2
}

work=$(mktemp -d "${TMPDIR:-/tmp}/console-boundary.XXXXXX")
trap 'rm -rf "$work"' EXIT
trap 'exit 130' HUP INT TERM

git_q() { git -c core.quotePath=false "$@"; }

# Changed paths: both sides of every rename, deletions included.
{
    if [ "$committed" -eq 1 ]; then
        git_q diff --name-only --no-renames "$merge_base" HEAD --
    else
        git_q diff --name-only --no-renames "$merge_base" --
        # The index as well: a staged gitlink (submodule) with no checked-out
        # directory does not show in the working-tree comparison above.
        git_q diff --cached --name-only --no-renames "$merge_base" --
        git_q ls-files --others --exclude-standard
    fi
} | sort -u >"$work/changed"

if grep -q '^"' "$work/changed"; then
    echo "check-boundary: a changed path contains characters git must quote" >&2
    exit 2
fi

if [ "$list_only" -eq 1 ]; then
    cat "$work/changed"
    exit 0
fi

failures=0
report() {
    # report STATUS NAME DETAIL
    printf '%-4s %-15s %s\n' "$1" "$2" "$3"
    if [ "$1" = FAIL ]; then
        failures=$((failures + 1))
    fi
}

in_allowlist() {
    local path=$1 entry
    while IFS= read -r entry; do
        case "$path" in "$entry"*) return 0 ;; esac
    done <<EOF
$ALLOW_PREFIXES
EOF
    while IFS= read -r entry; do
        [ "$path" = "$entry" ] && return 0
    done <<EOF
$ALLOW_EXACT
EOF
    return 1
}

mode_label=working-tree
[ "$committed" -eq 1 ] && mode_label=committed
changed_count=$(grep -c . "$work/changed" || true)
echo "check-boundary: base $base_ref, merge base ${merge_base:0:12}, $mode_label, $changed_count changed paths"

# 1. allowlist -------------------------------------------------------------
: >"$work/outside"
while IFS= read -r path; do
    [ -n "$path" ] || continue
    in_allowlist "$path" || printf '%s\n' "$path" >>"$work/outside"
done <"$work/changed"
if [ -s "$work/outside" ]; then
    report FAIL allowlist "$(grep -c . "$work/outside") path(s) outside the allowlist:"
    sed 's/^/       /' "$work/outside"
else
    report ok allowlist "all changed paths are inside the console allowlist"
fi

# 2. frozen-blobs ------------------------------------------------------------
frozen_bad=""
frozen_note=""
while IFS= read -r path; do
    base_blob=$(git rev-parse --verify --quiet "$merge_base:$path" || echo missing)
    head_blob=$(git rev-parse --verify --quiet "HEAD:$path" || echo missing)
    if [ "$head_blob" != "$base_blob" ]; then
        frozen_bad="$frozen_bad $path(HEAD)"
    fi
    if [ "$committed" -eq 0 ]; then
        if [ -f "$path" ]; then
            tree_blob=$(git hash-object --no-filters -- "$path")
        else
            tree_blob=missing
        fi
        if [ "$tree_blob" != "$base_blob" ]; then
            frozen_bad="$frozen_bad $path(working-tree)"
        fi
    fi
    tip_blob=$(git rev-parse --verify --quiet "$base_ref:$path" || echo missing)
    if [ "$tip_blob" != "$base_blob" ]; then
        frozen_note="$frozen_note $path"
    fi
done <<EOF
$FROZEN_FILES
EOF
if [ -n "$frozen_bad" ]; then
    report FAIL frozen-blobs "differ from the merge base:$frozen_bad"
else
    report ok frozen-blobs "Cargo.toml, Cargo.lock and macos.yml equal the merge base"
fi
if [ -n "$frozen_note" ]; then
    echo "     note: $base_ref has moved past the merge base for:$frozen_note (informational)"
fi

# 3. ignored-files -----------------------------------------------------------
# a) files present locally under the owned roots that git would silently drop
#    (working-tree mode only; a CI checkout has no untracked files);
# b) owned paths (tracked or new) that the ignore rules match, which catches a
#    force-added file in CI;
# c) path components or base names on the trap list, independent of .gitignore.
: >"$work/ignored"
while [ "$committed" -eq 0 ] && IFS= read -r root; do
    git_q ls-files --others --ignored --exclude-standard --directory -- "$root" |
        while IFS= read -r p; do
            case "$p" in */.DS_Store|.DS_Store) ;; *) printf 'ignored: %s\n' "$p" ;; esac
        done >>"$work/ignored"
done <<EOF
$OWNED_ROOTS
EOF

if [ "$committed" -eq 1 ]; then
    git_q ls-tree -r --name-only HEAD -- console specs/022-console-serving-parity >"$work/owned"
else
    git_q ls-files --cached --others --exclude-standard -- console specs/022-console-serving-parity >"$work/owned"
fi
grep -v '^"' "$work/owned" >"$work/owned.safe" || true
if [ -s "$work/owned.safe" ]; then
    git check-ignore --no-index --stdin <"$work/owned.safe" 2>/dev/null |
        sed 's/^/matched by .gitignore: /' >>"$work/ignored" || true
fi
cat "$work/owned.safe" "$work/changed" | sort -u >"$work/names"
while IFS= read -r path; do
    [ -n "$path" ] || continue
    case "$path" in console/*|specs/022-console-serving-parity/*|docs/console/*) ;; *) continue ;; esac
    rest=${path%/*}
    [ "$rest" = "$path" ] && rest=""
    while [ -n "$rest" ]; do
        comp=${rest##*/}
        while IFS= read -r trap_dir; do
            if [ "$comp" = "$trap_dir" ]; then
                printf 'trap directory name "%s": %s\n' "$comp" "$path" >>"$work/ignored"
            fi
        done <<EOF
$TRAP_DIRS
EOF
        case "$rest" in */*) rest=${rest%/*} ;; *) rest="" ;; esac
    done
    base=$(printf '%s' "${path##*/}" | tr '[:upper:]' '[:lower:]')
    while IFS= read -r trap_file; do
        # shellcheck disable=SC2254
        case "$base" in
            $trap_file) printf 'trap file name "%s": %s\n' "$trap_file" "$path" >>"$work/ignored" ;;
        esac
    done <<EOF
$TRAP_FILES
EOF
done <"$work/names"
if [ -s "$work/ignored" ]; then
    sort -u "$work/ignored" >"$work/ignored.u"
    report FAIL ignored-files "$(grep -c . "$work/ignored.u") problem(s):"
    sed 's/^/       /' "$work/ignored.u"
    echo "       (build with a CARGO_TARGET_DIR outside the repository; rename trap paths)"
else
    report ok ignored-files "nothing under console/ or the feature directory is ignored or trap-named"
fi

# 4. path-deps -----------------------------------------------------------------
# Every `path = "..."` or `workspace = "..."` value (double- or single-quoted)
# in a manifest under console/ must resolve inside console/. Target paths such
# as [lib] path resolve inside the crate and pass. A .cargo/ directory under
# console/ is refused outright, because its config files can redirect
# dependencies (paths, [patch]) without touching any Cargo.toml.
normalize() {
    # normalize DIR REL -> repository-relative path with . and .. collapsed,
    # or the marker "<outside>" if it climbs above the repository root.
    printf '%s/%s\n' "$1" "$2" | awk -F/ '{
        n = 0
        for (i = 1; i <= NF; i++) {
            if ($i == "" || $i == ".") continue
            if ($i == "..") { if (n == 0) { print "<outside>"; exit } n--; continue }
            stack[++n] = $i
        }
        out = ""
        for (i = 1; i <= n; i++) out = out (i > 1 ? "/" : "") stack[i]
        print out
    }'
}
read_owned() {
    if [ "$committed" -eq 1 ]; then git show "HEAD:$1"; else cat -- "$1"; fi
}
grep -E '^console/(.*/)?Cargo\.toml$' "$work/owned.safe" >"$work/manifests" || true
: >"$work/deps"
grep -E '^console/(.*/)?\.cargo/' "$work/owned.safe" |
    sed 's/^/Cargo configuration directory refused: /' >>"$work/deps" || true
manifest_count=0
while IFS= read -r manifest; do
    [ -n "$manifest" ] || continue
    if [ "$committed" -eq 0 ] && [ ! -f "$manifest" ]; then
        continue
    fi
    manifest_count=$((manifest_count + 1))
    dir=${manifest%/Cargo.toml}
    [ "$dir" = "$manifest" ] && dir=.
    read_owned "$manifest" |
        sed 's/#.*$//' |
        grep -Eo "(^|[^A-Za-z0-9_-])(path|workspace)[[:space:]]*=[[:space:]]*(\"[^\"]*\"|'[^']*')" |
        sed -E "s/.*[\"']([^\"']*)[\"']\$/\1/" |
        while IFS= read -r rel; do
            case "$rel" in
                /*) printf '%s: absolute path "%s"\n' "$manifest" "$rel" ;;
                *)
                    resolved=$(normalize "$dir" "$rel")
                    case "$resolved" in
                        console|console/*) ;;
                        *) printf '%s: "%s" resolves outside console/\n' "$manifest" "$rel" ;;
                    esac
                    ;;
            esac
        done >>"$work/deps" || true
    # Workspace members and excludes must also stay inside console/.
    read_owned "$manifest" | sed 's/#.*$//' | tr ',' '\n' |
        grep -Eo "\"[^\"]*\.\.[^\"]*\"|'[^']*\.\.[^']*'" | tr -d "\"'" |
        while IFS= read -r rel; do
            resolved=$(normalize "$dir" "$rel")
            case "$resolved" in
                console|console/*) ;;
                *) printf '%s: "%s" resolves outside console/\n' "$manifest" "$rel" ;;
            esac
        done >>"$work/deps" || true
done <"$work/manifests"
if [ -s "$work/deps" ]; then
    sort -u "$work/deps" >"$work/deps.u"
    report FAIL path-deps "$(grep -c . "$work/deps.u") reference(s) leave console/:"
    sed 's/^/       /' "$work/deps.u"
else
    report ok path-deps "$manifest_count manifest(s) under console/, no path leaves console/"
fi

# 5. reserved-names ------------------------------------------------------------
: >"$work/reserved"
while IFS= read -r manifest; do
    [ -n "$manifest" ] || continue
    if [ "$committed" -eq 0 ] && [ ! -f "$manifest" ]; then
        continue
    fi
    read_owned "$manifest" | sed 's/#.*$//' |
        grep -E '^[[:space:]]*name[[:space:]]*=' |
        sed -E "s/^[^\"']*[\"']([^\"']*)[\"'].*\$/\1/" |
        while IFS= read -r name; do
            while IFS= read -r reserved; do
                if [ "$name" = "$reserved" ]; then
                    printf '%s: reserved package name "%s"\n' "$manifest" "$name"
                fi
            done <<EOF
$RESERVED_PACKAGES
EOF
        done >>"$work/reserved" || true
done <"$work/manifests"
while IFS= read -r path; do
    case "/$path" in
        */experiments/*) printf 'reserved directory experiments/: %s\n' "$path" >>"$work/reserved" ;;
    esac
    case "/$path/" in
        */crates/serve-synthetic/*) printf 'reserved directory crates/serve-synthetic: %s\n' "$path" >>"$work/reserved" ;;
    esac
    case "/$path" in
        */docs/serving/*) printf 'reserved directory docs/serving/: %s\n' "$path" >>"$work/reserved" ;;
    esac
done <"$work/names"
if [ -s "$work/reserved" ]; then
    sort -u "$work/reserved" >"$work/reserved.u"
    report FAIL reserved-names "$(grep -c . "$work/reserved.u") use(s) of a reserved name:"
    sed 's/^/       /' "$work/reserved.u"
else
    report ok reserved-names "no reserved engine-track package or directory name is used"
fi

if [ "$failures" -gt 0 ]; then
    echo "check-boundary: FAILED ($failures check(s))"
    exit 1
fi
echo "check-boundary: passed"
