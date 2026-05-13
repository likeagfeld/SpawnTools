"""A scrollable monospaced text-log widget used by Tab 1 and Tab 4."""
from __future__ import annotations
import time
import tkinter as tk
from tkinter import ttk


class LogConsole(tk.Frame):
    """Append-only log view. Thread-safe `append()` via Tk's after-queue."""

    def __init__(self, parent, height: int = 16):
        super().__init__(parent)
        self.text = tk.Text(
            self, height=height, wrap='word',
            bg='#0a0e13', fg='#d9e2eb', insertbackground='#fff',
            relief='flat', bd=0,
            font=('Consolas', 10),
        )
        vs = ttk.Scrollbar(self, orient='vertical', command=self.text.yview)
        self.text.configure(yscrollcommand=vs.set)
        self.text.pack(side='left', fill='both', expand=True)
        vs.pack(side='right', fill='y')
        # Color tags
        self.text.tag_configure('error', foreground='#ff7a7a')
        self.text.tag_configure('warn', foreground='#ffba66')
        self.text.tag_configure('ok', foreground='#85d18e')
        self.text.tag_configure('dim', foreground='#7f8c93')
        self.text.config(state='disabled')

    def append(self, msg: str, tag: str | None = None) -> None:
        """Append a line. Safe to call from any thread."""
        try:
            self.after(0, self._do_append, msg, tag)
        except RuntimeError:
            # widget may have been destroyed
            pass

    def _do_append(self, msg: str, tag: str | None) -> None:
        try:
            self.text.config(state='normal')
            ts = time.strftime('%H:%M:%S')
            self.text.insert('end', f'[{ts}]  ', 'dim')
            if tag:
                self.text.insert('end', msg + '\n', tag)
            else:
                self.text.insert('end', msg + '\n')
            self.text.see('end')
            self.text.config(state='disabled')
        except tk.TclError:
            pass

    def clear(self) -> None:
        self.text.config(state='normal')
        self.text.delete('1.0', 'end')
        self.text.config(state='disabled')
