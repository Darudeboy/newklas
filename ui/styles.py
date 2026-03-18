from __future__ import annotations

import customtkinter as ctk


def apply_default_theme() -> None:
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")


def font(size: int = 14, *, weight: str | None = None) -> ctk.CTkFont:
    if weight:
        return ctk.CTkFont(size=size, weight=weight)
    return ctk.CTkFont(size=size)

