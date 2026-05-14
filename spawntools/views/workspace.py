"""Tab 1 — Workspace & QA.

Top: pick a GDI, extract, see file counts. Backups dir auto-created.
Middle: integrity-check button + log console below.
Bottom: project status (modified file count, oversize warnings).
"""
from __future__ import annotations
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from ..widgets.log_console import LogConsole
from ..core import disc as disc_core


class WorkspaceTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app
        self._build()

    def _build(self):
        # --- Top: disc + project paths ---
        head = ttk.LabelFrame(self, text='Disc & project paths', padding=8)
        head.pack(fill='x', pady=(0, 8))

        row1 = ttk.Frame(head); row1.pack(fill='x', pady=2)
        ttk.Label(row1, text='Disc (.gdi):', width=14).pack(side='left')
        self.gdi_var = tk.StringVar(value=self.app.cfg.last_disc_path)
        ttk.Entry(row1, textvariable=self.gdi_var).pack(side='left', fill='x', expand=True, padx=4)
        ttk.Button(row1, text='Browse…', command=self._browse_gdi).pack(side='left')

        row2 = ttk.Frame(head); row2.pack(fill='x', pady=2)
        ttk.Label(row2, text='Project dir:', width=14).pack(side='left')
        self.proj_var = tk.StringVar(value=self.app.cfg.last_project_dir)
        ttk.Entry(row2, textvariable=self.proj_var).pack(side='left', fill='x', expand=True, padx=4)
        ttk.Button(row2, text='Browse…', command=self._browse_project).pack(side='left')

        # --- Actions ---
        btn = ttk.Frame(self); btn.pack(fill='x', pady=4)
        ttk.Button(btn, text='Open / Extract',
                   command=self._on_open, style='Accent.TButton').pack(side='left', padx=2)
        ttk.Button(btn, text='Validate Integrity',
                   command=self._on_validate).pack(side='left', padx=2)
        ttk.Button(btn, text='Load Baseline →',
                   command=self._on_load_preset,
                   style='Accent.TButton').pack(side='left', padx=8)
        ttk.Button(btn, text='Reset Patches → Stock JP',
                   command=self._on_reset_patches).pack(side='left', padx=2)

        # --- Game / preset picker ---
        pk = ttk.Frame(self); pk.pack(fill='x', pady=2)
        ttk.Label(pk, text='Preset:', width=14).pack(side='left')
        self.preset_slug_var = tk.StringVar(value='spawn')
        self._preset_options = []  # populated in _populate_preset_dropdown
        self.preset_combo = ttk.Combobox(
            pk, textvariable=self.preset_slug_var, state='readonly', width=48,
        )
        self.preset_combo.pack(side='left', fill='x', expand=True, padx=4)
        ttk.Button(pk, text='Auto-detect from disc',
                   command=self._on_autodetect_preset).pack(side='left')
        self._populate_preset_dropdown()

        # --- Status panel ---
        st = ttk.LabelFrame(self, text='Status', padding=8)
        st.pack(fill='x', pady=4)
        self.status_var = tk.StringVar(value='No disc opened.')
        ttk.Label(st, textvariable=self.status_var, foreground='#444').pack(anchor='w')

        # --- Log console ---
        log_frame = ttk.LabelFrame(self, text='Activity log', padding=6)
        log_frame.pack(fill='both', expand=True, pady=4)
        self.log = LogConsole(log_frame, height=12)
        self.log.pack(fill='both', expand=True)

    # ---------- handlers ----------

    def _browse_gdi(self):
        p = filedialog.askopenfilename(
            title='Pick a Dreamcast disc (.gdi / .iso / .bin)',
            filetypes=[('Dreamcast disc', '*.gdi *.iso *.bin'), ('All', '*.*')],
            parent=self.app,
        )
        if p:
            self.gdi_var.set(p)
            self.proj_var.set(self._infer_project_dir(Path(p)))

    @staticmethod
    def _infer_project_dir(gdi: Path) -> str:
        """Pick the best default project directory for a freshly-selected GDI.

        Priority:
          1. If the GDI's grandparent dir (e.g. `<game>/disc/disc.gdi` →
             `<game>`) contains a `patches/` AND `extracted/` siblings of
             `disc/`, use that — it's a campaign workspace and the user's
             existing modifications must NOT be ignored.
          2. Else if the GDI's parent has `patches/` next to it, use parent.
          3. Else default to a fresh `<gdi_parent>/spawntools_project`.
        """
        for candidate in (gdi.parent.parent, gdi.parent):
            if (candidate / 'patches').is_dir() and (candidate / 'extracted').is_dir():
                return str(candidate)
        return str(gdi.parent / 'spawntools_project')

    def _browse_project(self):
        d = filedialog.askdirectory(
            title='Pick project directory (extracts here)',
            parent=self.app,
        )
        if d: self.proj_var.set(d)

    def _on_open(self):
        gdi = self.gdi_var.get().strip()
        proj = self.proj_var.get().strip()
        if not gdi or not Path(gdi).is_file():
            messagebox.showerror('Bad GDI', f'Pick a valid disc file.\n\n{gdi}', parent=self.app)
            return
        if not proj:
            messagebox.showerror('Bad project dir', 'Pick a project directory.', parent=self.app)
            return
        # Save to config + recents
        self.app.cfg.last_disc_path = gdi
        self.app.cfg.last_project_dir = proj
        self.app.cfg.save()

        # Run extraction on a background thread (it can take 30-90 s)
        self.log.append(f'opening {gdi}', tag='ok')
        self.log.append(f'project dir: {proj}', tag='dim')

        def runner():
            try:
                dctx = disc_core.open_disc(
                    Path(gdi), Path(proj),
                    progress=lambda m: self.log.append('  ' + m),
                )
                self.app.set_disc_context(dctx)
                # Detect existing campaign modifications so the user knows
                # whether this is a fresh project or a continuation.
                n_modified = 0
                for p in dctx.patches_dir.rglob('*'):
                    if not p.is_file(): continue
                    rel = p.relative_to(dctx.patches_dir).as_posix()
                    base = dctx.extracted_dir / rel
                    if base.exists() and base.stat().st_size == p.stat().st_size:
                        if base.read_bytes() != p.read_bytes():
                            n_modified += 1
                    elif base.exists():
                        n_modified += 1
                if n_modified > 0:
                    self.log.append(
                        f'Detected {n_modified} pre-existing modifications in patches/.',
                        tag='ok')
                    self.log.append(
                        '  Click "Load Spawn Baseline" to derive the EN '
                        'translations and notes from them.',
                        tag='dim')
                else:
                    self.log.append(
                        'Fresh project — patches/ matches extracted/ (no edits yet).',
                        tag='dim')
                self.log.append('open: OK', tag='ok')
                # Auto-detect the game via IP.BIN product code and pre-select
                # its preset. The combobox becomes an override, not the gate.
                from ..core import preset as preset_core
                detected_slug = preset_core.Preset.detect_for_disc(dctx)
                if detected_slug:
                    for i, g in enumerate(self._preset_options):
                        if g['slug'] == detected_slug:
                            self.preset_combo.current(i)
                            self.preset_slug_var.set(detected_slug)
                            self.log.append(
                                f'auto-detected game: {g["display_name"]}  '
                                f'(IP.BIN code {g.get("product_code","?")})',
                                tag='ok')
                            break
                else:
                    self.log.append(
                        'No IP.BIN match — pick a preset manually or leave on the '
                        'default if this is a fresh game not in the registry.',
                        tag='warn')
                self.status_var.set(
                    f'Disc: {Path(gdi).name}   '
                    f'Track03: {dctx.track03_path.name}   '
                    f'(sectors: {"BIN 2352" if dctx.is_bin_sectors else "ISO 2048"})   '
                    f'mods detected: {n_modified}'
                    + (f'   detected: {detected_slug}' if detected_slug else '')
                )
                # Trigger re-population of other tabs
                self.app.notify_disc_opened()
            except Exception as e:
                import traceback
                self.log.append('FAILED:\n' + traceback.format_exc(), tag='error')
        threading.Thread(target=runner, daemon=True).start()

    def _on_validate(self):
        dctx = self.app.disc
        if not dctx:
            messagebox.showinfo('No disc', 'Open a disc first.', parent=self.app)
            return
        self.log.append('=== Integrity audit ===', tag='ok')
        result = disc_core.integrity_check(dctx, progress=lambda m: self.log.append('  ' + m))
        if result['safe_to_build']:
            self.log.append('Integrity: ALL CHECKS PASS', tag='ok')
        else:
            self.log.append('Integrity: BLOCKED — see warnings above', tag='error')
        self.status_var.set(
            f"files: {result['files_checked']}   "
            f"modified: {result['modified']}   "
            f"identical: {result['identical']}   "
            f"oversize: {len(result['oversize'])}   "
            f"orphans: {len(result['orphans'])}"
        )

    def _populate_preset_dropdown(self):
        from ..core import preset as preset_core
        games = preset_core.Preset.list_available()
        self._preset_options = games
        labels = [f"{g['display_name']}  [{g['slug']}]" for g in games]
        self.preset_combo['values'] = labels
        # Default current selection
        current = self.preset_slug_var.get() or 'spawn'
        match = next((i for i, g in enumerate(games) if g['slug'] == current), 0)
        if labels:
            self.preset_combo.current(match)
            self.preset_slug_var.set(games[match]['slug'])
        self.preset_combo.bind('<<ComboboxSelected>>', self._on_preset_pick)

    def _on_preset_pick(self, _evt=None):
        idx = self.preset_combo.current()
        if 0 <= idx < len(self._preset_options):
            self.preset_slug_var.set(self._preset_options[idx]['slug'])

    def _on_autodetect_preset(self):
        if not self.app.disc:
            messagebox.showinfo(
                'Open disc first',
                'Open a disc before auto-detecting — fingerprint needs the loaded track.',
                parent=self.app)
            return
        from ..core import preset as preset_core
        slug = preset_core.Preset.detect_for_disc(self.app.disc)
        if not slug:
            messagebox.showinfo(
                'No match',
                'Disc fingerprint did not match any bundled preset. Pick one manually.',
                parent=self.app)
            return
        for i, g in enumerate(self._preset_options):
            if g['slug'] == slug:
                self.preset_combo.current(i)
                self.preset_slug_var.set(slug)
                self.log.append(f"auto-detected preset: {g['display_name']}", tag='ok')
                return

    def _on_load_preset(self):
        if not self.app.disc:
            messagebox.showinfo('Open disc first', 'Open a disc before loading the baseline.', parent=self.app)
            return
        slug = self.preset_slug_var.get() or 'spawn'
        from ..core import preset as preset_core
        try:
            preset = preset_core.Preset.load_bundled(slug)
        except RuntimeError as e:
            messagebox.showerror('Preset missing', str(e), parent=self.app)
            return

        self.log.append(f'=== Loading: {preset.name} (tier {preset.tier}) ===', tag='ok')
        self.log.append(f'  {preset.modified_count} modified files inventoried')
        self.log.append(f'  {len(preset.dict_entries)} JP->EN dictionary entries')
        self.log.append('  scanning extracted/ vs patches/ to derive EN translations...')

        # Make sure the Text Grid DB is open
        if self.app.tab_text_grid.db is None:
            self.app.tab_text_grid.disc_opened()

        def runner():
            try:
                result = preset_core.apply_preset(
                    self.app.disc, self.app.tab_text_grid.db, preset,
                    progress=lambda m: self.log.append(m),
                )
                # Final DB row counts — proves the apply actually landed
                counts = self.app.tab_text_grid.db.counts()
                self.log.append(
                    f'preset applied: '
                    f'{result["pre_filled"]:,} EN translations pre-filled, '
                    f'{result["dict_hints"]:,} dictionary hints attached',
                    tag='ok',
                )
                self.log.append(
                    f'StringDB now: total={counts.get("total", 0):,}  '
                    f'done={counts.get("done", 0):,}  '
                    f'todo={counts.get("todo", 0):,}  '
                    f'oversize={counts.get("oversize", 0):,}',
                    tag='ok',
                )
                # Push texture notes to Tab 2
                self.app.tab_textures.preset = preset
                self.after(0, self.app.tab_textures.reload)
                self.after(0, self.app.tab_text_grid._refresh)
                self.after(0, lambda: self.app.nb.select(2))   # jump to Text Grid
            except Exception as e:
                import traceback
                self.log.append('FAILED:\n' + traceback.format_exc(), tag='error')
        threading.Thread(target=runner, daemon=True).start()

    def _on_reset_patches(self):
        dctx = self.app.disc
        if not dctx:
            return
        if not messagebox.askyesno(
            'Reset patches?',
            f'This deletes the current patches/ dir and re-copies from extracted/.\n'
            f'All your translation edits will be lost (backups/ is unaffected).\n\n'
            f'Continue?',
            parent=self.app):
            return
        import shutil
        shutil.rmtree(dctx.patches_dir, ignore_errors=True)
        dctx.patches_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(dctx.extracted_dir, dctx.patches_dir, dirs_exist_ok=True)
        self.log.append('patches/ reset from extracted/', tag='warn')
        self.app.notify_disc_opened()    # re-scan everything
