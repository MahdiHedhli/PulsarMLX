#!/usr/bin/env python3
"""Regenerate decoder_ffn/provenance.json from the anchored bytes.

Order matters: every graph file except provenance.json and the
``PROVENANCE_SHA256`` line of source.py must be final before running this.
The tool writes provenance.json, then rewrites the single ``PROVENANCE_SHA256``
line in source.py to the digest of the bytes it just wrote. The loader template
digest is computed with that line zeroed, so it is unaffected by the rewrite.

Run with ``--check`` to verify the committed files without writing anything.
"""
import ast
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_ffn import source  # noqa: E402

SOURCE_PY = source.ROOT + 'decoder_ffn/source.py'


def compute(root):
    language, hc = (root / source.LANGUAGE).read_bytes(), (root / source.HC).read_bytes()
    if source.sha(language) != source.LANGUAGE_SHA256 or source.sha(hc) != source.HC_SHA256:
        raise SystemExit('UPSTREAM_DIGEST_MISMATCH')
    loader = (root / SOURCE_PY).read_bytes()
    template, count = re.subn(rb"PROVENANCE_SHA256 = '[0-9a-f]{64}'",
                              b"PROVENANCE_SHA256 = '" + b'0' * 64 + b"'", loader)
    if count != 1:
        raise SystemExit('LOADER_TEMPLATE_LINE')
    lt, ht = ast.parse(language), ast.parse(hc)
    ct = ast.parse((root / source.CAPSULE).read_bytes())
    language_nodes = [source._node(lt, n) for n in source.LANGUAGE_NAMES]
    hc_nodes = [source._node(ht, n) for n in source.HC_NAMES]
    original = source._node(source._node(lt, 'Glm5NextDecoderLayer'), '_ffn_block')
    transformed = copy.deepcopy(original)
    transformed.name = 'source_ffn_block'
    call = source._node(ct, 'source_ffn_block')
    all_nodes = language_nodes + hc_nodes + [call]
    existing = json.loads((root / source.PROVENANCE).read_bytes()) if (root / source.PROVENANCE).exists() else {}
    return {
        'schema': 'glm53-flash-decoder-ffn-provenance/2',
        'digest_scheme': source.DIGEST_SCHEME,
        'digest_scheme_note': 'canonical structural AST digests are interpreter-independent; see source._canonical',
        'upstream_commit': existing.get('upstream_commit'),
        'language_sha256': source.LANGUAGE_SHA256,
        'hyperconnection_sha256': source.HC_SHA256,
        'loader_template_sha256': source.sha(template),
        'graph_sha256': {p: source.sha((root / p).read_bytes()) for p in source.GRAPH_FILES},
        'caller_contract': {'original_ast_sha256': source.ast_sha(original),
                            'transformed_ast_sha256': source.ast_sha(transformed),
                            'transformations': ['rename _ffn_block to source_ffn_block only'],
                            'digest_scheme': source.DIGEST_SCHEME},
        'original_caller_body': ast.unparse(original),
        'transformed_caller_body': ast.unparse(transformed),
        'node_ast_sha256': {n.name: source.ast_sha(n) for n in all_nodes},
        'closure_globals': source._closure(all_nodes),
    }


def render(p):
    return (json.dumps(p, indent=2, sort_keys=True) + '\n').encode()


def main():
    check = '--check' in sys.argv
    provenance = render(compute(ROOT))
    digest = source.sha(provenance)
    loader = (ROOT / SOURCE_PY).read_bytes()
    updated = re.sub(rb"PROVENANCE_SHA256 = '[0-9a-f]{64}'",
                     b"PROVENANCE_SHA256 = '" + digest.encode() + b"'", loader, count=1)
    current = (ROOT / source.PROVENANCE).read_bytes() if (ROOT / source.PROVENANCE).exists() else b''
    same = current == provenance and updated == loader
    if check:
        print(json.dumps({'provenance_up_to_date': current == provenance, 'loader_pin_up_to_date': updated == loader,
                          'provenance_sha256': digest}))
        sys.exit(0 if same else 2)
    (ROOT / source.PROVENANCE).write_bytes(provenance)
    (ROOT / SOURCE_PY).write_bytes(updated)
    print(json.dumps({'written': True, 'provenance_sha256': digest, 'changed': not same}))


if __name__ == '__main__':
    main()
