"""Fast JP/PVR audit using regex-based scanning. Writes JSON per game so
downstream tooling can build evidence-based scan_targets per game.

Output:
  D:/DC_CapcomTranslationTools/audit_jp_per_game.json

Strategy:
  - For each file in extracted/, skip if extension is in BINARY_SKIP (audio, etc).
  - For files under 32 MB, count cp932 RUNS via a precompiled regex on the
    bytes. Way faster than the byte-by-byte Python loop.
  - Count PVRT occurrences via bytes.count().
  - Stream JSON incrementally to disk; flush per-game.
"""
from __future__ import annotations
import re, json, sys
from pathlib import Path
from collections import defaultdict

RC2 = Path(r"D:/Capcom Dreamcast  Games - Joe Patched/RC2 Translated")
OUT = Path(r"D:/DC_CapcomTranslationTools/audit_jp_per_game.json")

# Files we never need to scan
BINARY_SKIP = {'.adx', '.bgm', '.pcm', '.afs', '.gif', '.png', '.jpg', '.dat',
               '.dvi', '.aif', '.wav', '.mp3', '.mlt'}
MAX_FILE_SIZE = 32 * 1024 * 1024  # 32 MB

# cp932 run: (lead, trail) sequence with at least 4 chars (= 8 bytes)
# lead: 0x81-0x9F or 0xE0-0xFC
# trail: 0x40-0xFC except 0x7F
CP932_RUN = re.compile(
    rb'(?:[\x81-\x9f\xe0-\xfc][\x40-\x7e\x80-\xfc]){4,}'
)


def scan_one(data: bytes):
    """Return (jp_run_count, pvrt_count)."""
    jp = sum(1 for _ in CP932_RUN.finditer(data))
    pvrt = data.count(b'PVRT')
    return jp, pvrt


def main():
    games = sorted([d for d in RC2.iterdir() if d.is_dir() and not d.name.startswith('_')])
    result = {}
    for g in games:
        ext_dir = g / 'extracted'
        if not ext_dir.is_dir(): continue
        print(f'scanning {g.name}...', flush=True)
        files_by_ext = defaultdict(int)
        text_files = []   # (jp_runs, rel, size)
        tex_files = []    # (pvrt, rel, size)
        for p in ext_dir.rglob('*'):
            if not p.is_file(): continue
            ext = p.suffix.lower()
            try:
                sz = p.stat().st_size
            except OSError:
                continue
            files_by_ext[ext or '<noext>'] += 1
            if ext in BINARY_SKIP: continue
            if sz > MAX_FILE_SIZE: continue
            try:
                data = p.read_bytes()
            except OSError:
                continue
            jp, pvrt = scan_one(data)
            rel = p.relative_to(ext_dir).as_posix()
            if jp > 0:
                text_files.append([jp, rel, sz])
            if pvrt > 0:
                tex_files.append([pvrt, rel, sz])
        text_files.sort(reverse=True)
        tex_files.sort(reverse=True)
        result[g.name] = {
            'by_ext': dict(sorted(files_by_ext.items(), key=lambda x: -x[1])),
            'jp_top':   text_files[:50],
            'tex_top':  tex_files[:50],
            'totals': {
                'text_files_with_jp': len(text_files),
                'total_jp_runs':      sum(x[0] for x in text_files),
                'tex_files_with_pvrt': len(tex_files),
                'total_pvrts':        sum(x[0] for x in tex_files),
            },
        }
        # Flush after each game
        OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f'  text-bearing files: {len(text_files):>4}  '
              f'jp runs: {sum(x[0] for x in text_files):>6}  '
              f'tex-bearing files: {len(tex_files):>4}  '
              f'pvrts: {sum(x[0] for x in tex_files):>5}',
              flush=True)
    print(f'\\nwrote {OUT}')


if __name__ == '__main__':
    main()
