"""
Вставка из буфера с кириллицей в CustomTkinter (macOS/Windows).

У Tk/Ctk на macOS стандартный <<Paste>> часто вставляет только латиницу;
перехватываем вставку и читаем буфер как UTF-8 (в т.ч. через pbpaste на Darwin).
"""
from __future__ import annotations

import sys
import tkinter as tk
from typing import Any

import customtkinter as ctk


def _clipboard_text(widget: tk.Misc) -> str:
    try:
        s = widget.clipboard_get()
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
    try:
        raw = widget.tk.call("clipboard", "get")
        if raw:
            return str(raw)
    except tk.TclError:
        pass
    return ""


def _paste_into_entry(event: tk.Event) -> str | None:
    w = event.widget
    text = _clipboard_text(w)
    if not text:
        return None
    try:
        if w.selection_present():
            w.delete("sel.first", "sel.last")
    except tk.TclError:
        pass
    w.insert("insert", text)
    return "break"


def _paste_into_text(event: tk.Event) -> str | None:
    w = event.widget
    text = _clipboard_text(w)
    if not text:
        return None
    try:
        if w.tag_ranges("sel"):
            w.delete("sel.first", "sel.last")
    except tk.TclError:
        pass
    w.insert("insert", text)
    return "break"


def _patch_entry(inner: tk.Entry) -> None:
    if getattr(inner, "_blast_utf8_paste", False):
        return
    inner._blast_utf8_paste = True  # type: ignore[attr-defined]
    inner.bind("<<Paste>>", _paste_into_entry)
    if sys.platform == "darwin":
        inner.bind("<Command-v>", _paste_into_entry)
    inner.bind("<Control-v>", _paste_into_entry)


def _patch_textbox(inner: tk.Text) -> None:
    if getattr(inner, "_blast_utf8_paste", False):
        return
    inner._blast_utf8_paste = True  # type: ignore[attr-defined]
    inner.bind("<<Paste>>", _paste_into_text)
    if sys.platform == "darwin":
        inner.bind("<Command-v>", _paste_into_text)
    inner.bind("<Control-v>", _paste_into_text)


def install_utf8_clipboard_support(root: Any) -> None:
    """Обойти все CTkEntry / CTkTextbox под root и повесить UTF-8 вставку."""

    def scan(w: Any) -> None:
        try:
            children = w.winfo_children()
        except tk.TclError:
            return
        if isinstance(w, ctk.CTkEntry):
            inner = getattr(w, "_entry", None)
            if inner is not None:
                _patch_entry(inner)
        elif isinstance(w, ctk.CTkTextbox):
            inner = getattr(w, "_textbox", None)
            if inner is not None:
                _patch_textbox(inner)
        for ch in children:
            scan(ch)

    scan(root)
