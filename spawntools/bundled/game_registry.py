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
        # Audit: stage-text BINs carry most of the JP. Adding the 5 modified
        # stage TEX-bin files alongside the standard DP3 pair.
        scan_targets=[
            '1ST_READ.BIN', 'DPETC/MESSAGE.INI',
            'ST07TEX.BIN', 'EST07TEX.BIN', 'ST0ATEX.BIN', 'EST0ATEX.BIN',
            'PL1EPAK.BIN',
        ],
        deny_list=COMMON_DENY,
        product_code='T1247M', detect_label='CAPCOM VS SNK',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='heavy_metal',
        display_name='Heavy Metal — Geomatrix',
        rc2_dir=RC2_ROOT / 'Heavy Metal - Geomatrix (JP)',
        # Audit: 1ST_READ.BIN has real cp932 strings; LOBBY*.TEX carry text-in-
        # textures (handled via Tab 2). MESSAGE.INI was modified.
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI'],
        deny_list=COMMON_DENY,
        product_code='T1246M', detect_label='HEAVY METAL',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='jojo',
        display_name="JoJo's Bizarre Adventure",
        rc2_dir=RC2_ROOT / 'JoJo_s Bizarre Adventure[ (JP)',
        # Audit: 1ST_READ.BIN is unchanged vs baseline. Real string work lives
        # in the per-character archives 97_DASH.BIN / 95_JOJO.BIN.
        scan_targets=['97_DASH.BIN', '95_JOJO.BIN'],
        deny_list=COMMON_DENY,
        product_code='T1231M', detect_label='JOJO',
        notes_kind='std',
    ),
    GameConfig(
        slug='marvel_vs_capcom_2',
        display_name='Marvel vs. Capcom 2 — New Age of Heroes',
        rc2_dir=RC2_ROOT / 'Marvel vs. Capcom 2 - New Age of Heroes (JP)',
        # Audit: 1ST_READ + per-character PL*_DAT.BIN + EFKYTEX.BIN.
        scan_targets=[
            '1ST_READ.BIN',
            'PL31_DAT.BIN', 'PL04_DAT.BIN', 'PL17_DAT.BIN',
            'EFKYTEX.BIN',
        ],
        deny_list=COMMON_DENY,
        product_code='T1215M', detect_label='MARVEL VS. CAPCOM 2',
        notes_kind='std',
    ),
    GameConfig(
        slug='net_de_tennis',
        display_name='Net de Tennis',
        rc2_dir=RC2_ROOT / 'Net de Tennis (JP)',
        # Audit: standard DP3 pair carries the strings; SLW work (TITLE/NETWK_B/
        # SOFTKEY) is texture-side, handled via Tab 2.
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI'],
        deny_list=COMMON_DENY,
        product_code='T1234M', detect_label='NET DE TENNIS',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='power_stone_2',
        display_name='Power Stone 2',
        rc2_dir=RC2_ROOT / 'Power Stone 2 (JP)',
        # Audit: 1ST_READ + connect-screen menu BINs carry the strings.
        scan_targets=['1ST_READ.BIN', 'DM04_CONNECT.BIN'],
        deny_list=COMMON_DENY,
        product_code='T1218M', detect_label='POWER STONE 2',
        notes_kind='std',
    ),
    GameConfig(
        slug='project_justice',
        display_name='Project Justice',
        rc2_dir=RC2_ROOT / 'Project Justice (JP)',
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI'],
        deny_list=COMMON_DENY,
        product_code='T1221M', detect_label='MOERO JUSTICE GAKUEN',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='sf3_3rd_strike',
        display_name='Street Fighter III 3rd Strike',
        rc2_dir=RC2_ROOT / 'Street Fighter III 3rd Strike - Fight for the Future (JP)',
        # Audit: per-character PLAYER/PL*.BIN files + OPENING/BG20.BIN carry
        # the bulk of the strings, plus the DP3 pair.
        scan_targets=[
            '1ST_READ.BIN', 'DPETC/MESSAGE.INI',
            'PLAYER/PL00.BIN', 'PLAYER/PL02.BIN', 'PLAYER/PL09.BIN',
            'PLAYER/PL11.BIN', 'PLAYER/PL17.BIN', 'PLAYER/PL18.BIN',
            'PLAYER/PL19.BIN', 'PLAYER/PL20.BIN',
            'OPENING/BG20.BIN',
        ],
        deny_list=COMMON_DENY,
        product_code='T1209M', detect_label='STREET FIGHTER 3 3RD STRIKE',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='sfz3_ms',
        display_name='Street Fighter Zero 3 (Matching Service)',
        rc2_dir=RC2_ROOT / 'Street Fighter Zero 3  for Matching Service (JP)',
        # Audit: 1ST_READ + DPETC/MESSAGE.INI were UNCHANGED by the campaign.
        # All translatable content is in storyboard PAC/PVR textures handled
        # via Tab 2. Scan_targets kept minimal so the Text Grid doesn't lie.
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI'],
        deny_list=COMMON_DENY,
        product_code='T1230M', detect_label='STREET FIGHTER ZERO3',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='spfii_ms',
        display_name='Super Puzzle Fighter IIX (Matching Service)',
        rc2_dir=RC2_ROOT / 'Super Puzzle Fighter IIX for Matching Service (JP)',
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI'],
        deny_list=COMMON_DENY,
        product_code='T1250M', detect_label='SUPER PUZZLE FIGHTER2X',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='ssfiix_ms',
        display_name='Super Street Fighter IIX (Matching Service)',
        rc2_dir=RC2_ROOT / 'Super Street Fighter IIX for Matching Service - Grand Master Challenge (JP)',
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI'],
        deny_list=COMMON_DENY,
        product_code='T1236M', detect_label='SUPER STREET FIGHTER 2X',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='taisen_net_gimmick',
        display_name='Taisen Net Gimmick — Capcom & Psikyo All Stars',
        rc2_dir=RC2_ROOT / 'Taisen Net Gimmick - Capcom & Psikyo All Stars (JP)',
        # Audit: 1ST_READ was UNCHANGED; the real string container is the
        # 8.5 MB RESOURCE.BIN. Keep DPETC/MESSAGE.INI for the standard DP3
        # popup strings.
        scan_targets=['RESOURCE.BIN', 'DPETC/MESSAGE.INI'],
        deny_list=COMMON_DENY,
        product_code='T1248M', detect_label='NET GIMMICK',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='tech_romancer_ms',
        display_name='Tech Romancer (Matching Service)',
        rc2_dir=RC2_ROOT / 'Tech Romancer for Matching Service (JP)',
        # Audit: 1ST_READ has the in-game strings; demo-cutscene PZZs
        # (OP_DEMO, TTD_ILL_O) are LZSS-compressed and handled via Tab 2.
        scan_targets=['1ST_READ.BIN', 'DPETC/MESSAGE.INI'],
        deny_list=COMMON_DENY,
        product_code='T1232M', detect_label='KIKAIOH',
        notes_kind='dp3',
    ),
    GameConfig(
        slug='vampire_chronicle_ms',
        display_name='Vampire Chronicle (Matching Service)',
        rc2_dir=RC2_ROOT / 'Vampire Chronicle for Matching Service (JP)',
        # Audit: per-character PL0C/PL08.BIN carry character-specific text
        # alongside the DP3 pair.
        scan_targets=[
            '1ST_READ.BIN', 'DPETC/MESSAGE.INI',
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
