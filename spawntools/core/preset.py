"""Spawn baseline preset loader.

What this does, in one breath:
  Reads the bundled `spawn_preset/` metadata (dictionary, texture notes,
  binary notes), then derives the per-string EN translations by DIFFING
  the user's `patches/` dir against their `extracted/` dir. Every string
  where the bytes differ becomes a pre-filled, status=done row in the
  StringDB. Every modified picture file is annotated with our notes.

Why diff-derived instead of bundling actual EN strings:
  • The user already has the canonical patches/ on disk (it ships with
    the campaign repo).
  • Diff-derived stays in sync if the user updates patches/ via git pull.
  • Avoids re-encoding lossy cp932 round-trips on bundle/unbundle.

User flows the preset supports:
  1. "Show me everything the campaign changed" — Text Grid filtered to 'done';
     Texture tab highlights modified files; sidebar shows the notes.
  2. "Revert this one row to JP" — copy the JP bytes back at that offset.
  3. "Revert this whole file to JP" — copy extracted/ over patches/.
  4. "Start fresh from JP" — Reset Patches (Tab 1 button).
  5. "Continue from Farkus's baseline" — just don't revert; edit on top.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import encoding as enc_core
from . import strings as strings_core


@dataclass
class Preset:
    """The bundled Spawn-baseline metadata, loaded from JSON."""
    name: str
    tier: str
    description: str
    dict_entries: dict[str, str]
    texture_notes: dict[str, dict]
    binary_notes: dict[str, dict]
    modified_files: list[dict]
    modified_count: int = 0
    # Every JP→EN translation pre-derived from the campaign's patches/ at
    # build time. Lets users see + edit the existing translations even
    # before they extract a disc.
    translations: list[dict] | None = None

    @classmethod
    def load_bundled(cls) -> 'Preset':
        """Load the preset shipped in `spawntools/bundled/spawn_preset/`."""
        root = Path(__file__).resolve().parent.parent / 'bundled' / 'spawn_preset'
        if not root.is_dir():
            raise RuntimeError(
                f'Bundled Spawn preset not found at {root}. Run\n'
                f'  python -m spawntools.bundled.build_spawn_preset\n'
                f'to generate it.'
            )
        manifest = json.loads((root / 'preset.json').read_text(encoding='utf-8'))
        translations = None
        translations_path = root / 'translations.json'
        if translations_path.is_file():
            try:
                translations = json.loads(translations_path.read_text(encoding='utf-8'))
            except json.JSONDecodeError:
                translations = None
        return cls(
            name=manifest['name'],
            tier=manifest.get('tier', '?'),
            description=manifest.get('description', ''),
            dict_entries=json.loads((root / 'jp_en_dict.json').read_text(encoding='utf-8')),
            texture_notes=json.loads((root / 'texture_notes.json').read_text(encoding='utf-8')),
            binary_notes=json.loads((root / 'binary_notes.json').read_text(encoding='utf-8')),
            modified_files=manifest.get('modified_files', []),
            modified_count=manifest.get('modified_count', 0),
            translations=translations,
        )


# ---------- baseline-vs-patches diff scanner ----------

def scan_with_baseline(extracted: Path, patches: Path, source_rel: str,
                       db: strings_core.StringDB,
                       dict_map: dict[str, str],
                       progress: Optional[Callable[[str], None]] = None) -> dict:
    """For one file (e.g. 1ST_READ.BIN), find every JP run in the BASELINE
    copy. For each, check the PATCHES copy at the same offset:

      • If patches bytes match baseline → row is status='todo', en_text=''.
      • If patches bytes differ AND decode as printable ASCII → row is
        status='done', en_text = ASCII string (the campaign's translation).
      • If patches bytes differ but are NOT printable → still 'done' with
        en_text = '<binary diff>' so the user can investigate.

    Also: if the dictionary has a JP key but no row is pre-filled, we
    suggest the dict value in `notes` (the user can apply with one click
    in Tab 3).

    Returns: { 'jp_runs': N, 'pre_filled': M, 'identical': K, 'dict_hints': D }
    """
    log = progress or (lambda _m: None)
    base_path = extracted / source_rel
    pat_path = patches / source_rel
    if not (base_path.is_file() and pat_path.is_file()):
        return {'jp_runs': 0, 'pre_filled': 0, 'identical': 0, 'dict_hints': 0}

    base = base_path.read_bytes()
    pat = pat_path.read_bytes()
    if len(base) != len(pat):
        log(f'  WARNING: {source_rel} differs in size — baseline {len(base):,} vs patches {len(pat):,}')

    runs = enc_core.find_cp932_runs(base, min_chars=4)
    n_filled = n_identical = n_hints = 0
    import sqlite3, time
    now = int(time.time())

    for offset, char_count, jp_text in runs:
        budget = char_count * 2
        # Read patches bytes at the same offset
        pat_bytes = pat[offset:offset + budget]
        base_bytes = base[offset:offset + budget]

        # Decide status + EN
        if pat_bytes == base_bytes:
            status = 'todo'
            en_text = ''
            n_identical += 1
        else:
            # Try ASCII decode (most Spawn replacements are ASCII)
            try:
                en_text = pat_bytes.rstrip(b'\x00').decode('ascii')
                status = 'done'
                n_filled += 1
            except UnicodeDecodeError:
                # Try cp932 (some Spawn replacements use full-width Latin)
                try:
                    en_text = pat_bytes.rstrip(b'\x00').decode('cp932')
                    status = 'done'
                    n_filled += 1
                except UnicodeDecodeError:
                    en_text = '<binary diff — review manually>'
                    status = 'done'
                    n_filled += 1

        # Dictionary hint
        notes = ''
        if status == 'todo' and jp_text in dict_map:
            notes = f'dict suggests: {dict_map[jp_text]!r}'
            n_hints += 1

        try:
            db._conn.execute(
                """INSERT INTO strings
                   (source_file, byte_offset, byte_budget, jp_text, en_text,
                    status, notes, updated_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (source_rel, offset, budget, jp_text, en_text,
                 status, notes, now)
            )
        except sqlite3.IntegrityError:
            # Row exists from a previous scan — update it
            db._conn.execute(
                """UPDATE strings SET en_text=?, status=?, notes=?, updated_at=?
                   WHERE source_file=? AND byte_offset=?""",
                (en_text, status, notes, now, source_rel, offset)
            )
    db._conn.commit()
    log(f'  {source_rel}: {len(runs):,} JP runs, {n_filled:,} pre-filled, '
        f'{n_hints:,} dict hints')
    return {
        'jp_runs': len(runs), 'pre_filled': n_filled,
        'identical': n_identical, 'dict_hints': n_hints,
    }


def apply_preset(disc, db: strings_core.StringDB, preset: Preset,
                  progress: Optional[Callable[[str], None]] = None) -> dict:
    """Populate `db` with the campaign's known translations.

    Strategy (in order — each step tries to add what the previous didn't):

      1. **Diff scan** (preferred): if `disc` has both `extracted/` and
         `patches/`, diff every BIN/INI file and pre-fill rows where
         patches differ from baseline. This always reflects the user's
         CURRENT patches/ — the truest source of truth.

      2. **Bundled-translations fallback**: if the diff scan didn't run
         OR produced zero rows (e.g., patches/ is identical to extracted/
         because the user hasn't applied the .dcp yet), seed from
         `translations.json` so they can still see + edit the campaign's
         translations.

    Skips DENY_LIST (2_DP.BIN, GAME.BIN, etc.) because those contain CJK
    data bytes that aren't real strings.
    """
    log = progress or (lambda _m: None)
    summary = {
        'files_scanned': 0, 'jp_runs': 0,
        'pre_filled': 0, 'identical': 0, 'dict_hints': 0,
        'from_bundle': 0,
    }

    # === Step 1: live diff scan of the user's extracted/ vs patches/ ===
    candidates: list[str] = []
    for p in disc.extracted_dir.rglob('*'):
        if not p.is_file(): continue
        rel = p.relative_to(disc.extracted_dir).as_posix()
        name = p.name.upper()
        if name in strings_core.DENY_LIST: continue
        if not (name.endswith('.BIN') or name.endswith('.INI')): continue
        if name == '1ST_READ.BIN' or 'MESSAGE.INI' in name:
            candidates.append(rel)

    log(f'preset: scanning {len(candidates)} candidate file(s) for JP runs')
    for rel in candidates:
        result = scan_with_baseline(
            disc.extracted_dir, disc.patches_dir, rel,
            db, preset.dict_entries, progress=progress,
        )
        summary['files_scanned'] += 1
        for key in ('jp_runs', 'pre_filled', 'identical', 'dict_hints'):
            summary[key] += result[key]

    # === Step 2: bundled-translations fallback ===
    # If the diff found nothing (or very little) AND the bundle has translations,
    # seed those. Users without the .dcp applied see the campaign translations anyway.
    if preset.translations and summary['pre_filled'] < len(preset.translations) // 2:
        log(f'  diff found {summary["pre_filled"]:,} translations; '
            f'seeding {len(preset.translations):,} more from bundled translations.json')
        import sqlite3, time
        now = int(time.time())
        for entry in preset.translations:
            try:
                db._conn.execute(
                    """INSERT INTO strings
                       (source_file, byte_offset, byte_budget, jp_text, en_text,
                        status, notes, updated_at)
                       VALUES (?,?,?,?,?,'done','from bundled translations.json',?)""",
                    (entry['source_file'], entry['byte_offset'], entry['byte_budget'],
                     entry['jp'], entry['en'], now)
                )
                summary['from_bundle'] += 1
            except sqlite3.IntegrityError:
                # Row already filled by diff scan — don't override
                pass
        db._conn.commit()

    log(f'preset apply complete: {summary["pre_filled"]:,} from diff + '
        f'{summary["from_bundle"]:,} from bundle = '
        f'{summary["pre_filled"] + summary["from_bundle"]:,} EN translations; '
        f'{summary["dict_hints"]:,} dictionary hints attached')
    return summary


# ---------- revert helpers ----------

def revert_entry(db: strings_core.StringDB, entry_id: int,
                  disc, progress=None) -> tuple[bool, str]:
    """Revert ONE row back to its JP baseline. Writes the baseline bytes at
    the offset in patches/, clears en_text in DB."""
    log = progress or (lambda _m: None)
    e = db.get(entry_id)
    if not e: return False, 'entry not found'
    base_path = disc.extracted_dir / e.source_file
    pat_path = disc.patches_dir / e.source_file
    if not (base_path.is_file() and pat_path.is_file()):
        return False, 'baseline or patches file missing'
    base_bytes = base_path.read_bytes()[e.byte_offset:e.byte_offset + e.byte_budget]
    pat = bytearray(pat_path.read_bytes())
    pat[e.byte_offset:e.byte_offset + e.byte_budget] = base_bytes
    pat_path.write_bytes(bytes(pat))
    db.set_en(entry_id, '')
    db.set_status(entry_id, 'todo')
    log(f'  reverted {e.source_file}:0x{e.byte_offset:x} to JP baseline')
    return True, 'reverted'


def revert_file(disc, source_rel: str, progress=None) -> tuple[bool, str]:
    """Revert one whole patches/ file back to its baseline copy."""
    import shutil
    log = progress or (lambda _m: None)
    base = disc.extracted_dir / source_rel
    pat = disc.patches_dir / source_rel
    if not base.is_file():
        return False, f'no baseline copy of {source_rel}'
    shutil.copy(base, pat)
    log(f'  reverted file {source_rel} to baseline ({base.stat().st_size:,} bytes)')
    return True, 'reverted'
