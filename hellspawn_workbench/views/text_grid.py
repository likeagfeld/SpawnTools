"""Tab 3 — Text & Pointer Grid.

A spreadsheet of every JP string scanned from 1ST_READ.BIN (+ optionally
MESSAGE.INI and other small *.INI files). Columns:
  Offset  |  Pointer  |  Raw Hex  |  JP  |  Translated  |  Byte Status  |  Notes

Bottom: editor card for the currently-selected row.

Pointer-relocation info is REPORT-ONLY by default (campaign hard rule:
shrink or equal; never grow). The "Byte Status" column shows when an
oversize EN would require relocation; the user has to manually shorten.
"""
from __future__ import annotations
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

from ..core import strings as strings_core
from ..core import encoding as enc_core
from ..core import pointers as ptr_core


SAFE_SCAN_FILES = ('1ST_READ.BIN',)


class TextGridTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=6)
        self.app = app
        self.db: strings_core.StringDB | None = None
        self._iid_to_id: dict[str, int] = {}
        self._current_id: int | None = None
        self._build()

    def _build(self):
        # ---------- top bar ----------
        top = ttk.Frame(self); top.pack(fill='x', pady=(0, 6))
        ttk.Button(top, text='Scan 1ST_READ.BIN', command=self._on_scan).pack(side='left', padx=2)
        ttk.Button(top, text='Apply ALL done → patches/', command=self._on_commit,
                   style='Accent.TButton').pack(side='left', padx=2)
        ttk.Separator(top, orient='vertical').pack(side='left', fill='y', padx=8)
        ttk.Label(top, text='Show:').pack(side='left')
        self.show_var = tk.StringVar(value='All')
        for v in ('All', 'To-do', 'Done', 'Oversize', 'Skipped'):
            ttk.Radiobutton(top, text=v, value=v, variable=self.show_var,
                            command=self._refresh).pack(side='left', padx=2)
        ttk.Separator(top, orient='vertical').pack(side='left', fill='y', padx=8)
        ttk.Label(top, text='Filter:').pack(side='left')
        self.filter_var = tk.StringVar()
        ent = ttk.Entry(top, textvariable=self.filter_var, width=22)
        ent.pack(side='left', padx=4)
        ent.bind('<KeyRelease>', lambda _e: self._refresh())
        self.counts_var = tk.StringVar(value='—')
        ttk.Label(top, textvariable=self.counts_var, foreground='#666').pack(side='right', padx=4)

        # ---------- middle: spreadsheet ----------
        mid = ttk.Frame(self); mid.pack(fill='both', expand=True)
        cols = ('file', 'offset', 'budget', 'jp', 'en', 'status')
        self.tree = ttk.Treeview(mid, columns=cols, show='headings', height=18)
        self.tree.heading('file', text='File')
        self.tree.heading('offset', text='Offset')
        self.tree.heading('budget', text='Bytes')
        self.tree.heading('jp', text='Japanese')
        self.tree.heading('en', text='English')
        self.tree.heading('status', text='Status')
        self.tree.column('file', width=140, anchor='w')
        self.tree.column('offset', width=80, anchor='e')
        self.tree.column('budget', width=80, anchor='e')
        self.tree.column('jp', width=220, anchor='w')
        self.tree.column('en', width=220, anchor='w')
        self.tree.column('status', width=80, anchor='center')
        vs = ttk.Scrollbar(mid, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side='left', fill='both', expand=True)
        vs.pack(side='right', fill='y')
        # Tag colors per status
        self.tree.tag_configure('done', foreground='#0a7d33')
        self.tree.tag_configure('todo', foreground='#444')
        self.tree.tag_configure('oversize', foreground='#cc0000')
        self.tree.tag_configure('skip', foreground='#888')
        self.tree.bind('<<TreeviewSelect>>', self._on_pick_row)

        # ---------- bottom: editor card ----------
        ed = ttk.LabelFrame(self, text='Edit', padding=8)
        ed.pack(fill='x', pady=(6, 0))

        info = ttk.Frame(ed); info.pack(fill='x', pady=2)
        self.row_info_var = tk.StringVar(value='Pick a row above to edit.')
        ttk.Label(info, textvariable=self.row_info_var, foreground='#444').pack(anchor='w')

        ttk.Label(ed, text='Japanese:', font=('TkDefaultFont', 9, 'bold')).pack(anchor='w')
        self.jp_text = tk.Text(ed, height=2, wrap='word', state='disabled',
                                bg='#1a1a1a', fg='#dde', font=('MS Gothic', 11))
        self.jp_text.pack(fill='x', pady=(0, 4))

        ttk.Label(ed, text='English (cp932 only — keep ≤ byte budget):',
                  font=('TkDefaultFont', 9, 'bold')).pack(anchor='w')
        self.en_text = tk.Text(ed, height=3, wrap='word', font=('Segoe UI', 11))
        self.en_text.pack(fill='x', pady=(0, 4))
        self.en_text.bind('<KeyRelease>', lambda _e: self._update_meter())

        meter_row = ttk.Frame(ed); meter_row.pack(fill='x')
        self.meter_var = tk.StringVar(value='')
        ttk.Label(meter_row, textvariable=self.meter_var).pack(side='left', padx=4)
        ttk.Button(meter_row, text='Save', command=self._on_save).pack(side='right', padx=2)
        ttk.Button(meter_row, text='Mark Skip', command=lambda: self._on_mark('skip')).pack(side='right', padx=2)
        ttk.Button(meter_row, text='Mark To-do', command=lambda: self._on_mark('todo')).pack(side='right', padx=2)
        ttk.Button(meter_row, text='Revert to JP', command=self._on_revert).pack(side='right', padx=2)
        ttk.Button(meter_row, text='Use dict suggestion',
                   command=self._on_apply_dict_hint).pack(side='right', padx=2)
        self.en_text.bind('<Control-Return>', lambda _e: self._on_save())

    # ---------- bindings to app ----------

    def disc_opened(self):
        # Open the DB (it lives inside the project dir)
        if not self.app.disc:
            return
        db_path = self.app.disc.patches_dir.parent / 'strings.sqlite'
        self.db = strings_core.StringDB(db_path)
        self._refresh()

    # ---------- handlers ----------

    def _on_scan(self):
        if not self.db or not self.app.disc:
            messagebox.showinfo('Open disc first', 'Open a disc in tab 1 first.', parent=self.app)
            return
        # Run on a thread; the scan is fast but file I/O can vary
        def runner():
            n_total = 0
            for fname in SAFE_SCAN_FILES:
                p = self.app.disc.patches_dir / fname
                if not p.is_file(): continue
                if fname in strings_core.DENY_LIST: continue
                self.app.log_workspace(f'scanning {fname}…')
                n = self.db.scan_file(p, fname)
                self.app.log_workspace(f'  {fname}: {n} new strings')
                n_total += n
            self.app.log_workspace(f'scan complete: +{n_total} rows', tag='ok')
            self.after(0, self._refresh)
        threading.Thread(target=runner, daemon=True).start()

    def _refresh(self):
        if not self.db:
            return
        self.tree.delete(*self.tree.get_children())
        self._iid_to_id.clear()
        wanted = self.show_var.get()
        filt = self.filter_var.get().strip().lower()
        for e in self.db.all_entries():
            if wanted == 'To-do' and e.status != 'todo': continue
            if wanted == 'Done' and e.status != 'done': continue
            if wanted == 'Oversize' and e.status != 'oversize': continue
            if wanted == 'Skipped' and e.status != 'skip': continue
            if filt and (filt not in (e.jp_text or '').lower()
                          and filt not in (e.en_text or '').lower()
                          and filt not in (e.source_file or '').lower()):
                continue
            tag = (e.status,)
            iid = self.tree.insert('', 'end', tags=tag, values=(
                e.source_file,
                f'0x{e.byte_offset:x}',
                e.byte_status,
                (e.jp_text or '')[:30] + ('…' if e.jp_text and len(e.jp_text) > 30 else ''),
                (e.en_text or '')[:30] + ('…' if e.en_text and len(e.en_text) > 30 else ''),
                e.status,
            ))
            self._iid_to_id[iid] = e.id
        c = self.db.counts()
        self.counts_var.set(
            f"total: {c.get('total', 0)}   "
            f"todo: {c.get('todo', 0)}   done: {c.get('done', 0)}   "
            f"oversize: {c.get('oversize', 0)}   skip: {c.get('skip', 0)}"
        )

    def _on_pick_row(self, _evt=None):
        sel = self.tree.selection()
        if not sel: return
        eid = self._iid_to_id.get(sel[0])
        if eid is None: return
        e = self.db.get(eid)
        if not e: return
        self._current_id = eid
        self.row_info_var.set(
            f'{e.source_file}  @  0x{e.byte_offset:x}    budget {e.byte_budget} bytes   status: {e.status}'
        )
        self.jp_text.config(state='normal')
        self.jp_text.delete('1.0', 'end')
        self.jp_text.insert('1.0', e.jp_text)
        self.jp_text.config(state='disabled')
        self.en_text.delete('1.0', 'end')
        self.en_text.insert('1.0', e.en_text)
        self._update_meter()

    def _update_meter(self):
        if self._current_id is None: return
        e = self.db.get(self._current_id)
        en = self.en_text.get('1.0', 'end-1c').rstrip('\n')
        used = enc_core.cp932_len(en) if en else 0
        budget = e.byte_budget
        color = '#066b00'
        if used > budget:
            color = '#cc0000'
        elif budget > 0 and used >= budget * 0.85:
            color = '#cc7700'
        self.meter_var.set(f'{used:3d} / {budget} bytes')
        # NB: meter color tinting would need ttk.Style; we keep it text-only for portability

    def _on_save(self):
        if self._current_id is None: return
        en = self.en_text.get('1.0', 'end-1c').rstrip('\n')
        ok, msg = self.db.set_en(self._current_id, en)
        self.app.log_workspace(f'  string #{self._current_id}: {msg}',
                                tag='ok' if ok else 'warn')
        self._refresh()

    def _on_mark(self, status: str):
        if self._current_id is None: return
        self.db.set_status(self._current_id, status)
        self.app.log_workspace(f'  string #{self._current_id}: marked {status}')
        self._refresh()

    def _on_revert(self):
        if self._current_id is None: return
        from ..core import preset as preset_core
        ok, msg = preset_core.revert_entry(
            self.db, self._current_id, self.app.disc,
            progress=lambda m: self.app.log_workspace(m),
        )
        self.app.log_workspace(f'  revert: {msg}', tag='warn' if ok else 'error')
        if ok:
            self._refresh()
            # Re-select the same row
            for iid, eid in self._iid_to_id.items():
                if eid == self._current_id:
                    self.tree.selection_set(iid)
                    self._on_pick_row()
                    break

    def _on_apply_dict_hint(self):
        if self._current_id is None: return
        e = self.db.get(self._current_id)
        if not e or not e.notes:
            return
        # Notes field has format "dict suggests: 'EN text'"
        import re
        m = re.search(r"dict suggests:\s*'(.+?)'", e.notes)
        if not m:
            return
        suggestion = m.group(1)
        self.en_text.delete('1.0', 'end')
        self.en_text.insert('1.0', suggestion)
        self._update_meter()

    def _on_commit(self):
        if not self.db or not self.app.disc:
            return
        if not messagebox.askyesno(
            'Commit translations?',
            'Apply every "done" English translation into patches/ files now?\n\n'
            "Each modified file will be backed up to backups/ first. "
            "Files are written shrink-or-equal-size; oversize entries are skipped.",
            parent=self.app):
            return

        def runner():
            from ..core import strings as sc
            result = sc.commit_all_done(
                self.db, self.app.disc.patches_dir,
                progress=lambda m: self.app.log_workspace(m),
            )
            self.app.log_workspace(
                f'commit: {result["files_modified"]} files modified, '
                f'{result["strings_applied"]} strings applied, '
                f'{result["skipped"]} skipped',
                tag='ok',
            )
        threading.Thread(target=runner, daemon=True).start()
