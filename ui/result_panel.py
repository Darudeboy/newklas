from __future__ import annotations

import customtkinter as ctk

from ui.styles import font


class ResultPanel(ctk.CTkFrame):
    def __init__(self, master: ctk.CTkBaseClass):
        super().__init__(master)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 8))

        self.title_label = ctk.CTkLabel(
            header,
            text="Результаты",
            font=font(20, weight="bold"),
        )
        self.title_label.pack(side="left")

        self.status_label = ctk.CTkLabel(
            header,
            text="",
            font=font(13),
            text_color="#616161",
        )
        self.status_label.pack(side="right")

        self.text = ctk.CTkTextbox(self, font=font(13), wrap="word")
        self.text.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self.set_text("Готово. Запусти проверку, чтобы увидеть отчёт.")

    def set_text(self, value: str) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value or "")
        self.text.configure(state="normal")

    def set_status(self, value: str, *, color: str = "#616161") -> None:
        self.status_label.configure(text=value or "", text_color=color)

