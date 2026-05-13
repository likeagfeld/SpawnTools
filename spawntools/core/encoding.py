"""Text encoding for Capcom Dreamcast strings.

Spawn's strings are stored as Shift-JIS (Microsoft's variant: cp932). That's
the BASE encoding. On top of that, the game's renderer also handles:

  1. FULL-WIDTH LATIN — codepoints distinct from ASCII.
     'Ｉ Ｄ ０－９ Ｃ Ｏ Ｍ ＋' are 2-byte cp932 sequences.
     The string 'カプコンＩＤ' uses full-width 'Ｉ', NOT ASCII 'I'.
     `Spawn's '1人+COM' is actually '１人＋ＣＯＭ'` — every char full-width.

  2. CONTROL CODES — game-specific 1- or 2-byte escape sequences:
     • '$0'..'$9'   — color (DP3 MESSAGE.INI standard)
     • <font color="#XXXXXX">..</font> tag pairs in MESSAGE.INI VALUE text
     • <br>          — line break
     • single-byte button-icon glyphs (varies per game — Spawn uses font sheet)

  3. LINE-BREAK CALC — for redraw scripts. The renderer wraps text at a
     game-supplied pixel width. We approximate by measuring with PIL's font
     metrics. (For Spawn LOBBY texture redraws this is critical — wrap = on,
     budget per-line ~6 ASCII chars in some narrow strips.)

WARNING — DO NOT use `data.replace(b'\\x88\\xCA', b'th')` style bulk replace
across whole binaries. The bytes 0x88 0xCA (位) occur naturally in CODE/DATA
as well as strings. Spawn v20 bricked the disc this way. See `apply_safe_*`
helpers below.

The Workbench does NOT implement a generic .tbl mapper because Spawn doesn't
use one (everything is cp932-native). If a future game does, just wire it
into `decode_string`/`encode_string` here.
"""
from __future__ import annotations
import re
from dataclasses import dataclass


# ---------- full-width Latin helpers ----------

# These maps cover the most common Capcom-game full-width chars. Add as we
# encounter more.
ASCII_TO_FULLWIDTH = {
    '0': '０', '1': '１', '2': '２', '3': '３', '4': '４',
    '5': '５', '6': '６', '7': '７', '8': '８', '9': '９',
    'A': 'Ａ', 'B': 'Ｂ', 'C': 'Ｃ', 'D': 'Ｄ', 'E': 'Ｅ',
    'F': 'Ｆ', 'G': 'Ｇ', 'H': 'Ｈ', 'I': 'Ｉ', 'J': 'Ｊ',
    'K': 'Ｋ', 'L': 'Ｌ', 'M': 'Ｍ', 'N': 'Ｎ', 'O': 'Ｏ',
    'P': 'Ｐ', 'Q': 'Ｑ', 'R': 'Ｒ', 'S': 'Ｓ', 'T': 'Ｔ',
    'U': 'Ｕ', 'V': 'Ｖ', 'W': 'Ｗ', 'X': 'Ｘ', 'Y': 'Ｙ',
    'Z': 'Ｚ',
    '+': '＋', '-': '－', '/': '／', ':': '：', '.': '．',
    ' ': '　',
}
FULLWIDTH_TO_ASCII = {v: k for k, v in ASCII_TO_FULLWIDTH.items()}


def to_fullwidth(s: str) -> str:
    """Convert an ASCII string to full-width Latin equivalents.
    Used when the game's display routine expects full-width (e.g., Spawn
    'NETファイル' header where 'NET' is actually 'ＮＥＴ')."""
    return ''.join(ASCII_TO_FULLWIDTH.get(c, c) for c in s)


def to_ascii(s: str) -> str:
    """Inverse of to_fullwidth."""
    return ''.join(FULLWIDTH_TO_ASCII.get(c, c) for c in s)


# ---------- cp932 byte-aware utilities ----------

def cp932_len(s: str) -> int:
    """Byte length when encoded as cp932. The byte BUDGET for translations."""
    try:
        return len(s.encode('cp932', errors='strict'))
    except UnicodeEncodeError:
        # If a char doesn't encode in cp932, count it as 2 bytes (worst case)
        # so the meter shows red.
        return len(s.encode('cp932', errors='replace'))


def cp932_fits(s: str, budget: int) -> bool:
    return cp932_len(s) <= budget


def pad_with_nulls(s: str, budget: int) -> bytes:
    """Encode `s` in cp932 and pad with null bytes to exactly `budget`.
    Raises if `s` is already longer than the budget."""
    b = s.encode('cp932', errors='strict')
    if len(b) > budget:
        raise ValueError(f'{s!r} is {len(b)} bytes > budget {budget}')
    return b + b'\x00' * (budget - len(b))


# ---------- Capcom control codes ----------

# DP3 MESSAGE.INI uses these HTML-ish tag pairs. They're literal ASCII in the
# string, the runtime parses them at render time. We just count them as
# byte-budget overhead.
COLOR_TAG_RE = re.compile(r'<font\s+color="?#[0-9A-Fa-f]{6}"?>(.*?)</font>', re.DOTALL)
BR_RE = re.compile(r'<br>')
ANY_TAG_RE = re.compile(r'<[^>]+>')


def strip_color_tags(s: str) -> str:
    """Remove <font color=...>...</font> markup, keep inner text. For
    pixel-width calc and visual preview."""
    return COLOR_TAG_RE.sub(lambda m: m.group(1), s)


def strip_all_tags(s: str) -> str:
    """Remove every HTML-ish tag for plain-text length analysis."""
    return ANY_TAG_RE.sub('', s)


def visible_length(s: str) -> int:
    """Number of visible characters after stripping tags. Approximates how
    much screen space the text will need (1 char ≈ 1 full-width or 0.5
    proportional-Latin cell)."""
    return len(strip_all_tags(s))


# Per-color-code byte cost: '<font color="#CC0000">' = 22 bytes, '</font>' = 7
COLOR_TAG_BYTES = 22 + 7    # one full red color span costs 29 bytes


# ---------- line-break auto-calc ----------

# Game-specific defaults — adjust per renderer/font
@dataclass
class WrapStyle:
    max_pixel_width: int    # ~280 for DP3 dialog popups at 8x16 font
    avg_char_pixels: float  # average glyph width
    line_break_token: str = '<br>'


SPAWN_DP3_DIALOG = WrapStyle(max_pixel_width=280, avg_char_pixels=6.0)
SPAWN_TEX_STRIP_NARROW = WrapStyle(max_pixel_width=24, avg_char_pixels=4.5)


def auto_wrap(s: str, style: WrapStyle) -> str:
    """Insert `<br>` tokens where lines would otherwise exceed
    `style.max_pixel_width`. Uses simple greedy fill — splits on spaces.
    Tags are kept intact (don't break mid-tag)."""
    visible = strip_all_tags(s)
    if visible == s:
        # Pure text — easy
        return _greedy_wrap(s, style)
    # Has tags — re-build piecewise so tags don't break wrapping
    out = []
    pos = 0
    for m in ANY_TAG_RE.finditer(s):
        plain = s[pos:m.start()]
        out.append(_greedy_wrap(plain, style))
        out.append(m.group(0))
        pos = m.end()
    out.append(_greedy_wrap(s[pos:], style))
    return ''.join(out)


def _greedy_wrap(s: str, style: WrapStyle) -> str:
    words = s.split(' ')
    lines: list[str] = []
    cur = ''
    for w in words:
        candidate = w if not cur else cur + ' ' + w
        pixels = len(candidate) * style.avg_char_pixels
        if pixels <= style.max_pixel_width:
            cur = candidate
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return style.line_break_token.join(lines)


# ---------- safe null-bounded byte-level replace ----------

def find_null_bounded(blob: bytes, jp: bytes) -> list[int]:
    """Return every offset in `blob` where `b'\\x00' + jp + b'\\x00'` matches.

    The campaign rule: only replace JP strings that are actually null-terminated
    on BOTH sides. This avoids bricking the binary by overwriting bytes that
    happen to be CJK characters but are really code/data (Spawn v20 lesson).
    """
    sig = b'\x00' + jp + b'\x00'
    offsets: list[int] = []
    start = 0
    while True:
        i = blob.find(sig, start)
        if i < 0:
            return offsets
        # Plus-1 because the null is at i; the actual JP starts at i+1
        offsets.append(i + 1)
        start = i + 1


def apply_safe_replace(blob: bytes, jp: str, en: str) -> tuple[bytes, list[int]]:
    """Replace every null-bounded occurrence of `jp` (cp932) with `en` (any
    cp932-encodable). Pads the result with nulls to preserve byte length.

    Returns: (modified_blob, list_of_offsets_replaced)

    Refuses to replace if the EN bytes are longer than the JP bytes. The
    shrink-or-equal rule keeps every downstream pointer valid.
    """
    jp_b = jp.encode('cp932', errors='strict')
    en_b = en.encode('cp932', errors='strict')
    if len(en_b) > len(jp_b):
        raise ValueError(
            f'{en!r} ({len(en_b)} B) > {jp!r} ({len(jp_b)} B) — would grow binary'
        )
    padded = en_b + b'\x00' * (len(jp_b) - len(en_b))
    out = bytearray(blob)
    offsets = find_null_bounded(blob, jp_b)
    for off in offsets:
        out[off:off + len(jp_b)] = padded
    return bytes(out), offsets


# ---------- JP run scanner (for the Text Grid view) ----------

def find_cp932_runs(data: bytes, min_chars: int = 4) -> list[tuple[int, int, str]]:
    """Scan `data` for runs of >= `min_chars` consecutive cp932 double-byte
    Japanese characters. Returns list of (offset, char_count, decoded_text).

    The minimum-run filter keeps the spreadsheet manageable: a 4-CJK-char run
    is virtually always real text, while 1-3-char runs are mostly false
    positives (bytes that happen to be in the cp932 lead-byte range but live
    inside SH-4 instructions or data tables).
    """
    runs: list[tuple[int, int, str]] = []
    i, L = 0, len(data)
    while i < L - 1:
        start, run = i, 0
        while i < L - 1:
            b1, b2 = data[i], data[i + 1]
            if ((0x81 <= b1 <= 0x9f or 0xe0 <= b1 <= 0xfc) and
                    (0x40 <= b2 <= 0xfc and b2 != 0x7f)):
                run += 1
                i += 2
            else:
                break
        if run >= min_chars:
            try:
                txt = data[start:start + run * 2].decode('cp932', errors='replace')
            except Exception:
                txt = '<decode err>'
            runs.append((start, run, txt))
        else:
            i = max(start + 1, i + 1)
    return runs
