from __future__ import annotations

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

    def get_release_key(self) -> str:
        return (self.release_key.get() or "").strip().upper()

    def get_profile(self) -> str:
        return (self.profile.get() or "auto").strip().lower()

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

