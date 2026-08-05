#!/bin/sh

set -eu
umask 077

usage() {
    cat <<'EOF'
Usage: scripts/research/check_staged.sh [--repository ABSOLUTE_PATH]

Scans staged Git objects for whitespace errors, secrets, private paths,
machine identifiers, model/tensor files, caches, binaries, large files, and
Linux/CUDA selection changes. Findings are reported by gate, never by value.
EOF
}

fail() {
    echo "staged safety scan: $1" >&2
    exit 1
}

repository=.
while [ "$#" -gt 0 ]; do
    case "$1" in
        --help|-h)
            usage
            exit 0
            ;;
        --repository)
            shift
            [ "$#" -gt 0 ] || fail "missing repository argument"
            repository=$1
            shift
            ;;
        *)
            fail "unknown option"
            ;;
    esac
done

case "$repository" in
    /*) ;;
    *) repository=$(CDPATH= cd -- "$repository" 2>/dev/null && pwd) || fail "repository is unavailable" ;;
esac

git -C "$repository" rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail "repository is unavailable"

scan_dir=$(mktemp -d "${TMPDIR:-/tmp}/pulsarmlx-staged.XXXXXX" 2>/dev/null) || fail "temporary scan state is unavailable"
names_file="$scan_dir/names"
numstat_file="$scan_dir/numstat"
patch_file="$scan_dir/patch"
additions_file="$scan_dir/additions"
platform_file="$scan_dir/platform"

cleanup() {
    rm -f "$names_file" "$numstat_file" "$patch_file" "$additions_file" "$platform_file" 2>/dev/null
    rmdir "$scan_dir" 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM

if ! git -C "$repository" diff --cached --check >"$scan_dir/diff-check" 2>&1; then
    rm -f "$scan_dir/diff-check"
    fail "staged diff contains whitespace errors"
fi
rm -f "$scan_dir/diff-check"

git -C "$repository" -c core.quotePath=false diff --cached --name-only --diff-filter=ACMR >"$names_file" 2>/dev/null || fail "cannot enumerate staged files"
git -C "$repository" diff --cached --numstat --diff-filter=ACMR >"$numstat_file" 2>/dev/null || fail "cannot inspect staged file types"

if LC_ALL=C grep -Eq '^-[[:space:]]+-[[:space:]]+' "$numstat_file"; then
    fail "staged content includes a binary file"
fi

staged_count=0
staged_total=0
while IFS= read -r staged_path; do
    [ -n "$staged_path" ] || continue
    staged_count=$((staged_count + 1))
    if [ "$staged_count" -gt 512 ]; then
        fail "staged file count exceeds the bounded review limit"
    fi
    case "$staged_path" in
        \"*) fail "staged filename contains unsupported control characters" ;;
    esac

    lower_path=$(printf '%s' "$staged_path" | LC_ALL=C tr '[:upper:]' '[:lower:]')
    case "$lower_path" in
        *.gguf|*.safetensors|*.ckpt|*.pt|*.pth|*.onnx|*.mlmodel|*.npy|*.npz|*.tensor|*.f32|*.bin)
            fail "staged filename has a forbidden model, tensor, or binary extension"
            ;;
        */__pycache__/*|__pycache__/*|*/.pytest_cache/*|.pytest_cache/*|*/.mypy_cache/*|.mypy_cache/*|*/target/*|target/*|*/.pulsarmlx-local/*|.pulsarmlx-local/*)
            fail "staged filename is inside a cache or local-state directory"
            ;;
        .env|*/.env|.env.*|*/.env.*|*.pem|*.key|*.p12|*.pfx|*.log|*.trace)
            case "$lower_path" in
                .env.example|*/.env.example) ;;
                *) fail "staged filename may contain secrets or local logs" ;;
            esac
            ;;
    esac

    staged_entry=$(git -C "$repository" ls-files --stage -- "$staged_path" 2>/dev/null) || fail "cannot inspect a staged object"
    staged_mode=${staged_entry%% *}
    case "$staged_mode" in
        100644|100755) ;;
        120000) fail "staged content includes a symbolic link" ;;
        *) fail "staged content includes an unsupported Git object mode" ;;
    esac

    staged_size=$(git -C "$repository" cat-file -s ":$staged_path" 2>/dev/null) || fail "cannot inspect a staged object"
    case "$staged_size" in
        ''|*[!0-9]*) fail "staged object size is invalid" ;;
    esac
    if [ "$staged_size" -gt 1048576 ]; then
        fail "staged content exceeds the 1 MiB review limit"
    fi
    staged_total=$((staged_total + staged_size))
    if [ "$staged_total" -gt 16777216 ]; then
        fail "staged content exceeds the 16 MiB aggregate review limit"
    fi
done <"$names_file"

git -C "$repository" diff --cached --no-ext-diff --unified=0 --no-color >"$patch_file" 2>/dev/null || fail "cannot inspect staged content"
awk '/^\+\+\+ / { next } /^\+/ { print substr($0, 2) }' "$patch_file" >"$additions_file"

credential_pattern='-----BEGIN ([A-Z0-9 ]+ )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|hf_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{20,}'
credential_pattern="$credential_pattern|Bearer[[:space:]]+[A-Za-z0-9._~+/-]{20,}|(token|password|secret|api[_-]?key|authorization)[[:space:]_\"'-]*[:=][[:space:]]*['\"]?[A-Za-z0-9/+_.-]{16,}"
if LC_ALL=C grep -Eiq -- "$credential_pattern" "$additions_file"; then
    fail "staged content includes a credential-shaped value"
fi

if LC_ALL=C grep -Eq '/(Users|home)/[A-Za-z0-9._-]+/|/Volumes/[A-Za-z0-9._ -]+/' "$additions_file"; then
    fail "staged content includes a private absolute path"
fi

if LC_ALL=C grep -Eq '(^|[^[:xdigit:]])([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}([^[:xdigit:]]|$)' "$additions_file"; then
    fail "staged content includes a machine identifier"
fi

if LC_ALL=C grep -Eiq \
    '[[:xdigit:]]{8}-[[:xdigit:]]{4}-[1-5][[:xdigit:]]{3}-[89ab][[:xdigit:]]{3}-[[:xdigit:]]{12}|"(serial(_number)?|hardware_uuid|host(name)?|user(name)?|account_id)"[[:space:]]*:[[:space:]]*"[^<$][^"]+"' \
    "$additions_file"; then
    fail "staged content includes a private machine or account identifier"
fi

git -C "$repository" diff --cached --no-ext-diff --unified=0 --no-color -- \
    Cargo.toml Cargo.lock build.rs crates python .github/workflows scripts \
    ':(exclude)scripts/research/**' >"$platform_file" 2>/dev/null || fail "cannot inspect platform-selection changes"

if awk '/^(\+\+\+|---) / { next } /^[+-]/ { print substr($0, 2) }' "$platform_file" |
    LC_ALL=C grep -Eiq \
        'target_os.{0,40}linux|cfg.{0,40}linux|io_uring|(^|[^[:alnum:]_])cuda([^[:alnum:]_]|$)|cudarc|nvcc|nvidia'; then
    fail "staged content changes a Linux/CUDA selection surface"
fi

echo "staged safety scan: passed"
