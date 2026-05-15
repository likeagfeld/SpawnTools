"""Dreamcast Patcher (.dcp) apply helper.

A .dcp is a zip file containing one xdelta3 patch per modified disc file
(named "<rel>.xdelta"). Apply against extracted/<rel> to produce
patches/<rel>.

Two entry points:
  apply_dcp_from_file(dcp_path, extracted_dir, patches_dir, log) — local file
  fetch_and_apply_latest(slug, extracted_dir, patches_dir, log)  — GitHub

Runtime needs `pyxdelta` (Cython binding to libxdelta3). If unavailable,
raises RuntimeError with install hint.
"""
from __future__ import annotations
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

# Map game slug → GitHub release asset URL for the canonical EN .dcp.
# Update when new patches ship.
DCP_URLS = {
    'spawn': 'https://github.com/likeagfeld/SpawnTools/releases/latest/download/Spawn-T-En-Farkus-V0.2.dcp',
}


def apply_dcp_from_file(dcp_path: Path, extracted_dir: Path, patches_dir: Path,
                         log: Optional[Callable[[str], None]] = None) -> dict:
    """Apply every xdelta entry in a .dcp zip against extracted/, writing
    the patched output to patches/. The .dcp's filename is included in the
    log so the user knows which patch was applied.

    Returns: {'applied': N, 'skipped': [...], 'total_bytes': N}.
    """
    log = log or (lambda _m: None)
    try:
        import pyxdelta  # noqa
    except ImportError:
        raise RuntimeError(
            'pyxdelta is required to apply .dcp patches. Install via:\n'
            '  pip install pyxdelta\n'
            'Or apply the .dcp externally via a DCP-compatible tool first.'
        )
    import pyxdelta

    if not dcp_path.is_file():
        raise RuntimeError(f'.dcp not found: {dcp_path}')
    if not extracted_dir.is_dir():
        raise RuntimeError(f'extracted/ dir missing: {extracted_dir}')
    patches_dir.mkdir(parents=True, exist_ok=True)

    log(f'Applying {dcp_path.name} (zip of xdelta patches)')

    work = Path(tempfile.mkdtemp(prefix='dcp_apply_'))
    applied = 0
    skipped: list[tuple[str, str]] = []
    total_bytes = 0
    try:
        with zipfile.ZipFile(dcp_path, 'r') as z:
            entries = [i for i in z.infolist() if i.filename.endswith('.xdelta')]
            log(f'  {len(entries)} xdelta entries in archive')
            for info in entries:
                rel = info.filename[:-len('.xdelta')]
                src = extracted_dir / rel
                if not src.is_file():
                    skipped.append((rel, 'no extracted/<rel> source'))
                    continue
                # Stage
                src_staged = work / 'src.bin'
                src_staged.write_bytes(src.read_bytes())
                xd_staged = work / 'patch.xdelta'
                xd_staged.write_bytes(z.read(info))
                out_staged = work / 'out.bin'
                try:
                    pyxdelta.decode(str(src_staged), str(xd_staged), str(out_staged))
                except Exception as e:
                    skipped.append((rel, f'xdelta decode failed: {e}'))
                    continue
                new_bytes = out_staged.read_bytes()
                # Write into patches/
                target = patches_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(new_bytes)
                applied += 1
                total_bytes += len(new_bytes)
                log(f'  {rel}: {len(new_bytes):,} bytes')
    finally:
        shutil.rmtree(work, ignore_errors=True)

    log(f'.dcp applied: {applied} files, {total_bytes:,} bytes total; '
        f'{len(skipped)} skipped')
    return {'applied': applied, 'skipped': skipped, 'total_bytes': total_bytes}


def fetch_and_apply_latest(slug: str, extracted_dir: Path, patches_dir: Path,
                            log: Optional[Callable[[str], None]] = None) -> dict:
    """Download the canonical EN .dcp for `slug` from GitHub then apply it."""
    log = log or (lambda _m: None)
    url = DCP_URLS.get(slug)
    if not url:
        raise RuntimeError(
            f'No public .dcp URL registered for game slug "{slug}". '
            f'Use "Apply local .dcp..." to pick a file manually.'
        )
    log(f'Downloading {url} ...')
    # Save into the project dir so the user can keep it locally.
    dest = patches_dir.parent / Path(url).name
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = resp.read()
        dest.write_bytes(data)
        log(f'  saved {len(data):,} bytes to {dest}')
    except Exception as e:
        raise RuntimeError(f'Download failed: {e}')
    return apply_dcp_from_file(dest, extracted_dir, patches_dir, log)
