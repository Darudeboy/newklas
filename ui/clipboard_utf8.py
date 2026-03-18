"""
Кириллица из буфера в полях CustomTkinter.

Проблема: у Tk на macOS стандартный <<Paste>> в Entry часто портит UTF-8.
Решение: pyperclip + перехват <<Paste>> на внутренних Entry/Text + глобальные Cmd/Ctrl+V.
"""
from __future__ import annotations

import sys
import tkinter as tk
from typing import Any, Callable, Optional

import customtkinter as ctk


def _clipboard_unicode(app: tk.Misc) -> str:
    try:
        import pyperclip

        s = pyperclip.paste()
        if isinstance(s, str):
            return s
        return str(s) if s is not None else ""
    except Exception:
        pass
    try:
        s = app.clipboard_get()
        if isinstance(s, str) and s:
            return s
    except tk.TclError:
        pass
    if sys.platform == "darwin":
        try:
            import subprocess

            r = subprocess.run(
                ["pbpaste"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if r.returncode == 0 and r.stdout is not None:
                return r.stdout
        except Exception:
            pass
    return ""


def _paste_into_entry_widget(w: tk.Entry, app: tk.Misc) -> None:
    text = _clipboard_unicode(app)
    if not text:
        return
    try:
        st = str(w.cget("state") or "").lower()
        if st in ("readonly", "disabled"):
            return
    except tk.TclError:
        return
    try:
        if w.selection_present():
            w.delete("sel.first", "sel.last")
    except tk.TclError:
        pass
    w.insert("insert", text)


def _paste_into_text_widget(w: tk.Text, app: tk.Misc) -> None:
    text = _clipboard_unicode(app)
    if not text:
        return
    try:
        if w.tag_ranges("sel"):
            w.delete("sel.first", "sel.last")
    except tk.TclError:
        pass
    w.insert("insert", text)


def paste_into_focused_widget(app: tk.Misc) -> bool:
    w = app.focus_get()
    if w is None:
        return False
    try:
        wc = w.winfo_class()
    except tk.TclError:
        return False
    if wc in ("Entry", "TEntry"):
        _paste_into_entry_widget(w, app)  # type: ignore[arg-type]
        return True
    if wc == "Text":
        _paste_into_text_widget(w, app)  # type: ignore[arg-type]
        return True
    return False


def _bind_paste_on_entry(inner: tk.Entry, app: tk.Misc) -> None:
    def on_paste(_event: tk.Event) -> str:
        _paste_into_entry_widget(inner, app)
        return "break"

    inner.bind("<<Paste>>", on_paste)


def _bind_paste_on_text(inner: tk.Text, app: tk.Misc) -> None:
    def on_paste(_event: tk.Event) -> str:
        _paste_into_text_widget(inner, app)
        return "break"

    inner.bind("<<Paste>>", on_paste)


def _scan_widgets(root: Any, app: tk.Misc) -> None:
    def scan(w: Any) -> None:
        try:
            children = w.winfo_children()
        except tk.TclError:
            return
        if isinstance(w, ctk.CTkEntry):
            inner = getattr(w, "_entry", None)
            if inner is not None:
                _bind_paste_on_entry(inner, app)
        elif isinstance(w, ctk.CTkTextbox):
            inner = getattr(w, "_textbox", None)
            if inner is not None:
                _bind_paste_on_text(inner, app)
        for ch in children:
            scan(ch)

    scan(root)


def _add_edit_menu_paste(app: Any, paste_fn: Callable[[], bool]) -> None:
    if getattr(app, "_blast_edit_menu_added", False):
        return
    app._blast_edit_menu_added = True  # type: ignore[attr-defined]

    mb = tk.Menu(app, tearoff=0)
    edit = tk.Menu(mb, tearoff=0)
    mb.add_cascade(label="Правка", menu=edit)

    def do_paste() -> None:
        if not paste_fn():
            try:
                from tkinter import messagebox

                messagebox.showinfo(
                    "Вставка",
                    "Кликни внутрь поля ввода (строка с текстом), затем снова "
                    "«Вставить из буфера» или Cmd/Ctrl+V.",
                    parent=app,
                )
            except Exception:
                pass

    lbl = "Вставить из буфера (UTF-8)"
    if sys.platform == "darwin":
        edit.add_command(label=lbl, accelerator="⌘V", command=do_paste)
    else:
        edit.add_command(label=lbl, accelerator="Ctrl+V", command=do_paste)

    app.config(menu=mb)


def install_utf8_clipboard_support(app: Any) -> None:
    if getattr(app, "_blast_utf8_clipboard_installed", False):
        return
    app._blast_utf8_clipboard_installed = True  # type: ignore[attr-defined]

    def on_accel(_event: tk.Event) -> Optional[str]:
        if paste_into_focused_widget(app):
            return "break"
        return None

    for seq in (
        "<Command-v>",
        "<Command-V>",
        "<Control-v>",
        "<Control-V>",
        "<Meta-v>",
        "<Meta-V>",
    ):
        try:
            app.bind_all(seq, on_accel)
        except tk.TclError:
            continue

    def schedule_scan(delay_ms: int) -> None:
        def run() -> None:
            try:
                _scan_widgets(app, app)
            except Exception:
                pass

        app.after(delay_ms, run)

    schedule_scan(50)
    schedule_scan(300)
    schedule_scan(1200)

    try:
        _add_edit_menu_paste(app, lambda: paste_into_focused_widget(app))
    except Exception:
        pass
