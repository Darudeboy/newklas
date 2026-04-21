from __future__ import annotations

from typing import Any, Optional

import customtkinter as ctk

from ui.styles import font


class MainFormPanel(ctk.CTkFrame):
    def __init__(self, master: ctk.CTkBaseClass, *, controller):
        super().__init__(master)
        self.controller = controller

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkLabel(header, text="Релиз", font=font(20, weight="bold")).pack(
            side="left"
        )

        form = ctk.CTkFrame(self)
        form.pack(fill="x", padx=16, pady=(0, 12))

        self.release_key = ctk.StringVar(value="")
        self.profile = ctk.StringVar(value="auto")
        self.project_key = ctk.StringVar(value="")
        self.fix_version = ctk.StringVar(value="")
        self.dry_run = ctk.BooleanVar(value=False)
        self.post_success_comment = ctk.BooleanVar(value=False)
        self.target_lt = ctk.StringVar(value="45")

        row1 = ctk.CTkFrame(form, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(10, 6))
        ctk.CTkLabel(row1, text="Release key", width=110, anchor="w").pack(
            side="left"
        )
        self.release_entry = ctk.CTkEntry(row1, textvariable=self.release_key)
        self.release_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkLabel(row1, text="Профиль", width=70, anchor="w").pack(side="left")
        self.profile_entry = ctk.CTkEntry(row1, textvariable=self.profile, width=110)
        self.profile_entry.pack(side="left")

        row1b = ctk.CTkFrame(form, fg_color="transparent")
        row1b.pack(fill="x", padx=10, pady=(0, 6))
        ctk.CTkLabel(row1b, text="Project", width=110, anchor="w").pack(side="left")
        self.project_entry = ctk.CTkEntry(row1b, textvariable=self.project_key, width=110)
        self.project_entry.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(row1b, text="fixVersion", width=70, anchor="w").pack(side="left")
        self.fix_version_entry = ctk.CTkEntry(row1b, textvariable=self.fix_version)
        self.fix_version_entry.pack(side="left", fill="x", expand=True)

        row2 = ctk.CTkFrame(form, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkCheckBox(row2, text="Dry-run", variable=self.dry_run).pack(
            side="left", padx=(0, 12)
        )
        ctk.CTkCheckBox(
            row2, text="✅ Комментировать успех в Jira", variable=self.post_success_comment
        ).pack(side="left", padx=(0, 12))

        ctk.CTkLabel(row2, text="Target LT", width=70, anchor="w").pack(side="left")
        self.target_lt_entry = ctk.CTkEntry(row2, textvariable=self.target_lt, width=90)
        self.target_lt_entry.pack(side="left", padx=(0, 8))

        buttons = ctk.CTkFrame(self)
        buttons.pack(fill="x", padx=16, pady=(0, 16))

        ctk.CTkButton(buttons, text="Проверить", command=self._check).pack(
            side="left", padx=6, pady=8
        )
        ctk.CTkButton(buttons, text="Guided cycle", command=self._guided).pack(
            side="left", padx=6, pady=8
        )
        ctk.CTkButton(buttons, text="Следующий шаг", command=self._next_step).pack(
            side="left", padx=6, pady=8
        )
        ctk.CTkButton(
            buttons,
            text="Выполнить переход (если готов)",
            command=self._move_if_ready,
        ).pack(side="left", padx=6, pady=8)
        ctk.CTkButton(
            buttons,
            text="Авто workflow",
            command=self._autopilot,
            fg_color="#00695C",
            hover_color="#004D40",
            text_color="#FFFFFF",
        ).pack(side="left", padx=6, pady=8)
        ctk.CTkButton(
            buttons,
            text="Принудительный перевод",
            command=self._force_move,
            fg_color="#B71C1C",
            hover_color="#8E0000",
            text_color="#FFFFFF",
        ).pack(side="left", padx=6, pady=8)

        ctk.CTkButton(buttons, text="LT", width=60, command=self._lt).pack(
            side="right", padx=6, pady=8
        )
        ctk.CTkButton(buttons, text="RQG", width=60, command=self._rqg).pack(
            side="right", padx=6, pady=8
        )
        ctk.CTkButton(
            buttons, text="Tasks+PR", width=90, command=self._pr_status
        ).pack(side="right", padx=6, pady=8)

        ctk.CTkButton(
            buttons, text="БТ/FR", width=70, command=self._bt
        ).pack(side="right", padx=6, pady=8)

        # Operations (no-LLM) row
        ops = ctk.CTkFrame(self)
        ops.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkButton(ops, text="Link issues", command=self._link).pack(
            side="left", padx=6, pady=6
        )
        ctk.CTkButton(
            ops,
            text="Cleanup links",
            command=self._cleanup,
            fg_color="#EF6C00",
            hover_color="#E65100",
            text_color="#FFFFFF",
        ).pack(side="left", padx=6, pady=6)
        ctk.CTkButton(
            ops,
            text="Remove all links",
            command=self._remove_all,
            fg_color="#C62828",
            hover_color="#B71C1C",
            text_color="#FFFFFF",
        ).pack(side="left", padx=6, pady=6)

        ctk.CTkButton(ops, text="Master analyze", command=self._master_analyze).pack(
            side="right", padx=6, pady=6
        )
        ctk.CTkButton(ops, text="Deploy plan", command=self._deploy_plan).pack(
            side="right", padx=6, pady=6
        )
        ctk.CTkButton(ops, text="Architecture", command=self._arch).pack(
            side="right", padx=6, pady=6
        )

        # DPM: раскатка на стенды ИФТ / ПСИ
        dpm_row = ctk.CTkFrame(self)
        dpm_row.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkLabel(dpm_row, text="DPM", font=font(13, weight="bold"), width=40).pack(
            side="left", padx=(6, 2)
        )
        ctk.CTkButton(
            dpm_row,
            text="Раскатка ИФТ",
            command=self._dpm_deploy_ift,
            fg_color="#1565C0",
            hover_color="#0D47A1",
            text_color="#FFFFFF",
        ).pack(side="left", padx=6, pady=6)
        ctk.CTkButton(
            dpm_row,
            text="Раскатка ПСИ",
            command=self._dpm_deploy_psi,
            fg_color="#2E7D32",
            hover_color="#1B5E20",
            text_color="#FFFFFF",
        ).pack(side="left", padx=6, pady=6)
        ctk.CTkButton(
            dpm_row,
            text="DPM статус",
            command=self._dpm_status,
            fg_color="#455A64",
            hover_color="#37474F",
            text_color="#FFFFFF",
            width=100,
        ).pack(side="left", padx=6, pady=6)

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

    def _pr_status(self) -> None:
        self.controller.run_release_pr_status(release_key=self.get_release_key())

    def _bt(self) -> None:
        self.controller.run_business_requirements(release_key=self.get_release_key())

    def _link(self) -> None:
        self.controller.link_issues(
            release_key=self.get_release_key(),
            fix_version=self.get_fix_version(),
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
    """
    Модальное окно выбора микросервиса для раскатки через DPM.
    """

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
        self.geometry("520x400")
        self.resizable(False, True)
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
            wraplength=480,
        )
        hdr.pack(padx=16, pady=(16, 8), anchor="w")

        scroll = ctk.CTkScrollableFrame(self, width=480, height=240)
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        for i, svc in enumerate(services):
            display = self._format_name(svc)
            rb = ctk.CTkRadioButton(
                scroll,
                text=display,
                variable=self._selected,
                value=str(i),
                font=font(13),
            )
            rb.pack(anchor="w", padx=8, pady=4)

        if len(services) == 1:
            self._selected.set("0")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 16))

        ctk.CTkButton(
            btn_row,
            text=f"Раскатить на {target_stage}",
            command=self._on_ok,
            fg_color="#1565C0" if target_stage == "ИФТ" else "#2E7D32",
            hover_color="#0D47A1" if target_stage == "ИФТ" else "#1B5E20",
            text_color="#FFFFFF",
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row,
            text="Отмена",
            command=self._on_cancel,
            fg_color="#616161",
            hover_color="#424242",
            text_color="#FFFFFF",
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

