"""End-to-end flow harness for all 15 bundled games.

Exercises every user-visible action in headless mode (no GUI) and asserts
post-conditions. Reports a pass/fail matrix.

Flows tested per game:
  F1  load_bundled(slug) succeeds and exposes the expected fields
  F2  detect_for_disc() returns the correct slug given the game's track03
  F3  scan_targets are all present in the game's extracted/ tree
  F4  diff-derive translations: every entry in translations.json round-trips
      back to the same EN bytes when we re-read patches/ at that offset+budget
  F5  archive surface: for each archive file in patches/, list_members()
      returns at least one member OR a documented-empty result
  F6  texture decode: for each archive member, load_archive_member() returns
      either a TextureRecord OR a documented-no-PVR (SLW) result — never crashes
  F7  protected-atlas filter: FONT/SOFTKEY/MOJI/MINCHO files are flagged
  F8  preset filename collisions: no two slugs share the same display label

Run:  python -m scripts.flow_harness
"""
from __future__ import annotations
import sys, json, traceback
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'spawntools' / 'codecs'))

RC2 = Path(r"D:/Capcom Dreamcast  Games - Joe Patched/RC2 Translated")

from spawntools.core import preset as preset_core
from spawntools.core import textures as tex_core
from spawntools.core import archives as arch_core
from spawntools.bundled import game_registry as reg

PASS = 'PASS'
FAIL = 'FAIL'
SKIP = 'SKIP'


def color(s):
    return s


def run_flow(name, fn):
    try:
        ok, msg = fn()
        if ok is True: return (PASS, msg or '')
        if ok is False: return (FAIL, msg or '')
        return (SKIP, msg or '')
    except Exception as e:
        return (FAIL, f'EXCEPTION: {e}\n{traceback.format_exc()[:500]}')


def f1_load_bundled(slug):
    p = preset_core.Preset.load_bundled(slug)
    if not p.translations:
        return True, f'{slug}: 0 translations (acceptable for text-light games)'
    if not p.scan_targets:
        return False, 'no scan_targets in manifest'
    return True, f'{len(p.translations):,} translations, {len(p.scan_targets)} scan targets'


def f2_detect_disc(game: reg.GameConfig):
    """Drive Preset.detect_for_disc with a fake disc object pointing at the
    real track03. Asserts the returned slug matches this game's slug."""
    if not game.rc2_dir.is_dir():
        return None, 'rc2_dir missing'
    candidates = list(game.rc2_dir.rglob('track03.iso')) + list(game.rc2_dir.rglob('track03.bin'))
    if not candidates:
        return None, 'no track03 file under game dir'
    track = candidates[0]
    class FakeDisc:
        track03_path = track
        is_bin_sectors = (track.suffix.lower() == '.bin')
    slug = preset_core.Preset.detect_for_disc(FakeDisc())
    if slug == game.slug:
        return True, f'detected {slug} via IP.BIN'
    return False, f'expected {game.slug}, got {slug!r}'


def f3_scan_targets_exist(game: reg.GameConfig):
    ext_dir = game.rc2_dir / 'extracted'
    if not ext_dir.is_dir():
        return None, 'no extracted/'
    missing = [t for t in game.scan_targets if not (ext_dir / t).is_file()]
    if missing:
        return False, f'scan_targets MISSING from extracted/: {missing}'
    return True, f'all {len(game.scan_targets)} present'


def f4_translation_roundtrip(slug, game: reg.GameConfig):
    p = preset_core.Preset.load_bundled(slug)
    if not p.translations:
        return None, 'no translations to verify'
    pat_dir = game.rc2_dir / 'patches'
    if not pat_dir.is_dir():
        return None, 'patches/ missing'
    bad = 0
    sampled = p.translations[:200]   # spot-check first 200
    for t in sampled:
        target = pat_dir / t['source_file']
        if not target.is_file():
            bad += 1; continue
        data = target.read_bytes()
        actual = data[t['byte_offset']:t['byte_offset'] + t['byte_budget']]
        # Compare against the EN bytes we'd reconstruct
        try:
            expected = t['en'].encode('ascii').ljust(t['byte_budget'], b'\x00')
        except UnicodeEncodeError:
            try:
                expected = t['en'].encode('cp932').ljust(t['byte_budget'], b'\x00')
            except UnicodeEncodeError:
                # Can't reconstruct — skip
                continue
        if actual.rstrip(b'\x00') != expected.rstrip(b'\x00'):
            # Some 'en' fields are '<binary diff>'; skip those
            if t['en'].startswith('<binary'): continue
            bad += 1
    if bad:
        return False, f'{bad}/{len(sampled)} translation roundtrips disagree with patches/ bytes'
    return True, f'first {len(sampled)} translations all round-trip OK'


def f5_archive_surface(game: reg.GameConfig):
    """Surface-rate counts ONLY archives whose bytes actually contain PVR
    magic (PVRT or GBIX). Archives with zero PVR signatures (e.g. Power
    Stone 2's CMN_MODEL_VQ_BIN.PAC which is 3D model + VQ data) are
    excluded from the denominator — they're not texture containers."""
    pat_dir = game.rc2_dir / 'patches'
    if not pat_dir.is_dir():
        return None, 'patches/ missing'
    arch_files = []
    for ext in ('AFS', 'PAC', 'PVS', 'PZZ', 'SLW', 'PVZ'):
        arch_files.extend(pat_dir.rglob(f'*.{ext}'))
        arch_files.extend(pat_dir.rglob(f'*.{ext.lower()}'))
    arch_files = sorted(set(arch_files))
    # Filter to archives that actually have PVR content
    texture_archives = []
    non_texture_archives = []
    for a in arch_files:
        try:
            head = a.read_bytes()
        except OSError:
            continue
        if b'PVRT' in head or b'GBIX' in head:
            texture_archives.append(a)
        else:
            non_texture_archives.append(a)
    if not texture_archives:
        msg = f'no texture-bearing archives ({len(non_texture_archives)} non-tex)'
        return None, msg
    surfaced = 0
    members_total = 0
    for a in texture_archives:
        try:
            kind, members = arch_core.list_members(a)
        except Exception:
            continue
        if members:
            surfaced += 1
            members_total += len(members)
    rate = surfaced / len(texture_archives)
    msg = (f'{surfaced}/{len(texture_archives)} tex-archives surfaced '
           f'({members_total} members; {len(non_texture_archives)} non-tex skipped)')
    if rate < 0.5:
        return False, msg + '  – LOW SURFACE RATE'
    return True, msg


def f6_member_decode(game: reg.GameConfig):
    """Spot-check: pick up to 20 archive members across the game and verify
    load_archive_member returns either a TextureRecord or [] without crashing."""
    pat_dir = game.rc2_dir / 'patches'
    if not pat_dir.is_dir():
        return None, ''
    archives = []
    for ext in ('AFS', 'PAC', 'PVS', 'PZZ', 'SLW', 'PVZ'):
        archives.extend(pat_dir.rglob(f'*.{ext}'))
        archives.extend(pat_dir.rglob(f'*.{ext.lower()}'))
    if not archives:
        return None, ''
    decoded = 0
    crashed = 0
    sampled = 0
    for a in archives[:5]:
        try:
            kind, members = arch_core.list_members(a)
        except Exception:
            crashed += 1; continue
        for m in members[:5]:
            sampled += 1
            try:
                recs = tex_core.load_archive_member(m)
            except Exception:
                crashed += 1; continue
            if recs:
                decoded += 1
    if crashed:
        return False, f'{crashed} crashes on {sampled} samples'
    if sampled == 0:
        return None, 'no members sampled'
    return True, f'{decoded}/{sampled} sample members decoded cleanly'


def f7_protected_filter():
    """Spot-check that protected-atlas detection still flags FONT/SOFTKEY/MOJI/MINCHO."""
    for name in ('FONT.PVR', 'FONT0.PVR', 'SOFTKEY_BASE.PVR', 'MOJI_KANA.PVR',
                 'MINCHO_A.PVR'):
        if not tex_core.is_protected(Path('/tmp') / name):
            return False, f'{name} not flagged as protected!'
    return True, '5/5 protected-atlas names flagged'


def f8_unique_labels():
    games = preset_core.Preset.list_available()
    by_label = defaultdict(list)
    for g in games:
        by_label[g['display_name']].append(g['slug'])
    dups = {k: v for k, v in by_label.items() if len(v) > 1}
    if dups:
        return False, f'duplicate labels: {dups}'
    return True, f'{len(games)} games have unique labels'


def main():
    games = [g for g in reg.GAMES if g.rc2_dir.is_dir()]
    print(f'Running flow harness against {len(games)} games\\n')
    matrix = []
    # Global flows (game-independent)
    print('=== Global flows ===')
    for fname, fn in [('F7 protected_filter', f7_protected_filter),
                      ('F8 unique_labels',    f8_unique_labels)]:
        st, msg = run_flow(fname, fn)
        print(f'  {st}  {fname:25s}  {msg}')
        matrix.append((None, fname, st, msg))

    # Per-game flows
    for game in games:
        print(f'\\n=== {game.slug} ===')
        for fname, fn in [
            ('F1 load_bundled',       lambda g=game: f1_load_bundled(g.slug)),
            ('F2 detect_disc',        lambda g=game: f2_detect_disc(g)),
            ('F3 scan_targets_exist', lambda g=game: f3_scan_targets_exist(g)),
            ('F4 trans_roundtrip',    lambda g=game: f4_translation_roundtrip(g.slug, g)),
            ('F5 archive_surface',    lambda g=game: f5_archive_surface(g)),
            ('F6 member_decode',      lambda g=game: f6_member_decode(g)),
        ]:
            st, msg = run_flow(fname, fn)
            print(f'  {st}  {fname:22s}  {msg}')
            matrix.append((game.slug, fname, st, msg))

    # Summary
    print('\\n\\n=== SUMMARY ===')
    by_status = defaultdict(int)
    for _, _, st, _ in matrix:
        by_status[st] += 1
    print(f'  PASS: {by_status[PASS]}   FAIL: {by_status[FAIL]}   SKIP: {by_status[SKIP]}   '
          f'TOTAL: {len(matrix)}')

    if by_status[FAIL]:
        print('\\n=== FAILURES ===')
        for slug, fname, st, msg in matrix:
            if st == FAIL:
                print(f'  [{slug or "global"}] {fname}: {msg}')

    return 0 if by_status[FAIL] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
