"""Read each game's ACTUAL ISO9660 PVD volume label from its track03.
Writes a mapping {slug: volume_label} so game_registry.detect_label is
empirically driven, not guessed.

GD-ROM track03 is laid out as 2048-byte ISO9660 sectors starting at the GD
disc's LBA 45000. PVD sits at sector 16 (offset 32768) within the data
stream. The volume identifier is 32 bytes at byte offset 40 within the PVD.

For .bin tracks (2352-byte raw sectors), the data starts at +16 within each
sector. We auto-detect and apply the right offset.
"""
from __future__ import annotations
import json
from pathlib import Path

RC2 = Path(r"D:/Capcom Dreamcast  Games - Joe Patched/RC2 Translated")
OUT = Path(r"D:/DC_CapcomTranslationTools/disc_volume_labels.json")


def read_label(track_path: Path) -> str:
    data = track_path.read_bytes()
    # Try 2048-byte sector layout first
    for sec_size, off in [(2048, 0), (2352, 16)]:
        try:
            pvd_off = 16 * sec_size + off
            # Sanity-check: PVD starts with type=1 + 'CD001'
            if data[pvd_off + 1:pvd_off + 6] == b'CD001':
                vol_id = data[pvd_off + 40:pvd_off + 72].decode('ascii', errors='replace').strip()
                return vol_id
        except Exception:
            continue
    # PVD might be at a different sector; scan first 256 sectors
    for i in range(0, 256):
        for sec_size, off in [(2048, 0), (2352, 16)]:
            try:
                p = i * sec_size + off
                if data[p + 1:p + 6] == b'CD001' and data[p] == 1:
                    vol_id = data[p + 40:p + 72].decode('ascii', errors='replace').strip()
                    return vol_id
            except Exception:
                continue
    return ''


labels = {}
for game_dir in sorted(RC2.iterdir()):
    if not game_dir.is_dir() or game_dir.name.startswith('_'): continue
    track03 = None
    for cand in (game_dir / 'disc' / 'track03.iso',
                 game_dir / 'disc' / 'track03.bin',
                 game_dir / 'track03.iso',
                 game_dir / 'track03.bin'):
        if cand.is_file(): track03 = cand; break
    if not track03:
        # Walk for any track03.*
        for p in game_dir.rglob('track03.*'):
            track03 = p; break
    if not track03:
        labels[game_dir.name] = '<no track03 found>'
        continue
    try:
        label = read_label(track03)
    except Exception as e:
        label = f'<error: {e}>'
    labels[game_dir.name] = label
    print(f'{game_dir.name[:50]:50s}  -> {label!r}')

OUT.write_text(json.dumps(labels, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'\nwrote {OUT}')
