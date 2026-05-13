"""Tab 4 — Master Build.

Top: output path picker.
Middle: ONE big "GENERATE PATCHED GDI" button.
Below: live console log of the patch pipeline.

The build pipeline is:
  1. Pre-flight: integrity_check — refuse to build if oversize files exist
  2. patch_and_verify — writes patched track03.iso at original byte size,
     md5-verifies 1ST_READ.BIN region matches patches/
  3. generate_gdi_sidecar — writes a .gdi pointing at the new iso
  4. Reminds the user to copy track01/02 next to the new disc image
"""
from __future__ import annotations
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from ..core import disc as disc_core
from ..widgets.log_console import LogConsole


class MasterBuildTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app = app
        self._build()

    def _build(self):
        # Output picker
        path_row = ttk.Frame(self); path_row.pack(fill='x', pady=4)
        ttk.Label(path_row, text='Output disc image:', width=18).pack(side='left')
        self.out_var = tk.StringVar()
        ttk.Entry(path_row, textvariable=self.out_var).pack(side='left', fill='x', expand=True, padx=4)
        ttk.Button(path_row, text='Browse…', command=self._browse).pack(side='left')

        # Big build button
        btn_row = ttk.Frame(self); btn_row.pack(fill='x', pady=10)
        self.build_btn = ttk.Button(
            btn_row, text='⚒  GENERATE PATCHED GDI',
            command=self._on_build, style='Accent.TButton',
        )
        self.build_btn.pack(anchor='w', padx=4, ipady=4)
        ttk.Label(btn_row,
                  text='(Runs integrity audit first → in-place track03 patch via '
                       'process_game.patch_iso → md5 sync verify → sidecar .gdi)',
                  foreground='#666').pack(side='left', padx=10)

        # Log
        log_frame = ttk.LabelFrame(self, text='Build log', padding=4)
        log_frame.pack(fill='both', expand=True, pady=6)
        self.log = LogConsole(log_frame, height=24)
        self.log.pack(fill='both', expand=True)

    # ---------- handlers ----------

    def disc_opened(self):
        if self.app.disc:
            default_out = self.app.disc.patches_dir.parent / 'output' / 'track03.iso'
            self.out_var.set(str(default_out))

    def _browse(self):
        p = filedialog.asksaveasfilename(
            title='Save patched disc image as',
            defaultextension='.iso',
            filetypes=[('Disc image', '*.iso'), ('All', '*.*')],
            parent=self.app,
        )
        if p: self.out_var.set(p)

    def _on_build(self):
        if not self.app.disc:
            messagebox.showinfo('No disc', 'Open a disc in tab 1 first.', parent=self.app)
            return
        out_path = self.out_var.get().strip()
        if not out_path:
            messagebox.showinfo('No output path', 'Pick where to save the new disc image.', parent=self.app)
            return
        self.build_btn.config(state='disabled')

        def runner():
            try:
                self.log.append('=== Pre-flight integrity check ===', tag='ok')
                result = disc_core.integrity_check(
                    self.app.disc, progress=lambda m: self.log.append('  ' + m),
                )
                if not result['safe_to_build']:
                    self.log.append('!! refusing to build — fix oversize/orphan issues first', tag='error')
                    return
                self.log.append('=== Patch ===', tag='ok')
                iso = disc_core.patch_and_verify(
                    self.app.disc, Path(out_path),
                    progress=lambda m: self.log.append('  ' + m),
                )
                self.log.append('=== GDI sidecar ===', tag='ok')
                gdi = disc_core.generate_gdi_sidecar(
                    self.app.disc.source_gdi, iso,
                    progress=lambda m: self.log.append('  ' + m),
                )
                self.log.append(f'\n✓ Patched disc: {iso}', tag='ok')
                self.log.append(f'✓ GDI sidecar:  {gdi}', tag='ok')
                self.log.append(
                    '\nReminder: copy track01.iso and track02.raw next to the new .gdi '
                    'so emulators (Flycast/Redream) can load it.',
                    tag='warn',
                )
            except Exception as e:
                self.log.append(f'!! BUILD FAILED: {e}', tag='error')
            finally:
                self.after(0, lambda: self.build_btn.config(state='normal'))

        threading.Thread(target=runner, daemon=True).start()
