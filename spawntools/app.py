"""SpawnTools — main App (4-tab Tk root).

Wires together:
  • config.Config        — persistent paths & flags
  • core.disc.DiscContext — currently-opened disc info
  • Four view tabs       — workspace, textures, text_grid, master_build

On launch:
  1. Load Config from ~/.spawntools/config.json
  2. Verify _shared_tools/ is importable — if not, prompt the user once
  3. Build the 4-tab notebook
  4. If a last-used disc path is in config, optionally pre-populate
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .config import Config
from .core.disc import DiscContext
from .views.workspace import WorkspaceTab
from .views.textures import TexturesTab
from .views.text_grid import TextGridTab
from .views.master_build import MasterBuildTab


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('SpawnTools — Spawn translation suite')
        self.cfg = Config.load()
        self.geometry(self.cfg.window_geometry)
        self.minsize(1100, 700)

        self.disc: DiscContext | None = None

        # Configure ttk styles
        style = ttk.Style(self)
        try: style.theme_use(self.cfg.theme)
        except Exception: pass
        style.configure('Accent.TButton', font=('TkDefaultFont', 9, 'bold'))

        # Bootstrap _shared_tools/
        if not self.cfg.ensure_shared_tools():
            self.after(120, self._prompt_for_shared_tools)

        # Build menus + notebook
        self._build_menu()
        self._build_notebook()
        self._build_status()

    def _build_menu(self):
        menubar = tk.Menu(self)
        file_m = tk.Menu(menubar, tearoff=0)
        file_m.add_command(label='Settings…', command=self._open_settings)
        file_m.add_separator()
        file_m.add_command(label='Quit', command=self.destroy)
        menubar.add_cascade(label='File', menu=file_m)

        help_m = tk.Menu(menubar, tearoff=0)
        help_m.add_command(label='About', command=self._about)
        help_m.add_command(label='Open README', command=self._open_readme)
        menubar.add_cascade(label='Help', menu=help_m)

        self.config(menu=menubar)

    def _build_notebook(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill='both', expand=True, padx=4, pady=4)

        self.tab_workspace = WorkspaceTab(self.nb, app=self)
        self.tab_textures = TexturesTab(self.nb, app=self)
        self.tab_text_grid = TextGridTab(self.nb, app=self)
        self.tab_build = MasterBuildTab(self.nb, app=self)

        self.nb.add(self.tab_workspace, text='1 · Workspace & QA')
        self.nb.add(self.tab_textures, text='2 · Texture Workbench')
        self.nb.add(self.tab_text_grid, text='3 · Text & Pointer Grid')
        self.nb.add(self.tab_build, text='4 · Master Build')

    def _build_status(self):
        bar = ttk.Frame(self, relief='sunken')
        bar.pack(side='bottom', fill='x')
        self.status_var = tk.StringVar(value='Ready.')
        ttk.Label(bar, textvariable=self.status_var, anchor='w').pack(side='left', padx=8)

    # ---------- cross-tab plumbing ----------

    def set_disc_context(self, dctx: DiscContext) -> None:
        self.disc = dctx
        self.status_var.set(f'Disc: {dctx.source_gdi.name}   patches/: {dctx.patches_dir}')

    def notify_disc_opened(self) -> None:
        """Called by tab 1 after a successful open. Other tabs refresh."""
        try: self.tab_textures.reload()
        except Exception: pass
        try: self.tab_text_grid.disc_opened()
        except Exception: pass
        try: self.tab_build.disc_opened()
        except Exception: pass

    def log_workspace(self, msg: str, tag: str | None = None) -> None:
        """Other tabs route log lines to Tab 1's console for unified history."""
        try: self.tab_workspace.log.append(msg, tag)
        except Exception: pass

    # ---------- menu actions ----------

    def _prompt_for_shared_tools(self):
        messagebox.showinfo(
            'Locate _shared_tools',
            'SpawnTools needs to know where the canonical codec library '
            'lives (the folder with process_game.py, pvr_codec.py, tex_decode.py, '
            'tex_repack.py).\n\n'
            "Click OK and pick that folder.",
            parent=self,
        )
        d = filedialog.askdirectory(title='Locate _shared_tools/ folder', parent=self)
        if d:
            self.cfg.shared_tools_path = d
            self.cfg.save()
            if self.cfg.ensure_shared_tools():
                self.status_var.set('Shared tools located. Ready.')
            else:
                messagebox.showerror(
                    'Still missing',
                    f'process_game.py / pvr_codec.py / tex_decode.py not found in {d}.\n\n'
                    "Open Settings to try again.",
                    parent=self,
                )

    def _open_settings(self):
        SettingsDialog(self, self.cfg)

    def _about(self):
        from . import __version__
        messagebox.showinfo(
            'About',
            f'SpawnTools v{__version__}\n\n'
            f'Spawn — In the Demon\'s Hand translation suite.\n'
            f'Built on the proven _shared_tools/ codec library.\n\n'
            f'See README.md for the spec-vs-Spawn-reality reconciliation '
            f'(AFS / pointer relocation / mkisofs / tbl).',
            parent=self,
        )

    def _open_readme(self):
        import webbrowser
        from pathlib import Path
        readme = Path(__file__).resolve().parent / 'README.md'
        if readme.exists():
            webbrowser.open(readme.as_uri())


class SettingsDialog(tk.Toplevel):
    """File → Settings… — edit Config fields and persist."""

    def __init__(self, parent: App, cfg: Config):
        super().__init__(parent)
        self.title('Settings')
        self.geometry('560x180')
        self.transient(parent)
        self.cfg = cfg

        def add_path(row, label, var, picker_kind='dir'):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky='e', padx=6, pady=4)
            ttk.Entry(self, textvariable=var, width=60).grid(row=row, column=1, sticky='ew', padx=4)
            def browse():
                if picker_kind == 'dir':
                    p = filedialog.askdirectory(parent=self)
                else:
                    p = filedialog.askopenfilename(parent=self,
                                                    filetypes=[('Executable', '*.exe'), ('All', '*.*')])
                if p: var.set(p)
            ttk.Button(self, text='Browse…', command=browse).grid(row=row, column=2, padx=4)

        # Codec library is now bundled at spawntools/codecs/ — no setting needed.
        # xdelta3 path is unused by the in-place patch pipeline — removed.
        # Only the pointer-growth toggle survives.
        self.allow_growth_var = tk.BooleanVar(value=cfg.allow_pointer_growth)

        ttk.Checkbutton(
            self,
            text='Allow pointer growth (UNSAFE — disabled by default; see README §2)',
            variable=self.allow_growth_var,
        ).grid(row=0, column=1, sticky='w', padx=4, pady=8)

        ttk.Label(
            self,
            text=('The campaign\'s hard rule is shrink-or-equal.\n'
                  'Enabling pointer growth lets the Text Grid attempt to relocate '
                  'oversize strings into null padding. Spawn v20 bricked the disc '
                  'doing this without strict context checks. Use at your own risk.'),
            foreground='#666', wraplength=560, justify='left',
        ).grid(row=1, column=1, sticky='w', padx=4, pady=4)

        btns = ttk.Frame(self); btns.grid(row=2, column=0, columnspan=3, pady=12)
        ttk.Button(btns, text='Save', command=self._save, style='Accent.TButton').pack(side='left', padx=4)
        ttk.Button(btns, text='Cancel', command=self.destroy).pack(side='left')

        self.columnconfigure(1, weight=1)

    def _save(self):
        self.cfg.allow_pointer_growth = self.allow_growth_var.get()
        self.cfg.save()
        self.destroy()
