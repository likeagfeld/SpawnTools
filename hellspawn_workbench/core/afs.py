"""AFS archive support — Capcom-specific (Project Justice etc.).

AFS file layout (verified against Project Justice's `HUM_TC.AFS`):

  bytes 0-3:    'AFS\\x00' magic
  bytes 4-7:    u32 LE — number of entries
  then N x 8-byte TOC records:
    u32 offset (LE) — byte offset of file in archive (relative to archive start)
    u32 size   (LE) — byte size of file
  then optional padding to 2048-byte sector alignment
  then a metadata block at offset stored AT (offset_table_end + 0) — 32-byte
    entries with filenames

  Each file is stored at its TOC offset, padded to 2048-byte sector alignment.

SPAWN DOES NOT USE AFS. The Workbench's AFS module is here for users who
drop in Project Justice's extracted dir, OR for hypothetical Spawn
re-translation that might add new AFS archives. For Spawn specifically:
`detect_afs_files()` returns [] and the AFS tab is hidden.

Hard rule reminder: if we DO modify an AFS, EVERY entry must keep its
2048-byte sector alignment. If a replacement file changes size, all
following entries shift, the TOC must be rewritten, AND the parent track03
LBAs may need updating. We DON'T do that here — we only support REPLACING
a file with one of SAME OR SMALLER size (padded with nulls to original).
That's the no-grow rule.
"""
from __future__ import annotations
import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AfsEntry:
    index: int
    offset: int        # byte offset in archive
    size: int          # byte size
    name: str = ''


@dataclass
class AfsArchive:
    path: Path
    entries: list[AfsEntry]
    metadata_offset: int = 0


def detect_afs_files(root: Path) -> list[Path]:
    """Return every *.AFS file under `root`. Returns [] for Spawn (which
    doesn't have any), which lets the GUI hide the AFS tab."""
    return sorted(root.rglob('*.AFS')) + sorted(root.rglob('*.afs'))


def parse(path: Path) -> AfsArchive:
    """Parse an AFS archive's TOC. Does NOT load file contents."""
    with open(path, 'rb') as f:
        magic = f.read(4)
        if magic != b'AFS\x00':
            raise ValueError(f'{path.name}: not an AFS archive (magic={magic!r})')
        (count,) = struct.unpack('<I', f.read(4))
        entries: list[AfsEntry] = []
        for i in range(count):
            off, sz = struct.unpack('<II', f.read(8))
            entries.append(AfsEntry(index=i, offset=off, size=sz))

        # Metadata block: typically immediately after the TOC, padded to 2048.
        # The format is 32-byte entries: filename(zero-terminated)[?] + timestamps.
        toc_end = 8 + count * 8
        # Sector align to 0x800
        metadata_off = (toc_end + 0x7FF) & ~0x7FF
        try:
            f.seek(metadata_off)
            for ent in entries:
                rec = f.read(32)
                # Filename is the first null-terminated string in the record
                name = rec.split(b'\x00')[0].decode('cp932', errors='replace')
                if name:
                    ent.name = name
        except Exception:
            pass

    return AfsArchive(path=path, entries=entries, metadata_offset=metadata_off)


def extract_entry(arch: AfsArchive, entry: AfsEntry) -> bytes:
    """Read the raw bytes of one entry from the archive."""
    with open(arch.path, 'rb') as f:
        f.seek(entry.offset)
        return f.read(entry.size)


def replace_entry_in_place(arch: AfsArchive, entry: AfsEntry,
                            new_bytes: bytes) -> dict:
    """Replace one entry's bytes WITHOUT changing its TOC offset or size.

    Hard rule: `len(new_bytes) <= entry.size`. Pads with nulls if shorter.
    Refuses if larger.

    Returns: { 'old_size': N, 'new_size': M, 'padded': True/False }
    """
    if len(new_bytes) > entry.size:
        raise ValueError(
            f'{entry.name or entry.index}: replacement {len(new_bytes)} B > '
            f'original {entry.size} B. Refusing to grow (would shift TOC).'
        )
    padded = new_bytes + b'\x00' * (entry.size - len(new_bytes))
    with open(arch.path, 'r+b') as f:
        f.seek(entry.offset)
        f.write(padded)
    return {
        'old_size': entry.size,
        'new_size': len(new_bytes),
        'padded': len(new_bytes) < entry.size,
    }
