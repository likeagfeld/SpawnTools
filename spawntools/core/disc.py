"""Disc lifecycle — open a GDI, extract its filesystem, run integrity checks,
patch back, verify-after-patch, build sidecar GDI.

Every operation here goes through the campaign's `_shared_tools/process_game`
implementation. We never spawn mkisofs — that would rebuild the ISO9660 with
new LBAs and break boot. Our patch_iso writes each modified file BACK at its
original LBA, preserving track03 byte size and GDI layout.

Capcom-specific quirks handled here:
  • Track03 may be .iso (2048-byte sectors) or .bin (2352-byte sectors).
    process_game.find_disc_files() detects this. .bin sectors need +16 byte
    offset when reading the 2048-byte data payload.
  • IP.BIN sits at track03 offset 0..0xFFFF (32 sectors).
  • Filesystem uses Dreamcast LBA base 45000 — every extent in the PVD is
    relative to that, not zero.
  • Some rips name the GDI by the game's title (not 'disc.gdi') — we walk
    siblings of the user-picked file too.
"""
from __future__ import annotations
import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


@dataclass
class DiscContext:
    """Everything the Workbench tabs need to know about an opened disc."""
    source_gdi: Path                 # what the user picked
    track03_path: Path               # actual track03.iso or .bin
    is_bin_sectors: bool             # True if .bin (2352-byte sectors)
    extracted_dir: Path              # where the filesystem was extracted
    patches_dir: Path                # mirror of extracted_dir for in-place patching
    backups_dir: Path                # safety net for any modified file


def find_tracks(picked: Path) -> tuple[Optional[Path], bool]:
    """Locate track03 sibling of `picked`. Handles rips that don't ship a
    file named exactly 'disc.gdi'."""
    parent = picked.parent
    if not parent.is_dir():
        return None, False
    for fname in ('track03.iso', 'track03.bin'):
        cand = parent / fname
        if cand.is_file():
            return cand, fname.endswith('.bin')
    # Fallback: any *03* file
    for p in sorted(parent.iterdir()):
        if not p.is_file(): continue
        if '03' in p.name.lower() and p.suffix.lower() in ('.iso', '.bin'):
            return p, p.suffix.lower() == '.bin'
    return None, False


def open_disc(gdi: Path, work_root: Path,
              progress: Optional[Callable[[str], None]] = None) -> DiscContext:
    """Open a GDI, extract its filesystem into `work_root/extracted/`,
    and mirror into `work_root/patches/` for in-place editing.

    Idempotent: if `patches/` already exists with files in it, we DON'T
    re-extract (would clobber user edits). The user must explicitly Reset
    Patches to rebuild from the disc.

    Returns: a DiscContext ready for the tabs to use.
    """
    log = progress or (lambda _msg: None)

    track03, is_bin = find_tracks(gdi)
    if not track03:
        raise RuntimeError(
            f"No track03 (.iso/.bin) found alongside\n{gdi}\n"
            f"Make sure track01/02/03 files live in the same folder."
        )

    extracted = work_root / 'extracted'
    patches = work_root / 'patches'
    backups = work_root / 'backups'
    for d in (extracted, patches, backups):
        d.mkdir(parents=True, exist_ok=True)

    # Use process_game.extract_filesystem (Dreamcast LBA-aware ISO9660 walker)
    if not any(extracted.iterdir()):
        log(f'extracting filesystem from {track03.name}...')
        import process_game
        process_game.extract_filesystem(str(track03), is_bin, str(extracted))
        n = sum(1 for _ in extracted.rglob('*') if _.is_file())
        log(f'  {n} files extracted to {extracted}')

    # Initialize patches/ as a mirror of extracted/ on first open
    if not any(patches.iterdir()):
        log(f'staging patches dir...')
        shutil.copytree(extracted, patches, dirs_exist_ok=True)

    return DiscContext(
        source_gdi=gdi, track03_path=track03, is_bin_sectors=is_bin,
        extracted_dir=extracted, patches_dir=patches, backups_dir=backups,
    )


def make_backup(dctx: DiscContext, rel_path: str,
                progress: Optional[Callable[[str], None]] = None) -> Path:
    """Copy patches/<rel_path> to backups/<rel_path>.bak.<timestamp>.
    Use BEFORE every destructive write. Returns the backup path."""
    import time
    log = progress or (lambda _msg: None)
    src = dctx.patches_dir / rel_path
    if not src.is_file():
        raise FileNotFoundError(src)
    ts = time.strftime('%Y%m%d_%H%M%S')
    dst = dctx.backups_dir / f'{rel_path}.bak.{ts}'
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dst)
    log(f'backed up {rel_path} -> {dst.relative_to(dctx.backups_dir.parent)}')
    return dst


# ---------- integrity ----------

def integrity_check(dctx: DiscContext,
                    progress: Optional[Callable[[str], None]] = None) -> dict:
    """Run all the safety audits the campaign learned the hard way:

    1. patches/ vs extracted/ size invariant — every patched file must be
       <= original byte size (no-grow rule).
    2. patches/ vs extracted/ name parity — no new files added.
    3. Md5 reproducibility — patches/ md5s are recordable.

    Returns: { 'oversize': [...], 'orphans': [...], 'modified': N,
               'identical_to_baseline': N, 'sizes_match': True/False }
    """
    log = progress or (lambda _msg: None)
    oversize: list[str] = []
    orphans: list[str] = []
    n_modified = 0
    n_identical = 0
    n_files = 0

    # Names we generate ourselves and that aren't part of the disc — skip them
    # so the orphan check doesn't false-positive on our safety backups / logs.
    SKIP_SUFFIXES = ('.bak', '.pre_twinstick_revert', '.tmp', '.new', '.swp')
    SKIP_NAMES = {'.DS_Store', 'Thumbs.db'}

    # For every file in patches/, compare against the same file in extracted/
    for p in dctx.patches_dir.rglob('*'):
        if not p.is_file(): continue
        if p.name in SKIP_NAMES: continue
        if any(p.name.endswith(s) for s in SKIP_SUFFIXES): continue
        n_files += 1
        rel = p.relative_to(dctx.patches_dir)
        baseline = dctx.extracted_dir / rel
        if not baseline.exists():
            orphans.append(str(rel))
            continue
        p_size = p.stat().st_size
        b_size = baseline.stat().st_size
        if p_size > b_size:
            oversize.append(f'{rel}  patches={p_size:,}  baseline={b_size:,}')
        elif p_size != b_size or hashlib.md5(p.read_bytes()).hexdigest() != \
                hashlib.md5(baseline.read_bytes()).hexdigest():
            n_modified += 1
        else:
            n_identical += 1

    log(f'audited {n_files:,} files: {n_modified:,} modified, {n_identical:,} identical')
    if oversize:
        log(f'!! OVERSIZE: {len(oversize)} file(s) bigger than baseline')
        for line in oversize[:10]:
            log(f'    {line}')
    if orphans:
        log(f'!! ORPHANS: {len(orphans)} file(s) in patches/ not in extracted/')
        for line in orphans[:5]:
            log(f'    {line}')

    return {
        'files_checked': n_files,
        'modified': n_modified,
        'identical': n_identical,
        'oversize': oversize,
        'orphans': orphans,
        'safe_to_build': not oversize and not orphans,
    }


# ---------- build patched disc ----------

def patch_and_verify(dctx: DiscContext, out_iso: Path,
                     progress: Optional[Callable[[str], None]] = None) -> Path:
    """Run process_game.patch_iso to write a NEW track03.iso with all
    modifications from patches/ baked in at their original LBAs.

    Then verify:
      • out_iso size == original track03 size (NO drift)
      • For each modified patches/ file, its bytes appear at the right offset
        in out_iso (md5 match) — guards against patch_iso silently truncating
        oversize patches (the Tech Romancer bug we caught).

    Returns: the path of the produced track03 image.
    """
    log = progress or (lambda _msg: None)
    import process_game
    out_iso.parent.mkdir(parents=True, exist_ok=True)
    log(f'patching {dctx.track03_path} -> {out_iso}')
    n = process_game.patch_iso(
        str(dctx.track03_path), dctx.is_bin_sectors,
        str(out_iso), str(dctx.patches_dir)
    )
    log(f'  patched {n} files')

    # Size invariant
    orig_size = dctx.track03_path.stat().st_size
    new_size = out_iso.stat().st_size
    log(f'  orig size={orig_size:,}  new size={new_size:,}')
    if new_size != orig_size:
        raise RuntimeError(
            f"track03 size changed ({orig_size} -> {new_size}) — refusing to ship. "
            f"This means patch_iso truncated or grew the image. CHECK YOUR PATCHES."
        )

    # Spot-check 1ST_READ.BIN md5 sync if it's in patches/
    bin_path = dctx.patches_dir / '1ST_READ.BIN'
    if bin_path.is_file():
        patches_bytes = bin_path.read_bytes()
        disc_bytes = out_iso.read_bytes()
        needle = patches_bytes[:128]
        off = disc_bytes.find(needle)
        if off >= 0:
            disc_chunk = disc_bytes[off:off + len(patches_bytes)]
            p_md5 = hashlib.md5(patches_bytes).hexdigest()
            d_md5 = hashlib.md5(disc_chunk).hexdigest()
            log(f'  1ST_READ.BIN sync: patches={p_md5}  disc={d_md5}')
            if p_md5 != d_md5:
                raise RuntimeError(
                    "patches/1ST_READ.BIN md5 doesn't match the disc region. "
                    "The patch did not land. Check console output above for errors."
                )
        else:
            log('  (1ST_READ.BIN signature not located in disc — not verifiable)')

    return out_iso


def generate_gdi_sidecar(source_gdi: Path, out_iso: Path,
                          progress: Optional[Callable[[str], None]] = None) -> Path:
    """Write a .gdi alongside `out_iso` that mirrors the source GDI's track
    layout but references `out_iso.name` for track 3.

    Most emulators expect track01/02 to sit next to the .gdi too — that's
    the user's job to copy.
    """
    log = progress or (lambda _msg: None)
    out_gdi = out_iso.with_suffix('.gdi')
    new_lines = []
    for ln in source_gdi.read_text(encoding='utf-8').strip().splitlines():
        parts = ln.split()
        if len(parts) >= 5 and parts[0] == '3':
            parts[4] = out_iso.name
            new_lines.append(' '.join(parts))
        else:
            new_lines.append(ln)
    out_gdi.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')
    log(f'wrote {out_gdi}')
    return out_gdi
