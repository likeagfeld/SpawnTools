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
    # Dreamcast IP.BIN product code (T1216M, T1247M, etc.). Read directly from
    # the first 16 bytes of track03 at byte offset 0x40. 100% reliable — each
    # commercial Dreamcast release has a unique Sega-assigned code.
    product_code: str = ''
    # Legacy ISO9660 PVD volume label — kept for the few discs where IP.BIN
    # isn't readable. Most Capcom DC discs report 'DREAMCAST' here, so this
    # is a weak signal — only used as a fallback.
    detect_label: str = ''
    notes_kind: str = 'std'


# Common deny lists (filenames that contain CJK as DATA, not strings)
COMMON_DENY = ['2_DP.BIN', 'GAME.BIN', 'GGAM.BIN', 'MEMDEF.BIN']


# Per-game scan_targets derived from the audit at audit_jp_per_game.json +
# evidence_modified_files.txt. Each entry below was picked because the campaign
# ACTUALLY modified that file AND the baseline contains real cp932 string runs
# (not pixel-data false positives). Files modified-but-with-zero-JP-runs are
# texture/binary work and surface via Tab 2 instead.

GAMES: list[GameConfig] = [
    GameConfig(
        slug='spawn',
        display_name="Spawn — In the Demon's Hand",
        rc2_dir=RC2_ROOT / "Spawn - In the Demon's Hand (JP)",
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI'],
        deny_list=COMMON_DENY,
        product_code='T1216M', detect_label='SPAWN',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='cvs_pro',
        display_name='Capcom vs. SNK — Millennium Fight 2000 Pro',
        rc2_dir=RC2_ROOT / 'Capcom vs. SNK - Millennium Fight 2000 Pro (JP)',
        scan_targets=[
            '1ST_READ.BIN', 'DPETC/MESSAGE.INI', 'ASK.BIN',
            'MESJ_WIN.BIN',
            'ST07TEX.BIN', 'EST07TEX.BIN', 'ST0ATEX.BIN', 'EST0ATEX.BIN',
            'DM01TEX.BIN', 'DM00TEX.BIN',
            'STG04TEX.BIN',
            'DC13TEX.BIN', 'DC02TEX.BIN', 'DC14TEX.BIN', 'DC01TEX.BIN', 'DC05TEX.BIN',
            'PL1EPAK.BIN', 'PL10PAK.BIN',
        ],
        deny_list=COMMON_DENY,
        product_code='T1247M', detect_label='CAPCOM VS SNK',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='heavy_metal',
        display_name='Heavy Metal — Geomatrix',
        rc2_dir=RC2_ROOT / 'Heavy Metal - Geomatrix (JP)',
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI', 'DEMO.BIN'],
        deny_list=COMMON_DENY,
        product_code='T1246M', detect_label='HEAVY METAL',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='jojo',
        display_name="JoJo's Bizarre Adventure",
        rc2_dir=RC2_ROOT / 'JoJo_s Bizarre Adventure[ (JP)',
        # Per-character training archives carry the bulk of the JP.
        scan_targets=[
            '97_DASH.BIN', '95_JOJO.BIN', '93_LOBBY.BIN', '91_MENU.BIN',
            'JOJO/PL01_TRN.BIN',
            'DASH/PL0F_TRN.BIN', 'DASH/PL10_TRN.BIN', 'DASH/PS13_TRN.BIN',
            'DASH/PL16_TRN.BIN', 'DASH/PS03_TRN.BIN', 'DASH/STF00_TRN.BIN',
            'DPETC/MESSAGE.INI',
        ],
        deny_list=COMMON_DENY,
        product_code='T1231M', detect_label='JOJO',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='marvel_vs_capcom_2',
        display_name='Marvel vs. Capcom 2 — New Age of Heroes',
        rc2_dir=RC2_ROOT / 'Marvel vs. Capcom 2 - New Age of Heroes (JP)',
        # Every modified PL*_DAT.BIN + the EFKYTEX/ASK + DP3 pair.
        scan_targets=[
            '1ST_READ.BIN', 'DPETC/MESSAGE.INI', 'ASK.BIN', 'EFKYTEX.BIN',
            'PL01_DAT.BIN', 'PL04_DAT.BIN', 'PL0B_DAT.BIN', 'PL0E_DAT.BIN',
            'PL12_DAT.BIN', 'PL17_DAT.BIN', 'PL1C_DAT.BIN', 'PL1D_DAT.BIN',
            'PL20_DAT.BIN', 'PL22_DAT.BIN', 'PL2D_DAT.BIN', 'PL31_DAT.BIN',
            'PL33_DAT.BIN', 'PL38_DAT.BIN', 'PL39_DAT.BIN', 'PL3A_DAT.BIN',
        ],
        deny_list=COMMON_DENY,
        product_code='T1215M', detect_label='MARVEL VS. CAPCOM 2',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='net_de_tennis',
        display_name='Net de Tennis',
        rc2_dir=RC2_ROOT / 'Net de Tennis (JP)',
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI', 'ASKLIBS.BIN'],
        deny_list=COMMON_DENY,
        product_code='T1234M', detect_label='NET DE TENNIS',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='power_stone_2',
        display_name='Power Stone 2',
        rc2_dir=RC2_ROOT / 'Power Stone 2 (JP)',
        scan_targets=[
            '1ST_READ.BIN', 'DPETC/MESSAGE.INI', 'ASKLIBS.BIN',
            'DM04_CONNECT.BIN', 'CMN_MOT.BIN',
        ],
        deny_list=COMMON_DENY,
        product_code='T1218M', detect_label='POWER STONE 2',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='project_justice',
        display_name='Project Justice',
        rc2_dir=RC2_ROOT / 'Project Justice (JP)',
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI', 'ASKLIB.BIN'],
        deny_list=COMMON_DENY,
        product_code='T1221M', detect_label='MOERO JUSTICE GAKUEN',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='sf3_3rd_strike',
        display_name='Street Fighter III 3rd Strike',
        rc2_dir=RC2_ROOT / 'Street Fighter III 3rd Strike - Fight for the Future (JP)',
        scan_targets=[
            '1ST_READ.BIN', 'DPETC/MESSAGE.INI', 'KANJI/ASKLIBS.BIN',
            'PLAYER/PL00.BIN', 'PLAYER/PL02.BIN', 'PLAYER/PL09.BIN',
            'PLAYER/PL11.BIN', 'PLAYER/PL17.BIN', 'PLAYER/PL18.BIN',
            'PLAYER/PL19.BIN', 'PLAYER/PL20.BIN',
            'OPENING/BG20.BIN',
            'STAGE/BG00.BIN', 'STAGE/BG11.BIN', 'STAGE/BG19.BIN',
            'ENDING/BG39.BIN',
        ],
        deny_list=COMMON_DENY,
        product_code='T1209M', detect_label='STREET FIGHTER 3 3RD STRIKE',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='sfz3_ms',
        display_name='Street Fighter Zero 3 (Matching Service)',
        rc2_dir=RC2_ROOT / 'Street Fighter Zero 3  for Matching Service (JP)',
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI'],
        deny_list=COMMON_DENY,
        product_code='T1230M', detect_label='STREET FIGHTER ZERO3',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='spfii_ms',
        display_name='Super Puzzle Fighter IIX (Matching Service)',
        rc2_dir=RC2_ROOT / 'Super Puzzle Fighter IIX for Matching Service (JP)',
        scan_targets=[
            '1ST_READ.BIN', 'DPETC/MESSAGE.INI', 'ASK.BIN',
            'PL06_FEL.OSB', 'PL00_MOR.OSB',
        ],
        deny_list=COMMON_DENY,
        product_code='T1250M', detect_label='SUPER PUZZLE FIGHTER2X',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='ssfiix_ms',
        display_name='Super Street Fighter IIX (Matching Service)',
        rc2_dir=RC2_ROOT / 'Super Street Fighter IIX for Matching Service - Grand Master Challenge (JP)',
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI', 'ASK.BIN'],
        deny_list=COMMON_DENY,
        product_code='T1236M', detect_label='SUPER STREET FIGHTER 2X',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='taisen_net_gimmick',
        display_name='Taisen Net Gimmick — Capcom & Psikyo All Stars',
        rc2_dir=RC2_ROOT / 'Taisen Net Gimmick - Capcom & Psikyo All Stars (JP)',
        scan_targets=[
            '1ST_READ.BIN', 'DPETC/MESSAGE.INI',
            'RESOURCE.BIN', 'ASK.BIN', 'WAZAALL.BIN',
        ],
        deny_list=COMMON_DENY,
        product_code='T1248M', detect_label='NET GIMMICK',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='tech_romancer_ms',
        display_name='Tech Romancer (Matching Service)',
        rc2_dir=RC2_ROOT / 'Tech Romancer for Matching Service (JP)',
        scan_targets=[
            '1ST_READ.BIN', 'DPETC/MESSAGE.INI',
            'SOUND/WIS.OSB',
        ],
        deny_list=COMMON_DENY,
        product_code='T1232M', detect_label='KIKAIOH',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='vampire_chronicle_ms',
        display_name='Vampire Chronicle (Matching Service)',
        rc2_dir=RC2_ROOT / 'Vampire Chronicle for Matching Service (JP)',
        scan_targets=[
            '1ST_READ.BIN', 'DPETC/MESSAGE.INI', 'ASK.BIN',
            'PL0C.BIN', 'PL08.BIN',
        ],
        deny_list=COMMON_DENY,
        product_code='T1235M', detect_label='VAMPIRE CHRONICLE',
        notes_kind='dp3',
    ),
]


def by_slug(slug: str) -> GameConfig | None:
    for g in GAMES:
        if g.slug == slug: return g
    return None
