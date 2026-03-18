from __future__ import annotations

import os
from typing import Callable

import customtkinter as ctk

from ui.styles import font


class LogPanel(ctk.CTkFrame):
    def __init__(
        self, master: ctk.CTkBaseClass, *, log_file_path_getter: Callable[[], str]
    ):
        super().__init__(master)
        self._get_log_path = log_file_path_getter

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkLabel(header, text="Логи", font=font(20, weight="bold")).pack(
            side="left"
        )
        ctk.CTkButton(header, text="Обновить", width=120, command=self.refresh).pack(
            side="right"
        )

        self.text = ctk.CTkTextbox(self, font=font(12), wrap="none")
        self.text.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.refresh()

    def refresh(self) -> None:
        path = self._get_log_path() or ""
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                content = f"Не удалось прочитать лог: {e}"
        else:
            content = f"Лог-файл не найден: {path}"

        if len(content) > 40000:
            content = "…(tail)…\n" + content[-40000:]

        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.configure(state="normal")

