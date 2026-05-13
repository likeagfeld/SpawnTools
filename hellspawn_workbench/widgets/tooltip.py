"""Tiny hover tooltip — tk has none built in."""
from __future__ import annotations
import tkinter as tk


class Tooltip:
    def __init__(self, widget, text: str, delay_ms: int = 400):
        self.widget = widget
        self.text = text
        self.delay = delay_ms
        self._tip = None
        self._after_id = None
        widget.bind('<Enter>', self._enter, add='+')
        widget.bind('<Leave>', self._leave, add='+')
        widget.bind('<ButtonPress>', self._leave, add='+')

    def _enter(self, _e):
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _leave(self, _e):
        self._cancel(); self._hide()

    def _cancel(self):
        if self._after_id:
            try: self.widget.after_cancel(self._after_id)
            except Exception: pass
            self._after_id = None

    def _show(self):
        if self._tip: return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        t = tk.Toplevel(self.widget)
        t.wm_overrideredirect(True)
        t.wm_geometry(f'+{x}+{y}')
        tk.Label(t, text=self.text, bg='#222', fg='#eee',
                  padx=6, pady=3, font=('TkDefaultFont', 9),
                  relief='solid', borderwidth=1, wraplength=320).pack()
        self._tip = t

    def _hide(self):
        if self._tip:
            try: self._tip.destroy()
            except Exception: pass
            self._tip = None
