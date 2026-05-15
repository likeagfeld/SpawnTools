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
        self.title('SpawnTools — Capcom Dreamcast translation suite')
        self.cfg = Config.load()
        self.geometry(self.cfg.window_geometry)
        self.minsize(1100, 700)

        # Window/taskbar icon
        from pathlib import Path as _P
        icon_root = _P(__file__).resolve().parent.parent / 'assets' / 'icons'
        try:
            ico = icon_root / 'spawn.ico'
            if ico.is_file():
                self.iconbitmap(default=str(ico))
        except Exception:
            pass
        # PhotoImage fallback (Linux/macOS dock + Tk built-in icon path)
        try:
            from tkinter import PhotoImage
            png = icon_root / 'spawn-256.png'
            if png.is_file():
                self._app_icon_img = PhotoImage(file=str(png))
                self.iconphoto(True, self._app_icon_img)
        except Exception:
            pass

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
        help_m.add_command(label='Help…', command=self._open_help)
        help_m.add_command(label='About SpawnTools', command=self._about)
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
            'About SpawnTools',
            f'SpawnTools v{__version__}\n\n'
            f'A GUI for translating Capcom Dreamcast titles.\n'
            f'Auto-detects which of 15 supported games you loaded via the '
            f'Sega IP.BIN product code, then pre-fills the right baseline.\n\n'
            f'Built on the codec library used to ship the existing Spawn '
            f'EN patch.\n\n'
            f'https://github.com/likeagfeld/SpawnTools',
            parent=self,
        )

    def _open_help(self):
        HelpDialog(self)


HELP_SECTIONS = [
    ('Getting started', """\
1. Click Open / Extract on Tab 1 and pick the Dreamcast disc (.gdi / .iso / .bin).
2. SpawnTools reads the disc's IP.BIN product code and auto-detects which of the
   15 supported games you loaded. The detected name shows next to "Game:".
3. Click Load Baseline → the bundled JP→EN translations are seeded into Tab 3
   AND committed into your patches/ dir. Tab 2 lights up with ● modified for
   every texture the campaign already redrew (Spawn ships 22 pre-built textures
   inside the release; other games will fill in as community patches publish).
4. Edit anything you want on Tabs 2 + 3, then go to Tab 4 → Master Build to
   bake a new track03 and a sidecar .gdi.

Hard rules the tool enforces automatically:
  - Track03 byte size stays identical (no disc layout drift)
  - Every replaced file is ≤ original byte size (shrink-or-equal)
  - FONT/SOFTKEY/MOJI/MINCHO atlases are flagged protected (touching them
    breaks the runtime text renderer)
  - 2_DP.BIN / GAME.BIN / GGAM.BIN / MEMDEF.BIN are deny-listed from the
    bulk JP scanner (they have CJK bytes as data, not strings)\
"""),
    ('Tab 1 — Workspace & QA', """\
Disc:    .gdi/.iso/.bin file picker. Auto-fills Project dir; if the GDI sits
         inside an existing campaign workspace (peer extracted/ + patches/
         dirs), that workspace is reused so your edits aren't dropped.
Project: where SpawnTools will store extracted/, patches/, backups/, strings.sqlite.

Buttons:
  Open / Extract            — extract disc into project/extracted, mirror to patches/
  Validate Integrity        — audit patches/ vs extracted/ for oversize / orphans
  Load Baseline →           — seed Tab 3 + write campaign EN bytes into patches/
  Reset Patches → Stock JP  — wipe patches/, restart from JP baseline
  Fetch latest from GitHub  — download the canonical .dcp EN patch for the
                              auto-detected game, then apply + auto-Load Baseline
  Browse local .dcp…        — apply any .dcp you have on disk + auto-Load Baseline

"Game:" label is read-only — IP.BIN is authoritative; you can't override the
detected game. If the disc isn't one of the 15 supported titles the label says so.\
"""),
    ('Tab 2 — Texture Workbench', """\
Left panel:
  Show: All / Modified / Stock filter (modified = patches/ differs from extracted/)
  Filter box: substring match on filename
  File tree: every .TEX / .PVR / archive-member (AFS, PAC, PVS, PZZ, SLW, PVZ),
    plus loose .BIN files with embedded PVRT/GBIX magic, plus Capcom proprietary
    raw-pixel containers (MvC2 STG*TEX.BIN, Power Stone 2 *_CONNECT.BIN, etc.)
  Sub-tex list: every record inside the current container

Center: side-by-side Original (extracted/) vs Translated (patches/) previews.

Right panel — actions grouped by scope:
  Export to PNG          Export Original (JP baseline) · Export Modified (current patches/)
  Edit this sub-tex      Import & Auto-Convert (this sub-tex) · Revert this sub-tex → JP
                         (re-encodes PNG using the original pixfmt/datafmt; the
                          revert sidesteps the decoder and byte-slices the
                          baseline TXB0 pixel region, so it works even on the
                          non-square RECTANGLE_TWIDDLED sub-textures the decoder
                          can't render)
  Whole-file actions     Restore WHOLE file → baseline · Revert WHOLE file → JP

Raw-blob format override:
  For Capcom proprietary BIN containers, the tool picks the right
  (pixfmt, datafmt) automatically per game from bundled raw_format_profiles.json
  (derived from Ghidra+FIDB attribution + verified samples). If a particular
  chunk needs a different format, use the "Format override" combos in the right
  panel.\
"""),
    ('Tab 3 — Text & Pointer Grid', """\
Spreadsheet of every JP string scanned from the loaded game's preset.scan_targets.
Targets are per-game evidence-based (CvS Pro adds 18 stage TEX-BINs + ASK.BIN,
MvC2 adds 20 per-character _DAT.BIN files, JoJo adds 12 character-training
archives, SF III adds PLAYER/PL*.BIN, etc. — see bundled/game_registry.py).

Columns: File, Offset, Bytes, Japanese, English, Status.

Status filter: All / To-do / Done / Oversize / Skipped.

Buttons:
  Scan for JP             — re-scan preset.scan_targets and populate the grid
  Apply ALL done → patches — write every "done" row's EN bytes into patches/<file>
                            at the recorded offset, null-padded to byte_budget.
                            Sanity-checks that the JP bytes are at the offset
                            BEFORE writing (so re-runs are safe).

Right-click a row for: Revert to JP / Use dict suggestion / Mark skipped.

Byte budget rule: EN must fit in the original JP byte length. The grid flags
oversize entries red so you can shorten them before committing.\
"""),
    ('Tab 4 — Master Build', """\
1. Pre-flight integrity check (same as Tab 1's Validate Integrity)
2. In-place track03 patch via process_game.patch_iso — every modified file is
   written back at its ORIGINAL LBA so the disc layout / boot path stays intact
3. MD5-verified disc-vs-patches sync — if the disc bytes don't match patches/
   bytes at every modified region, the build fails and the disc isn't shipped
4. Writes a sidecar .gdi pointing at the new track03 — load THAT .gdi in
   Flycast / Redream to boot-test

Output goes to project/disc/disc-patched.gdi (or similar).\
"""),
    ('Supported games (15)', """\
Auto-detected via the Sega IP.BIN product code at track03 offset 0x40:

  T1216M Spawn — In the Demon's Hand
  T1247M Capcom vs. SNK — Millennium Fight 2000 Pro
  T1246M Heavy Metal — Geomatrix
  T1231M JoJo's Bizarre Adventure
  T1215M Marvel vs. Capcom 2
  T1234M Net de Tennis
  T1218M Power Stone 2
  T1221M Project Justice (Moero Justice Gakuen)
  T1209M Street Fighter III 3rd Strike
  T1230M Street Fighter Zero 3 for Matching Service
  T1250M Super Puzzle Fighter IIX (MS)
  T1236M Super Street Fighter IIX (MS)
  T1248M Taisen Net Gimmick (Capcom & Psikyo All Stars)
  T1232M Tech Romancer (MS)
  T1235M Vampire Chronicle (MS)

Bundled translation pairs total ~26,800 (Spawn 1,575; CvS Pro 10,093;
JoJo 1,489; MvC2 720; Power Stone 2 849; …).\
"""),
    ('Troubleshooting', """\
"Load Baseline shows 0 done":
  Make sure you opened the disc first (Tab 1 → Open / Extract). Load Baseline
  needs an active disc to know which preset to load.

"Tab 2 shows 0 modified after Load Baseline":
  This was a v1.1.0 bug fixed in v1.2.0. Update to v1.2.0+.

"Integrity audit reports orphans":
  Files with names ending in .bak / .pre_*_revert / .tmp / .new / .swp / .DS_Store /
  Thumbs.db are skipped. Any other file in patches/ not present in extracted/
  needs to be removed before the disc-build pipeline will run.

"Fetch latest from GitHub failed":
  The per-game .dcp URL is registered in spawntools/core/dcp.py:DCP_URLS.
  Currently only Spawn has a URL. For other games, use Browse local .dcp…
  with a .dcp you have on disk.

".dcp apply errors with 'pyxdelta is required'":
  The launcher auto-installs pyxdelta on first run. If pip can't build the C
  extension on your system, install Visual C++ Build Tools (Windows) or
  apply the .dcp externally with a DCP-compatible tool first.

"Disc won't boot after Master Build":
  Run Tab 1 → Validate Integrity. If "safe_to_build" is True and the disc
  still won't boot, you may have edited a protected glyph atlas (FONT/SOFTKEY/
  MOJI/MINCHO PVRs). Revert those files and try again.\
"""),
    ('About', """\
SpawnTools is built on the codec library used to ship the existing Spawn EN
patch (T-En patch by Farkus, V0.2). The Spawn .dcp is bundled — apply it
externally if you just want the patch and don't need the tool.

Repository: https://github.com/likeagfeld/SpawnTools
Latest release: https://github.com/likeagfeld/SpawnTools/releases/latest

License: MIT.\
"""),
]


class HelpDialog(tk.Toplevel):
    """Embedded help window — left sidebar of sections, right pane of text."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title('SpawnTools — Help')
        self.geometry('900x600')
        self.transient(parent)

        # Two-column split
        paned = ttk.Panedwindow(self, orient='horizontal')
        paned.pack(fill='both', expand=True, padx=6, pady=6)

        # Left: section list
        left = ttk.Frame(paned)
        paned.add(left, weight=0)
        ttk.Label(left, text='Topics', font=('TkDefaultFont', 10, 'bold')
                  ).pack(anchor='w', padx=4, pady=2)
        self.section_list = tk.Listbox(left, width=28, exportselection=False)
        for title, _ in HELP_SECTIONS:
            self.section_list.insert('end', title)
        self.section_list.pack(fill='both', expand=True, padx=4, pady=2)
        self.section_list.bind('<<ListboxSelect>>', self._on_pick)

        # Right: content
        right = ttk.Frame(paned)
        paned.add(right, weight=1)
        from tkinter.scrolledtext import ScrolledText
        self.text = ScrolledText(right, wrap='word', font=('TkDefaultFont', 10),
                                  padx=10, pady=10)
        self.text.pack(fill='both', expand=True)
        self.text.config(state='disabled')

        # Footer
        btns = ttk.Frame(self); btns.pack(fill='x', pady=4)
        ttk.Button(btns, text='Open GitHub repo',
                   command=self._open_repo).pack(side='left', padx=6)
        ttk.Button(btns, text='Close', command=self.destroy
                   ).pack(side='right', padx=6)

        self.section_list.selection_set(0)
        self._show(0)

    def _on_pick(self, _evt=None):
        sel = self.section_list.curselection()
        if sel: self._show(sel[0])

    def _show(self, idx: int):
        if 0 <= idx < len(HELP_SECTIONS):
            _, body = HELP_SECTIONS[idx]
            self.text.config(state='normal')
            self.text.delete('1.0', 'end')
            self.text.insert('1.0', body)
            self.text.config(state='disabled')

    def _open_repo(self):
        import webbrowser
        webbrowser.open('https://github.com/likeagfeld/SpawnTools')


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
