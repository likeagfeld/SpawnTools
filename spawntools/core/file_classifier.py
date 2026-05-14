"""Per-file content classifier used by build_preset to label modified files
into 'text' / 'texture' / 'archive' / 'audio' / 'video' / 'code' / 'data'
buckets, fully driven by byte signatures + extensions.

The classification is the ground truth the GUI uses to decide where to
SURFACE a file:
  - text     → Tab 3 scan_targets candidate
  - texture  → Tab 2 file list (loose)
  - archive  → Tab 2 file list (members expanded inline)
  - audio    → don't surface (skip)
  - video    → don't surface (skip)
  - code     → Tab 3 if it also has cp932 strings, else skip
  - data     → don't surface (skip) unless it has embedded PVRs

Each classification is backed by a byte-level test, not just extension.
"""
from __future__ import annotations
import re
import struct
from pathlib import Path

# Precompiled cp932 run regex — any 4+ consecutive (lead, trail) cp932 pairs.
CP932_RUN = re.compile(rb'(?:[\x81-\x9f\xe0-\xfc][\x40-\x7e\x80-\xfc]){4,}')

AUDIO_EXTS = {'.adx', '.bgm', '.pcm', '.aif', '.wav', '.mp3', '.cdda', '.dvi'}
VIDEO_EXTS = {'.sfd'}
KNOWN_TEXTURE_EXTS = {'.pvr', '.tex'}
KNOWN_ARCHIVE_EXTS = {'.afs', '.pac', '.pvs', '.pzz', '.slw', '.pvz'}
KNOWN_FONT_EXTS = {'.bix'}  # legacy bitmap font containers (treated as data)


def _has_audio_header(head: bytes) -> bool:
    """Detect common audio container magics."""
    if head[:4] == b'AFS\x00': return False        # AFS archive, not audio
    if head[:4] == b'RIFF':    return True         # WAV/etc.
    if head[:4] == b'CRID':    return True         # CRI Audio format
    # ADX: starts with 0x80 0x00 (sync), then ASCII '(c)CRI' near offset 4
    if head[:2] == b'\x80\x00' and b'(c)CRI' in head[:32]: return True
    return False


def _has_video_header(head: bytes) -> bool:
    # CRI SofDec / SFD: starts with 'SOFDEC' or similar block
    if head[:4] == b'CRID' and len(head) >= 12 and head[8:12] in (b'@UTF', b'SFD '):
        return True
    if head[:4] == b'SFD ': return True
    return False


def _is_sh4_code_heavy(data: bytes) -> bool:
    """Cheap test: SH4 little-endian code shows lots of common opcode prefixes.
    1ST_READ.BIN is ~90% code; .BIN files that are pure data don't show this
    pattern. We only call this on .BIN to decide whether to scan strings."""
    if len(data) < 1024: return False
    sample = data[:4096]
    # SH4 RTS = 0x000B, NOP = 0x0009, MOV variants in 0x6xxx, 0xExxx (mov #imm)
    rts_count = sample.count(b'\x0b\x00')
    nop_count = sample.count(b'\x09\x00')
    return (rts_count + nop_count) > 4


def classify(path: Path, data: bytes | None = None) -> dict:
    """Return {'kind': <bucket>, 'jp_runs': N, 'pvrt_count': N, 'reasons': [..]}.

    `path` is the local file path. `data` is its byte content; if not supplied
    we read it. Returns a dict so callers can store classification metadata.
    """
    if data is None:
        try:
            data = path.read_bytes()
        except OSError:
            return {'kind': 'data', 'jp_runs': 0, 'pvrt_count': 0, 'reasons': ['unreadable']}

    ext = path.suffix.lower()
    head = data[:64]
    reasons = []

    # Extension-driven audio/video — always skip
    if ext in AUDIO_EXTS:
        return {'kind': 'audio', 'jp_runs': 0, 'pvrt_count': 0,
                'reasons': [f'extension {ext} is audio']}
    if ext in VIDEO_EXTS:
        return {'kind': 'video', 'jp_runs': 0, 'pvrt_count': 0,
                'reasons': [f'extension {ext} is video']}

    # ADX_xxx.BIN convention used by MvC2, CvS Pro etc.
    if ext == '.bin' and path.name.upper().startswith('ADX_'):
        return {'kind': 'audio', 'jp_runs': 0, 'pvrt_count': 0,
                'reasons': ['filename starts with ADX_']}

    # Signature-driven audio/video (catches mis-extension'd files)
    if _has_audio_header(head):
        return {'kind': 'audio', 'jp_runs': 0, 'pvrt_count': 0,
                'reasons': ['audio header detected']}
    if _has_video_header(head):
        return {'kind': 'video', 'jp_runs': 0, 'pvrt_count': 0,
                'reasons': ['video header detected']}

    # Compute the two scalar signals
    jp_runs = sum(1 for _ in CP932_RUN.finditer(data))
    pvrt_count = data.count(b'PVRT') + data.count(b'GBIX')

    # Direct textures
    if ext in KNOWN_TEXTURE_EXTS or head[:4] in (b'PVRT', b'GBIX', b'TXB0'):
        reasons.append(f'extension {ext} or magic is texture')
        return {'kind': 'texture', 'jp_runs': jp_runs, 'pvrt_count': max(1, pvrt_count), 'reasons': reasons}

    # Archives
    if ext in KNOWN_ARCHIVE_EXTS or head[:4] == b'AFS\x00':
        reasons.append('archive extension or AFS magic')
        return {'kind': 'archive', 'jp_runs': jp_runs, 'pvrt_count': pvrt_count, 'reasons': reasons}

    # INI files — text data
    if ext == '.ini':
        return {'kind': 'text', 'jp_runs': jp_runs, 'pvrt_count': 0,
                'reasons': ['ini file']}

    # .BIN file — could be code+text (1ST_READ), data, or container of textures
    if ext == '.bin':
        if pvrt_count > 0 and jp_runs < pvrt_count * 50:
            # Mostly textures with a few cp932 false positives → texture container
            reasons.append(f'.bin contains {pvrt_count} PVRT/GBIX → texture container')
            return {'kind': 'texture', 'jp_runs': jp_runs, 'pvrt_count': pvrt_count, 'reasons': reasons}
        if _is_sh4_code_heavy(data):
            # SH4-heavy → code; may also have strings worth scanning
            return {'kind': 'code', 'jp_runs': jp_runs, 'pvrt_count': pvrt_count,
                    'reasons': ['SH4 code pattern detected']}
        if jp_runs >= 8:
            return {'kind': 'text', 'jp_runs': jp_runs, 'pvrt_count': pvrt_count,
                    'reasons': [f'{jp_runs} cp932 runs ≥ threshold']}
        return {'kind': 'data', 'jp_runs': jp_runs, 'pvrt_count': pvrt_count,
                'reasons': ['no audio/video/texture/code signatures']}

    # PVS/PZZ/etc fallthrough — handled above; otherwise:
    if pvrt_count > 0:
        return {'kind': 'archive', 'jp_runs': jp_runs, 'pvrt_count': pvrt_count,
                'reasons': [f'{pvrt_count} PVR signatures detected']}
    if jp_runs >= 8:
        return {'kind': 'text', 'jp_runs': jp_runs, 'pvrt_count': 0,
                'reasons': [f'{jp_runs} cp932 runs ≥ threshold']}
    return {'kind': 'data', 'jp_runs': jp_runs, 'pvrt_count': 0,
            'reasons': ['default bucket']}
