from __future__ import annotations

import logging
import os
from tkinter import messagebox

import customtkinter as ctk

from config import JiraConfig
from core.gigachat_assistant import build_assistant
from core.jira_client import JiraService
from history import OperationHistory
from onboarding import show_onboarding_if_needed
from ui.clipboard_utf8 import install_utf8_clipboard_support
from ui.chat_panel import ChatPanel
from ui.controllers import AppController
from ui.forms import MainFormPanel
from ui.log_panel import LogPanel
from ui.result_panel import ResultPanel
from ui.styles import apply_default_theme, font
from ui.tech_panel import TechPanel


class ModernJiraApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        apply_default_theme()

        self.title("Blast - Jira Automation Tool")
        self.geometry("1200x800")

        self.config_dir = os.path.join(os.path.expanduser("~"), ".jira_tool")
        self.history_path = os.path.join(self.config_dir, "history.json")
        self.log_path = os.path.join(self.config_dir, "app.log")
        os.makedirs(self.config_dir, exist_ok=True)

        self._setup_logging()

        self.config = JiraConfig()
        self.jira_service = JiraService(self.config)
        self.history = OperationHistory()
        if os.path.exists(self.history_path):
            try:
                self.history.load_from_file(self.history_path)
            except Exception:
                pass

        self.assistant = build_assistant()

        self._build_layout()
        self._wire_controller()
        try:
            self.tech_panel.refresh()
        except Exception:
            pass

        self.after(
            80,
            lambda: install_utf8_clipboard_support(self),
        )

        self.after(100, self.controller.check_connection_async)
        self.after(200, lambda: show_onboarding_if_needed(self))

    def _setup_logging(self) -> None:
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.FileHandler(self.log_path, encoding="utf-8"),
                logging.StreamHandler(),
            ],
        )
        self.logger = logging.getLogger(self.__class__.__name__)

    def _build_layout(self) -> None:
        self.sidebar = ctk.CTkFrame(self, width=260, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        ctk.CTkLabel(
            self.sidebar,
            text="Blast",
            font=font(28, weight="bold"),
        ).pack(pady=(24, 4))
        ctk.CTkLabel(
            self.sidebar,
            text="controlled redesign",
            font=font(12),
            text_color="gray",
        ).pack(pady=(0, 18))

        self.connection_label = ctk.CTkLabel(
            self.sidebar, text="● Проверка…", font=font(12), text_color="orange"
        )
        self.connection_label.pack(pady=(0, 12))

        self.main = ctk.CTkFrame(self, corner_radius=0)
        self.main.pack(side="right", fill="both", expand=True)

        self.form = MainFormPanel(self.main, controller=None)  # wired later
        self.form.pack(fill="x")

        self.tabs = ctk.CTkTabview(self.main)
        self.tabs.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.tab_results = self.tabs.add("Результаты")
        self.tab_assistant = self.tabs.add("Assistant")
        self.tab_tech = self.tabs.add("Tech")
        self.tab_logs = self.tabs.add("Логи")

        self.result_panel = ResultPanel(self.tab_results)
        self.result_panel.pack(fill="both", expand=True)

        self.chat_panel = ChatPanel(
            self.tab_assistant,
            assistant=self.assistant,
            get_context=lambda: self.controller.get_context(),
            execute_command=lambda text, *, snapshot=None, result=None, assistant=None: self.controller.execute_chat_command(
                text, snapshot=snapshot, result=result, assistant=assistant
            ),
        )
        self.chat_panel.pack(fill="both", expand=True)
        if getattr(self.assistant, "gigachat_active", lambda: False)():
            self.chat_panel.append(
                "GigaChat подключён: свободные вопросы в чате уходят в модель "
                "(контекст — последняя проверка гейтов). Команды БТ и кнопки слева — без LLM.\n"
            )

        self.tech_panel = TechPanel(
            self.tab_tech, get_context=lambda: self.controller.get_context()
        )
        self.tech_panel.pack(fill="both", expand=True)

        self.log_panel = LogPanel(self.tab_logs, log_file_path_getter=lambda: self.log_path)
        self.log_panel.pack(fill="both", expand=True)

    def _wire_controller(self) -> None:
        def ui_set_status(text: str, color: str) -> None:
            self.result_panel.set_status(text, color=color)

        def ui_set_result_text(text: str) -> None:
            self.result_panel.set_text(text)
            try:
                self.tech_panel.refresh()
            except Exception:
                pass

        def ui_show_error(title: str, msg: str) -> None:
            self.after(0, lambda: messagebox.showerror(title, msg))

        def ui_show_info(title: str, msg: str) -> None:
            self.after(0, lambda: messagebox.showinfo(title, msg))

        def ui_set_connection(ok: bool) -> None:
            def update():
                if ok:
                    self.connection_label.configure(text="● Подключено", text_color="green")
                else:
                    self.connection_label.configure(text="● Ошибка", text_color="red")
            self.after(0, update)

        self.controller = AppController(
            jira_service=self.jira_service,
            history=self.history,
            history_path=self.history_path,
            ui_set_status=lambda t, c: self.after(0, lambda: ui_set_status(t, c)),
            ui_set_result_text=lambda t: self.after(0, lambda: ui_set_result_text(t)),
            ui_show_error=ui_show_error,
            ui_show_info=ui_show_info,
            ui_ask_yes_no=lambda title, msg: messagebox.askyesno(title, msg),
            ui_set_connection=ui_set_connection,
        )

        self.form.controller = self.controller
        self.controller._ui_schedule_main = lambda fn: self.after(0, fn)
        self.controller._form_get_release_key = self.form.get_release_key
        self.controller._form_get_fix_version = self.form.get_fix_version
        self.controller._form_get_dry_run = self.form.is_dry_run
        self.controller._form_get_profile = self.form.get_profile

