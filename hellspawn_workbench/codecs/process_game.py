"""Unified per-game translation pipeline for Dreamcast Capcom games.

For each game folder under RC2/, this script:
  1. Locates disc.gdi + tracks (handles .iso or .bin track03)
  2. Extracts the filesystem via the Dreamcast-aware ISO9660 walker
  3. Surveys file types (counts of .TEX, .BIN, .PVR, etc.)
  4. Scans binaries for Shift-JIS UI strings (full-width Latin aware)
  5. Applies the JP->EN dictionary in safe null-boundary mode
  6. Hot-swaps any JP/US texture pairs found (CFGJP/CFGUS etc.)
  7. Transplants DPETC/MESSAGE.INI from CvS Pro EN if game uses DreamPipe
  8. Builds a new track03 with all patches applied in-place
  9. Writes a per-game report

Usage:
    python process_game.py "Net de Tennis (JP)"
    python process_game.py --all
"""
import os, sys, io, struct, shutil, json, re, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(__file__))
from jp_en_dict import DICT, by_length_desc

RC2_ROOT = r"D:\Capcom Dreamcast  Games - Joe Patched\RC2"
OUT_ROOT = r"D:\Capcom Dreamcast  Games - Joe Patched\RC2 Translated"
CVSPRO_EN_MSG = r"D:\Capcom Dreamcast  Games - Joe Patched\translated\cvspro_extract\track03_files\DPETC\MESSAGE.INI"

LBA_OFFSET = 45000
BLOCK = 2048

SKIP_BIN_EXTS = {'.PVR','.PVP','.MLT','.SFD','.ADX','.MDL','.MOB','.TEX',
                 '.SMD','.SDF','.RMP','.DAT','.FON','.DRV','.GIF'}


def find_disc_files(game_dir):
    """Recursively find disc.gdi and tracks; return (gdi, track01, track02, track03, is_bin)."""
    for root, dirs, files in os.walk(game_dir):
        if 'disc.gdi' in files:
            base = root
            gdi = os.path.join(base, 'disc.gdi')
            t01 = next((os.path.join(base, f) for f in files
                        if f.startswith('track01.') and f.endswith(('.iso','.bin'))), None)
            t02 = os.path.join(base, 'track02.raw') if 'track02.raw' in files else None
            t03_iso = os.path.join(base, 'track03.iso') if 'track03.iso' in files else None
            t03_bin = os.path.join(base, 'track03.bin') if 'track03.bin' in files else None
            is_bin = t03_bin is not None and t03_iso is None
            t03 = t03_bin if is_bin else t03_iso
            return gdi, t01, t02, t03, is_bin
    return None, None, None, None, False


def read_lba_iso(f, lba, nbytes):
    f.seek((lba - LBA_OFFSET) * BLOCK)
    return f.read(nbytes)


def read_lba_bin(f, lba, nbytes):
    out = bytearray()
    left = nbytes
    sector = lba - LBA_OFFSET
    while left > 0:
        f.seek(sector * 2352 + 16)
        want = min(2048, left)
        out.extend(f.read(want))
        left -= want
        sector += 1
    return bytes(out)


def parse_dir(f, ext_lba, sz, reader):
    data = reader(f, ext_lba, sz)
    pos = 0
    out = []
    while pos < len(data):
        rl = data[pos]
        if rl == 0:
            pos = ((pos // BLOCK) + 1) * BLOCK
            continue
        rec = data[pos:pos+rl]
        ext = struct.unpack('<I', rec[2:6])[0]
        size = struct.unpack('<I', rec[10:14])[0]
        flags = rec[25]
        nlen = rec[32]
        name = rec[33:33+nlen]
        is_dir = bool(flags & 0x02)
        if name not in (b'\x00', b'\x01'):
            ns = name.split(b';')[0].decode('ascii', errors='replace')
            out.append((ns, ext, size, is_dir))
        pos += rl
    return out


def walk(f, ext_lba, sz, path, reader):
    for name, ext, size, is_dir in parse_dir(f, ext_lba, sz, reader):
        rel = path + '/' + name
        if is_dir:
            yield from walk(f, ext, size, rel, reader)
        else:
            yield rel, ext, size


def extract_filesystem(track03, is_bin, out_dir):
    reader = read_lba_bin if is_bin else read_lba_iso
    with open(track03, 'rb') as f:
        if is_bin:
            pvd = read_lba_bin(f, 45016, 2048)
        else:
            f.seek(16 * BLOCK)
            pvd = f.read(BLOCK)
        if pvd[1:6] != b'CD001':
            return None, 0, 0
        root_ext = struct.unpack('<I', pvd[158:162])[0]
        root_sz = struct.unpack('<I', pvd[166:170])[0]
        count, total = 0, 0
        for rel, ext, size in walk(f, root_ext, root_sz, '', reader):
            out_path = out_dir + rel.replace('/', os.sep)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            data = reader(f, ext, size)
            with open(out_path, 'wb') as g:
                g.write(data)
            count += 1
            total += size
    return True, count, total


def survey(extracted_dir):
    """Count file types."""
    ext_counts = {}
    for root, dirs, files in os.walk(extracted_dir):
        for f in files:
            e = os.path.splitext(f)[1].upper()
            ext_counts[e] = ext_counts.get(e, 0) + 1
    return ext_counts


def scan_jp_strings(extracted_dir):
    """Return total JP-CJK strings >= 4 chars across all non-asset files."""
    def is_lead(b): return (0x81<=b<=0x9F) or (0xE0<=b<=0xFC)
    def is_trail(b): return (0x40<=b<=0x7E) or (0x80<=b<=0xFC)
    total = 0
    by_file = {}
    for root, dirs, files in os.walk(extracted_dir):
        for f in files:
            if os.path.splitext(f)[1].upper() in SKIP_BIN_EXTS:
                continue
            path = os.path.join(root, f)
            try:
                data = open(path, 'rb').read()
            except Exception:
                continue
            cnt = 0
            i = 0
            while i < len(data):
                if not is_lead(data[i]):
                    i += 1; continue
                start = i
                run = bytearray()
                while i < len(data):
                    b = data[i]
                    if is_lead(b) and i+1 < len(data) and is_trail(data[i+1]):
                        run.extend(data[i:i+2]); i += 2
                    elif 0x20 <= b <= 0x7E:
                        run.append(b); i += 1
                    else:
                        break
                if len(run) >= 8:
                    try:
                        s = run.decode('shift_jis')
                        if any(0x3040 <= ord(c) <= 0x9FFF for c in s):
                            cnt += 1
                    except UnicodeDecodeError:
                        pass
                i = max(start+1, i)
            if cnt:
                total += cnt
                by_file[os.path.relpath(path, extracted_dir)] = cnt
    return total, by_file


def safe_apply_dict(extracted_dir, output_dir, dict_items):
    """Apply dict in safe null-bounded mode. Writes modified files to output_dir."""
    grand_total = 0
    files_touched = 0
    for root, dirs, files in os.walk(extracted_dir):
        for f in files:
            ext = os.path.splitext(f)[1].upper()
            if ext in SKIP_BIN_EXTS:
                continue
            src = os.path.join(root, f)
            rel = os.path.relpath(src, extracted_dir)
            try:
                buf = bytearray(open(src, 'rb').read())
            except Exception:
                continue
            count = 0
            for jp, en in dict_items:
                try:
                    jp_b = jp.encode('shift_jis')
                except UnicodeEncodeError:
                    continue
                en_b = en.encode('latin-1', errors='replace')
                if len(en_b) > len(jp_b):
                    en_b = en_b[:len(jp_b)]
                replacement = en_b + b'\x00' * (len(jp_b) - len(en_b))
                off = 0
                L = len(buf)
                while True:
                    idx = buf.find(jp_b, off)
                    if idx < 0:
                        break
                    if idx > 0 and buf[idx-1] != 0:
                        off = idx + 1; continue
                    end = idx + len(jp_b)
                    if end < L and buf[end] != 0:
                        off = idx + 1; continue
                    buf[idx:end] = replacement
                    count += 1
                    off = end
            if count > 0:
                dst = os.path.join(output_dir, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                open(dst, 'wb').write(bytes(buf))
                grand_total += count
                files_touched += 1
    return grand_total, files_touched


def hot_swap_jp_us(extracted_dir, output_dir):
    """Find JP/US texture pairs (XXXJP/XXXUS or XXX/XXXU) and hot-swap."""
    swaps = []
    files_in = os.listdir(extracted_dir)
    # Identify pairs: foo.TEX + fooU.TEX, or fooJP.TEX + fooUS.TEX
    for fn in files_in:
        upper = fn.upper()
        if not upper.endswith('.TEX'):
            continue
        base = upper[:-4]  # name without .TEX
        # JP/US pair
        if base.endswith('JP'):
            us = base[:-2] + 'US'
            us_file = next((f for f in files_in if f.upper() == us + '.TEX'), None)
            if us_file:
                jp_path = os.path.join(extracted_dir, fn)
                us_path = os.path.join(extracted_dir, us_file)
                if os.path.getsize(jp_path) == os.path.getsize(us_path):
                    out_path = os.path.join(output_dir, fn)
                    shutil.copyfile(us_path, out_path)
                    swaps.append(f"{fn} <- {us_file}")
        # X.TEX + XU.TEX pair (e.g. WARNING <- WARNINGU)
        else:
            u_variant = next((f for f in files_in
                              if f.upper() == base + 'U.TEX'), None)
            if u_variant:
                jp_path = os.path.join(extracted_dir, fn)
                u_path = os.path.join(extracted_dir, u_variant)
                if os.path.getsize(jp_path) == os.path.getsize(u_path):
                    out_path = os.path.join(output_dir, fn)
                    shutil.copyfile(u_path, out_path)
                    swaps.append(f"{fn} <- {u_variant}")
    return swaps


def transplant_message_ini(extracted_dir, output_dir):
    """If game has DPETC/MESSAGE.INI, transplant CvS Pro EN entries."""
    target = os.path.join(extracted_dir, 'DPETC', 'MESSAGE.INI')
    if not os.path.exists(target):
        return 0
    if not os.path.exists(CVSPRO_EN_MSG):
        return 0
    pat = re.compile(rb'^(\d+)="(.*)"\s*$', re.S)
    def parse(p):
        with open(p, 'rb') as f:
            raw = f.read()
        entries = []
        for L in raw.splitlines(keepends=True):
            m = pat.match(L)
            if m:
                entries.append((L, m.group(1).decode('ascii'), m.group(2)))
            else:
                entries.append((L, None, None))
        return entries, raw
    jp_entries, jp_raw = parse(target)
    en_entries, _ = parse(CVSPRO_EN_MSG)
    en_map = {k: v for raw, k, v in en_entries if k is not None}
    out_lines = []
    swapped = 0
    for raw, k, v in jp_entries:
        if k is None or k not in en_map:
            out_lines.append(raw); continue
        en_val = en_map[k]
        orig_no_lf = raw.rstrip(b'\r\n')
        lf = raw[len(orig_no_lf):]
        prefix = f'{k}="'.encode('ascii')
        suffix = b'"'
        budget = len(orig_no_lf) - len(prefix) - len(suffix)
        if len(en_val) > budget:
            # truncate at word
            en_val = en_val[:budget]
            for i in range(len(en_val)-1, 0, -1):
                if en_val[i:i+1] in (b' ', b'.', b',', b';', b':', b'!', b'?'):
                    en_val = en_val[:i]; break
        pad = budget - len(en_val)
        new_line = prefix + en_val + b' ' * pad + suffix + lf
        out_lines.append(new_line)
        swapped += 1
    new_data = b''.join(out_lines)
    orig_size = os.path.getsize(target)
    if len(new_data) > orig_size:
        new_data = new_data[:orig_size]
    elif len(new_data) < orig_size:
        new_data = new_data + b'\x00' * (orig_size - len(new_data))
    out_path = os.path.join(output_dir, 'DPETC', 'MESSAGE.INI')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    open(out_path, 'wb').write(new_data)
    return swapped


def patch_iso(src_track, is_bin, out_track, output_dir):
    """Copy track + patch every file in output_dir back at its original LBA."""
    shutil.copy2(src_track, out_track)
    sec_size = 2352 if is_bin else 2048
    data_off = 16 if is_bin else 0
    patched = 0
    reader = read_lba_bin if is_bin else read_lba_iso
    with open(out_track, 'r+b') as f:
        if is_bin:
            pvd = read_lba_bin(f, 45016, 2048)
        else:
            f.seek(16 * BLOCK)
            pvd = f.read(BLOCK)
        if pvd[1:6] != b'CD001':
            return 0
        root_ext = struct.unpack('<I', pvd[158:162])[0]
        root_sz = struct.unpack('<I', pvd[166:170])[0]
        # Build map of files -> (ext, size)
        file_map = {}
        for rel, ext, size in walk(f, root_ext, root_sz, '', reader):
            file_map[rel.lstrip('/').replace('/', os.sep).upper()] = (ext, size)
        # Walk output_dir
        for root, dirs, files in os.walk(output_dir):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, output_dir).replace('/', os.sep).upper()
                if rel not in file_map:
                    continue
                ext, orig_size = file_map[rel]
                new_data = open(full, 'rb').read()
                if len(new_data) > orig_size:
                    new_data = new_data[:orig_size]
                # Write sector-by-sector
                sector = ext - LBA_OFFSET
                pos = 0
                while pos < len(new_data):
                    chunk = new_data[pos:pos+2048]
                    if is_bin:
                        f.seek(sector * 2352 + 16)
                    else:
                        f.seek(sector * 2048)
                    f.write(chunk)
                    pos += 2048
                    sector += 1
                # zero-pad to original size
                if len(new_data) < orig_size:
                    pad = orig_size - len(new_data)
                    if is_bin:
                        f.seek((ext + (len(new_data)+2047)//2048 - 45000) * 2352 + 16)
                    else:
                        f.seek((ext + (len(new_data)+2047)//2048 - 45000) * 2048)
                    f.write(b'\x00' * pad)
                patched += 1
    return patched


def process_game(game_name, force=False):
    src_dir = os.path.join(RC2_ROOT, game_name)
    out_dir = os.path.join(OUT_ROOT, game_name)
    extracted = os.path.join(out_dir, 'extracted')
    patches = os.path.join(out_dir, 'patches')
    disc_out = os.path.join(out_dir, 'disc')
    report_path = os.path.join(out_dir, 'report.json')

    if os.path.exists(report_path) and not force:
        print(f"[SKIP] {game_name}  (report.json exists)")
        return

    os.makedirs(extracted, exist_ok=True)
    os.makedirs(patches, exist_ok=True)
    os.makedirs(disc_out, exist_ok=True)

    gdi, t01, t02, t03, is_bin = find_disc_files(src_dir)
    if not t03:
        print(f"[FAIL] {game_name}: no track03 found")
        return

    report = {'game': game_name, 'track_format': 'BIN' if is_bin else 'ISO'}
    print(f"\n=== {game_name} === ({report['track_format']} track)")

    # 1. Extract
    if not os.listdir(extracted):
        print(f"  extracting...")
        ok, n, total = extract_filesystem(t03, is_bin, extracted)
        report['extracted'] = {'ok': ok, 'files': n, 'mb': round(total/1e6, 1)}
        print(f"    {n} files, {total/1e6:.1f} MB")
    else:
        print(f"  already extracted, skipping")

    # 2. Survey
    survey_counts = survey(extracted)
    report['survey'] = dict(sorted(survey_counts.items(), key=lambda x: -x[1])[:20])
    top = list(report['survey'].items())[:5]
    print(f"  top file types: {top}")

    # 3. Scan JP
    print(f"  scanning JP strings...")
    jp_total, jp_by_file = scan_jp_strings(extracted)
    report['jp_strings'] = {'total': jp_total, 'top_files': dict(sorted(jp_by_file.items(), key=lambda x: -x[1])[:15])}
    print(f"    {jp_total} JP-CJK strings >= 4 chars detected")

    # 4. Apply dictionary
    print(f"  applying JP->EN dictionary...")
    items = list(by_length_desc())
    replaced, touched = safe_apply_dict(extracted, patches, items)
    report['dict_replacements'] = {'count': replaced, 'files': touched}
    print(f"    {replaced} replacements across {touched} files")

    # 5. Hot-swap JP/US texture pairs
    swaps = hot_swap_jp_us(extracted, patches)
    report['hot_swaps'] = swaps
    if swaps:
        print(f"  hot-swapped {len(swaps)} JP/US texture pair(s)")

    # 6. Transplant MESSAGE.INI (DreamPipe games)
    msg_swap = transplant_message_ini(extracted, patches)
    report['message_ini_swap'] = msg_swap
    if msg_swap:
        print(f"  transplanted {msg_swap} CvS Pro EN MESSAGE.INI entries")

    # 7. Patch ISO
    print(f"  patching track03 into {disc_out}...")
    out_t03 = os.path.join(disc_out, os.path.basename(t03))
    patched = patch_iso(t03, is_bin, out_t03, patches)
    report['iso_patches'] = patched
    print(f"    {patched} files patched into disc")

    # 8. Copy gdi + other tracks
    for src in (gdi, t01, t02):
        if src and os.path.exists(src):
            dst = os.path.join(disc_out, os.path.basename(src))
            if not os.path.exists(dst):
                shutil.copy2(src, dst)

    # Save report
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"  done. report -> {report_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('game', nargs='?')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()

    if args.all:
        for game in sorted(os.listdir(RC2_ROOT)):
            game_dir = os.path.join(RC2_ROOT, game)
            if not os.path.isdir(game_dir):
                continue
            if 'spawn' in game.lower():
                continue  # already done in spawn_jp project
            try:
                process_game(game, force=args.force)
            except Exception as e:
                print(f"[ERROR] {game}: {e}")
    elif args.game:
        process_game(args.game, force=args.force)


if __name__ == '__main__':
    main()
