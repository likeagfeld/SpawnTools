"""Archive member access for Tab 2.

The texture workbench used to walk patches/ for loose .TEX/.PVR files only.
That left 6 games half-supported in the GUI because their textures live
inside archives:

  AFS  (Project Justice, JoJo)         – Sega archive, header table of off+size
  PAC  (Power Stone 2, SF Zero 3 MS)   – Capcom archive
  PVS  (JoJo)                          – Capcom archive
  PZZ  (SF III 3rd Strike)             – 128-byte header, 16 LZSS-compressed PVRs
  SLW  (Net de Tennis)                 – single Naomi-LZSS stream → concat raw VRAM
  PVZ  (Tech Romancer)                 – single Naomi-LZSS stream → PVR

This module exposes a single, member-aware API so the GUI can present each
archive as an expandable node whose children are the embedded textures —
each editable end-to-end (decode → export PNG → edit → import PNG → re-pack
back into the archive at the SAME byte size).

Member identity uses a virtual path syntax `<archive_path>#<member_id>` —
no temp dirs, nothing extracted to disk. Lets us reuse the existing
TextureRecord pipeline.
"""
from __future__ import annotations
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional



@dataclass
class ArchiveMember:
    archive_path: Path     # absolute path to the .afs/.pac/.pzz/.slw/.pvz/.pvs
    archive_kind: str      # 'AFS' | 'PAC' | 'PVS' | 'PZZ' | 'SLW' | 'PVZ'
    member_id: int         # index within the archive (0-based)
    label: str             # display label
    raw_offset: int        # byte offset where this member's blob lives in the archive
    raw_size: int          # raw blob size in archive (compressed size for LZSS members)
    pvr_bytes: bytes       # decoded PVR bytes (decompressed if LZSS, raw if direct)
    is_compressed: bool    # True for PZZ entries, SLW slots, PVZ whole-file


ARCHIVE_EXTS = {'.afs', '.pac', '.pvs', '.pzz', '.slw', '.pvz'}
# Loose BIN files that may carry embedded PVRT/GBIX texture chunks. We don't
# treat EVERY .BIN as a texture container (they're more often code/data) — we
# scan only those whose payload contains the magic. The walker calls
# `list_members` which runs the signature scan and reports zero hits cheaply
# for the non-texture cases.


def is_archive(path: Path) -> bool:
    if path.suffix.lower() in ARCHIVE_EXTS:
        return True
    try:
        with open(path, 'rb') as f:
            head = f.read(16)
    except OSError:
        return False
    if head[:4] == b'AFS\x00':
        return True
    # .BIN with embedded PVRT/GBIX — opt-in via cheap header peek then deep scan.
    # We only return True here if the bytes actually contain a PVR signature.
    if path.suffix.lower() == '.bin':
        try:
            data = path.read_bytes()
        except OSError:
            return False
        return (b'PVRT' in data) or (b'GBIX' in data)
    return False


def _import_codecs():
    """Lazy-import vendored codecs. Adds spawntools/codecs/ to sys.path."""
    codecs_dir = Path(__file__).resolve().parent.parent / 'codecs'
    if str(codecs_dir) not in sys.path:
        sys.path.insert(0, str(codecs_dir))
    import archive_unpackers  # noqa
    import naomi_lzss  # noqa
    return archive_unpackers, naomi_lzss


def list_members(path: Path) -> tuple[str, list[ArchiveMember]]:
    """Inspect an archive and return its kind + the list of members WITHOUT
    writing anything to disk.

    Returns ('', []) for unsupported / unrecognised files.
    """
    if not path.is_file():
        return '', []
    data = path.read_bytes()
    ext = path.suffix.lower()

    # AFS — 'AFS\0' + count + (off:u32, size:u32) × count
    if data[:4] == b'AFS\x00':
        n = struct.unpack('<I', data[4:8])[0]
        if 0 < n < 10000:
            members = []
            for i in range(n):
                off, sz = struct.unpack('<II', data[8 + i*8 : 16 + i*8])
                if sz == 0 or off + sz > len(data):
                    continue
                blob = data[off:off + sz]
                members.append(ArchiveMember(
                    archive_path=path, archive_kind='AFS', member_id=i,
                    label=f'entry_{i:03d}',
                    raw_offset=off, raw_size=sz, pvr_bytes=blob, is_compressed=False,
                ))
            return 'AFS', members

    # PZZ — variable-size header of 16 (off, sz) u32 LE pairs, plus optional
    # leading metadata. Headers observed in the wild:
    #   SF III 3rd Strike:  first_off in {0x8, 0x10, 0x28, 0x30, 0x40, 0x80, 0x150}
    #   Tech Romancer:      first_off in {0x18, 0x20, 0x30, 0x150}
    # The strict "must be >=128" rule misses every short-header PZZ. Relax: as
    # long as we have 16 (off, sz) pairs (128 bytes) AND the first nonzero
    # entry decompresses cleanly via NaomiLZSS, accept it.
    if ext == '.pzz' or _looks_like_pzz_loose(data):
        _, naomi = _import_codecs()
        if len(data) >= 128:
            header = struct.unpack('<32I', data[:128])
            members = []
            for i in range(16):
                off, sz = header[i*2], header[i*2 + 1]
                if sz == 0 or off == 0 or off + sz > len(data):
                    continue
                comp = data[off:off + sz]
                try:
                    decomp = bytes(naomi.decompress(comp))
                except Exception:
                    continue
                if len(decomp) < 16:
                    continue
                # Sanity: real PZZ entries decompress to PVRs (PVRT or GBIX).
                # If neither magic appears in the first 16 bytes, this isn't
                # a real PZZ entry — bail rather than emit a fake member.
                if (b'PVRT' not in decomp[:64]) and (b'GBIX' not in decomp[:16]):
                    continue
                members.append(ArchiveMember(
                    archive_path=path, archive_kind='PZZ', member_id=i,
                    label=f'entry_{i:02d}',
                    raw_offset=off, raw_size=sz, pvr_bytes=decomp, is_compressed=True,
                ))
            if members:
                return 'PZZ', members

    # PVZ — single LZSS stream from byte 0 → PVR (Tech Romancer)
    if ext == '.pvz':
        _, naomi = _import_codecs()
        try:
            decomp = bytes(naomi.decompress(data))
        except Exception:
            decomp = b''
        if decomp[:4] in (b'PVRT', b'GBIX'):
            return 'PVZ', [ArchiveMember(
                archive_path=path, archive_kind='PVZ', member_id=0,
                label='pvr', raw_offset=0, raw_size=len(data),
                pvr_bytes=decomp, is_compressed=True,
            )]

    # PAC / PVS — Capcom archive with embedded PVRs. Try the bundled
    # unpack_pac_or_pvs first (it knows the Capcom header layout), then
    # fall back to a pure PVRT/GBIX signature scan.
    if ext in ('.pac', '.pvs'):
        members = _scan_pvr_signatures(data, path, archive_kind=ext.upper().lstrip('.'))
        if members:
            return ext.upper().lstrip('.'), members
        # Last resort: signature scan over the whole file (catches PACs whose
        # PVRT/GBIX entries don't sit at structurally-discoverable offsets)
        members = _scan_pvr_signatures(data, path, archive_kind=ext.upper().lstrip('.'))
        if members:
            return ext.upper().lstrip('.'), members

    # Loose .BIN files with embedded PVRT/GBIX (Taisen Net Gimmick has 277,
    # SFZ3 has 24, Tech Romancer has 22). Always try signature scan since the
    # filename gives no hint.
    if ext == '.bin' and (b'PVRT' in data or b'GBIX' in data):
        members = _scan_pvr_signatures(data, path, archive_kind='BIN')
        if members:
            return 'BIN', members

    # Final fallback for unknown extensions: pure PVRT/GBIX signature scan
    # (covers .PAC variants we didn't structurally recognise, plus stray
    # texture containers under weird extensions).
    if (b'PVRT' in data) or (b'GBIX' in data):
        members = _scan_pvr_signatures(data, path, archive_kind=ext.upper().lstrip('.') or 'CONTAINER')
        if members:
            return members[0].archive_kind, members

    # SLW — single LZSS stream → concat raw VRAM. Members are slots; without
    # the game-side dimension table we can only show the whole blob. Surface
    # it as a single member; the user can still export the raw bytes.
    if ext == '.slw':
        _, naomi = _import_codecs()
        try:
            decomp = bytes(naomi.decompress(data))
        except Exception:
            decomp = b''
        if decomp:
            return 'SLW', [ArchiveMember(
                archive_path=path, archive_kind='SLW', member_id=0,
                label='raw_blob',
                raw_offset=0, raw_size=len(data),
                pvr_bytes=decomp, is_compressed=True,
            )]

    return '', []


def _looks_like_pzz_loose(data: bytes) -> bool:
    """Looser PZZ test: 16 (off,sz) pairs, monotonic non-decreasing offsets,
    each entry within file bounds. Doesn't require header[0] == 0x80."""
    if len(data) < 128:
        return False
    try:
        header = struct.unpack('<32I', data[:128])
    except struct.error:
        return False
    last_end = 0
    saw = 0
    for i in range(16):
        off, sz = header[i*2], header[i*2 + 1]
        if sz == 0:
            continue
        if off < last_end or off + sz > len(data) or off >= len(data):
            return False
        last_end = off + sz
        saw += 1
    return saw > 0


def _scan_pvr_signatures(data: bytes, path: Path, archive_kind: str) -> list[ArchiveMember]:
    """Find every PVRT / GBIX header in a PAC/PVS body and emit a member per hit."""
    members: list[ArchiveMember] = []
    i = 0
    L = len(data)
    idx = 0
    while i < L - 16:
        magic = data[i:i + 4]
        if magic == b'GBIX':
            # GBIX(8 hdr + payload) + PVRT(8 hdr + body)
            try:
                pvrt_off = i + 8 + struct.unpack('<I', data[i + 4:i + 8])[0]
                if data[pvrt_off:pvrt_off + 4] != b'PVRT':
                    i += 4
                    continue
                body_size = struct.unpack('<I', data[pvrt_off + 4:pvrt_off + 8])[0]
                total = (pvrt_off + 8 + body_size) - i
                blob = data[i:i + total]
                members.append(ArchiveMember(
                    archive_path=path, archive_kind=archive_kind, member_id=idx,
                    label=f'pvr_{idx:02d}',
                    raw_offset=i, raw_size=total, pvr_bytes=blob, is_compressed=False,
                ))
                idx += 1
                i += total
                continue
            except Exception:
                pass
        if magic == b'PVRT':
            try:
                body_size = struct.unpack('<I', data[i + 4:i + 8])[0]
                total = 8 + body_size
                if i + total > L:
                    i += 4
                    continue
                blob = data[i:i + total]
                members.append(ArchiveMember(
                    archive_path=path, archive_kind=archive_kind, member_id=idx,
                    label=f'pvr_{idx:02d}',
                    raw_offset=i, raw_size=total, pvr_bytes=blob, is_compressed=False,
                ))
                idx += 1
                i += total
                continue
            except Exception:
                pass
        i += 1
    return members


def replace_member(member: ArchiveMember, new_pvr_bytes: bytes) -> dict:
    """Write `new_pvr_bytes` back into `member.archive_path` at the same slot.

    Hard rule: the archive byte size MUST stay identical. If the new content
    doesn't fit, we refuse.

    For LZSS-compressed slots (PZZ, PVZ, SLW), the new PVR bytes are
    NaomiLZSS-compressed first and the compressed size must fit in
    `member.raw_size`.
    """
    arch = member.archive_path
    data = bytearray(arch.read_bytes())
    orig_arch_size = len(data)

    if member.archive_kind in ('PZZ', 'PVZ', 'SLW'):
        _, naomi = _import_codecs()
        compressed = bytes(naomi.compress(new_pvr_bytes))
        if len(compressed) > member.raw_size:
            return {
                'ok': False,
                'reason': (
                    f'Re-compressed size {len(compressed):,} bytes exceeds the slot '
                    f'budget of {member.raw_size:,} bytes. Naomi-LZSS encoder is ~9% '
                    f"larger than Capcom's so this can happen even on a same-size PVR. "
                    f'Shrink the PVR (e.g. lower resolution or simpler imagery) and retry.'
                ),
                'new_size': len(compressed),
                'budget': member.raw_size,
            }
        slot = data[member.raw_offset:member.raw_offset + member.raw_size]
        slot[:] = compressed + b'\x00' * (member.raw_size - len(compressed))
        data[member.raw_offset:member.raw_offset + member.raw_size] = slot
    else:
        # Direct (uncompressed) member — AFS / PAC / PVS slot
        if len(new_pvr_bytes) > member.raw_size:
            return {
                'ok': False,
                'reason': (
                    f'New PVR size {len(new_pvr_bytes):,} bytes exceeds the slot '
                    f'budget of {member.raw_size:,} bytes.'
                ),
                'new_size': len(new_pvr_bytes),
                'budget': member.raw_size,
            }
        slot = data[member.raw_offset:member.raw_offset + member.raw_size]
        slot[:] = new_pvr_bytes + b'\x00' * (member.raw_size - len(new_pvr_bytes))
        data[member.raw_offset:member.raw_offset + member.raw_size] = slot

    if len(data) != orig_arch_size:
        return {'ok': False, 'reason': f'internal error: archive size changed ({orig_arch_size}→{len(data)})'}

    arch.write_bytes(bytes(data))
    return {'ok': True, 'new_size': len(new_pvr_bytes), 'archive_size': orig_arch_size}
