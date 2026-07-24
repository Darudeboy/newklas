"""
Интерактивный макет тёмного UI (не подключён к Jira).

Запуск:
    python -m ui.preview_dark_ui
"""
from __future__ import annotations

import customtkinter as ctk

from ui.styles import (
    COLORS,
    RADIUS,
    STATUS,
    apply_default_theme,
    badge_colors,
    card_frame,
    entry_kwargs,
    font,
    muted_label,
    section_label,
    styled_button,
    textbox_kwargs,
)


class DarkUiPreview(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        apply_default_theme()
        self.title("Blast — UI Preview (dark)")
        self.geometry("1280x820")
        self.configure(fg_color=COLORS["bg"])

        self._build_sidebar()
        self._build_main()

    def _build_sidebar(self) -> None:
        side = ctk.CTkFrame(
            self,
            width=220,
            corner_radius=0,
            fg_color=COLORS["sidebar"],
            border_width=0,
        )
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        ctk.CTkLabel(
            side,
            text="BLAST",
            font=font(26, weight="bold"),
            text_color=COLORS["text"],
        ).pack(anchor="w", padx=20, pady=(28, 2))
        muted_label(side, "Release tools").pack(anchor="w", padx=20, pady=(0, 20))

        for label, active in (
            ("Обзор", True),
            ("Проверки", False),
            ("Результаты", False),
            ("Ассистент", False),
            ("Тех. данные", False),
        ):
            btn = styled_button(
                side,
                label,
                kind="primary" if active else "ghost",
                height=36,
                anchor="w",
            )
            btn.pack(fill="x", padx=14, pady=4)

        muted_label(side, "Jira · подключено").pack(
            side="bottom", anchor="w", padx=20, pady=20
        )

    def _build_main(self) -> None:
        main = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        main.pack(side="right", fill="both", expand=True)

        header = ctk.CTkFrame(main, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(18, 8))

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            left,
            text="Релизный центр",
            font=font(22, weight="bold"),
            text_color=COLORS["text"],
        ).pack(anchor="w")
        muted_label(
            left, "Управление проверкой, workflow и поставками"
        ).pack(anchor="w", pady=(2, 0))

        badge_bg, badge_fg = badge_colors("ok")
        badge = ctk.CTkLabel(
            header,
            text="  Jira: подключено  ",
            font=font(12),
            fg_color=badge_bg,
            text_color=badge_fg,
            corner_radius=RADIUS["pill"],
        )
        badge.pack(side="right", padx=(8, 0))

        scroll = ctk.CTkScrollableFrame(
            main, fg_color=COLORS["bg"], corner_radius=0
        )
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self._release_card(scroll)
        self._workflow_card(scroll)
        self._ops_card(scroll)
        self._results_card(scroll)

    def _release_card(self, parent) -> None:
        card = card_frame(parent)
        card.pack(fill="x", padx=8, pady=8)

        section_label(card, "Релиз").pack(anchor="w", padx=16, pady=(14, 8))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 8))

        for label, value, width in (
            ("Release key", "HRPRELEASE-12345", 220),
            ("Project", "HRM", 100),
            ("fixVersion", "2026.3", 120),
            ("Профиль", "auto", 90),
        ):
            col = ctk.CTkFrame(row, fg_color="transparent")
            col.pack(side="left", padx=(0, 10))
            muted_label(col, label, size=11).pack(anchor="w")
            e = ctk.CTkEntry(col, width=width, **entry_kwargs())
            e.insert(0, value)
            e.pack(anchor="w", pady=(4, 0))

        opts = ctk.CTkFrame(card, fg_color="transparent")
        opts.pack(fill="x", padx=16, pady=(4, 14))
        ctk.CTkCheckBox(
            opts,
            text="Dry-run",
            text_color=COLORS["text_muted"],
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            border_color=COLORS["border"],
        ).pack(side="left", padx=(0, 16))
        ctk.CTkCheckBox(
            opts,
            text="Комментарий «Релиз проверен»",
            text_color=COLORS["text_muted"],
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            border_color=COLORS["border"],
        ).pack(side="left")

    def _workflow_card(self, parent) -> None:
        card = card_frame(parent)
        card.pack(fill="x", padx=8, pady=8)
        section_label(card, "Workflow").pack(anchor="w", padx=16, pady=(14, 8))
        muted_label(
            card, "Основные действия выделены мягким индиго / бирюзой"
        ).pack(anchor="w", padx=16, pady=(0, 8))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 14))
        styled_button(row, "Проверить", kind="primary").pack(side="left", padx=(0, 8))
        styled_button(row, "Guided cycle", kind="secondary").pack(side="left", padx=(0, 8))
        styled_button(row, "Авто workflow", kind="success").pack(side="left", padx=(0, 8))
        styled_button(row, "Принудительный перевод", kind="danger").pack(
            side="left", padx=(0, 8)
        )

    def _ops_card(self, parent) -> None:
        card = card_frame(parent)
        card.pack(fill="x", padx=8, pady=8)
        section_label(card, "Операции").pack(anchor="w", padx=16, pady=(14, 8))

        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=16, pady=(0, 8))
        for text, kind in (
            ("Link issues", "secondary"),
            ("Cleanup links", "warning"),
            ("Remove all links", "danger"),
            ("Deploy plan", "secondary"),
            ("Architecture", "ghost"),
        ):
            styled_button(row1, text, kind=kind).pack(side="left", padx=(0, 8))

        row2 = ctk.CTkFrame(card, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=(0, 14))
        muted_label(row2, "DPM").pack(side="left", padx=(0, 10))
        styled_button(row2, "Раскатка ИФТ", kind="info").pack(side="left", padx=(0, 8))
        styled_button(row2, "Раскатка ПСИ", kind="success").pack(side="left", padx=(0, 8))
        styled_button(row2, "DPM статус", kind="neutral").pack(side="left")

    def _results_card(self, parent) -> None:
        card = card_frame(parent)
        card.pack(fill="both", expand=True, padx=8, pady=8)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(14, 8))
        section_label(header, "Результаты").pack(side="left")

        badge_bg, badge_fg = badge_colors("ok")
        ctk.CTkLabel(
            header,
            text="  Готово  ",
            font=font(12),
            fg_color=badge_bg,
            text_color=badge_fg,
            corner_radius=RADIUS["pill"],
        ).pack(side="right")

        box = ctk.CTkTextbox(card, height=180, font=font(13), **textbox_kwargs())
        box.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        box.insert(
            "1.0",
            "Пример отчёта\n"
            "──────────────\n"
            f"Статус progress: {STATUS['progress']}\n"
            f"Статус ok:       {STATUS['ok']}\n"
            f"Статус warn:     {STATUS['warn']}\n"
            f"Статус error:    {STATUS['error']}\n\n"
            "Карточки, кнопки и поля используют единую тёмную палитру.\n",
        )


def main() -> None:
    app = DarkUiPreview()
    app.mainloop()


if __name__ == "__main__":
    main()
