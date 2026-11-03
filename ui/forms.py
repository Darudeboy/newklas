from __future__ import annotations

from typing import Any, Optional

import customtkinter as ctk

from ui.styles import (
    COLORS,
    card_frame,
    entry_kwargs,
    font,
    muted_label,
    section_label,
    styled_button,
)


class MainFormPanel(ctk.CTkFrame):
    def __init__(self, master: ctk.CTkBaseClass, *, controller):
        super().__init__(master, fg_color="transparent")
        self.controller = controller

        self.release_key = ctk.StringVar(value="")
        self.profile = ctk.StringVar(value="auto")
        self.project_key = ctk.StringVar(value="")
        self.fix_version = ctk.StringVar(value="")
        self.dry_run = ctk.BooleanVar(value=False)
        self.post_success_comment = ctk.BooleanVar(value=True)
        self.target_lt = ctk.StringVar(value="45")

        self._build_release_card()
        self._build_workflow_card()
        self._build_ops_card()
        self._build_dpm_card()

    def _field_label(self, parent, text: str) -> None:
        muted_label(parent, text, size=11).pack(anchor="w")

    def _build_release_card(self) -> None:
        card = card_frame(self)
        card.pack(fill="x", padx=16, pady=(12, 8))

        section_label(card, "Релиз").pack(anchor="w", padx=16, pady=(14, 10))

        form = ctk.CTkFrame(card, fg_color="transparent")
        form.pack(fill="x", padx=16, pady=(0, 6))

        row1 = ctk.CTkFrame(form, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 8))

        col_rel = ctk.CTkFrame(row1, fg_color="transparent")
        col_rel.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self._field_label(col_rel, "Release key")
        self.release_entry = ctk.CTkEntry(
            col_rel, textvariable=self.release_key, **entry_kwargs()
        )
        self.release_entry.pack(fill="x", pady=(4, 0))

        col_prof = ctk.CTkFrame(row1, fg_color="transparent")
        col_prof.pack(side="left")
        self._field_label(col_prof, "Профиль")
        self.profile_entry = ctk.CTkEntry(
            col_prof, textvariable=self.profile, width=110, **entry_kwargs()
        )
        self.profile_entry.pack(pady=(4, 0))

        row2 = ctk.CTkFrame(form, fg_color="transparent")
        row2.pack(fill="x", pady=(0, 8))

        col_proj = ctk.CTkFrame(row2, fg_color="transparent")
        col_proj.pack(side="left", padx=(0, 10))
        self._field_label(col_proj, "Project")
        self.project_entry = ctk.CTkEntry(
            col_proj, textvariable=self.project_key, width=120, **entry_kwargs()
        )
        self.project_entry.pack(pady=(4, 0))

        col_fv = ctk.CTkFrame(row2, fg_color="transparent")
        col_fv.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self._field_label(col_fv, "fixVersion")
        self.fix_version_entry = ctk.CTkEntry(
            col_fv, textvariable=self.fix_version, **entry_kwargs()
        )
        self.fix_version_entry.pack(fill="x", pady=(4, 0))

        col_lt = ctk.CTkFrame(row2, fg_color="transparent")
        col_lt.pack(side="left")
        self._field_label(col_lt, "Target LT")
        self.target_lt_entry = ctk.CTkEntry(
            col_lt, textvariable=self.target_lt, width=90, **entry_kwargs()
        )
        self.target_lt_entry.pack(pady=(4, 0))

        opts = ctk.CTkFrame(card, fg_color="transparent")
        opts.pack(fill="x", padx=16, pady=(4, 14))
        ctk.CTkCheckBox(
            opts,
            text="Dry-run",
            variable=self.dry_run,
            text_color=COLORS["text_muted"],
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            border_color=COLORS["border"],
            checkmark_color=COLORS["text"],
        ).pack(side="left", padx=(0, 16))
        ctk.CTkCheckBox(
            opts,
            text='Комментарий «Релиз проверен» в Jira (1 раз)',
            variable=self.post_success_comment,
            text_color=COLORS["text_muted"],
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            border_color=COLORS["border"],
            checkmark_color=COLORS["text"],
        ).pack(side="left")

    def _build_workflow_card(self) -> None:
        card = card_frame(self)
        card.pack(fill="x", padx=16, pady=8)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(14, 6))
        section_label(head, "Workflow").pack(side="left")
        muted_label(head, "проверка и переходы").pack(side="left", padx=(10, 0))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 8))

        styled_button(row, "Проверить", command=self._check, kind="primary").pack(
            side="left", padx=(0, 8), pady=4
        )
        styled_button(row, "Guided cycle", command=self._guided, kind="secondary").pack(
            side="left", padx=(0, 8), pady=4
        )
        styled_button(
            row, "Следующий шаг", command=self._next_step, kind="secondary"
        ).pack(side="left", padx=(0, 8), pady=4)
        styled_button(
            row,
            "Выполнить переход",
            command=self._move_if_ready,
            kind="secondary",
        ).pack(side="left", padx=(0, 8), pady=4)
        styled_button(
            row, "Авто workflow", command=self._autopilot, kind="success"
        ).pack(side="left", padx=(0, 8), pady=4)
        styled_button(
            row,
            "Принудительный перевод",
            command=self._force_move,
            kind="danger",
        ).pack(side="left", padx=(0, 8), pady=4)

        tools = ctk.CTkFrame(card, fg_color="transparent")
        tools.pack(fill="x", padx=16, pady=(0, 14))
        muted_label(tools, "Быстрые проверки").pack(side="left", padx=(0, 10))
        styled_button(tools, "LT", command=self._lt, kind="ghost", width=64).pack(
            side="left", padx=(0, 6)
        )
        styled_button(tools, "RQG", command=self._rqg, kind="ghost", width=64).pack(
            side="left", padx=(0, 6)
        )
        styled_button(
            tools, "Stories", command=self._stories, kind="ghost", width=80
        ).pack(side="left", padx=(0, 6))
        styled_button(
            tools, "Tasks+PR", command=self._pr_status, kind="ghost", width=90
        ).pack(side="left", padx=(0, 6))
        styled_button(tools, "БТ/FR", command=self._bt, kind="ghost", width=70).pack(
            side="left"
        )

    def _build_ops_card(self) -> None:
        card = card_frame(self)
        card.pack(fill="x", padx=16, pady=8)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(14, 6))
        section_label(head, "Операции").pack(side="left")
        muted_label(head, "задачи, анализ, артефакты").pack(side="left", padx=(10, 0))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 14))

        styled_button(row, "Link issues", command=self._link, kind="secondary").pack(
            side="left", padx=(0, 8), pady=4
        )
        styled_button(
            row, "Cleanup links", command=self._cleanup, kind="warning"
        ).pack(side="left", padx=(0, 8), pady=4)
        styled_button(
            row, "Remove all links", command=self._remove_all, kind="danger"
        ).pack(side="left", padx=(0, 8), pady=4)

        styled_button(
            row, "Release analyze", command=self._master_analyze, kind="secondary"
        ).pack(side="right", padx=(8, 0), pady=4)
        styled_button(
            row, "Deploy plan", command=self._deploy_plan, kind="secondary"
        ).pack(side="right", padx=(8, 0), pady=4)
        styled_button(row, "Architecture", command=self._arch, kind="ghost").pack(
            side="right", padx=(8, 0), pady=4
        )

    def _build_dpm_card(self) -> None:
        card = card_frame(self)
        card.pack(fill="x", padx=16, pady=(8, 4))

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(14, 6))
        section_label(head, "DPM").pack(side="left")
        muted_label(head, "раскатка на стенды").pack(side="left", padx=(10, 0))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 14))

        styled_button(
            row, "Раскатка ИФТ", command=self._dpm_deploy_ift, kind="info"
        ).pack(side="left", padx=(0, 8), pady=4)
        styled_button(
            row, "Раскатка ПСИ", command=self._dpm_deploy_psi, kind="success"
        ).pack(side="left", padx=(0, 8), pady=4)
        styled_button(
            row, "DPM статус", command=self._dpm_status, kind="neutral", width=110
        ).pack(side="left", pady=4)

    def get_release_key(self) -> str:
        return (self.release_key.get() or "").strip().upper()

    def get_profile(self) -> str:
        return (self.profile.get() or "auto").strip().lower()

    def get_project_key(self) -> str:
        return (self.project_key.get() or "").strip().upper()

    def get_fix_version(self) -> str:
        return (self.fix_version.get() or "").strip()

    def is_dry_run(self) -> bool:
        return bool(self.dry_run.get())

    def want_success_comment(self) -> bool:
        return bool(self.post_success_comment.get())

    def get_target_lt(self) -> float:
        raw = (self.target_lt.get() or "").strip()
        return float(raw) if raw else 45.0

    def _check(self) -> None:
        self.controller.run_release_check(
            release_key=self.get_release_key(),
            profile=self.get_profile(),
            dry_run=self.is_dry_run(),
            post_success_comment=self.want_success_comment(),
        )

    def _guided(self) -> None:
        self.controller.start_release_guided_cycle(
            release_key=self.get_release_key(),
            profile=self.get_profile(),
            dry_run=self.is_dry_run(),
            post_success_comment=self.want_success_comment(),
        )

    def _next_step(self) -> None:
        self.controller.run_next_release_step(
            release_key=self.get_release_key(),
            dry_run=self.is_dry_run(),
        )

    def _move_if_ready(self) -> None:
        self.controller.move_release_if_ready(
            release_key=self.get_release_key(),
            dry_run=self.is_dry_run(),
        )

    def _autopilot(self) -> None:
        self.controller.start_workflow_autopilot(
            release_key=self.get_release_key(),
            profile=self.get_profile(),
            dry_run=self.is_dry_run(),
            post_success_comment=self.want_success_comment(),
        )

    def _force_move(self) -> None:
        self.controller.force_move_release_transition(
            release_key=self.get_release_key(),
            dry_run=self.is_dry_run(),
        )

    def _lt(self) -> None:
        self.controller.run_lt_check(
            release_key=self.get_release_key(),
            target_lt=self.get_target_lt(),
        )

    def _rqg(self) -> None:
        self.controller.run_rqg_check(release_key=self.get_release_key())

    def _stories(self) -> None:
        self.controller.run_story_check(release_key=self.get_release_key())

    def _pr_status(self) -> None:
        self.controller.run_release_pr_status(release_key=self.get_release_key())

    def _bt(self) -> None:
        self.controller.run_business_requirements(release_key=self.get_release_key())

    def _link(self) -> None:
        self.controller.link_issues(
            release_key=self.get_release_key(),
            fix_version=self.get_fix_version(),
            project_key=self.get_project_key(),
            dry_run=self.is_dry_run(),
        )

    def _cleanup(self) -> None:
        self.controller.cleanup_issues(
            release_key=self.get_release_key(),
            fix_version=self.get_fix_version(),
            dry_run=self.is_dry_run(),
        )

    def _remove_all(self) -> None:
        self.controller.remove_all_issues(
            release_key=self.get_release_key(),
            fix_version=self.get_fix_version(),
            dry_run=self.is_dry_run(),
        )

    def _master_analyze(self) -> None:
        self.controller.analyze_master_services(release_key=self.get_release_key())

    def _deploy_plan(self) -> None:
        self.controller.create_deploy_plan()

    def _arch(self) -> None:
        self.controller.run_architecture_update(
            release_key=self.get_release_key(),
            project_key=self.get_project_key(),
            fix_version=self.get_fix_version(),
        )

    def _dpm_deploy_ift(self) -> None:
        self.controller.dpm_deploy(
            release_key=self.get_release_key(),
            target_stage="ИФТ",
            dry_run=self.is_dry_run(),
        )

    def _dpm_deploy_psi(self) -> None:
        self.controller.dpm_deploy(
            release_key=self.get_release_key(),
            target_stage="ПСИ",
            dry_run=self.is_dry_run(),
        )

    def _dpm_status(self) -> None:
        self.controller.dpm_status(release_key=self.get_release_key())


class DpmServiceChooser(ctk.CTkToplevel):
    """Модальное окно выбора микросервиса для раскатки через DPM."""

    def __init__(
        self,
        master,
        *,
        services: list[dict[str, Any]],
        target_stage: str,
        format_name_fn,
        get_key_fn,
        title: str = "Выбор микросервиса",
    ):
        super().__init__(master)
        self.title(title)
        self.geometry("520x420")
        self.resizable(False, True)
        self.configure(fg_color=COLORS["bg"])
        self.grab_set()
        self.lift()

        self.result: Optional[dict[str, Any]] = None
        self._format_name = format_name_fn
        self._get_key = get_key_fn
        self._services = services
        self._selected = ctk.StringVar(value="")

        hdr = ctk.CTkLabel(
            self,
            text=f"Выберите микросервис для раскатки на {target_stage}:",
            font=font(15, weight="bold"),
            text_color=COLORS["text"],
            wraplength=480,
        )
        hdr.pack(padx=16, pady=(16, 8), anchor="w")

        scroll = ctk.CTkScrollableFrame(
            self,
            width=480,
            height=240,
            fg_color=COLORS["card"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border"],
        )
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        for i, svc in enumerate(services):
            display = self._format_name(svc)
            rb = ctk.CTkRadioButton(
                scroll,
                text=display,
                variable=self._selected,
                value=str(i),
                font=font(13),
                text_color=COLORS["text"],
                fg_color=COLORS["primary"],
                hover_color=COLORS["primary_hover"],
                border_color=COLORS["border"],
            )
            rb.pack(anchor="w", padx=8, pady=4)

        if len(services) == 1:
            self._selected.set("0")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 16))

        kind = "info" if target_stage == "ИФТ" else "success"
        styled_button(
            btn_row,
            f"Раскатить на {target_stage}",
            command=self._on_ok,
            kind=kind,
        ).pack(side="left", padx=(0, 8))
        styled_button(
            btn_row, "Отмена", command=self._on_cancel, kind="neutral"
        ).pack(side="left")

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _on_ok(self) -> None:
        idx_str = self._selected.get()
        if not idx_str:
            return
        idx = int(idx_str)
        if 0 <= idx < len(self._services):
            self.result = self._services[idx]
        self.grab_release()
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.grab_release()
        self.destroy()
