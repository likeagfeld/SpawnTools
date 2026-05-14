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
import json
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


_RAW_PROFILES_CACHE: dict | None = None


def _load_raw_profiles() -> dict:
    """Lazy-load bundled/raw_format_profiles.json — per-game (pixfmt, datafmt)
    defaults baked in from Ghidra+FIDB attribution + manual verification.

    Returns {slug: {'pixfmt': int, 'datafmt': int}}. Slugs not present fall
    back to RGB565 SQUARE_TWIDDLED.
    """
    global _RAW_PROFILES_CACHE
    if _RAW_PROFILES_CACHE is not None:
        return _RAW_PROFILES_CACHE
    path = Path(__file__).resolve().parent.parent / 'bundled' / 'raw_format_profiles.json'
    out: dict = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            raw = {}
        for slug, info in raw.items():
            if not isinstance(info, dict): continue
            try:
                pf = int(info['pixfmt'], 16) if isinstance(info['pixfmt'], str) else int(info['pixfmt'])
                df = int(info['datafmt'], 16) if isinstance(info['datafmt'], str) else int(info['datafmt'])
                out[slug] = {'pixfmt': pf, 'datafmt': df}
            except Exception:
                continue
    _RAW_PROFILES_CACHE = out
    return out


def _profile_for(slug: str | None) -> tuple[int, int]:
    """Return (pixfmt, datafmt) for slug, or (RGB565, SQUARE_TWIDDLED) default."""
    if not slug: return (0x01, 0x01)
    prof = _load_raw_profiles().get(slug)
    return (prof['pixfmt'], prof['datafmt']) if prof else (0x01, 0x01)



@dataclass
class ArchiveMember:
    archive_path: Path     # absolute path to the .afs/.pac/.pzz/.slw/.pvz/.pvs
    archive_kind: str      # 'AFS' | 'PAC' | 'PVS' | 'PZZ' | 'SLW' | 'PVZ' | 'RAW' | 'BIN'
    member_id: int         # index within the archive (0-based)
    label: str             # display label
    raw_offset: int        # byte offset where this member's blob lives in the archive
    raw_size: int          # raw blob size in archive (compressed size for LZSS members)
    pvr_bytes: bytes       # decoded PVR bytes (or raw pixel bytes for RAW members)
    is_compressed: bool    # True for PZZ entries, SLW slots, PVZ whole-file
    # Optional decode hints for RAW members (no PVR header — dims/format must
    # be supplied externally). Left as 0 for normal PVR-bearing members.
    raw_width: int = 0
    raw_height: int = 0
    raw_pixfmt: int = 0
    raw_datafmt: int = 0


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


def _detect_slug_for_path(path: Path) -> str | None:
    """Walk up from path looking for a track03 to fingerprint via IP.BIN.
    Used by list_members to pick the right per-game raw-blob defaults."""
    for ancestor in [path] + list(path.parents)[:6]:
        for cand in (ancestor / 'disc' / 'track03.bin',
                     ancestor / 'disc' / 'track03.iso',
                     ancestor / 'track03.bin',
                     ancestor / 'track03.iso'):
            if not cand.is_file(): continue
            try:
                with open(cand, 'rb') as fh:
                    head = fh.read(0x200)
            except OSError:
                continue
            is_bin = cand.suffix.lower() == '.bin'
            data_off = 16 if is_bin else 0
            ip = head[data_off:data_off + 0x100]
            if b'SEGA' not in ip[:0x10]: continue
            code = ip[0x40:0x4A].decode('ascii', errors='replace').strip()
            # Match against bundled games.json
            idx_path = Path(__file__).resolve().parent.parent / 'bundled' / 'games.json'
            if not idx_path.is_file(): return None
            try:
                idx = json.loads(idx_path.read_text(encoding='utf-8'))
                for g in idx.get('games', []):
                    if g.get('product_code') == code:
                        return g['slug']
            except Exception:
                pass
            return None
    return None


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

    # Capcom proprietary raw-pixel containers (MvC2 STG*TEX.BIN, EFKYTEX.BIN,
    # PL*_DAT.BIN; Net de Tennis SLW; Power Stone 2 stage BINs). No PVR magic,
    # just concatenated raw twiddled pixel data. The pixfmt/datafmt defaults
    # come from the per-game profile baked at bundled/raw_format_profiles.json
    # (auto-attributed via Ghidra+FIDB + verified on representative chunks).
    if ext == '.bin':
        slug = _detect_slug_for_path(path)
        default_pf, default_df = _profile_for(slug)
        members = _surface_raw_blobs(data, path, default_pf, default_df)
        if members:
            return 'RAW', members

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


def _surface_raw_blobs(data: bytes, path: Path,
                       default_pf: int = 0x01, default_df: int = 0x01) -> list[ArchiveMember]:
    """Try the well-known Capcom raw-pixel container shapes:

      1. STG*TEX.BIN: file_size is N × (sq*sq*2) for some power-of-two sq —
         N concatenated square-twiddled textures (3× 512×512 RGB565 for MvC2).
      2. EFKYTEX.BIN-style: 8-byte zero header + one raw blob.
      3. PL*_DAT.BIN: top-level offset table (u32 LE) → entries with their own
         sub-blobs.

    For each detected blob, emit ONE ArchiveMember preset to the most likely
    decode (RGB565 SQUARE_TWIDDLED for square dims, RECTANGLE for non-square).
    The GUI exposes alternate hypotheses via Tab 2's hypothesis-cycle button.
    """
    from . import raw_blob
    sz = len(data)
    members: list[ArchiveMember] = []
    name_up = path.name.upper()

    # Pattern A: PL*_DAT-style header table.
    # u32 LE offsets, monotonic across non-zero runs. 0x00000000 acts as a
    # section separator inside the table — we collect non-zero values
    # MONOTONICALLY, then STOP at the first non-zero that's less than the
    # previous max (= we've crossed into the first entry's body bytes).
    if sz >= 256 and not data.startswith(b'\x00\x00\x00\x00'):
        try:
            table = struct.unpack('<32I', data[:128])
        except struct.error:
            table = ()
        # Walk the table, accumulating only monotonic-or-zero
        nonzero: list[int] = []
        last_max = 0
        for v in table:
            if v == 0: continue
            if v < last_max: break       # body bytes — stop reading the table
            nonzero.append(v)
            last_max = v
        # First entry must be small (an offset into the file, not a magic value)
        if (nonzero and nonzero[0] < 0x1000 and
                all(0 < v < sz for v in nonzero) and
                len(set(nonzero)) == len(nonzero)):
            boundaries = nonzero + [sz]
            for i, off in enumerate(nonzero):
                blob_len = boundaries[i + 1] - off
                if blob_len < 0x40: continue   # too small for anything useful
                # Pick best dim hypothesis IF body size fits power-of-two dims
                hyps = raw_blob.hypotheses_for_file(path, offset=off, length=blob_len)
                if hyps:
                    pick = next((h for h in hyps if h.pixfmt == 0x01 and h.datafmt == 0x01),
                                next((h for h in hyps if h.pixfmt == 0x01), hyps[0]))
                    label = f'entry_{i:02d}@0x{off:x}  {pick.width}x{pick.height} pf0x{pick.pixfmt:02x}'
                    members.append(ArchiveMember(
                        archive_path=path, archive_kind='RAW',
                        member_id=i, label=label,
                        raw_offset=off, raw_size=blob_len,
                        pvr_bytes=data[off:off + blob_len],
                        is_compressed=False,
                        raw_width=pick.width, raw_height=pick.height,
                        raw_pixfmt=pick.pixfmt, raw_datafmt=pick.datafmt,
                    ))
                else:
                    # Likely a sub-container (its own offset table inside).
                    # Surface anyway so the user can export the raw bytes.
                    members.append(ArchiveMember(
                        archive_path=path, archive_kind='RAW',
                        member_id=i,
                        label=f'entry_{i:02d}@0x{off:x}  {blob_len:,}B  sub-container',
                        raw_offset=off, raw_size=blob_len,
                        pvr_bytes=data[off:off + blob_len],
                        is_compressed=False,
                    ))
            if members:
                return members

    # Pattern B: STG*TEX-style — N evenly-sized blobs (square OR non-square),
    # optionally after a small header. Capcom uses 0x8000-sized atlas-list
    # headers in MvC2 STG*TEX.BIN; smaller offsets in other games.
    HDR_OFFSETS = (0, 0x8, 0x10, 0x40, 0x80, 0x100, 0x200, 0x400,
                   0x800, 0x1000, 0x2000, 0x4000, 0x8000)
    CHUNK_SIZES = (0x100000, 0x80000, 0x40000, 0x20000, 0x10000, 0x8000, 0x4000)
    DIM_PAIRS = [(d, d) for d in (1024, 512, 256, 128, 64)] + [
        (512, 256), (256, 512), (1024, 512), (512, 1024),
        (256, 128), (128, 256), (1024, 256), (256, 1024),
    ]
    for chunk in CHUNK_SIZES:
        for hdr in HDR_OFFSETS:
            rest = sz - hdr
            if rest <= 0 or rest % chunk: continue
            n = rest // chunk
            if n not in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 32): continue
            # Find a (w, h) where w*h*2 == chunk
            for (w, h) in DIM_PAIRS:
                if w * h * 2 != chunk: continue
                # Use per-game pixfmt; force RECTANGLE_TWIDDLED for non-square.
                df = default_df if w == h else 0x0d
                for i in range(n):
                    off = hdr + i * chunk
                    members.append(ArchiveMember(
                        archive_path=path, archive_kind='RAW',
                        member_id=i,
                        label=f'chunk_{i}@0x{off:x}  {w}x{h}',
                        raw_offset=off, raw_size=chunk,
                        pvr_bytes=data[off:off + chunk],
                        is_compressed=False,
                        raw_width=w, raw_height=h,
                        raw_pixfmt=default_pf, raw_datafmt=df,
                    ))
                return members
            if members: return members
        if members: return members

    # Pattern C: EFKYTEX-style — small zero header + one blob with rectangle dims.
    if sz > 0x1000 and data[:8] == b'\x00' * 8:
        body_len = sz - 8
        for w in (1024, 512, 256, 128):
            for h in (1024, 512, 256, 128, 64):
                if w * h * 2 == body_len:
                    df = default_df if w == h else 0x0d
                    members.append(ArchiveMember(
                        archive_path=path, archive_kind='RAW',
                        member_id=0,
                        label=f'blob@0x8  {w}x{h}',
                        raw_offset=8, raw_size=body_len,
                        pvr_bytes=data[8:],
                        is_compressed=False,
                        raw_width=w, raw_height=h,
                        raw_pixfmt=default_pf, raw_datafmt=df,
                    ))
                    return members

    return []


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
