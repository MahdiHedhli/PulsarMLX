#!/usr/bin/env bash
# Content hygiene check for the PulsarMLX Console work (spec 022).
#
# Scans what the console work adds, relative to the merge base with the target
# branch, for content that must never enter the repository (constitution
# principle XI) and for AI attribution, which the owner has ruled out. The
# patterns are ported from scripts/research/check_staged.sh and from the
# documentation credential scan, with sk- shaped keys added. Findings are
# reported by gate, path and line, never by value.
#
# Usage:
#   console/tools/check-hygiene.sh [--base REF] [--committed] [--commits RANGE]
#
#   --base REF       Target branch (default: origin/main).
#   --committed      Scan merge-base..HEAD only (CI). Without it the working
#                    tree is scanned as well: tracked changes, staged or not,
#                    and untracked files under the console allowlist.
#   --commits RANGE  Commit range whose messages are checked for attribution
#                    lines (default: merge-base..HEAD).
#
# File gates: Git object modes other than regular files and symbolic links
# (for example a submodule), binary content (git's binary detection or any NUL
# byte), symbolic links, files over 1 MiB, more than 16 MiB in total, forbidden
# model, tensor and binary extensions, and whitespace errors (git diff --check).
# There is no limit on the number of files: the scan covers a whole branch, not
# one commit.
# Line gates (added lines only, so unchanged lines of a shared document such as
# README.md are not re-judged): see the PATTERNS section below.
#
# Allow markers. A line that legitimately matches one of the heuristic line
# gates (credential-assignment, bearer-token, uuid, machine-id, identity-json)
# may carry the token hygiene-allow:<id> in a comment on the same line, where
# <id> is listed in console/tools/hygiene-allow.txt with its reason. An
# unlisted id is itself a failure. Markers never excuse the other line gates
# (private keys, service tokens, home paths, AI attribution), a file gate or a
# commit-message finding.
#
# Requires bash (3.2 or later), git, grep, sed, awk and tr. Read-only.

set -euo pipefail
export LC_ALL=C
export GIT_PAGER=cat

# ===========================================================================
# PATTERNS. Every line gate lives here: NAME|FLAGS|EXTENDED-REGEX, where FLAGS
# is "i" for a case-insensitive match or "-" for a case-sensitive one. Some
# literals are written with a one-character bracket (for example [C]) so that
# this file does not match its own patterns.
# ===========================================================================
line_gates() {
    cat <<'EOF'
private-key|-|-----BEGIN ([A-Z0-9 ]+ )?PRIVATE KEY-----
github-token|-|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}
aws-key|-|(^|[^A-Z0-9])(AKIA|ASIA)[0-9A-Z]{16}([^A-Z0-9]|$)
anthropic-key|-|sk-ant-[A-Za-z0-9_-]{16,}
sk-key|-|(^|[^A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}
service-token|-|hf_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}
bearer-token|i|bearer[[:space:]]+[A-Za-z0-9._~+/-]{16,}
credential-assignment|i|(token|password|passwd|secret|api[_-]?key|authorization)[[:space:]_"'-]*[:=][[:space:]]*(['"][A-Za-z0-9/+_.-]{16,}|[A-Za-z0-9/+_.-]{16,}([[:space:],]|$))
home-path|-|/(Users|home)/[A-Za-z0-9._-]+/|/Volumes/[A-Za-z0-9._ -]+/
uuid|-|(^|[^[:xdigit:]])[[:xdigit:]]{8}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12}([^[:xdigit:]]|$)
machine-id|-|(^|[^[:xdigit:]:])([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}([^[:xdigit:]:]|$)
identity-json|i|"(serial(_number)?|hardware_uuid|host(name)?|user(name)?|account_id)"[[:space:]]*:[[:space:]]*"[^<$][^"]+"
ai-attribution|i|[C]o-[A]uthored-[B]y|[G]enerated[[:space:]]+(with|by)[[:space:]]+\[?(Claude|ChatGPT|OpenAI|Codex|Copilot|GitHub Copilot|Gemini|Cursor|Aider|Devin|GPT|Anthropic|an AI|AI)([^A-Za-z]|$)|noreply@[a]nthropic[.]com|claude[.]com/[c]laude-code
EOF
}
# Commit messages are checked with the ai-attribution gate only.
COMMIT_GATE=ai-attribution
# Forbidden extensions (lower-cased, without the dot).
FORBIDDEN_EXTENSIONS='gguf safetensors ckpt pt pth onnx mlmodel npy npz bin f32 tensor'
MAX_FILE_BYTES=1048576
MAX_TOTAL_BYTES=16777216
ALLOW_FILE=console/tools/hygiene-allow.txt
ALLOW_MARKER_RE='hygiene-allow:[A-Za-z0-9_.-]+'
# The only line gates an allow marker can excuse.
EXCUSABLE_GATES=' credential-assignment bearer-token uuid machine-id identity-json '
# ===========================================================================

usage() {
    sed -n '2,38p' "$0" | sed 's/^# \{0,1\}//'
}

base_ref=origin/main
committed=0
commit_range=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --base)
            [ "$#" -ge 2 ] || { echo "check-hygiene: --base needs a value" >&2; exit 2; }
            base_ref=$2
            shift 2
            ;;
        --base=*) base_ref=${1#--base=}; shift ;;
        --committed) committed=1; shift ;;
        --commits)
            [ "$#" -ge 2 ] || { echo "check-hygiene: --commits needs a value" >&2; exit 2; }
            commit_range=$2
            shift 2
            ;;
        --commits=*) commit_range=${1#--commits=}; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "check-hygiene: unknown argument: $1" >&2; exit 2 ;;
    esac
done

top=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "check-hygiene: not inside a git work tree" >&2
    exit 2
}
cd "$top"
boundary=console/tools/check-boundary.sh
[ -f "$boundary" ] || { echo "check-hygiene: $boundary is missing" >&2; exit 2; }

case "$base_ref" in -*) echo "check-hygiene: invalid base ref" >&2; exit 2 ;; esac
git rev-parse --verify --quiet "$base_ref^{commit}" >/dev/null || {
    echo "check-hygiene: base ref '$base_ref' is not available (fetch it first)" >&2
    exit 2
}
merge_base=$(git merge-base "$base_ref" HEAD)
[ -n "$commit_range" ] || commit_range="$merge_base..HEAD"
case "$commit_range" in -*) echo "check-hygiene: invalid commit range" >&2; exit 2 ;; esac

work=$(mktemp -d "${TMPDIR:-/tmp}/console-hygiene.XXXXXX")
trap 'rm -rf "$work"' EXIT
trap 'exit 130' HUP INT TERM

git_q() { git -c core.quotePath=false "$@"; }
# Paths are passed as literal pathspecs so no character is interpreted.
export GIT_LITERAL_PATHSPECS=1

boundary_args=(--base "$base_ref")
[ "$committed" -eq 1 ] && boundary_args+=(--committed)
bash "$boundary" "${boundary_args[@]}" --list-paths >"$work/changed"
bash "$boundary" --print-allowlist >"$work/allowlist"

in_allowlist() {
    local path=$1 entry
    while IFS= read -r entry; do
        [ -n "$entry" ] || continue
        case "$entry" in
            */) case "$path" in "$entry"*) return 0 ;; esac ;;
            *) [ "$path" = "$entry" ] && return 0 ;;
        esac
    done <"$work/allowlist"
    return 1
}

# Split the changed paths into existing tracked files and untracked files.
: >"$work/tracked"
: >"$work/untracked"
if [ "$committed" -eq 1 ]; then
    while IFS= read -r path; do
        [ -n "$path" ] || continue
        # Blobs only: a submodule entry is reported by the file-mode gate.
        if [ "$(git cat-file -t "HEAD:$path" 2>/dev/null || true)" = blob ]; then
            printf '%s\n' "$path" >>"$work/tracked"
        fi
    done <"$work/changed"
else
    git_q ls-files --cached >"$work/index"
    while IFS= read -r path; do
        [ -n "$path" ] || continue
        { [ -f "$path" ] || [ -L "$path" ]; } || continue
        if grep -qxF -- "$path" "$work/index"; then
            printf '%s\n' "$path" >>"$work/tracked"
        elif in_allowlist "$path"; then
            printf '%s\n' "$path" >>"$work/untracked"
        fi
    done <"$work/changed"
fi
file_count=$(cat "$work/tracked" "$work/untracked" | grep -c . || true)

failures=0
report() {
    printf '%-4s %-22s %s\n' "$1" "$2" "$3"
    if [ "$1" = FAIL ]; then
        failures=$((failures + 1))
    fi
}
mode_label=working-tree
[ "$committed" -eq 1 ] && mode_label=committed
echo "check-hygiene: base $base_ref, merge base ${merge_base:0:12}, $mode_label, $file_count file(s) to scan"

# --- File gates -------------------------------------------------------------
: >"$work/binary"
: >"$work/large"
: >"$work/ext"
: >"$work/link"
: >"$work/mode"
: >"$work/whitespace"
diff_range=("$merge_base")
[ "$committed" -eq 1 ] && diff_range+=(HEAD)

# Git object modes: only regular files (100644, 100755) and symbolic links
# (120000, reported by their own gate). A submodule (160000) is never scanned
# by the gates below, so it is refused here.
changed_paths=()
while IFS= read -r path; do
    if [ -n "$path" ]; then changed_paths+=("$path"); fi
done <"$work/changed"
if [ "${#changed_paths[@]}" -gt 0 ]; then
    if [ "$committed" -eq 1 ]; then
        git_q ls-tree -r HEAD -- "${changed_paths[@]}"
    else
        git_q ls-files -s -- "${changed_paths[@]}"
    fi | awk '$1 !~ /^100(644|755)$/ && $1 != "120000" { sub(/^[^\t]*\t/, ""); print }' >"$work/mode"
fi

tracked_paths=()
while IFS= read -r path; do
    if [ -n "$path" ]; then tracked_paths+=("$path"); fi
done <"$work/tracked"
if [ "${#tracked_paths[@]}" -gt 0 ]; then
    git_q diff --numstat --no-renames "${diff_range[@]}" -- "${tracked_paths[@]}" |
        awk -F'\t' '$1 == "-" && $2 == "-" { print $3 }' >>"$work/binary"
fi
while IFS= read -r path; do
    [ -n "$path" ] || continue
    numstat=$(git_q diff --no-index --numstat -- /dev/null "$path" 2>/dev/null || true)
    case "$numstat" in
        -$'\t'-$'\t'*) printf '%s\n' "$path" >>"$work/binary" ;;
    esac
done <"$work/untracked"

total_bytes=0
while IFS= read -r path; do
    [ -n "$path" ] || continue
    if [ "$committed" -eq 1 ]; then
        mode=$(git ls-tree HEAD -- "$path" | awk '{ print $1 }')
        size=$(git cat-file -s "HEAD:$path")
        [ "$mode" = 120000 ] && printf '%s\n' "$path" >>"$work/link"
        nul=$(git cat-file blob "HEAD:$path" | tr -cd '\000' | wc -c | tr -d ' ')
    else
        if [ -L "$path" ]; then
            printf '%s\n' "$path" >>"$work/link"
            continue
        fi
        size=$(wc -c <"$path" | tr -d ' ')
        nul=$(tr -cd '\000' <"$path" | wc -c | tr -d ' ')
    fi
    # git's binary detection looks only at the first 8000 bytes; a NUL byte
    # anywhere makes the file binary here.
    [ "$nul" -eq 0 ] || printf '%s\n' "$path" >>"$work/binary"
    total_bytes=$((total_bytes + size))
    if [ "$size" -gt "$MAX_FILE_BYTES" ]; then
        printf '%s (%s bytes)\n' "$path" "$size" >>"$work/large"
    fi
    name=$(printf '%s' "${path##*/}" | tr '[:upper:]' '[:lower:]')
    case "$name" in
        *.*)
            ext=${name##*.}
            for bad in $FORBIDDEN_EXTENSIONS; do
                [ "$ext" = "$bad" ] && printf '%s\n' "$path" >>"$work/ext"
            done
            ;;
    esac
done < <(cat "$work/tracked" "$work/untracked")
sort -u "$work/binary" >"$work/binary.u"
mv "$work/binary.u" "$work/binary"

# Whitespace errors, as check_staged.sh checks with git diff --check.
if [ "${#tracked_paths[@]}" -gt 0 ]; then
    git_q diff --check --no-color --no-renames "${diff_range[@]}" -- "${tracked_paths[@]}" |
        grep -E '^[^+[:space:]][^:]*:[0-9]+:' | cut -d: -f1,2 >>"$work/whitespace" || true
fi
while IFS= read -r path; do
    [ -n "$path" ] || continue
    git_q diff --no-index --check --no-color -- /dev/null "$path" 2>/dev/null |
        grep -E '^[^+[:space:]][^:]*:[0-9]+:' | cut -d: -f1,2 >>"$work/whitespace" || true
done <"$work/untracked"

file_gate() {
    # file_gate NAME FILE OK-TEXT
    if [ -s "$2" ]; then
        report FAIL "$1" "$(grep -c . "$2") file(s):"
        sed 's/^/       /' "$2"
    else
        report ok "$1" "$3"
    fi
}
file_gate file-mode "$work/mode" "only regular files and symbolic links"
file_gate binary-file "$work/binary" "no binary content"
file_gate symbolic-link "$work/link" "no symbolic links"
file_gate file-size "$work/large" "no file over $MAX_FILE_BYTES bytes"
if [ "$total_bytes" -gt "$MAX_TOTAL_BYTES" ]; then
    report FAIL total-size "$total_bytes bytes in total, over $MAX_TOTAL_BYTES"
else
    report ok total-size "$total_bytes bytes in total, at most $MAX_TOTAL_BYTES"
fi
file_gate forbidden-extension "$work/ext" "no model, tensor or binary extensions"
file_gate whitespace "$work/whitespace" "no whitespace errors in added lines"

# --- Added lines ------------------------------------------------------------
# Build two parallel files: the text of every added line, and its location.
: >"$work/patch"
if [ "${#tracked_paths[@]}" -gt 0 ]; then
    git_q diff --unified=0 --no-color --no-ext-diff --no-renames --text \
        "${diff_range[@]}" -- "${tracked_paths[@]}" >>"$work/patch"
fi
while IFS= read -r path; do
    [ -n "$path" ] || continue
    git_q diff --no-index --unified=0 --no-color --no-ext-diff --text \
        -- /dev/null "$path" >>"$work/patch" 2>/dev/null || true
done <"$work/untracked"

awk -v text="$work/added.txt" -v loc="$work/added.loc" '
    # Inside a hunk every "+" line is content, even one that starts "+++ ".
    left > 0 && /^\+/ {
        print substr($0, 2) > text
        print path ":" line > loc
        line++
        left--
        next
    }
    /^\+\+\+ / {
        path = substr($0, 5)
        sub(/\t$/, "", path)
        if (substr(path, 1, 2) == "b/") path = substr(path, 3)
        next
    }
    /^--- / { next }
    /^@@ / {
        split($0, f, " ")
        spec = f[3]
        sub(/^\+/, "", spec)
        split(spec, g, ",")
        line = g[1] + 0
        left = (g[2] == "" ? 1 : g[2] + 0)
        next
    }
    /^\+/ {
        print substr($0, 2) > text
        print path ":" line > loc
        line++
        next
    }
' "$work/patch"
touch "$work/added.txt" "$work/added.loc"

# Allow markers: blank out lines whose marker id is listed; record unknown ids.
: >"$work/allow.ids"
if [ -f "$ALLOW_FILE" ]; then
    sed -e 's/#.*$//' -e 's/^[[:space:]]*//' "$ALLOW_FILE" | awk 'NF { print $1 }' >"$work/allow.ids"
fi
awk -v ids="$work/allow.ids" -v bad="$work/allow.bad" -v re="$ALLOW_MARKER_RE" '
    BEGIN { while ((getline id < ids) > 0) ok[id] = 1 }
    {
        if (match($0, re)) {
            id = substr($0, RSTART + 14, RLENGTH - 14)
            if (id in ok) { print ""; next }
            print NR > bad
        }
        print
    }
' "$work/added.txt" >"$work/added.filtered"
touch "$work/allow.bad"

line_findings() {
    # line_findings FLAGS REGEX SOURCE -> "path:line" for each match in SOURCE.
    # -a keeps GNU grep from stopping at NUL data.
    local flags=$1 regex=$2 src=$3 opts=-anE
    [ "$flags" = i ] && opts=-aniE
    grep $opts -e "$regex" "$src" 2>/dev/null | cut -d: -f1 |
        awk -v loc="$work/added.loc" '
            BEGIN { n = 0; while ((getline l < loc) > 0) where[++n] = l }
            { print where[$1 + 0] }
        ' || true
}

total_lines=$(grep -c '' "$work/added.txt" || true)
while IFS='|' read -r gate flags regex; do
    [ -n "$gate" ] || continue
    src="$work/added.txt"
    case "$EXCUSABLE_GATES" in *" $gate "*) src="$work/added.filtered" ;; esac
    line_findings "$flags" "$regex" "$src" >"$work/hits"
    if [ -s "$work/hits" ]; then
        report FAIL "$gate" "$(grep -c . "$work/hits") added line(s):"
        sed 's/^/       /' "$work/hits"
    else
        report ok "$gate" "none in $total_lines added line(s)"
    fi
done < <(line_gates)

if [ -s "$work/allow.bad" ]; then
    awk -v loc="$work/added.loc" '
        BEGIN { n = 0; while ((getline l < loc) > 0) where[++n] = l }
        { print where[$1 + 0] }
    ' "$work/allow.bad" >"$work/allow.where"
    report FAIL allow-marker "$(grep -c . "$work/allow.where") marker(s) with an id not in $ALLOW_FILE:"
    sed 's/^/       /' "$work/allow.where"
else
    report ok allow-marker "every allow marker is listed in $ALLOW_FILE"
fi

# --- Commit messages ----------------------------------------------------------
commit_regex=$(line_gates | awk -F'|' -v g="$COMMIT_GATE" '
    $1 == g { sub(/^[^|]*\|[^|]*\|/, ""); print }
')
: >"$work/commits.bad"
commit_total=0
for sha in $(git rev-list "$commit_range"); do
    commit_total=$((commit_total + 1))
    git log -1 --format=%B "$sha" >"$work/msg"
    if grep -aqiE -e "$commit_regex" "$work/msg"; then
        printf '%s\n' "${sha:0:12}" >>"$work/commits.bad"
    fi
done
if [ -s "$work/commits.bad" ]; then
    report FAIL commit-attribution "$(grep -c . "$work/commits.bad") commit message(s) in $commit_range:"
    sed 's/^/       /' "$work/commits.bad"
else
    report ok commit-attribution "no attribution lines in $commit_total commit message(s) in $commit_range"
fi

if [ "$failures" -gt 0 ]; then
    echo "check-hygiene: FAILED ($failures gate(s))"
    exit 1
fi
echo "check-hygiene: passed"
