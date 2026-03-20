from __future__ import annotations

import threading
import tkinter as tk

import customtkinter as ctk

_GIGA_WAIT = "⏳ GigaChat…"

from core.assistant import Assistant
from ui.styles import font


class ChatPanel(ctk.CTkFrame):
    def __init__(
        self,
        master: ctk.CTkBaseClass,
        *,
        assistant: Assistant,
        get_context,
        execute_command=None,
    ):
        super().__init__(master)
        self._assistant = assistant
        self._get_context = get_context
        self._execute_command = execute_command

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
            "Команды в чате: ключ релиза — в поле Release key или в тексте. "
            "Часть команд распознаётся LLM, а действия с эффектом — с подтверждением.\n"
            "• запусти RQG / проведи RQG — отчёт RQG (comalarest)\n"
            "• запусти проверку релиза / проверь гейты — полная проверка гейтов\n"
            "• статус релиза — то же, что «Проверить» (сводка по этапу и гейтам)\n"
            "• собери релиз — линковка задач по fixVersion из формы\n"
            "• убери лишние задачи — cleanup связей (эталон fixVersion в форме)\n"
            "• собери деплой план — master analyze + диалог Deploy plan в Confluence\n"
            "• опубликуй деплой план — только Confluence (если уже был analyze)\n"
            "• следующий шаг / двигай дальше — guided cycle\n"
            "• выполни переход — перевод по workflow, если гейты зелёные\n"
            "• собери бизнес-требования для HRPRELEASE-… — БТ/FR\n\n"
            "Свободные вопросы — в GigaChat (если включён).\n"
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

        if callable(self._execute_command):
            # Execute deterministic controller commands first.
            # If it returns non-None, we must NOT call assistant.reply() again.
            cmd_result = self._execute_command(
                q, snapshot=snapshot, result=result, assistant=self._assistant
            )
            if cmd_result is not None:
                self.append(f"Assistant: {cmd_result}\n")
                return

        use_thread = getattr(self._assistant, "gigachat_active", lambda: False)()
        if use_thread:
            try:
                self.send_btn.configure(state="disabled")
                self.append(f"Assistant: {_GIGA_WAIT}\n")
            except Exception:
                pass

            def work() -> None:
                try:
                    ans = self._assistant.reply(q, snapshot=snapshot, result=result)
                except Exception as e:
                    ans = f"Ошибка: {e}"

                def done() -> None:
                    try:
                        self.chat.configure(state="normal")
                        pos = self.chat.search(_GIGA_WAIT, "1.0", tk.END, backwards=True)
                        if pos:
                            ls = self.chat.index(f"{pos} linestart")
                            le = self.chat.index(f"{pos} lineend + 1 char")
                            self.chat.delete(ls, le)
                    except Exception:
                        pass
                    self.append(f"Assistant: {ans}\n")
                    try:
                        self.send_btn.configure(state="normal")
                    except Exception:
                        pass

                self.after(0, done)

            threading.Thread(target=work, daemon=True).start()
            return

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

