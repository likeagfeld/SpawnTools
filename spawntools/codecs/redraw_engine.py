"""Generic redraw engine: take a config of sprite replacements and produce
a modified PNG that can be repacked into a TXB0 .TEX.

A redraw spec has the form:
  {
    'tex': 'LOBBY37',          # source TXB0 .TEX base name
    'subtex': 3,                # which sub-texture in the TEX
    'sprites': [
       {'bbox': [x0,y0,x1,y1], 'en': 'NEW REG', 'style': 'orange', 'orient': 'v', 'font': 'cooper'},
       ...
    ],
  }

Style names map to pre-defined color triples. Orient 'h' or 'v' (vertical
means the text is rotated 90 CCW in the atlas so we render horizontally
then rotate 90 CW to paste).

Font names: 'cooper' (default chunky), 'impact' (condensed), 'arial' (clean).
"""
import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np


STYLES = {
    'pink':   {'top':(255,220,235), 'middle':(255,100,165), 'bottom':(200,30,90),  'outline':(0,0,0), 'outline_w':2},
    'orange': {'top':(255,240,180), 'middle':(255,175,40),  'bottom':(215,100,10), 'outline':(0,0,0), 'outline_w':2},
    'red':    {'top':(255,200,200), 'middle':(255,60,60),   'bottom':(180,0,0),    'outline':(0,0,0), 'outline_w':2},
    'white':  {'top':(255,255,255), 'middle':(230,230,230), 'bottom':(180,180,180),'outline':(0,0,0), 'outline_w':2},
    'gray':   {'top':(200,200,200), 'middle':(140,140,140), 'bottom':(80,80,80),   'outline':(0,0,0), 'outline_w':2},
    'cyan':   {'top':(220,255,255), 'middle':(100,220,255), 'bottom':(40,140,200), 'outline':(0,0,0), 'outline_w':2},
    'yellow': {'top':(255,255,200), 'middle':(255,230,80),  'bottom':(220,180,0),  'outline':(0,0,0), 'outline_w':2},
}

FONTS = {
    'cooper':  'C:/Windows/Fonts/CooperBlackStd.otf',
    'impact':  'C:/Windows/Fonts/impact.ttf',
    'arial':   'C:/Windows/Fonts/arialbd.ttf',
    'stencil': 'C:/Windows/Fonts/STENCIL.TTF',
    'comic':   'C:/Windows/Fonts/comicbd.ttf',
    'bahn':    'C:/Windows/Fonts/bahnschrift.ttf',
}


def find_font_size(text, target_w, target_h, font_path, max_size=80):
    """Binary search for the largest font size where text fits.
    Account for the outline padding (which extends the visual size)."""
    lo, hi, best = 6, max_size, 6
    while lo <= hi:
        mid = (lo + hi) // 2
        f = ImageFont.truetype(font_path, mid)
        bb = f.getbbox(text)
        # +4 for outline buffer on each side
        if bb[2] - bb[0] + 4 <= target_w and bb[3] - bb[1] + 4 <= target_h:
            best = mid; lo = mid + 1
        else:
            hi = mid - 1
    return best


def _draw_multiline(lines, font, w, h, top_y, line_step, style):
    """Helper: draw 2+ lines of text centered horizontally with vertical gradient + stroke."""
    out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    # First, build text-shaped alpha mask for the entire block
    mask = Image.new('L', (w, h), 0)
    md = ImageDraw.Draw(mask)
    stroke_layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stroke_layer)
    ow = style['outline_w']
    for i, line in enumerate(lines):
        bb = font.getbbox(line)
        tw = bb[2] - bb[0]
        ox = (w - tw) // 2 - bb[0]
        oy = top_y + i * line_step - bb[1]
        # Stroke
        for dx in range(-ow, ow + 1):
            for dy in range(-ow, ow + 1):
                if dx*dx + dy*dy <= ow*ow:
                    sd.text((ox+dx, oy+dy), line, font=font, fill=style['outline'])
        md.text((ox, oy), line, font=font, fill=255)
    # Build gradient and clip with mask
    gradient = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    g = gradient.load()
    top, mid, bot = style['top'], style['middle'], style['bottom']
    for y in range(h):
        t = y / max(1, h-1)
        if t < 0.5:
            u = t * 2
            r = int(top[0] + (mid[0]-top[0]) * u); gg = int(top[1] + (mid[1]-top[1]) * u); b = int(top[2] + (mid[2]-top[2]) * u)
        else:
            u = (t - 0.5) * 2
            r = int(mid[0] + (bot[0]-mid[0]) * u); gg = int(mid[1] + (bot[1]-mid[1]) * u); b = int(mid[2] + (bot[2]-mid[2]) * u)
        for x in range(w):
            g[x, y] = (r, gg, b, 255)
    fill = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    fill.paste(gradient, (0, 0), mask)
    out = Image.alpha_composite(out, stroke_layer)
    out = Image.alpha_composite(out, fill)
    return out


def render_label(text, w, h, style, font_path, padding=2):
    """Render `text` to fit inside a (w,h) box. Falls back to condensed font
    or splitting on space if a single line of `font_path` can't fit."""
    out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    if not text:
        return out
    avail_w, avail_h = max(1, w - 2*padding), max(1, h - 2*padding)
    size = find_font_size(text, avail_w, int(avail_h * 1.1), font_path)
    # If the chosen size is tiny, try Impact (condensed) as fallback for better readability
    if size < 9 and font_path != FONTS.get('impact'):
        alt = FONTS.get('impact')
        if alt:
            alt_size = find_font_size(text, avail_w, int(avail_h * 1.1), alt)
            if alt_size > size + 2:
                font_path = alt; size = alt_size
    # If still tiny, try splitting on spaces and wrapping to 2 lines
    lines = [text]
    if size < 10 and ' ' in text:
        words = text.split(' ')
        # try every split
        best_size = size; best_lines = [text]
        for i in range(1, len(words)):
            L1 = ' '.join(words[:i]); L2 = ' '.join(words[i:])
            # both lines must fit
            s1 = find_font_size(L1, avail_w, int(avail_h * 0.55), font_path)
            s2 = find_font_size(L2, avail_w, int(avail_h * 0.55), font_path)
            s = min(s1, s2)
            if s > best_size:
                best_size = s; best_lines = [L1, L2]
        size = best_size; lines = best_lines
    font = ImageFont.truetype(font_path, size)
    # Layout multiline
    if len(lines) > 1:
        # measure each line
        line_h = font.getbbox('Ag')[3] - font.getbbox('Ag')[1]
        block_h = line_h * len(lines) + 2 * (len(lines) - 1)
        oy_block = (h - block_h) // 2
        # Need full mask + stroke layers built up across lines.
        full_text_layer = _draw_multiline(lines, font, w, h, oy_block, line_h + 2, style)
        return full_text_layer
    bb = font.getbbox(text)
    tw, th = bb[2]-bb[0], bb[3]-bb[1]
    ox = (w - tw) // 2 - bb[0]
    oy = (h - th) // 2 - bb[1]

    # Stroke
    sl = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sl)
    ow = style['outline_w']
    for dx in range(-ow, ow+1):
        for dy in range(-ow, ow+1):
            if dx*dx + dy*dy <= ow*ow:
                sd.text((ox+dx, oy+dy), text, font=font, fill=style['outline'])

    # Fill with vertical gradient
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).text((ox, oy), text, font=font, fill=255)
    gradient = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    g = gradient.load()
    top, mid, bot = style['top'], style['middle'], style['bottom']
    for y in range(h):
        t = y / max(1, h-1)
        if t < 0.5:
            u = t * 2
            r = int(top[0] + (mid[0]-top[0]) * u); gg = int(top[1] + (mid[1]-top[1]) * u); b = int(top[2] + (mid[2]-top[2]) * u)
        else:
            u = (t - 0.5) * 2
            r = int(mid[0] + (bot[0]-mid[0]) * u); gg = int(mid[1] + (bot[1]-mid[1]) * u); b = int(mid[2] + (bot[2]-mid[2]) * u)
        for x in range(w):
            g[x, y] = (r, gg, b, 255)
    fill = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    fill.paste(gradient, (0, 0), mask)
    out = Image.alpha_composite(out, sl)
    out = Image.alpha_composite(out, fill)
    return out


def erase_region(img, x0, y0, x1, y1):
    arr = np.array(img)
    arr[y0:y1, x0:x1, 3] = 0
    return Image.fromarray(arr, 'RGBA')


def apply_sprites(src_img, sprites, mode='clean'):
    """src_img: PIL RGBA. sprites: list of dicts as in module docstring.
    mode='clean': erase whole image, keep only skip sprites' alpha-mask + draw new sprites.
    mode='patch': erase only sprite bboxes that are getting English replacements.

    'clean' mode uses the per-sprite alpha mask (not rectangle) when copying
    skipped sprites back, so dilated bboxes from neighbour sprites don't
    pollute the kept regions.
    """
    from scipy import ndimage  # local import (kept lazy)
    W, H = src_img.size
    src_arr = np.array(src_img)
    if mode == 'clean':
        canvas_arr = np.zeros_like(src_arr)
        # Build a "keep mask" from skipped sprites: only their actual alpha pixels
        # inside their bbox should be preserved.
        for sp in sprites:
            if sp.get('skip'):
                x0, y0, x1, y1 = sp['bbox']
                region = src_arr[y0:y1, x0:x1]
                # Keep only non-transparent pixels
                m = region[..., 3] > 16
                canvas_arr[y0:y1, x0:x1][m] = region[m]
        out = Image.fromarray(canvas_arr, 'RGBA')
    else:
        out = src_img.copy()

    for sp in sprites:
        if sp.get('skip'):
            continue
        x0, y0, x1, y1 = sp['bbox']
        w, h = x1 - x0, y1 - y0
        text = sp.get('en', '')
        if not text:
            continue
        if mode == 'patch':
            # Use mask-based erase: only clear pixels that have non-zero alpha
            arr = np.array(out)
            sub = arr[max(0, y0-3):min(H, y1+3), max(0, x0-3):min(W, x1+3)]
            sub[..., 3] = 0
            out = Image.fromarray(arr, 'RGBA')
        style = STYLES[sp.get('style', 'orange')]
        font_path = FONTS[sp.get('font', 'cooper')]
        orient = sp.get('orient', 'h' if w >= h else 'v')
        if text.isdigit():
            font_path = FONTS['arial']
        if orient == 'h':
            lbl = render_label(text, w, h, style, font_path)
        else:
            lbl = render_label(text, h, w, style, font_path)
            lbl = lbl.rotate(-90, expand=True)
            if lbl.size != (w, h):
                lbl = lbl.resize((w, h), Image.LANCZOS)
        out.alpha_composite(lbl, dest=(x0, y0))
    return out
