from __future__ import annotations

import customtkinter as ctk

from core.assistant import Assistant
from ui.styles import font


class ChatPanel(ctk.CTkFrame):
    def __init__(
        self,
        master: ctk.CTkBaseClass,
        *,
        assistant: Assistant,
        get_context,
    ):
        super().__init__(master)
        self._assistant = assistant
        self._get_context = get_context

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 8))

        ctk.CTkLabel(header, text="Assistant", font=font(20, weight="bold")).pack(
            side="left"
        )

        quick = ctk.CTkFrame(self)
        quick.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkButton(
            quick, text="Краткий summary", width=140, command=self._quick_summary
        ).pack(side="left", padx=6, pady=8)
        ctk.CTkButton(
            quick, text="Объясни блокеры", width=140, command=self._quick_blockers
        ).pack(side="left", padx=6, pady=8)
        ctk.CTkButton(
            quick, text="Что дальше", width=120, command=self._quick_next_actions
        ).pack(side="left", padx=6, pady=8)

        self.chat = ctk.CTkTextbox(self, font=font(13), wrap="word")
        self.chat.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        input_row = ctk.CTkFrame(self)
        input_row.pack(fill="x", padx=16, pady=(0, 16))

        self.input = ctk.CTkEntry(input_row, placeholder_text="Спроси про результат…")
        self.input.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=8)
        self.input.bind("<Return>", lambda _e: self.send())

        self.send_btn = ctk.CTkButton(
            input_row, text="Отправить", width=120, command=self.send
        )
        self.send_btn.pack(side="right", pady=8)

        self.append(
            "Assistant готов. Сначала запусти проверку релиза, затем можешь спросить «почему заблокировано?».\n"
        )

    def append(self, text: str) -> None:
        self.chat.configure(state="normal")
        self.chat.insert("end", text)
        self.chat.see("end")
        self.chat.configure(state="normal")

    def send(self) -> None:
        q = (self.input.get() or "").strip()
        if not q:
            return
        self.input.delete(0, "end")
        snapshot, result = self._get_context()
        self.append(f"\nВы: {q}\n")
        answer = self._assistant.reply(q, snapshot=snapshot, result=result)
        self.append(f"Assistant: {answer}\n")

    def _quick_summary(self) -> None:
        _snapshot, result = self._get_context()
        self.append("\n[Краткий summary]\n")
        self.append(self._assistant.quick_summary(result=result or {}) + "\n")

    def _quick_blockers(self) -> None:
        _snapshot, result = self._get_context()
        self.append("\n[Блокеры]\n")
        self.append(self._assistant.quick_blockers(result=result or {}) + "\n")

    def _quick_next_actions(self) -> None:
        _snapshot, result = self._get_context()
        self.append("\n[Что дальше]\n")
        self.append(self._assistant.quick_next_actions(result=result or {}) + "\n")

