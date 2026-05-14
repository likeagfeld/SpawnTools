"""Tab 2 — Texture Workbench.

Left:   file list (every .TEX/.PVR under patches/, with protected atlases dimmed).
Center: side-by-side Original vs Translated previews.
Right:  per-sub-tex info + actions [Export Original/Modified PNG] [Import & Auto-Convert] [Restore Original].
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from PIL import Image, ImageTk
from typing import Optional

from ..core import textures as tex_core
from ..core import archives as arch_core


class TexturesTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=6)
        self.app = app
        self._photo_orig: Optional[ImageTk.PhotoImage] = None
        self._photo_new: Optional[ImageTk.PhotoImage] = None
        self._current_records: list[tex_core.TextureRecord] = []
        self._current_file: Optional[Path] = None
        self._current_member = None    # archives.ArchiveMember when viewing an archive entry
        self.preset = None       # populated by workspace tab's _on_load_preset
        self._modified_cache: dict[str, bool] = {}    # rel_path -> True if patches/ != extracted/
        self._build()

    def _build(self):
        # Three-column layout
        outer = ttk.Panedwindow(self, orient='horizontal')
        outer.pack(fill='both', expand=True)

        # --- LEFT: file list ---
        left = ttk.Frame(outer, width=280)
        outer.add(left, weight=0)

        ttk.Label(left, text='Texture files (patches/)',
                  font=('TkDefaultFont', 10, 'bold')).pack(anchor='w', padx=4, pady=2)

        # Modified/stock filter
        sf_row = ttk.Frame(left); sf_row.pack(fill='x', padx=4, pady=(2, 2))
        ttk.Label(sf_row, text='Show:').pack(side='left')
        self.status_filter = tk.StringVar(value='All')
        for label in ('All', 'Modified', 'Stock'):
            ttk.Radiobutton(sf_row, text=label, value=label, variable=self.status_filter,
                            command=self._populate_files).pack(side='left', padx=2)

        # Search/filter
        f_row = ttk.Frame(left); f_row.pack(fill='x', padx=4, pady=(0, 2))
        self.filter_var = tk.StringVar()
        ent = ttk.Entry(f_row, textvariable=self.filter_var)
        ent.pack(side='left', fill='x', expand=True)
        ent.bind('<KeyRelease>', lambda _e: self._populate_files())

        # File list — now with a Status column
        list_frame = ttk.Frame(left); list_frame.pack(fill='both', expand=True, padx=4, pady=4)
        self.file_tree = ttk.Treeview(
            list_frame, columns=('status', 'size'),
            show='tree headings', height=22,
        )
        self.file_tree.heading('#0', text='File')
        self.file_tree.heading('status', text=' ')      # single-column-width
        self.file_tree.heading('size', text='Bytes')
        self.file_tree.column('#0', width=160, anchor='w')
        self.file_tree.column('status', width=28, anchor='center')
        self.file_tree.column('size', width=70, anchor='e')
        vs = ttk.Scrollbar(list_frame, orient='vertical', command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=vs.set)
        self.file_tree.pack(side='left', fill='both', expand=True)
        vs.pack(side='right', fill='y')
        self.file_tree.bind('<<TreeviewSelect>>', self._on_pick_file)
        # Row color tags
        self.file_tree.tag_configure('protected', foreground='#999')
        self.file_tree.tag_configure('modified',  background='#e6f4ea',
                                       foreground='#0a7d33')
        self.file_tree.tag_configure('stock',     foreground='#444')

        # Summary line under the file list
        self.list_summary_var = tk.StringVar(value='')
        ttk.Label(left, textvariable=self.list_summary_var,
                  foreground='#555', font=('TkDefaultFont', 9)).pack(
            fill='x', padx=6, pady=(0, 4)
        )

        # Sub-tex picker
        sub_label = ttk.Label(left, text='Sub-textures')
        sub_label.pack(anchor='w', padx=4)
        self.subtex_list = tk.Listbox(left, height=10, exportselection=False)
        self.subtex_list.pack(fill='x', padx=4, pady=2)
        self.subtex_list.bind('<<ListboxSelect>>', self._on_pick_subtex)

        # --- CENTER: previews ---
        center = ttk.Frame(outer)
        outer.add(center, weight=3)

        prev = ttk.Frame(center)
        prev.pack(fill='both', expand=True, padx=8, pady=8)

        col_orig = ttk.LabelFrame(prev, text='Original (baseline)')
        col_orig.pack(side='left', fill='both', expand=True, padx=4)
        self.canvas_orig = tk.Canvas(col_orig, bg='#101418', highlightthickness=0)
        self.canvas_orig.pack(fill='both', expand=True, padx=6, pady=6)

        col_new = ttk.LabelFrame(prev, text='Translated (patches/)')
        col_new.pack(side='left', fill='both', expand=True, padx=4)
        self.canvas_new = tk.Canvas(col_new, bg='#101418', highlightthickness=0)
        self.canvas_new.pack(fill='both', expand=True, padx=6, pady=6)

        # --- RIGHT: actions + info ---
        right = ttk.Frame(outer, width=260)
        outer.add(right, weight=0)

        ttk.Label(right, text='Sub-texture info', font=('TkDefaultFont', 10, 'bold')).pack(anchor='w', padx=6, pady=2)
        self.info_lbl = ttk.Label(right, text='—', justify='left', wraplength=240)
        self.info_lbl.pack(anchor='w', padx=6, pady=4)

        ttk.Separator(right).pack(fill='x', pady=4)
        # --- Format override (POWER-USER): only visible when current
        # selection is a RAW archive member. Default format is auto-set
        # per game via raw_format_profiles.json; this lets you flip it if
        # the auto-pick is wrong for an unusual chunk.
        self.raw_fmt_frame = ttk.LabelFrame(right,
                                             text='Format override (auto-set per game)', padding=4)
        ttk.Label(self.raw_fmt_frame, text='pixfmt:').grid(row=0, column=0, sticky='w')
        self.raw_pixfmt_var = tk.StringVar(value='RGB565 (0x01)')
        self.raw_pixfmt_combo = ttk.Combobox(
            self.raw_fmt_frame, textvariable=self.raw_pixfmt_var,
            values=['ARGB1555 (0x00)', 'RGB565 (0x01)', 'ARGB4444 (0x02)'],
            state='readonly', width=20,
        )
        self.raw_pixfmt_combo.grid(row=0, column=1, padx=2, pady=1)
        self.raw_pixfmt_combo.bind('<<ComboboxSelected>>', self._on_raw_fmt_change)

        ttk.Label(self.raw_fmt_frame, text='datafmt:').grid(row=1, column=0, sticky='w')
        self.raw_datafmt_var = tk.StringVar(value='SQUARE_TWIDDLED (0x01)')
        self.raw_datafmt_combo = ttk.Combobox(
            self.raw_fmt_frame, textvariable=self.raw_datafmt_var,
            values=['SQUARE_TWIDDLED (0x01)', 'RECTANGLE (0x09)',
                    'RECTANGLE_TWIDDLED (0x0d)', 'SQUARE_TWIDDLED_MIPMAP (0x02)'],
            state='readonly', width=22,
        )
        self.raw_datafmt_combo.grid(row=1, column=1, padx=2, pady=1)
        self.raw_datafmt_combo.bind('<<ComboboxSelected>>', self._on_raw_fmt_change)
        # Pack/forget done in _on_pick_subtex when the current rec is/isn't RAW

        ttk.Label(right, text='Export to PNG', font=('TkDefaultFont', 9, 'bold')
                  ).pack(anchor='w', padx=6, pady=(2, 0))
        ttk.Button(right, text='Export Original (JP baseline)…',
                   command=lambda: self._on_export_png(source='baseline')
                   ).pack(fill='x', padx=6, pady=2)
        ttk.Button(right, text='Export Modified (current patches/)…',
                   command=lambda: self._on_export_png(source='modified')
                   ).pack(fill='x', padx=6, pady=2)
        ttk.Separator(right).pack(fill='x', pady=4)
        ttk.Button(right, text='Import & Auto-Convert…', command=self._on_import_png,
                   style='Accent.TButton').pack(fill='x', padx=6, pady=2)
        ttk.Button(right, text='Restore Original', command=self._on_restore).pack(fill='x', padx=6, pady=2)

        ttk.Separator(right).pack(fill='x', pady=4)
        # Modified-vs-baseline marker
        self.modified_marker_var = tk.StringVar(value='')
        ttk.Label(right, textvariable=self.modified_marker_var,
                  font=('TkDefaultFont', 9, 'bold')).pack(fill='x', padx=6)

        # Baseline notes (from the preset)
        ttk.Label(right, text='Campaign notes:',
                  foreground='#666').pack(anchor='w', padx=6, pady=(8, 0))
        self.notes_text = tk.Text(right, height=10, wrap='word',
                                   bg='#fafbfc', fg='#234',
                                   relief='flat', bd=0,
                                   font=('TkDefaultFont', 9))
        self.notes_text.pack(fill='x', padx=6, pady=2)
        self.notes_text.config(state='disabled')

        ttk.Separator(right).pack(fill='x', pady=4)
        ttk.Button(right, text='Revert this file → JP baseline',
                   command=self._on_revert_file).pack(fill='x', padx=6, pady=2)

        ttk.Separator(right).pack(fill='x', pady=4)
        self.status_var = tk.StringVar(value='')
        ttk.Label(right, textvariable=self.status_var, foreground='#666',
                  wraplength=240, justify='left').pack(fill='x', padx=6, pady=2)

    # ---------- data ----------

    def reload(self):
        """Re-populate the file list. Called when the disc context changes."""
        self._modified_cache.clear()      # invalidate cached md5 results
        self._populate_files()

    def _is_modified(self, patches_path: Path) -> bool:
        """Cached patches/ vs extracted/ byte-diff check. Uses size-then-content
        so identical files short-circuit fast (no md5 needed)."""
        rel = patches_path.relative_to(self.app.disc.patches_dir).as_posix()
        cached = self._modified_cache.get(rel)
        if cached is not None:
            return cached
        base = self.app.disc.extracted_dir / rel
        if not base.exists():
            self._modified_cache[rel] = False
            return False
        if base.stat().st_size != patches_path.stat().st_size:
            self._modified_cache[rel] = True
            return True
        # Same size: compare content. For large textures this can take a few ms;
        # we only do it on file-list (re-)populate.
        is_diff = base.read_bytes() != patches_path.read_bytes()
        self._modified_cache[rel] = is_diff
        return is_diff

    def _populate_files(self):
        self.file_tree.delete(*self.file_tree.get_children())
        if not self.app.disc:
            self.list_summary_var.set('No disc opened.')
            return
        filt = self.filter_var.get().strip().lower()
        status_want = self.status_filter.get()      # 'All' / 'Modified' / 'Stock'

        # Collect all .TEX / .PVR files under patches/ + archive containers
        # whose members carry textures (AFS/PAC/PVS/PZZ/SLW/PVZ).
        files = []
        for ext in ('TEX', 'PVR', 'AFS', 'PAC', 'PVS', 'PZZ', 'SLW', 'PVZ'):
            files.extend(self.app.disc.patches_dir.rglob(f'*.{ext}'))
            files.extend(self.app.disc.patches_dir.rglob(f'*.{ext.lower()}'))
        # Deduplicate (case mismatch on Windows)
        files = sorted(set(files), key=lambda p: str(p).lower())

        # Pass 1: classify (compute modified status + tags) and count by status
        n_modified = n_stock = n_protected = 0
        rows: list[tuple[Path, str, bool, bool]] = []   # (path, rel, is_modified, is_protected)
        for p in files:
            rel = p.relative_to(self.app.disc.patches_dir).as_posix()
            if filt and filt not in rel.lower():
                continue
            modified = self._is_modified(p)
            protected = tex_core.is_protected(p)
            if status_want == 'Modified' and not modified: continue
            if status_want == 'Stock'    and     modified: continue
            if modified: n_modified += 1
            else:        n_stock += 1
            if protected: n_protected += 1
            rows.append((p, rel, modified, protected))

        # Pass 2: flat insert. Archives are surfaced as one row per member
        # (no nesting — keeps the list visually identical to the Spawn-era
        # loose-file experience). The archive itself isn't shown as a row
        # since you can only edit its members, not the container directly.
        for p, rel, modified, protected in rows:
            tags = []
            if modified:  tags.append('modified')
            else:         tags.append('stock')
            if protected: tags.append('protected')
            status_glyph = '●' if modified else '○'

            if arch_core.is_archive(p):
                kind, members = arch_core.list_members(p)
                if not members:
                    # Archive failed to decode — still show the file so the user
                    # knows it's there. Avoids silent gaps.
                    self.file_tree.insert(
                        '', 'end', iid=str(p),
                        text=f'{rel}   [archive: {kind or "unknown"} – no members]',
                        values=(status_glyph, f'{p.stat().st_size:,}'),
                        tags=tuple(tags),
                    )
                    continue
                for m in members:
                    self.file_tree.insert(
                        '', 'end', iid=f'{p}#{m.member_id}',
                        text=f'{rel}  ▸ {m.label} ({m.archive_kind})',
                        values=(status_glyph, f'{m.raw_size:,}'),
                        tags=tuple(tags),
                    )
            else:
                label = rel + ('   🔒' if protected else '')
                self.file_tree.insert(
                    '', 'end', iid=str(p), text=label,
                    values=(status_glyph, f'{p.stat().st_size:,}'),
                    tags=tuple(tags),
                )

        # Summary
        self.list_summary_var.set(
            f'● modified: {n_modified}    '
            f'○ stock: {n_stock}'
            + (f'    🔒 protected: {n_protected}' if n_protected else '')
        )

    def _on_pick_file(self, _evt=None):
        sel = self.file_tree.selection()
        if not sel: return
        iid = sel[0]
        # Archive-member iids encode as '<archive_path>#<member_id>'.
        if '#' in iid and iid.rsplit('#', 1)[1].isdigit():
            archive_path_str, member_id_str = iid.rsplit('#', 1)
            self._load_archive_member(Path(archive_path_str), int(member_id_str))
            return
        path = Path(iid)
        if tex_core.is_protected(path):
            self.status_var.set(
                'Protected: runtime glyph atlas. Editing FONT/SOFTKEY/MOJI/MINCHO '
                'breaks the renderer. Skip.'
            )
        self._load_file(path)

    def _load_file(self, path: Path):
        self._current_file = path
        self._current_member = None
        self.subtex_list.delete(0, 'end')
        try:
            self._current_records = tex_core.load(path)
        except Exception as e:
            self._current_records = []
            messagebox.showerror('Decode error', f'{path.name}: {e}', parent=self.app)
            return
        for r in self._current_records:
            self.subtex_list.insert(
                'end',
                f'sub_{r.sub_index:02d}  {r.width}x{r.height}  pf=0x{r.pixfmt:02x} df=0x{r.datafmt:02x}'
            )
        if self._current_records:
            self.subtex_list.selection_set(0)
            self._on_pick_subtex()

    def _load_archive_member(self, archive_path: Path, member_id: int):
        """Decode one member of an archive and present it as if it were a
        single-PVR file in the sub-tex list."""
        self._current_file = archive_path
        self._current_member = None
        self.subtex_list.delete(0, 'end')
        kind, members = arch_core.list_members(archive_path)
        member = next((m for m in members if m.member_id == member_id), None)
        if member is None:
            messagebox.showerror(
                'Member missing',
                f'Could not find member #{member_id} inside {archive_path.name}.',
                parent=self.app)
            return
        self._current_member = member
        recs = tex_core.load_archive_member(member)
        self._current_records = recs
        if not recs:
            # SLW raw blob or undecodable — present a placeholder row so the
            # info pane still shows the size + offset info
            self.subtex_list.insert('end',
                f'{member.label}  ({member.archive_kind} blob, no PVR header)')
            self.info_lbl.config(text='\n'.join([
                f'Archive: {archive_path.name}',
                f'Member: {member.label}  ({member.archive_kind})',
                f'Raw size: {member.raw_size:,} bytes',
                f'Offset in archive: 0x{member.raw_offset:x}',
                'No PVR header — raw-VRAM blob, not editable as a PVR.',
            ]))
            self._show_on(self.canvas_new, None, attr='_photo_new')
            self._show_on(self.canvas_orig, None, attr='_photo_orig')
            return
        for r in recs:
            self.subtex_list.insert(
                'end',
                f'{member.label}  {r.width}x{r.height}  '
                f'pf=0x{r.pixfmt:02x} df=0x{r.datafmt:02x}'
            )
        self.subtex_list.selection_set(0)
        self._on_pick_subtex()

    def _on_pick_subtex(self, _evt=None):
        sel = self.subtex_list.curselection()
        if not sel: return
        rec = self._current_records[sel[0]]
        # Update info
        flags = []
        if rec.is_paletted: flags.append('PALETTED')
        if rec.is_vq:       flags.append('VQ')
        if rec.is_mipmap:   flags.append('MIPMAP')
        is_raw = self._current_member is not None and self._current_member.archive_kind == 'RAW'
        info_lines = [
            f'File: {rec.file_path.name}',
            f'Sub-tex index: {rec.sub_index}',
            f'Dimensions: {rec.width} × {rec.height}',
            f'pixfmt: 0x{rec.pixfmt:02x}',
            f'datafmt: 0x{rec.datafmt:02x}',
        ]
        if flags:
            info_lines.append('Flags: ' + ', '.join(flags))
        if is_raw:
            info_lines.append('(RAW blob: dims/format are best-guess; use the cycler below)')
        self.info_lbl.config(text='\n'.join(info_lines))

        # Show/hide the raw-blob format cycler based on current member kind
        if is_raw:
            self.raw_fmt_frame.pack(fill='x', padx=6, pady=4)
            pf_map = {0x00: 'ARGB1555 (0x00)', 0x01: 'RGB565 (0x01)', 0x02: 'ARGB4444 (0x02)'}
            df_map = {0x01: 'SQUARE_TWIDDLED (0x01)', 0x09: 'RECTANGLE (0x09)',
                      0x0d: 'RECTANGLE_TWIDDLED (0x0d)', 0x02: 'SQUARE_TWIDDLED_MIPMAP (0x02)'}
            self.raw_pixfmt_var.set(pf_map.get(rec.pixfmt, f'? (0x{rec.pixfmt:02x})'))
            self.raw_datafmt_var.set(df_map.get(rec.datafmt, f'? (0x{rec.datafmt:02x})'))
        else:
            try: self.raw_fmt_frame.pack_forget()
            except Exception: pass

        # Modified-vs-baseline detection
        rel = rec.file_path.relative_to(self.app.disc.patches_dir).as_posix()
        baseline_path = self.app.disc.extracted_dir / rel
        is_modified = False
        if baseline_path.exists():
            is_modified = baseline_path.read_bytes() != rec.file_path.read_bytes()
        if is_modified:
            self.modified_marker_var.set('● MODIFIED FROM BASELINE')
        else:
            self.modified_marker_var.set('○ identical to baseline')

        # Preset notes for this file
        self.notes_text.config(state='normal')
        self.notes_text.delete('1.0', 'end')
        if self.preset and rel in self.preset.texture_notes:
            note = self.preset.texture_notes[rel]
            self.notes_text.insert('end', note.get('description', '') + '\n')
            sub_notes = note.get('subtex_notes', {})
            key = str(rec.sub_index)
            if key in sub_notes:
                self.notes_text.insert('end', '\n', '')
                self.notes_text.insert('end', f'sub_{rec.sub_index}: {sub_notes[key]}\n')
            for k, v in sub_notes.items():
                if k.startswith('note'):
                    self.notes_text.insert('end', '\n' + str(v) + '\n')
        elif not self.preset:
            self.notes_text.insert('end',
                'No preset loaded. Click "Load Spawn Baseline" on Tab 1 to '
                'see campaign notes for the modified textures.')
        else:
            self.notes_text.insert('end', '(no campaign notes for this file)')
        self.notes_text.config(state='disabled')

        # Show patches/ image on right canvas
        self._show_on(self.canvas_new, rec.image, attr='_photo_new')

        # Find baseline (extracted/) copy and show on left
        rel = rec.file_path.relative_to(self.app.disc.patches_dir)
        baseline_path = self.app.disc.extracted_dir / rel
        try:
            baseline_recs = tex_core.load(baseline_path)
            base_rec = next((r for r in baseline_recs if r.sub_index == rec.sub_index), None)
            self._show_on(self.canvas_orig, base_rec.image if base_rec else None,
                          attr='_photo_orig')
        except Exception:
            self._show_on(self.canvas_orig, None, attr='_photo_orig')

    def _show_on(self, canvas: tk.Canvas, img, attr: str):
        canvas.delete('all')
        if img is None:
            canvas.create_text(120, 100, text='—', fill='#666')
            return
        cw = max(200, canvas.winfo_width())
        ch = max(150, canvas.winfo_height())
        scale = min(cw / img.size[0], ch / img.size[1], 4.0)
        new_size = (max(1, int(img.size[0] * scale)),
                    max(1, int(img.size[1] * scale)))
        scaled = img.resize(new_size, Image.NEAREST if scale >= 1 else Image.LANCZOS)
        photo = ImageTk.PhotoImage(scaled)
        setattr(self, attr, photo)
        canvas.create_image(cw // 2 - new_size[0] // 2,
                             ch // 2 - new_size[1] // 2, image=photo, anchor='nw')

    # ---------- actions ----------

    def _on_raw_fmt_change(self, _evt=None):
        """User changed the raw-blob pixfmt/datafmt cycler. Re-decode the
        current member with the new format and re-render the preview."""
        if self._current_member is None or self._current_member.archive_kind != 'RAW':
            return
        def parse_hex(s):
            try: return int(s[s.rindex('(0x') + 3:s.rindex(')')], 16)
            except (ValueError, IndexError): return 0
        new_pf = parse_hex(self.raw_pixfmt_var.get())
        new_df = parse_hex(self.raw_datafmt_var.get())
        m = self._current_member
        m.raw_pixfmt = new_pf
        m.raw_datafmt = new_df
        recs = tex_core.load_archive_member(m)
        self._current_records = recs
        # Refresh the listbox label and preview
        if recs:
            r = recs[0]
            self.subtex_list.delete(0)
            self.subtex_list.insert(0,
                f'{m.label}  {r.width}x{r.height}  '
                f'pf=0x{r.pixfmt:02x} df=0x{r.datafmt:02x}'
            )
            self.subtex_list.selection_set(0)
        # Re-render the preview canvas with the new decode
        if recs and recs[0].image is not None:
            self._show_on(self.canvas_new, recs[0].image, attr='_photo_new')
        else:
            self._show_on(self.canvas_new, None, attr='_photo_new')

    def _selected_rec(self):
        sel = self.subtex_list.curselection()
        if sel:
            return self._current_records[sel[0]]
        # Tk can silently drop the listbox selection when another widget steals
        # the X11 selection (notes Text, etc.). If there's exactly one sub-tex
        # — or if we already picked one and the records haven't changed —
        # fall back to it instead of bouncing the user.
        if len(self._current_records) == 1:
            self.subtex_list.selection_set(0)
            return self._current_records[0]
        return None

    def _on_export_png(self, source: str = 'modified'):
        """Export the selected sub-texture to PNG.

        `source='modified'` → patches/ (the EN/current version).
        `source='baseline'` → extracted/ (the JP/original version).
        """
        rec = self._selected_rec()
        if not rec:
            messagebox.showinfo('Pick a sub-tex', 'Pick a sub-texture first.', parent=self.app)
            return

        # Resolve which record to actually export. For 'baseline' we
        # re-decode the matching sub-tex from extracted/ rather than reusing
        # the patches/ record.
        export_rec = rec
        suffix_label = 'modified'
        if source == 'baseline':
            try:
                rel = rec.file_path.relative_to(self.app.disc.patches_dir)
                baseline_path = self.app.disc.extracted_dir / rel
                baseline_recs = tex_core.load(baseline_path)
                export_rec = next(
                    (r for r in baseline_recs if r.sub_index == rec.sub_index), None
                )
            except Exception as e:
                messagebox.showerror(
                    'No baseline copy',
                    f"Couldn't load the JP baseline for {rec.file_path.name}: {e}",
                    parent=self.app,
                )
                return
            if export_rec is None:
                messagebox.showwarning(
                    'No baseline sub-tex',
                    f"The baseline copy of {rec.file_path.name} has no sub_{rec.sub_index}.",
                    parent=self.app,
                )
                return
            suffix_label = 'original'

        if export_rec.image is None:
            hint = ''
            if export_rec.is_paletted:
                sibling = export_rec.file_path.with_suffix('.PVP')
                hint = (
                    f"\n\nThis is a paletted PVR (pixfmt 0x{export_rec.pixfmt:02x}). "
                    f"It needs a sibling .PVP palette file to decode. Looked for:\n"
                    f"  {sibling}\n"
                    f"DPTEX entries usually want BANK01.PVP (NOT BANK00 — that renders rainbow)."
                )
            elif export_rec.datafmt == 0x12:
                hint = '\n\ndatafmt 0x12 is not yet fully implemented in the bundled decoder.'
            messagebox.showwarning(
                'Sub-tex undecodable',
                f'sub_{export_rec.sub_index} ({export_rec.width}x{export_rec.height}, '
                f'pf=0x{export_rec.pixfmt:02x} df=0x{export_rec.datafmt:02x}) failed to '
                f'decode — nothing to export.{hint}',
                parent=self.app,
            )
            return

        default_name = (
            f'{export_rec.file_path.stem}_sub{export_rec.sub_index:02d}_{suffix_label}.png'
        )
        out = filedialog.asksaveasfilename(
            title=f'Export {suffix_label.title()} PNG',
            defaultextension='.png',
            initialfile=default_name, parent=self.app,
            filetypes=[('PNG', '*.png')],
        )
        if not out: return
        tex_core.export_png(export_rec, Path(out))
        messagebox.showinfo('Exported', f'Wrote {out}', parent=self.app)

    def _on_import_png(self):
        rec = self._selected_rec()
        if not rec:
            messagebox.showinfo('Pick a sub-tex', 'Pick a sub-texture first.', parent=self.app)
            return
        if rec.image is None and rec.is_paletted:
            sibling = rec.file_path.with_suffix('.PVP')
            messagebox.showwarning(
                'Sub-tex undecodable',
                f'sub_{rec.sub_index} is paletted (pixfmt 0x{rec.pixfmt:02x}) and the '
                f'sibling palette did not load. Looked for:\n  {sibling}\n'
                f'DPTEX entries usually want BANK01.PVP (NOT BANK00 — that renders rainbow). '
                f'Drop the palette next to the PVR and reload.',
                parent=self.app,
            )
            return
        if tex_core.is_protected(rec.file_path):
            messagebox.showwarning(
                'Protected atlas',
                f'{rec.file_path.name} is a runtime glyph atlas. The campaign '
                f"rule is to NEVER touch FONT/SOFTKEY/MOJI/MINCHO. Refusing.",
                parent=self.app,
            )
            return
        png = filedialog.askopenfilename(
            title='Import PNG (will be auto-converted to match the sub-tex format)',
            filetypes=[('PNG', '*.png'), ('All', '*.*')], parent=self.app,
        )
        if not png: return
        try:
            # Back up the file FIRST (campaign hard rule: always have a known-good copy)
            from ..core import disc as disc_core
            rel = str(rec.file_path.relative_to(self.app.disc.patches_dir))
            disc_core.make_backup(self.app.disc, rel)
            # Archive-member path? Route through replace_member (size-preserving repack).
            if self._current_member is not None:
                result = tex_core.import_png_replace_member(self._current_member, Path(png))
                kind = self._current_member.archive_kind
                messagebox.showinfo(
                    'Imported',
                    f"Wrote {self._current_member.label} into {rec.file_path.name} "
                    f"[{kind}]\n"
                    f"PVR size: {result['new_size']:,} bytes (slot budget preserved)\n"
                    f"pixfmt: 0x{result['pixfmt']:02x}  datafmt: 0x{result['datafmt']:02x}\n"
                    f"{'resized to match member dimensions' if result['resized'] else ''}",
                    parent=self.app,
                )
            else:
                result = tex_core.import_png_replace(rec, Path(png))
                messagebox.showinfo(
                    'Imported',
                    f"Wrote sub_{rec.sub_index} into {rec.file_path.name}\n"
                    f"size: {result['new_size']:,} bytes (unchanged)\n"
                    f"pixfmt: 0x{result['pixfmt']:02x}  datafmt: 0x{result['datafmt']:02x}\n"
                    f"{'resized to match sub-tex dimensions' if result['resized'] else ''}",
                    parent=self.app,
                )
            # Bust the modified-cache for this file and re-populate list
            rel_post = rec.file_path.relative_to(self.app.disc.patches_dir).as_posix()
            self._modified_cache.pop(rel_post, None)
            self._populate_files()
            if self._current_member is not None:
                self._load_archive_member(rec.file_path, self._current_member.member_id)
            else:
                self._load_file(rec.file_path)
        except Exception as e:
            messagebox.showerror('Import error', str(e), parent=self.app)

    def _on_revert_file(self):
        rec = self._selected_rec()
        if not rec: return
        rel = rec.file_path.relative_to(self.app.disc.patches_dir).as_posix()
        if not messagebox.askyesno(
            'Revert file to JP baseline?',
            f'This copies extracted/{rel} OVER patches/{rel}, losing every '
            f'English edit in that file (textures AND any binary string '
            f'edits in that file).\n\nContinue?',
            parent=self.app):
            return
        from ..core import preset as preset_core
        ok, msg = preset_core.revert_file(self.app.disc, rel)
        if ok:
            self.app.log_workspace(f'reverted {rel} to baseline', tag='warn')
            self._modified_cache.pop(rel, None)
            self._populate_files()
            self._load_file(rec.file_path)
        else:
            messagebox.showerror('Revert failed', msg, parent=self.app)

    def _on_restore(self):
        rec = self._selected_rec()
        if not rec: return
        rel = rec.file_path.relative_to(self.app.disc.patches_dir)
        baseline = self.app.disc.extracted_dir / rel
        if not baseline.exists():
            messagebox.showerror('No baseline', f'No baseline copy at\n{baseline}', parent=self.app)
            return
        if not messagebox.askyesno(
            'Restore original?',
            f'Overwrite patches/{rel} with the baseline copy?\n\n'
            f'(Your backups/ dir is unaffected.)',
            parent=self.app):
            return
        tex_core.restore_original(rec, baseline)
        self._modified_cache.pop(str(rel).replace('\\', '/'), None)
        self._populate_files()
        self._load_file(rec.file_path)
        messagebox.showinfo('Restored', f'patches/{rel} restored from baseline.', parent=self.app)
