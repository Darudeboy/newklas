from __future__ import annotations

import customtkinter as ctk

from ui.styles import (
    COLORS,
    RADIUS,
    STATUS,
    badge_colors,
    font,
    resolve_status_color,
    textbox_kwargs,
)


class ResultPanel(ctk.CTkFrame):
    def __init__(self, master: ctk.CTkBaseClass):
        super().__init__(master, fg_color="transparent")

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 8))

        self.title_label = ctk.CTkLabel(
            header,
            text="Результаты",
            font=font(18, weight="bold"),
            text_color=COLORS["text"],
        )
        self.title_label.pack(side="left")

        self.status_label = ctk.CTkLabel(
            header,
            text="  ожидание  ",
            font=font(12),
            fg_color=badge_colors("idle")[0],
            text_color=badge_colors("idle")[1],
            corner_radius=RADIUS["pill"],
        )
        self.status_label.pack(side="right")

        self.text = ctk.CTkTextbox(self, font=font(13), wrap="word", **textbox_kwargs())
        self.text.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self.set_text("Готово. Запусти проверку, чтобы увидеть отчёт.")

    def set_text(self, value: str) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value or "")
        self.text.configure(state="normal")

    def set_status(self, value: str, *, color: str = "") -> None:
        resolved = resolve_status_color(color) if color else STATUS["idle"]
        kind = "idle"
        if resolved == STATUS["ok"]:
            kind = "ok"
        elif resolved == STATUS["error"]:
            kind = "error"
        elif resolved == STATUS["warn"]:
            kind = "warn"
        elif resolved == STATUS["progress"]:
            kind = "progress"
        bg, fg = badge_colors(kind)
        self.status_label.configure(
            text=f"  {value or '—'}  ",
            fg_color=bg,
            text_color=fg,
        )
