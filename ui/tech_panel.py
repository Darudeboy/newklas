from __future__ import annotations

import json

import customtkinter as ctk

from ui.styles import font, section_label, styled_button, textbox_kwargs


class TechPanel(ctk.CTkFrame):
    def __init__(self, master: ctk.CTkBaseClass, *, get_context):
        super().__init__(master, fg_color="transparent")
        self._get_context = get_context

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 8))
        section_label(header, "Технические детали").pack(side="left")
        styled_button(
            header, "Обновить", width=120, command=self.refresh, kind="ghost"
        ).pack(side="right")

        self.text = ctk.CTkTextbox(self, font=font(12), wrap="none", **textbox_kwargs())
        self.text.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.text.configure(state="normal")
        self.text.insert("1.0", "Нажми «Обновить», чтобы увидеть snapshot/result.\n")
        self.text.configure(state="normal")

    def refresh(self) -> None:
        snapshot, result = self._get_context()
        payload = {"snapshot": snapshot, "result": result}
        dumped = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        if len(dumped) > 30000:
            dumped = dumped[:30000] + "\n…(truncated)…"
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", dumped)
        self.text.configure(state="normal")
