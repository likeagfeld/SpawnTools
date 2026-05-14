"""Mine the Ghidra dumps to extract per-game intel:
  - All named functions matching texture / sprite / load patterns
  - All defined strings containing texture filename patterns
  - Counts of named functions per FIDB-attributed source
"""
import json
import re
from collections import Counter
from pathlib import Path

DUMP_DIR = Path(r"D:\DC_CapcomTranslationTools\spawn_re_ghidra\ghidra_dumps")

TEX_FN_RE = re.compile(r'(tex|pvr|sprite|twiddl|kmtex|kmpvr|load_te|load_pv|gbix)', re.I)
TEX_STR_RE = re.compile(r'\.tex|\.pvr|\.bin|texture|sprite', re.I)

result = {}
for json_path in sorted(DUMP_DIR.glob('*.json')):
    slug = json_path.stem.replace('_1ST_READ.bin', '')
    try:
        d = json.loads(json_path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f'  ERR {slug}: {e}')
        continue
    funcs = d.get('functions', [])
    strs = d.get('strings', [])
    tex_funcs = [f for f in funcs if TEX_FN_RE.search(f['name'])]
    tex_strs = [s for s in strs if TEX_STR_RE.search(s.get('value', ''))]
    result[slug] = {
        'functions': len(funcs),
        'strings':   len(strs),
        'tex_funcs': len(tex_funcs),
        'tex_strs':  len(tex_strs),
        'tex_func_names': [f['name'] for f in tex_funcs[:8]],
        'tex_str_samples': [s['value'] for s in tex_strs[:10]],
    }

print(f'{"game":24s} {"funcs":>6} {"strs":>6} {"texFn":>6} {"texStr":>7}')
print('-' * 70)
for slug, info in result.items():
    print(f'{slug:24s} {info["functions"]:>6} {info["strings"]:>6} '
          f'{info["tex_funcs"]:>6} {info["tex_strs"]:>7}')

print('\n--- Per-game texture functions + sample filenames ---')
for slug, info in result.items():
    print(f'\n{slug}:')
    print(f'  tex funcs: {info["tex_func_names"]}')
    print(f'  tex strs:  {info["tex_str_samples"][:5]}')
