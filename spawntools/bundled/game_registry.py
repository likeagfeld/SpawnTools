"""Per-game preset config registry.

Each entry tells the bundle builder where the canonical RC2 campaign workspace
lives for that game and what to scan for JP→EN string pairs. The actual
translation rows are diff-derived at build time from `extracted/` vs `patches/`
— we don't hand-write any English here.

Fields per game:
  slug          short kebab-case id used in `bundled/<slug>_preset/`
  display_name  user-facing label
  rc2_dir       absolute path under RC2 Translated/ on Gary's local disk
                (this is the BUILD-TIME source; end users never need it)
  scan_targets  list of patches-relative paths to diff-scan for JP cp932 runs
                (typically '1ST_READ.BIN' and any MESSAGE.INI / INI files)
  deny_list     filenames that LOOK CJK but are data, not strings — never
                bulk-edit. Surfaces in the workbench's protected-binary check.
  detect_label  ISO9660 volume label substring (uppercase) used to fingerprint
                a freshly-loaded disc and auto-select this preset
  notes_kind    'dp3' for Dream Passport titles (have DPETC/MESSAGE.INI),
                'std' for everything else
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

RC2_ROOT = Path(r"D:/Capcom Dreamcast  Games - Joe Patched/RC2 Translated")


@dataclass
class GameConfig:
    slug: str
    display_name: str
    rc2_dir: Path
    scan_targets: list[str] = field(default_factory=list)
    deny_list: list[str] = field(default_factory=list)
    detect_label: str = ''
    notes_kind: str = 'std'


# Common deny lists (filenames that contain CJK as DATA, not strings)
COMMON_DENY = ['2_DP.BIN', 'GAME.BIN', 'GGAM.BIN', 'MEMDEF.BIN']


GAMES: list[GameConfig] = [
    GameConfig(
        slug='spawn',
        display_name="Spawn — In the Demon's Hand",
        rc2_dir=RC2_ROOT / "Spawn - In the Demon's Hand (JP)",
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI'],
        deny_list=COMMON_DENY,
        detect_label='SPAWN',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='cvs_pro',
        display_name='Capcom vs. SNK — Millennium Fight 2000 Pro',
        rc2_dir=RC2_ROOT / 'Capcom vs. SNK - Millennium Fight 2000 Pro (JP)',
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI'],
        deny_list=COMMON_DENY,
        detect_label='CAPCOM VS SNK',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='heavy_metal',
        display_name='Heavy Metal — Geomatrix',
        rc2_dir=RC2_ROOT / 'Heavy Metal - Geomatrix (JP)',
        scan_targets=['1ST_READ.BIN'],
        deny_list=COMMON_DENY,
        detect_label='HEAVY METAL',
        notes_kind='std',
    ),
    GameConfig(
        slug='jojo',
        display_name="JoJo's Bizarre Adventure",
        rc2_dir=RC2_ROOT / 'JoJo_s Bizarre Adventure[ (JP)',
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI'],
        deny_list=COMMON_DENY,
        detect_label='JOJO',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='marvel_vs_capcom_2',
        display_name='Marvel vs. Capcom 2 — New Age of Heroes',
        rc2_dir=RC2_ROOT / 'Marvel vs. Capcom 2 - New Age of Heroes (JP)',
        scan_targets=['1ST_READ.BIN'],
        deny_list=COMMON_DENY,
        detect_label='MARVEL',
        notes_kind='std',
    ),
    GameConfig(
        slug='net_de_tennis',
        display_name='Net de Tennis',
        rc2_dir=RC2_ROOT / 'Net de Tennis (JP)',
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI'],
        deny_list=COMMON_DENY,
        detect_label='NET DE TENNIS',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='power_stone_2',
        display_name='Power Stone 2',
        rc2_dir=RC2_ROOT / 'Power Stone 2 (JP)',
        scan_targets=['1ST_READ.BIN'],
        deny_list=COMMON_DENY,
        detect_label='POWER STONE',
        notes_kind='std',
    ),
    GameConfig(
        slug='project_justice',
        display_name='Project Justice',
        rc2_dir=RC2_ROOT / 'Project Justice (JP)',
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI'],
        deny_list=COMMON_DENY,
        detect_label='PROJECT JUSTICE',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='sf3_3rd_strike',
        display_name='Street Fighter III 3rd Strike',
        rc2_dir=RC2_ROOT / 'Street Fighter III 3rd Strike - Fight for the Future (JP)',
        scan_targets=['1ST_READ.BIN'],
        deny_list=COMMON_DENY,
        detect_label='3RD STRIKE',
        notes_kind='std',
    ),
    GameConfig(
        slug='sfz3_ms',
        display_name='Street Fighter Zero 3 (Matching Service)',
        rc2_dir=RC2_ROOT / 'Street Fighter Zero 3  for Matching Service (JP)',
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI'],
        deny_list=COMMON_DENY,
        detect_label='ZERO 3',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='spfii_ms',
        display_name='Super Puzzle Fighter IIX (Matching Service)',
        rc2_dir=RC2_ROOT / 'Super Puzzle Fighter IIX for Matching Service (JP)',
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI'],
        deny_list=COMMON_DENY,
        detect_label='PUZZLE FIGHTER',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='ssfiix_ms',
        display_name='Super Street Fighter IIX (Matching Service)',
        rc2_dir=RC2_ROOT / 'Super Street Fighter IIX for Matching Service - Grand Master Challenge (JP)',
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI'],
        deny_list=COMMON_DENY,
        detect_label='SUPER SF',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='taisen_net_gimmick',
        display_name='Taisen Net Gimmick — Capcom & Psikyo All Stars',
        rc2_dir=RC2_ROOT / 'Taisen Net Gimmick - Capcom & Psikyo All Stars (JP)',
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI'],
        deny_list=COMMON_DENY,
        detect_label='NET GIMMICK',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='tech_romancer_ms',
        display_name='Tech Romancer (Matching Service)',
        rc2_dir=RC2_ROOT / 'Tech Romancer for Matching Service (JP)',
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI'],
        deny_list=COMMON_DENY,
        detect_label='TECH ROMANCER',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='vampire_chronicle_ms',
        display_name='Vampire Chronicle (Matching Service)',
        rc2_dir=RC2_ROOT / 'Vampire Chronicle for Matching Service (JP)',
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI'],
        deny_list=COMMON_DENY,
        detect_label='VAMPIRE',
        notes_kind='dp3',
    ),
]


def by_slug(slug: str) -> GameConfig | None:
    for g in GAMES:
        if g.slug == slug: return g
    return None
