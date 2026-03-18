from __future__ import annotations

import json

import customtkinter as ctk

from ui.styles import font


class TechPanel(ctk.CTkFrame):
    def __init__(self, master: ctk.CTkBaseClass, *, get_context):
        super().__init__(master)
        self._get_context = get_context

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkLabel(
            header, text="Технические детали", font=font(20, weight="bold")
        ).pack(side="left")
        ctk.CTkButton(header, text="Обновить", width=120, command=self.refresh).pack(
            side="right"
        )

        self.text = ctk.CTkTextbox(self, font=font(12), wrap="none")
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

