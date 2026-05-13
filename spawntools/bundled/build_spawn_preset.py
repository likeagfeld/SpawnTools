"""Regenerate the bundled Spawn-baseline preset metadata.

Reads the canonical campaign artifacts:
  - `_shared_tools/jp_en_dict.py` (the 700+ entry dictionary)
  - The current `patches/` dir for Spawn

Writes:
  - `bundled/spawn_preset/preset.json`     — file inventory + counts
  - `bundled/spawn_preset/jp_en_dict.json` — dictionary as JSON
  - `bundled/spawn_preset/texture_notes.json`
  - `bundled/spawn_preset/binary_notes.json`

SpawnTools's `core/preset.py` loads these at runtime when the user
clicks "Load Spawn Baseline" on Tab 1. We do NOT bundle the actual
patches/ binaries here — those live alongside the user's disc copy.
The preset is JUST METADATA + DICT — the EN translations come from
diffing extracted/ vs patches/ at scan time.

Run once when the patches dir or dict changes:
    python -m spawntools.bundled.build_spawn_preset
"""
from __future__ import annotations
import sys
import json
import hashlib
from pathlib import Path

# Path to _shared_tools (importable as a sibling lib)
SHARED_TOOLS = Path(r"D:/Capcom Dreamcast  Games - Joe Patched/RC2 Translated/_shared_tools")
SPAWN_DIR = Path(r"D:/Capcom Dreamcast  Games - Joe Patched/RC2 Translated/Spawn - In the Demon's Hand (JP)")
BUNDLE = Path(__file__).resolve().parent / 'spawn_preset'


def main():
    BUNDLE.mkdir(parents=True, exist_ok=True)

    # ---------- JP→EN dictionary ----------
    sys.path.insert(0, str(SHARED_TOOLS))
    import jp_en_dict
    dict_count = len(jp_en_dict.DICT)
    print(f'JP->EN dict: {dict_count} entries')
    (BUNDLE / 'jp_en_dict.json').write_text(
        json.dumps(jp_en_dict.DICT, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )

    # ---------- file inventory ----------
    ext_dir = SPAWN_DIR / 'extracted'
    patches_dir = SPAWN_DIR / 'patches'
    modified: list[dict] = []
    identical_count = 0
    if ext_dir.is_dir() and patches_dir.is_dir():
        for p in patches_dir.rglob('*'):
            if not p.is_file():
                continue
            rel = p.relative_to(patches_dir).as_posix()
            b = ext_dir / rel
            if not b.exists():
                continue
            p_bytes = p.read_bytes()
            b_bytes = b.read_bytes()
            if p_bytes == b_bytes:
                identical_count += 1
            else:
                modified.append({
                    'rel': rel,
                    'baseline_md5': hashlib.md5(b_bytes).hexdigest(),
                    'patched_md5': hashlib.md5(p_bytes).hexdigest(),
                    'size': len(b_bytes),
                    'patched_size': len(p_bytes),
                })

    print(f'modified files: {len(modified)}   identical: {identical_count}')
    for m in modified:
        print(f'  {m["rel"]:30s}  {m["size"]:>10,}  '
              f'{m["baseline_md5"][:8]} -> {m["patched_md5"][:8]}')

    # ---------- texture notes (hand-curated from the campaign) ----------
    texture_notes = {
        'LOBBY37.TEX': {
            'description': 'Top banners + KDD legal text + Terms of Use paragraphs',
            'subtex_notes': {
                '0': 'Top banner — "FIND PLAYER" (was JP banner). Re-rendered with '
                      'rotate(-90, expand=True) for the vertical-strip atlas layout '
                      'the DC sampler expects.',
                '1': 'KDD legal text + Terms paragraphs as multi-line vertical strips. '
                      'All vertical strips get the same text (game samples one strip '
                      'at multiple screen X positions — observed empirically).',
            },
        },
        'LOBBY38.TEX': {
            'description': 'Lobby/menu HUD strips (PERSONAL STATUS, descriptions, L-trigger help)',
            'subtex_notes': {
                '2': 'Yellow headers — PERSONAL STATUS, Save IDs, etc.',
                '4': 'Random Match / Beginner Only button labels. v23 redraw used '
                      'mode=clean to erase old upside-down pixels from the v18 '
                      'rotate(+90) bug.',
                '7': 'Current Players label — bumped font size to fix fuzziness.',
                '12': 'Lトリガーでログ閲覧 -> "L Trigger: view log"',
            },
        },
        'LOBBY40.TEX': {
            'description': 'AUTO MATCH popup descriptions + footer',
            'subtex_notes': {},
        },
        'CFGJP.TEX': {
            'description': 'Config screen — controller diagram + key configuration labels',
            'subtex_notes': {
                '3': 'Three views of the Dreamcast gamepad (front, top, side).',
            },
        },
        'CFGUS.TEX': {
            'description': 'US controller-config TEX — sibling of CFGJP.TEX',
            'subtex_notes': {},
        },
        'COCKPITJP.TEX': {
            'description': 'In-game HUD overlay sprites (BOSS, TOP, character poses, kanji headers)',
            'subtex_notes': {},
        },
        'DPTEX/TAG_SU.PVR': {
            'description': 'Paletted PVR — popup-button atlas. 512x512 PAL_8BPP '
                            'TWIDDLED_MIPMAP, uses BANK01.PVP palette (NOT BANK00 — '
                            'that renders rainbow).',
            'subtex_notes': {
                '0_strip0': '対戦待機 -> Wait',
                '0_strip1': 'キャンセル -> Cancel',
                'note': 'Byte-identical across 5 DP3 games (Spawn, JoJo, Net de Tennis, '
                        'Project Justice, Vampire Chronicle) — translate once, ship 5x.',
            },
        },
    }
    (BUNDLE / 'texture_notes.json').write_text(
        json.dumps(texture_notes, indent=2, ensure_ascii=False), encoding='utf-8',
    )

    # ---------- binary file notes ----------
    binary_notes = {
        '1ST_READ.BIN': {
            'description': 'Main game executable. ~347 safe null-bounded JP->EN binary '
                            'replacements. cp932 strings only, shrink-or-equal byte budget.',
        },
        '2_DP.BIN': {
            'description': 'Dream Passport 3 framework binary + JP IME word dictionary. '
                            'Personal Status format-string fixes only (時間 -> Hr at offset '
                            '0x15bc78 and 5 more copies). Most of this file is the IME word '
                            'dictionary — DO NOT BULK-EDIT it.',
        },
        'DPETC/MESSAGE.INI': {
            'description': 'DP3 framework string table (~786 numeric keys). Transplanted '
                            "from CvS Pro EN's community translation. Each KEY=VALUE line "
                            'preserves its byte length (English padded with trailing spaces).',
        },
    }
    (BUNDLE / 'binary_notes.json').write_text(
        json.dumps(binary_notes, indent=2, ensure_ascii=False), encoding='utf-8',
    )

    # ---------- manifest ----------
    manifest = {
        'name': "Spawn - In the Demon's Hand (campaign baseline)",
        'tier': 'done',
        'modified_files': modified,
        'modified_count': len(modified),
        'identical_count': identical_count,
        'dict_entries': dict_count,
        'texture_files_with_notes': len(texture_notes),
        'binary_files_with_notes': len(binary_notes),
        'description': (
            "Built from the canonical Spawn translation campaign. "
            "Loads every existing English string + every redrawn texture as the "
            "baseline. You can revert any row / file / everything to stock JP "
            "- or continue from here with new edits."
        ),
        'expected_paths_hint': {
            'spawn_dir': str(SPAWN_DIR),
            'shared_tools': str(SHARED_TOOLS),
        },
    }
    (BUNDLE / 'preset.json').write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8',
    )
    print(f'\nwrote: {BUNDLE / "preset.json"}')
    print(f'       {BUNDLE / "jp_en_dict.json"}  ({dict_count} entries)')
    print(f'       {BUNDLE / "texture_notes.json"}  ({len(texture_notes)} entries)')
    print(f'       {BUNDLE / "binary_notes.json"}  ({len(binary_notes)} entries)')


if __name__ == '__main__':
    main()
