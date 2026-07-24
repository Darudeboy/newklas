from __future__ import annotations

import threading
import tkinter as tk

import customtkinter as ctk

_GIGA_WAIT = "⏳ GigaChat…"

from core.assistant import Assistant
from ui.styles import (
    card_frame,
    entry_kwargs,
    font,
    muted_label,
    section_label,
    styled_button,
    textbox_kwargs,
)


class ChatPanel(ctk.CTkFrame):
    def __init__(
        self,
        master: ctk.CTkBaseClass,
        *,
        assistant: Assistant,
        get_context,
        execute_command=None,
    ):
        super().__init__(master, fg_color="transparent")
        self._assistant = assistant
        self._get_context = get_context
        self._execute_command = execute_command

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 8))
        section_label(header, "Ассистент").pack(side="left")
        muted_label(header, "команды и GigaChat").pack(side="left", padx=(10, 0))

        quick = card_frame(self)
        quick.pack(fill="x", padx=16, pady=(0, 8))
        inner = ctk.CTkFrame(quick, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=8)

        styled_button(
            inner, "Краткий summary", width=140, command=self._quick_summary, kind="ghost"
        ).pack(side="left", padx=4, pady=4)
        styled_button(
            inner, "Объясни блокеры", width=140, command=self._quick_blockers, kind="ghost"
        ).pack(side="left", padx=4, pady=4)
        styled_button(
            inner, "Что дальше", width=120, command=self._quick_next_actions, kind="ghost"
        ).pack(side="left", padx=4, pady=4)

        self.chat = ctk.CTkTextbox(self, font=font(13), wrap="word", **textbox_kwargs())
        self.chat.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        input_row = card_frame(self)
        input_row.pack(fill="x", padx=16, pady=(0, 16))
        inner_in = ctk.CTkFrame(input_row, fg_color="transparent")
        inner_in.pack(fill="x", padx=10, pady=8)

        self.input = ctk.CTkEntry(
            inner_in,
            placeholder_text="Спроси про результат или дай команду…",
            **entry_kwargs(),
        )
        self.input.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.input.bind("<Return>", lambda _e: self.send())

        self.send_btn = styled_button(
            inner_in, "Отправить", width=120, command=self.send, kind="primary"
        )
        self.send_btn.pack(side="right")

        self.append(
            "Команды в чате: ключ релиза — в поле Release key или в тексте. "
            "Часть команд распознаётся LLM, а действия с эффектом — с подтверждением.\n"
            "• запусти RQG / проведи RQG — отчёт RQG (comalarest)\n"
            "• запусти проверку релиза / проверь гейты — полная проверка гейтов\n"
            "• статус релиза — то же, что «Проверить» (сводка по этапу и гейтам)\n"
            "• собери релиз — линковка задач по Project и fixVersion из формы\n"
            "• убери лишние задачи — cleanup связей (эталон fixVersion в форме)\n"
            "• собери деплой план — master analyze + диалог Deploy plan в Confluence\n"
            "• опубликуй деплой план — только Confluence (если уже был analyze)\n"
            "• следующий шаг / двигай дальше — guided cycle\n"
            "• выполни переход — перевод по workflow, если гейты зелёные\n"
            "• автопилот / авто workflow / прогон без остановок — цикл проверки и переходов\n"
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
