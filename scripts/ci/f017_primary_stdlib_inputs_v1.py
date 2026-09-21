"""Bounded source-as-data closure for the primary-only doctor.

No research imports or numerical execution occur in source preparation. The
named current modules must match a prospectively supplied input manifest.
"""
import ast
import hashlib
import json
from pathlib import Path
import sys

ROOTS = ('f017_primary_stdlib_cases_v1',)
SEARCH = ('scripts/ci', 'scripts/research', 'scripts/research/tests',
          'scripts/research/tests/f017_sequence54')
FORBIDDEN = ('numpy', 'blas', 'secondary')

def need(value, message):
    if not value:
        raise ValueError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def census(source):
    source = Path(source).resolve(strict=True)
    pending = list(ROOTS); modules = {}; files = {}; edges = []; surfaces = []
    while pending:
        name = pending.pop()
        if name in modules:
            continue
        need(not any(word in name.lower() for word in FORBIDDEN), 'FORBIDDEN_SOURCE_DEPENDENCY')
        matches = [source/directory/(name+'.py') for directory in SEARCH
                   if (source/directory/(name+'.py')).is_file()]
        need(len(matches) == 1, 'EXACT_SOURCE_MODULE:'+name)
        path = matches[0]; relative = str(path.relative_to(source))
        need(path.resolve(strict=True) == path and path.stat().st_size <= 1048576,
             'SOURCE_REGULAR_BOUND')
        raw = path.read_bytes(); tree = ast.parse(raw, filename=relative)
        modules[name] = relative; files[relative] = sha(raw)
        need(len(modules) <= 64, 'MODULE_CENSUS_BOUND')
        for node in ast.walk(tree):
            imports = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module] if isinstance(node, ast.ImportFrom) and node.module else []
            for target in imports:
                top = target.split('.')[0]
                need(not any(word in top.lower() for word in FORBIDDEN),
                     'FORBIDDEN_SOURCE_DEPENDENCY:'+target)
                standard = top in sys.stdlib_module_names
                edges.append(dict(source=relative, line=node.lineno,
                                  target=target, stdlib=standard))
                if not standard:
                    need(top == target, 'DOTTED_PROJECT_IMPORT_NOT_ADMITTED')
                    pending.append(target)
        # A finite review surface, not an automatic proof of all dynamic calls.
        for node in tree.body:
            surfaces.append(dict(path=relative, line=node.lineno,
                                 end_line=node.end_lineno, kind=type(node).__name__))
    return dict(scope='PRIMARY_STDLIB_ONLY', files=files, modules=modules,
                edges=edges, top_level_surfaces=surfaces,
                completeness='NAMED_STATIC_IMPORT_CLOSURE_PLUS_RUNTIME_ORIGIN_GUARD')

def require_fixture_generation(value, current):
    need(set(value) == {'schema','scope','generation','source_head','source_tree',
                       'files','criteria','archive_input_status'}, 'GENERATION_FIELDS')
    need(value['schema'] == 'pulsarmlx.primary-stdlib-fixture-generation/1'
         and value['scope'] == 'PRIMARY_STDLIB_ONLY'
         and type(value['generation']) is int and value['generation'] in (1, 2),
         'GENERATION_SCHEMA')
    need(value['files'] == current['files'], 'FROZEN_INPUT_IDENTITY')
    return value
