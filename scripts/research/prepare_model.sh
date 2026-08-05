#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)

usage() {
    cat <<'EOF'
Usage: scripts/research/prepare_model.sh \
  --model ABSOLUTE_PATH \
  --inspection ABSOLUTE_PATH \
  --oracle-work ABSOLUTE_PATH \
  --oracle-output ABSOLUTE_PATH \
  --oracle ABSOLUTE_PATH \
  --evidence-dir ABSOLUTE_PATH \
  --fixture-evidence ABSOLUTE_PATH

Validates explicit external path relationships without resolving, opening,
stating, hashing, creating, or modifying any supplied path.
EOF
}

fail() {
    echo "research path preparation: $1" >&2
    exit 2
}

model_path=${PULSARMLX_MODEL_GGUF-}
inspection_path=${PULSARMLX_ROUTER_INSPECTION-}
oracle_work_path=${PULSARMLX_ORACLE_WORK-}
oracle_output_path=${PULSARMLX_ORACLE_OUTPUT-}
oracle_path=${PULSARMLX_ROUTER_ORACLE-}
evidence_path=${PULSARMLX_ROUTER_EVIDENCE-}
fixture_evidence_path=${PULSARMLX_ROUTER_FIXTURE_EVIDENCE-}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --help|-h)
            usage
            exit 0
            ;;
        --model|--inspection|--oracle-work|--oracle-output|--oracle|--evidence-dir|--fixture-evidence)
            option=$1
            shift
            [ "$#" -gt 0 ] || fail "missing value for an option"
            case "$option" in
                --model) model_path=$1 ;;
                --inspection) inspection_path=$1 ;;
                --oracle-work) oracle_work_path=$1 ;;
                --oracle-output) oracle_output_path=$1 ;;
                --oracle) oracle_path=$1 ;;
                --evidence-dir) evidence_path=$1 ;;
                --fixture-evidence) fixture_evidence_path=$1 ;;
            esac
            shift
            ;;
        *)
            fail "unknown option"
            ;;
    esac
done

validate_path() {
    path_label=$1
    candidate=$2

    [ -n "$candidate" ] || fail "$path_label is required"
    case "$candidate" in
        /*) ;;
        *) fail "$path_label must be absolute" ;;
    esac

    newline='
'
    case "$candidate" in
        *"$newline"*) fail "$path_label contains a control character" ;;
    esac
    if printf '%s' "$candidate" | LC_ALL=C grep -q '[[:cntrl:]]'; then
        fail "$path_label contains a control character"
    fi

    case "$candidate" in
        /|*//*|*/.|*/..|*/./*|*/../*|*/)
            fail "$path_label must be a normalized absolute path"
            ;;
    esac

    candidate_folded=$(printf '%s' "$candidate" | LC_ALL=C tr '[:upper:]' '[:lower:]')
    repository_folded=$(printf '%s' "$repository_root" | LC_ALL=C tr '[:upper:]' '[:lower:]')
    case "$candidate_folded" in
        "$repository_folded"|"$repository_folded"/*)
            fail "$path_label must remain outside the repository"
            ;;
    esac
}

paths_overlap() {
    first_path=$(printf '%s' "$1" | LC_ALL=C tr '[:upper:]' '[:lower:]')
    second_path=$(printf '%s' "$2" | LC_ALL=C tr '[:upper:]' '[:lower:]')
    [ "$first_path" = "$second_path" ] && return 0
    case "$first_path" in
        "$second_path"/*) return 0 ;;
    esac
    case "$second_path" in
        "$first_path"/*) return 0 ;;
    esac
    return 1
}

require_disjoint() {
    first_label=$1
    first_path=$2
    second_label=$3
    second_path=$4
    if paths_overlap "$first_path" "$second_path"; then
        fail "$first_label and $second_label must not alias or contain one another"
    fi
}

validate_path model "$model_path"
validate_path inspection "$inspection_path"
validate_path oracle-work "$oracle_work_path"
validate_path oracle-output "$oracle_output_path"
validate_path oracle "$oracle_path"
validate_path evidence-dir "$evidence_path"
validate_path fixture-evidence "$fixture_evidence_path"

require_disjoint model "$model_path" inspection "$inspection_path"
require_disjoint model "$model_path" oracle-work "$oracle_work_path"
require_disjoint model "$model_path" oracle-output "$oracle_output_path"
require_disjoint model "$model_path" oracle "$oracle_path"
require_disjoint model "$model_path" evidence-dir "$evidence_path"
require_disjoint model "$model_path" fixture-evidence "$fixture_evidence_path"

require_disjoint oracle-work "$oracle_work_path" oracle-output "$oracle_output_path"
require_disjoint oracle-work "$oracle_work_path" inspection "$inspection_path"
require_disjoint oracle-work "$oracle_work_path" evidence-dir "$evidence_path"
require_disjoint oracle-work "$oracle_work_path" fixture-evidence "$fixture_evidence_path"

oracle_folded=$(printf '%s' "$oracle_path" | LC_ALL=C tr '[:upper:]' '[:lower:]')
oracle_output_folded=$(printf '%s' "$oracle_output_path" | LC_ALL=C tr '[:upper:]' '[:lower:]')
case "$oracle_folded" in
    "$oracle_output_folded"/*) ;;
    *) fail "oracle must be a child of oracle-output" ;;
esac

require_disjoint oracle-output "$oracle_output_path" inspection "$inspection_path"
require_disjoint oracle-output "$oracle_output_path" evidence-dir "$evidence_path"
require_disjoint oracle-output "$oracle_output_path" fixture-evidence "$fixture_evidence_path"
require_disjoint inspection "$inspection_path" evidence-dir "$evidence_path"
require_disjoint inspection "$inspection_path" fixture-evidence "$fixture_evidence_path"
require_disjoint evidence-dir "$evidence_path" fixture-evidence "$fixture_evidence_path"

echo "research path preparation: validated explicit external paths (model bytes untouched)"
