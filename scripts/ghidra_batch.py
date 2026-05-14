"""Headless Ghidra batch RE for all 15 Capcom DC games.

For each game's 1ST_READ.BIN:
  1. Import as SH-4 little-endian raw binary at base 0x8C010000
  2. Apply Katana / Naomi / Kunoichi FIDBs to recover library function names
  3. AutoAnalyze
  4. Dump named functions + strings to spawn_re_ghidra/ghidra_dumps/<slug>.json
"""
from __future__ import annotations
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

GHIDRA = Path(r"D:\Ghidra\ghidra_12.0.4_PUBLIC_20260303\ghidra_12.0.4_PUBLIC")
HEADLESS = GHIDRA / "support" / "analyzeHeadless.bat"
SCRIPT_DIR = Path(r"D:\DC_CapcomTranslationTools\spawn_re_ghidra")
PROJ_DIR = SCRIPT_DIR / "ghidra_project"
OUT_DIR = SCRIPT_DIR / "ghidra_dumps"
RC2 = Path(r"D:\Capcom Dreamcast  Games - Joe Patched\RC2 Translated")

PROJ_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

GAMES: list[tuple[str, Path]] = [
    ('spawn',                RC2 / "Spawn - In the Demon's Hand (JP)/patches/1ST_READ.BIN"),
    ('cvs_pro',              RC2 / 'Capcom vs. SNK - Millennium Fight 2000 Pro (JP)/extracted/1ST_READ.BIN'),
    ('heavy_metal',          RC2 / 'Heavy Metal - Geomatrix (JP)/extracted/1ST_READ.BIN'),
    ('jojo',                 RC2 / 'JoJo_s Bizarre Adventure[ (JP)/extracted/1ST_READ.BIN'),
    ('mvc2',                 RC2 / 'Marvel vs. Capcom 2 - New Age of Heroes (JP)/extracted/1ST_READ.BIN'),
    ('net_de_tennis',        RC2 / 'Net de Tennis (JP)/extracted/1ST_READ.BIN'),
    ('power_stone_2',        RC2 / 'Power Stone 2 (JP)/extracted/1ST_READ.BIN'),
    ('project_justice',      RC2 / 'Project Justice (JP)/extracted/1ST_READ.BIN'),
    ('sf3_3rd_strike',       RC2 / 'Street Fighter III 3rd Strike - Fight for the Future (JP)/extracted/1ST_READ.BIN'),
    ('sfz3_ms',              RC2 / 'Street Fighter Zero 3  for Matching Service (JP)/extracted/1ST_READ.BIN'),
    ('spfii_ms',             RC2 / 'Super Puzzle Fighter IIX for Matching Service (JP)/extracted/1ST_READ.BIN'),
    ('ssfiix_ms',            RC2 / 'Super Street Fighter IIX for Matching Service - Grand Master Challenge (JP)/extracted/1ST_READ.BIN'),
    ('taisen_net_gimmick',   RC2 / 'Taisen Net Gimmick - Capcom & Psikyo All Stars (JP)/extracted/1ST_READ.BIN'),
    ('tech_romancer_ms',     RC2 / 'Tech Romancer for Matching Service (JP)/extracted/1ST_READ.BIN'),
    ('vampire_chronicle_ms', RC2 / 'Vampire Chronicle for Matching Service (JP)/extracted/1ST_READ.BIN'),
]


SHORT_STAGE = Path(r'C:\re_stage')


def run_one(slug: str, bin_path: Path) -> bool:
    if not bin_path.is_file():
        print(f'  SKIP {slug}: missing {bin_path}')
        return False
    out_json = OUT_DIR / f'{slug}.json'
    if out_json.is_file() and out_json.stat().st_size > 1024:
        print(f'  SKIP {slug}: dump already exists at {out_json}')
        return True
    # Copy the binary to a short, paren-free, ampersand-free path so the
    # Ghidra wrapper .bat (which runs through cmd.exe) doesn't choke on it.
    SHORT_STAGE.mkdir(parents=True, exist_ok=True)
    staged = SHORT_STAGE / f'{slug}_1ST_READ.bin'
    shutil.copy(bin_path, staged)
    print(f'=== {slug}  ({bin_path.stat().st_size:,} bytes; staged at {staged}) ===')
    cmd = [
        str(HEADLESS),
        str(PROJ_DIR), slug,
        '-import', str(staged),
        '-processor', 'SuperH4:LE:32:default',
        '-loader', 'BinaryLoader',
        '-loader-image-base', '0x8C010000',
        '-overwrite',
        '-scriptPath', str(SCRIPT_DIR),
        '-postScript', 'AttachAllFidbs.java',
        '-postScript', 'DumpSymbolsAndStrings.java',
        f'-Ddump.outDir={OUT_DIR}',
    ]
    # Point at the installed JDK on D: drive — old config has stale E:\ path
    env = {k: v for k, v in __import__('os').environ.items()}
    jdk = Path(r"D:\Ghidra\OpenJDK21U-jdk_x64_windows_hotspot_21.0.10_7")
    for candidate in jdk.glob('jdk-21*'):
        env['JAVA_HOME_OVERRIDE'] = str(candidate)
        env['JAVA_HOME'] = str(candidate)
        break
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, env=env)
    log = OUT_DIR / f'{slug}.log'
    log.write_text(
        f'== STDOUT ==\n{result.stdout}\n\n== STDERR ==\n{result.stderr}',
        encoding='utf-8', errors='replace',
    )
    if result.returncode != 0:
        print(f'  FAILED  exit={result.returncode}  log={log}')
        return False
    print(f'  OK  log={log}  dump={out_json if out_json.is_file() else "<NOT WRITTEN>"}')
    return True


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for slug, bin_path in GAMES:
        if only and slug != only: continue
        run_one(slug, bin_path)


if __name__ == '__main__':
    main()
