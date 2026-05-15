"""Apply Spawn's V0.2 .dcp patches to extract the modified-texture bytes,
then stage them inside bundled/spawn_preset/modified_files/ so the GUI's
Load Baseline can copy them into the user's patches/ dir.

Skips huge binaries (GAME.BIN, MEMDEF.BIN, 2_DP.BIN) — their content
modifications are too small to justify the size cost. The TEXT side of
those is already covered by translations.json + commit_all_done.

This script needs pyxdelta on the BUILD machine only. Users never need it.

Run:  python -m scripts.bundle_modified_files spawn
"""
from __future__ import annotations
import sys
import zipfile
import shutil
import tempfile
import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUNDLE = REPO / 'spawntools' / 'bundled'

# Per-game .dcp + extracted/ source. For Spawn we have V0.2 shipped.
GAME_DCPS = {
    'spawn': {
        'dcp': REPO / 'patches' / 'Spawn-T-En-Farkus-V0.2.dcp',
        'extracted': Path(r"D:/Capcom Dreamcast  Games - Joe Patched/RC2 Translated/Spawn - In the Demon's Hand (JP)/extracted"),
    },
}

# Files we DON'T bundle (too large or text-only covered by translations.json)
SKIP_NAMES = {'GAME.BIN', 'MEMDEF.BIN', '2_DP.BIN', '1ST_READ.BIN', 'DPETC/MESSAGE.INI'}


def bundle_for_slug(slug: str) -> dict:
    info = GAME_DCPS.get(slug)
    if not info:
        return {'error': f'no dcp registered for {slug}'}
    dcp = info['dcp']
    src_extracted = info['extracted']
    if not dcp.is_file():
        return {'error': f'.dcp missing: {dcp}'}
    if not src_extracted.is_dir():
        return {'error': f'extracted/ missing: {src_extracted}'}

    out_dir = BUNDLE / f'{slug}_preset' / 'modified_files'
    if out_dir.is_dir():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        import pyxdelta
    except ImportError:
        return {'error': 'pyxdelta not available on this machine'}

    work = Path(tempfile.mkdtemp(prefix=f'{slug}_bundle_'))
    bundled = []
    skipped = []
    total_bytes = 0
    try:
        with zipfile.ZipFile(dcp, 'r') as z:
            for entry in z.infolist():
                if not entry.filename.endswith('.xdelta'):
                    continue
                rel = entry.filename[:-len('.xdelta')]
                if rel in SKIP_NAMES or Path(rel).name in SKIP_NAMES:
                    skipped.append((rel, 'in SKIP_NAMES'))
                    continue
                # Stage the source file
                src_file = src_extracted / rel
                if not src_file.is_file():
                    skipped.append((rel, 'src extracted/ missing'))
                    continue
                src_staged = work / 'src.bin'
                src_staged.write_bytes(src_file.read_bytes())
                # Stage the xdelta
                xd_staged = work / 'p.xdelta'
                xd_staged.write_bytes(z.read(entry))
                # Apply
                out_staged = work / 'out.bin'
                pyxdelta.decode(str(src_staged), str(xd_staged), str(out_staged))
                new_bytes = out_staged.read_bytes()
                # Write into the bundle
                bundle_target = out_dir / rel
                bundle_target.parent.mkdir(parents=True, exist_ok=True)
                bundle_target.write_bytes(new_bytes)
                bundled.append((rel, len(new_bytes), hashlib.md5(new_bytes).hexdigest()))
                total_bytes += len(new_bytes)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    return {
        'slug': slug,
        'bundled': bundled,
        'skipped': skipped,
        'total_bytes': total_bytes,
        'out_dir': out_dir,
    }


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if only:
        result = bundle_for_slug(only)
        print(f'=== {only} ===')
        if 'error' in result:
            print(f'  ERROR: {result["error"]}')
            return 1
        print(f'  bundled: {len(result["bundled"])} files, '
              f'{result["total_bytes"]:,} bytes total')
        for rel, sz, md5 in result['bundled']:
            print(f'    {sz:>10,}  {md5[:8]}  {rel}')
        if result['skipped']:
            print(f'  skipped: {len(result["skipped"])} files')
            for rel, why in result['skipped']:
                print(f'    {rel}  ({why})')
    else:
        for slug in GAME_DCPS:
            result = bundle_for_slug(slug)
            print(f'{slug}: {result.get("total_bytes", 0):,} bytes bundled, '
                  f'{len(result.get("bundled", []))} files')
    return 0


if __name__ == '__main__':
    sys.exit(main())
