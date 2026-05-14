"""Generalized bundled-preset builder — produces one `bundled/<slug>_preset/`
per game registered in `game_registry.py`.

For each game, writes:
  preset.json       — file inventory (md5s), counts, detection label, deny list
  jp_en_dict.json   — shared 796-entry JP→EN dictionary
  translations.json — every diff-derivable EN translation pair
  texture_notes.json / binary_notes.json — sparse per-game notes

Run:
    python -m spawntools.bundled.build_preset           # all games
    python -m spawntools.bundled.build_preset spawn     # just one
"""
from __future__ import annotations
import sys
import json
import hashlib
from pathlib import Path

from .game_registry import GAMES, GameConfig, by_slug
from ..core.file_classifier import classify as classify_file

SHARED_TOOLS = Path(r"D:/Capcom Dreamcast  Games - Joe Patched/RC2 Translated/_shared_tools")
BUNDLE_ROOT = Path(__file__).resolve().parent


def find_cp932_runs(data: bytes, min_chars: int = 4):
    """Find every cp932 run of at least min_chars CJK characters."""
    out = []
    i, L = 0, len(data)
    while i < L - 1:
        start, run = i, 0
        while i < L - 1:
            b1, b2 = data[i], data[i + 1]
            if ((0x81 <= b1 <= 0x9f or 0xe0 <= b1 <= 0xfc)
                    and (0x40 <= b2 <= 0xfc and b2 != 0x7f)):
                run += 1
                i += 2
            else:
                break
        if run >= min_chars:
            txt = data[start:start + run * 2].decode('cp932', errors='replace')
            out.append((start, run, txt))
        else:
            i = max(start + 1, i + 1)
    return out


def derive_translations(game: GameConfig) -> list[dict]:
    """Diff extracted/ vs patches/ for each scan_target, return EN translation rows."""
    ext_dir = game.rc2_dir / 'extracted'
    pat_dir = game.rc2_dir / 'patches'
    if not (ext_dir.is_dir() and pat_dir.is_dir()):
        return []
    translations: list[dict] = []
    for rel in game.scan_targets:
        base_path = ext_dir / rel
        pat_path = pat_dir / rel
        if not (base_path.is_file() and pat_path.is_file()):
            continue
        base = base_path.read_bytes()
        pat = pat_path.read_bytes()
        if len(base) != len(pat):
            continue  # size mismatch — skip rather than emit garbage
        for offset, char_count, jp in find_cp932_runs(base, min_chars=4):
            budget = char_count * 2
            pat_bytes = pat[offset:offset + budget]
            if pat_bytes == base[offset:offset + budget]:
                continue
            try:
                en = pat_bytes.rstrip(b'\x00').decode('ascii')
            except UnicodeDecodeError:
                try:
                    en = pat_bytes.rstrip(b'\x00').decode('cp932')
                except UnicodeDecodeError:
                    en = '<binary diff - review manually>'
            translations.append({
                'source_file': rel,
                'byte_offset': offset,
                'byte_budget': budget,
                'jp': jp,
                'en': en,
            })
    return translations


def inventory_modified(game: GameConfig) -> tuple[list[dict], int]:
    """Walk patches/, compare each file vs extracted/, classify each modified
    file by content, and SKIP audio/video files from the surfaced inventory.
    """
    ext_dir = game.rc2_dir / 'extracted'
    pat_dir = game.rc2_dir / 'patches'
    modified: list[dict] = []
    identical = 0
    skipped_audio_video = 0
    if not (ext_dir.is_dir() and pat_dir.is_dir()):
        return modified, identical
    for p in pat_dir.rglob('*'):
        if not p.is_file(): continue
        rel = p.relative_to(pat_dir).as_posix()
        if p.name.endswith('.pre_twinstick_revert'): continue
        if p.suffix.lower() == '.bak': continue
        b = ext_dir / rel
        if not b.exists(): continue
        p_bytes = p.read_bytes()
        b_bytes = b.read_bytes()
        if p_bytes == b_bytes:
            identical += 1
            continue
        # Classify by BASELINE bytes (patches/ may have been overwritten with
        # English content that no longer looks like the original).
        cls = classify_file(b, b_bytes)
        if cls['kind'] in ('audio', 'video'):
            skipped_audio_video += 1
            continue
        modified.append({
            'rel': rel,
            'baseline_md5': hashlib.md5(b_bytes).hexdigest(),
            'patched_md5': hashlib.md5(p_bytes).hexdigest(),
            'size': len(b_bytes),
            'patched_size': len(p_bytes),
            'kind': cls['kind'],
            'jp_runs': cls['jp_runs'],
            'pvrt_count': cls['pvrt_count'],
        })
    return modified, identical


def build_one(game: GameConfig, shared_dict: dict) -> dict:
    """Build the bundled preset for one game. Returns a summary dict."""
    bundle = BUNDLE_ROOT / f'{game.slug}_preset'
    bundle.mkdir(parents=True, exist_ok=True)

    # Shared dictionary (same for every game)
    (bundle / 'jp_en_dict.json').write_text(
        json.dumps(shared_dict, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )

    # Diff-derived translations
    translations = derive_translations(game)
    (bundle / 'translations.json').write_text(
        json.dumps(translations, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )

    # File inventory
    modified, identical = inventory_modified(game)

    # Existing notes? Keep them; otherwise emit empty stubs.
    tex_notes_path = bundle / 'texture_notes.json'
    if not tex_notes_path.exists():
        tex_notes_path.write_text('{}', encoding='utf-8')
    bin_notes_path = bundle / 'binary_notes.json'
    if not bin_notes_path.exists():
        bin_notes_path.write_text('{}', encoding='utf-8')

    # Per-kind counts so the GUI can show e.g. "8 textures, 3 text files,
    # 1 archive" without re-scanning at runtime.
    kind_counts: dict[str, int] = {}
    for m in modified:
        kind_counts[m['kind']] = kind_counts.get(m['kind'], 0) + 1

    manifest = {
        'name': f'{game.display_name} (campaign baseline)',
        'slug': game.slug,
        'display_name': game.display_name,
        'tier': 'done',
        'product_code': game.product_code,
        'detect_label': game.detect_label,
        'notes_kind': game.notes_kind,
        'deny_list': game.deny_list,
        'scan_targets': game.scan_targets,
        'modified_files': modified,
        'modified_count': len(modified),
        'modified_by_kind': kind_counts,
        'identical_count': identical,
        'translations_count': len(translations),
        'dict_entries': len(shared_dict),
        'description': (
            f"Bundled baseline for {game.display_name}. EN translations are "
            f"diff-derived from extracted/ vs patches/. Edit them in Tab 3 or "
            f"revert per-row / per-file / all to stock JP."
        ),
    }
    (bundle / 'preset.json').write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )
    return {
        'slug': game.slug,
        'modified': len(modified),
        'identical': identical,
        'translations': len(translations),
    }


def main(only_slug: str | None = None):
    sys.path.insert(0, str(SHARED_TOOLS))
    import jp_en_dict
    shared_dict = jp_en_dict.DICT

    summary_rows = []
    targets = [by_slug(only_slug)] if only_slug else GAMES
    targets = [t for t in targets if t is not None]

    for game in targets:
        if not game.rc2_dir.is_dir():
            print(f'{game.slug:24s} SKIP — rc2_dir missing: {game.rc2_dir}')
            continue
        result = build_one(game, shared_dict)
        summary_rows.append(result)
        print(f"{game.slug:24s}  {result['translations']:>5} translations  "
              f"{result['modified']:>4} modified  {result['identical']:>5} identical")

    # Master games index for the GUI's preset-picker + detect_for_disc
    index = {
        'games': [
            {
                'slug': g.slug,
                'display_name': g.display_name,
                'product_code': g.product_code,
                'detect_label': g.detect_label,
                'preset_dir': f'{g.slug}_preset',
            }
            for g in GAMES
        ],
    }
    (BUNDLE_ROOT / 'games.json').write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding='utf-8',
    )
    print(f'\nwrote {len(summary_rows)} preset bundles + games.json')


if __name__ == '__main__':
    only = sys.argv[1] if len(sys.argv) > 1 else None
    main(only)
