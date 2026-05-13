"""Translatable strings — scan, edit, commit.

Sits on top of `encoding.py` and adds the Workbench's project-level
abstractions:

  • TranslationEntry — one row in the Text & Pointer Grid.
  • StringDB        — SQLite store keyed by (source_file, byte_offset).
  • commit_translation() — applies an EN translation, writes patched bytes,
    backs up the original, and updates the row state.

Scope: 1ST_READ.BIN + MESSAGE.INI + any other small *.BIN/*.INI files the
campaign has confirmed safe for byte-level edits. We DO NOT bulk-edit
GAME.BIN, MEMDEF.BIN, GGAM.BIN, or 2_DP.BIN — those contain naturally-
occurring CJK byte sequences as data, and the skill explicitly flags
2_DP.BIN as containing the IME word dictionary which must never be touched.
"""
from __future__ import annotations
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import encoding


# Files we explicitly REFUSE to bulk-scan. The user can still load any file
# manually, but the auto-pipeline avoids these because the campaign's hard
# lessons say they're trap zones.
DENY_LIST = {
    '2_DP.BIN',          # contains the JP IME word dictionary
    'GAME.BIN',          # 90 MB asset blob — too many false positives
    'GGAM.BIN',          # ditto
    'MEMDEF.BIN',        # save format definitions
}


SCHEMA = """
CREATE TABLE IF NOT EXISTS strings (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  source_file  TEXT NOT NULL,         -- relative to patches/ root
  byte_offset  INTEGER NOT NULL,
  byte_budget  INTEGER NOT NULL,      -- cp932 byte length of JP, == max EN bytes
  jp_text      TEXT NOT NULL,
  en_text      TEXT DEFAULT '',
  pointer_addr INTEGER DEFAULT NULL,  -- absolute RAM addr referencing this string (if known)
  status       TEXT DEFAULT 'todo',   -- 'todo' | 'done' | 'skip' | 'oversize' | 'bad_encoding'
  notes        TEXT DEFAULT '',
  updated_at   INTEGER,
  UNIQUE(source_file, byte_offset)
);
CREATE INDEX IF NOT EXISTS idx_strings_status ON strings(status);
CREATE INDEX IF NOT EXISTS idx_strings_file ON strings(source_file);
"""


@dataclass
class TranslationEntry:
    id: int
    source_file: str
    byte_offset: int
    byte_budget: int
    jp_text: str
    en_text: str = ''
    pointer_addr: Optional[int] = None
    status: str = 'todo'
    notes: str = ''

    @property
    def en_byte_len(self) -> int:
        return encoding.cp932_len(self.en_text) if self.en_text else 0

    @property
    def fits(self) -> bool:
        return self.en_byte_len <= self.byte_budget

    @property
    def byte_status(self) -> str:
        """One-glance status string for the spreadsheet view."""
        if not self.en_text:
            return f'  - / {self.byte_budget}'
        used = self.en_byte_len
        return f'{used:3d} / {self.byte_budget}'


class StringDB:
    """SQLite-backed string store. One row per JP string discovered in scan."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False so we can read from the Worker thread too.
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)

    def close(self):
        self._conn.close()

    # ---------- ingest ----------

    def scan_file(self, file_path: Path, source_rel: str) -> int:
        """Scan `file_path` for cp932 runs, upsert each as a 'todo' row.
        Returns count of new rows added."""
        data = file_path.read_bytes()
        runs = encoding.find_cp932_runs(data, min_chars=4)
        n_new = 0
        now = int(time.time())
        for offset, char_count, txt in runs:
            try:
                self._conn.execute(
                    """INSERT INTO strings
                       (source_file, byte_offset, byte_budget, jp_text, status, updated_at)
                       VALUES (?, ?, ?, ?, 'todo', ?)""",
                    (source_rel, offset, char_count * 2, txt, now)
                )
                n_new += 1
            except sqlite3.IntegrityError:
                # row already exists from a previous scan — skip
                pass
        self._conn.commit()
        return n_new

    # ---------- query ----------

    def all_entries(self, only_file: Optional[str] = None) -> list[TranslationEntry]:
        sql = "SELECT * FROM strings"
        args: tuple = ()
        if only_file:
            sql += " WHERE source_file=?"
            args = (only_file,)
        sql += " ORDER BY source_file, byte_offset"
        return [self._row_to_entry(r) for r in self._conn.execute(sql, args)]

    def get(self, entry_id: int) -> Optional[TranslationEntry]:
        r = self._conn.execute("SELECT * FROM strings WHERE id=?", (entry_id,)).fetchone()
        return self._row_to_entry(r) if r else None

    @staticmethod
    def _row_to_entry(r: sqlite3.Row) -> TranslationEntry:
        return TranslationEntry(
            id=r['id'], source_file=r['source_file'], byte_offset=r['byte_offset'],
            byte_budget=r['byte_budget'], jp_text=r['jp_text'], en_text=r['en_text'] or '',
            pointer_addr=r['pointer_addr'], status=r['status'] or 'todo',
            notes=r['notes'] or '',
        )

    def counts(self) -> dict:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) FROM strings GROUP BY status"
        ).fetchall()
        out = {'todo': 0, 'done': 0, 'skip': 0, 'oversize': 0, 'bad_encoding': 0}
        for s, n in rows:
            out[s or 'todo'] = n
        out['total'] = sum(out.values())
        return out

    # ---------- update ----------

    def set_en(self, entry_id: int, en: str) -> tuple[bool, str]:
        """Set the English text; auto-update status based on byte budget."""
        e = self.get(entry_id)
        if not e:
            return False, 'not found'
        try:
            en_bytes = encoding.cp932_len(en)
        except UnicodeEncodeError as ex:
            self._conn.execute(
                "UPDATE strings SET en_text=?, status='bad_encoding', updated_at=? WHERE id=?",
                (en, int(time.time()), entry_id))
            self._conn.commit()
            return False, f"can't encode: {ex}"
        if en_bytes > e.byte_budget:
            self._conn.execute(
                "UPDATE strings SET en_text=?, status='oversize', updated_at=? WHERE id=?",
                (en, int(time.time()), entry_id))
            self._conn.commit()
            return False, f'too long: {en_bytes} > {e.byte_budget}'
        status = 'done' if en else 'todo'
        self._conn.execute(
            "UPDATE strings SET en_text=?, status=?, updated_at=? WHERE id=?",
            (en, status, int(time.time()), entry_id))
        self._conn.commit()
        return True, f'saved ({en_bytes} / {e.byte_budget} bytes)'

    def set_status(self, entry_id: int, status: str):
        self._conn.execute(
            "UPDATE strings SET status=?, updated_at=? WHERE id=?",
            (status, int(time.time()), entry_id))
        self._conn.commit()


# ---------- commit translations back to patches/ ----------

def commit_all_done(db: StringDB, patches_dir: Path,
                    progress=None) -> dict:
    """Apply every 'done' translation to its source_file under patches_dir.

    For each (file, offset, jp, en) we re-encode the EN bytes, null-pad to
    the original byte_budget, and write at the offset. Backups go to
    patches_dir.parent/backups/ via the caller (Workbench's disc module
    handles that).

    Returns: { 'files_modified': N, 'strings_applied': M, 'skipped': K }
    """
    log = progress or (lambda _m: None)
    files: dict[str, bytes] = {}
    applied = 0
    skipped = 0
    for entry in db.all_entries():
        if entry.status != 'done' or not entry.en_text:
            continue
        rel = entry.source_file
        path = patches_dir / rel
        if not path.is_file():
            skipped += 1; continue
        # Cache the file bytes
        if rel not in files:
            files[rel] = bytearray(path.read_bytes())
        try:
            padded = encoding.pad_with_nulls(entry.en_text, entry.byte_budget)
        except ValueError as e:
            log(f'  SKIP {rel}:0x{entry.byte_offset:x}  {e}')
            skipped += 1
            continue
        # Sanity: confirm the JP bytes match what's at that offset (campaign
        # rule: read the bytes BEFORE patching to avoid clobbering wrong data)
        existing = bytes(files[rel][entry.byte_offset:entry.byte_offset + entry.byte_budget])
        try:
            jp_b = entry.jp_text.encode('cp932', errors='strict')
        except UnicodeEncodeError:
            log(f'  SKIP {rel}:0x{entry.byte_offset:x}  JP not cp932-encodable')
            skipped += 1; continue
        if not existing.startswith(jp_b):
            log(f'  SKIP {rel}:0x{entry.byte_offset:x}  expected JP not at offset')
            skipped += 1; continue
        # Write
        files[rel][entry.byte_offset:entry.byte_offset + entry.byte_budget] = padded
        applied += 1

    # Flush
    n_files = 0
    for rel, data in files.items():
        path = patches_dir / rel
        if path.read_bytes() == bytes(data):
            continue
        path.write_bytes(bytes(data))
        n_files += 1
        log(f'wrote patches/{rel}  ({len(data):,} bytes — unchanged size)')

    return {'files_modified': n_files, 'strings_applied': applied, 'skipped': skipped}
