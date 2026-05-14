"""EXHAUSTIVE JP content audit across every file in RC2 Translated/.

Per game, walks every single file (no extension filter), classifies it
by content signature, counts real cp932 JP runs (including the full-
width Latin trick from HANDOFF.md §3.8), and reports per-extension
totals plus per-file rankings.

Where applicable, attempts NaomiLZSS decompression and re-scans the
decompressed body. Excludes DTPK audio containers, ADX, ADP streams,
SFD video.

Output JSON: D:/DC_CapcomTranslationTools/exhaustive_jp_audit.json
Output text: D:/DC_CapcomTranslationTools/exhaustive_jp_audit.txt
"""
from __future__ import annotations
import json
import re
import struct
import sys
import traceback
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'spawntools' / 'codecs'))
try:
    import naomi_lzss
except Exception:
    naomi_lzss = None

RC2 = Path(r"D:\Capcom Dreamcast  Games - Joe Patched\RC2 Translated")
OUT_JSON = Path(r"D:\DC_CapcomTranslationTools\exhaustive_jp_audit.json")
OUT_TXT  = Path(r"D:\DC_CapcomTranslationTools\exhaustive_jp_audit.txt")

# cp932 runs ≥ 4 CJK chars (= 8 bytes)
CP932_RUN = re.compile(rb'(?:[\x81-\x9f\xe0-\xfc][\x40-\x7e\x80-\xfc]){4,}')
# Full-width Latin run (single high byte 0x82 + trail 0x4f..0x7a covers FF21-FF5A)
FULLWIDTH_RE = re.compile(rb'(?:\x82[\x4f-\x9a]){4,}')

MAX_FILE = 8 * 1024 * 1024    # skip > 8MB per file (big enough for stage textures)

# Audio/video extensions we never scan
SKIP_EXTS = {
    '.adx', '.adp', '.bgm', '.pcm', '.cdda', '.aif', '.wav', '.mp3',
    '.sfd', '.dvi', '.mlt',                # SFD/DVI = video; MLT often audio
    '.afs',                                 # huge audio archives
    '.gif', '.png', '.jpg', '.jpeg',
}

# Texture extensions
TEX_EXTS = {'.tex', '.pvr', '.pvz', '.pvs', '.pzz', '.slw'}


def is_dtpk(head: bytes) -> bool:
    return head[:4] == b'DTPK'


def is_riff(head: bytes) -> bool:
    return head[:4] == b'RIFF'


def looks_lzss(head: bytes, sz: int) -> bool:
    """Tiny heuristic: a NaomiLZSS stream starts with a u16 bitmask.
    Truly LZSS-compressed assets typically have few set bits in the
    first bitmask, but this isn't unique. We treat it as a SUGGESTION
    and only count strings from the decompressed body IF decompression
    yields >= 64 bytes AND the body contains a recognised magic
    (PVRT/GBIX/TXB0) OR cp932-runs."""
    if sz < 8 or naomi_lzss is None: return False
    return True   # always attempt for files that don't match other patterns


def scan_one(path: Path) -> dict:
    """Return classification + scan stats for a single file."""
    info = {
        'rel': '',
        'size': 0,
        'ext': path.suffix.lower(),
        'kind': 'data',
        'jp_runs': 0,            # cp932 4+ CJK runs in raw bytes
        'fullwidth_runs': 0,     # full-width Latin runs in raw bytes
        'pvrt_count': 0,         # 'PVRT' substring count
        'gbix_count': 0,         # 'GBIX' substring count
        'has_txb0': False,
        'jp_in_lzss': 0,         # cp932 runs found after NaomiLZSS decompress
        'lzss_pvrt': 0,
    }
    try:
        sz = path.stat().st_size
    except OSError:
        return info
    info['size'] = sz
    if sz > MAX_FILE: info['kind'] = 'too-large'; return info
    if info['ext'] in SKIP_EXTS: info['kind'] = 'audio/video'; return info
    try:
        data = path.read_bytes()
    except OSError:
        return info
    head = data[:32]
    if is_dtpk(head): info['kind'] = 'audio-dtpk'; return info
    if is_riff(head): info['kind'] = 'audio-riff'; return info

    # Texture / archive signature
    if head[:4] == b'TXB0': info['kind'] = 'tex-container'; info['has_txb0'] = True
    elif head[:4] == b'PVRT' or head[:4] == b'GBIX': info['kind'] = 'pvr'
    elif head[:4] == b'AFS\x00': info['kind'] = 'afs-archive'
    else:
        # Heuristic: text file vs. binary
        ascii_count = sum(1 for b in data[:512] if 0x20 <= b < 0x80 or b in (9, 10, 13))
        if sz > 0 and ascii_count > 350:  # mostly printable
            info['kind'] = 'text-or-ini'
        elif info['ext'] == '.bin':
            info['kind'] = 'bin'
        else:
            info['kind'] = info['ext'].lstrip('.') or 'unknown'

    # Count things — fast bytes ops
    info['jp_runs'] = sum(1 for _ in CP932_RUN.finditer(data))
    info['fullwidth_runs'] = sum(1 for _ in FULLWIDTH_RE.finditer(data))
    info['pvrt_count'] = data.count(b'PVRT')
    info['gbix_count'] = data.count(b'GBIX')

    # NaomiLZSS decompress: ONLY on .pvz / .pzz files (definitive LZSS
    # containers per the campaign). Skip .bin / .dat — they're rarely
    # LZSS and decompressing thousands of them blows memory.
    if (naomi_lzss is not None and sz < 256 * 1024 and sz > 4 and
            info['ext'] in ('.pvz', '.pzz')):
        try:
            decomp = bytes(naomi_lzss.decompress(data[:262144]))
            if 64 < len(decomp) < 4 * 1024 * 1024:
                info['jp_in_lzss'] = sum(1 for _ in CP932_RUN.finditer(decomp))
                info['lzss_pvrt'] = decomp.count(b'PVRT') + decomp.count(b'GBIX')
                if info['jp_in_lzss'] > 0 or info['lzss_pvrt'] > 0:
                    info['kind'] = info['kind'] + '+lzss'
        except Exception:
            pass

    return info


def audit_game(game_dir: Path) -> dict:
    ext_dir = game_dir / 'extracted'
    pat_dir = game_dir / 'patches'
    if not ext_dir.is_dir(): return {'error': 'no extracted/'}
    print(f'  scanning {game_dir.name[:50]}...', flush=True)

    files = sorted(ext_dir.rglob('*'))
    rows = []
    by_ext_jp = Counter()
    by_ext_files = Counter()
    by_ext_tex = Counter()
    skipped = Counter()
    for i, p in enumerate(files):
        if not p.is_file(): continue
        try:
            info = scan_one(p)
        except Exception as e:
            info = {'rel': '', 'size': 0, 'ext': p.suffix.lower(),
                    'kind': f'EXC: {e}', 'jp_runs': 0, 'fullwidth_runs': 0,
                    'pvrt_count': 0, 'gbix_count': 0, 'has_txb0': False,
                    'jp_in_lzss': 0, 'lzss_pvrt': 0}
        rel = p.relative_to(ext_dir).as_posix()
        info['rel'] = rel
        if i % 200 == 0:
            print(f'    .. {i}/{len(files)}', flush=True)
        by_ext_files[info['ext'] or '<noext>'] += 1
        if info['kind'] in ('audio/video', 'audio-dtpk', 'audio-riff', 'too-large'):
            skipped[info['kind']] += 1
            continue
        if info['jp_runs'] > 0 or info['jp_in_lzss'] > 0:
            by_ext_jp[info['ext'] or '<noext>'] += info['jp_runs'] + info['jp_in_lzss']
        if info['pvrt_count'] > 0 or info['has_txb0'] or info['lzss_pvrt'] > 0:
            by_ext_tex[info['ext'] or '<noext>'] += 1
        if (info['jp_runs'] > 0 or info['jp_in_lzss'] > 0 or
                info['pvrt_count'] > 0 or info['has_txb0']):
            rows.append(info)

    # Sort jp-bearing
    rows.sort(key=lambda r: -(r['jp_runs'] + r['jp_in_lzss']))

    # Which of these are MODIFIED in patches/?
    modified_set = set()
    if pat_dir.is_dir():
        for p in pat_dir.rglob('*'):
            if not p.is_file(): continue
            rel = p.relative_to(pat_dir).as_posix()
            base = ext_dir / rel
            if not base.exists(): continue
            try:
                if p.stat().st_size == base.stat().st_size and p.read_bytes() == base.read_bytes():
                    continue
            except OSError:
                continue
            modified_set.add(rel)

    for r in rows:
        r['campaign_modified'] = r['rel'] in modified_set

    return {
        'game': game_dir.name,
        'total_files': sum(by_ext_files.values()),
        'skipped': dict(skipped),
        'by_ext_files': dict(by_ext_files.most_common()),
        'by_ext_jp_runs': dict(by_ext_jp.most_common()),
        'by_ext_tex_files': dict(by_ext_tex.most_common()),
        'jp_bearing': rows[:50],   # top 50 files
        'modified_with_jp': [r for r in rows if r['campaign_modified']][:50],
    }


def main():
    games = sorted([d for d in RC2.iterdir() if d.is_dir() and not d.name.startswith('_')])
    print(f'Scanning {len(games)} games\n', flush=True)
    full = {}
    for g in games:
        try:
            full[g.name] = audit_game(g)
        except Exception as e:
            full[g.name] = {'error': str(e), 'tb': traceback.format_exc()[:500]}
            print(f'  ERROR: {e}', flush=True)
    OUT_JSON.write_text(json.dumps(full, indent=2, ensure_ascii=False), encoding='utf-8')
    # Compact text summary
    with OUT_TXT.open('w', encoding='utf-8') as f:
        for name, info in full.items():
            f.write(f'\n=== {name} ===\n')
            if 'error' in info:
                f.write(f'  ERROR: {info["error"]}\n'); continue
            f.write(f'  files: {info["total_files"]}   skipped: {info.get("skipped",{})}\n')
            f.write(f'  by-ext jp-runs (top 8): {list(info["by_ext_jp_runs"].items())[:8]}\n')
            f.write(f'  by-ext tex-files (top 8): {list(info["by_ext_tex_files"].items())[:8]}\n')
            f.write(f'  top 15 JP-bearing files (cp932 raw + LZSS):\n')
            for r in info['jp_bearing'][:15]:
                marker = ' MODIFIED' if r.get('campaign_modified') else ''
                f.write(f'    [{r["kind"]:14s}] jp={r["jp_runs"]:>5} fw={r["fullwidth_runs"]:>3} '
                        f'lzss_jp={r["jp_in_lzss"]:>4} pvrt={r["pvrt_count"]:>3}  '
                        f'{r["size"]:>10,}  {r["rel"]}{marker}\n')
    print(f'\nwrote {OUT_JSON}\nwrote {OUT_TXT}', flush=True)


if __name__ == '__main__':
    main()
