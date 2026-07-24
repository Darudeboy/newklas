from __future__ import annotations

from typing import Any

import customtkinter as ctk


# ---------------------------------------------------------------------------
# Dark professional palette (soft indigo / teal accents)
# ---------------------------------------------------------------------------

COLORS = {
    "bg": "#151922",
    "sidebar": "#10141C",
    "card": "#1D2430",
    "card_alt": "#222A38",
    "border": "#2A3443",
    "input": "#171D28",
    "hover": "#263041",
    "text": "#E8ECF2",
    "text_muted": "#9AA6B8",
    "text_dim": "#6E7A8C",
    "primary": "#5B6CDB",
    "primary_hover": "#4C5BC4",
    "primary_soft": "#2A3358",
    "success": "#3D9B8F",
    "success_hover": "#34867C",
    "success_soft": "#1E3A38",
    "warning": "#C49A4A",
    "warning_hover": "#B0883F",
    "warning_soft": "#3A3220",
    "danger": "#C46B6B",
    "danger_hover": "#B05C5C",
    "danger_soft": "#3A2428",
    "neutral": "#4A5568",
    "neutral_hover": "#3D4757",
    "info": "#5B8FBF",
    "info_hover": "#4D7CA8",
}

STATUS = {
    "progress": COLORS["primary"],
    "ok": COLORS["success"],
    "error": COLORS["danger"],
    "warn": COLORS["warning"],
    "idle": COLORS["text_muted"],
    "cancel": COLORS["text_dim"],
}

# Legacy Material hex → soft dark tokens (controllers / forms migration)
_LEGACY_COLOR_MAP = {
    "#1565C0": STATUS["progress"],
    "#0D47A1": COLORS["primary_hover"],
    "#2E7D32": STATUS["ok"],
    "#1B5E20": COLORS["success_hover"],
    "#C62828": STATUS["error"],
    "#B71C1C": COLORS["danger"],
    "#8E0000": COLORS["danger_hover"],
    "#EF6C00": STATUS["warn"],
    "#E65100": COLORS["warning_hover"],
    "#00695C": COLORS["success"],
    "#004D40": COLORS["success_hover"],
    "#455A64": COLORS["neutral"],
    "#37474F": COLORS["neutral_hover"],
    "#616161": STATUS["idle"],
    "#424242": COLORS["neutral_hover"],
    "green": STATUS["ok"],
    "red": STATUS["error"],
    "orange": STATUS["warn"],
    "gray": STATUS["idle"],
}

RADIUS = {
    "sm": 8,
    "md": 12,
    "lg": 16,
    "pill": 20,
}

SPACE = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 24,
}


def apply_default_theme() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")


def font(size: int = 14, *, weight: str | None = None) -> ctk.CTkFont:
    if weight:
        return ctk.CTkFont(size=size, weight=weight)
    return ctk.CTkFont(size=size)


def resolve_status_color(color: str | None) -> str:
    """Map legacy / named colors to soft dark status tokens."""
    if not color:
        return STATUS["idle"]
    key = color.strip()
    mapped = _LEGACY_COLOR_MAP.get(key) or _LEGACY_COLOR_MAP.get(key.upper())
    if mapped:
        return mapped
    if key.startswith("#") and len(key) in (4, 7):
        return key
    return STATUS["idle"]


def button_style(kind: str = "secondary") -> dict[str, Any]:
    """Return kwargs for CTkButton by semantic kind."""
    base = {
        "corner_radius": RADIUS["md"],
        "height": 34,
        "font": font(13),
        "border_width": 0,
    }
    styles = {
        "primary": {
            "fg_color": COLORS["primary"],
            "hover_color": COLORS["primary_hover"],
            "text_color": COLORS["text"],
        },
        "secondary": {
            "fg_color": COLORS["card_alt"],
            "hover_color": COLORS["hover"],
            "text_color": COLORS["text"],
            "border_width": 1,
            "border_color": COLORS["border"],
        },
        "ghost": {
            "fg_color": "transparent",
            "hover_color": COLORS["hover"],
            "text_color": COLORS["text_muted"],
            "border_width": 1,
            "border_color": COLORS["border"],
        },
        "success": {
            "fg_color": COLORS["success"],
            "hover_color": COLORS["success_hover"],
            "text_color": COLORS["text"],
        },
        "warning": {
            "fg_color": COLORS["warning"],
            "hover_color": COLORS["warning_hover"],
            "text_color": COLORS["text"],
        },
        "danger": {
            "fg_color": COLORS["danger"],
            "hover_color": COLORS["danger_hover"],
            "text_color": COLORS["text"],
        },
        "neutral": {
            "fg_color": COLORS["neutral"],
            "hover_color": COLORS["neutral_hover"],
            "text_color": COLORS["text"],
        },
        "info": {
            "fg_color": COLORS["info"],
            "hover_color": COLORS["info_hover"],
            "text_color": COLORS["text"],
        },
    }
    out = dict(base)
    out.update(styles.get(kind, styles["secondary"]))
    return out


def styled_button(master, text: str, command=None, *, kind: str = "secondary", **extra):
    kwargs = button_style(kind)
    kwargs.update(extra)
    return ctk.CTkButton(master, text=text, command=command, **kwargs)


def card_frame(master, **extra) -> ctk.CTkFrame:
    opts = {
        "fg_color": COLORS["card"],
        "corner_radius": RADIUS["lg"],
        "border_width": 1,
        "border_color": COLORS["border"],
    }
    opts.update(extra)
    return ctk.CTkFrame(master, **opts)


def section_label(master, text: str) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        master,
        text=text,
        font=font(16, weight="bold"),
        text_color=COLORS["text"],
        anchor="w",
    )


def muted_label(master, text: str, *, size: int = 12) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        master,
        text=text,
        font=font(size),
        text_color=COLORS["text_muted"],
        anchor="w",
    )


def entry_kwargs() -> dict[str, Any]:
    return {
        "fg_color": COLORS["input"],
        "border_color": COLORS["border"],
        "border_width": 1,
        "text_color": COLORS["text"],
        "placeholder_text_color": COLORS["text_dim"],
        "corner_radius": RADIUS["sm"],
        "height": 34,
    }


def textbox_kwargs() -> dict[str, Any]:
    return {
        "fg_color": COLORS["input"],
        "border_color": COLORS["border"],
        "border_width": 1,
        "text_color": COLORS["text"],
        "corner_radius": RADIUS["md"],
    }


def badge_colors(kind: str = "idle") -> tuple[str, str]:
    """Return (fg_color, text_color) for status badge."""
    mapping = {
        "ok": (COLORS["success_soft"], COLORS["success"]),
        "error": (COLORS["danger_soft"], COLORS["danger"]),
        "warn": (COLORS["warning_soft"], COLORS["warning"]),
        "progress": (COLORS["primary_soft"], COLORS["primary"]),
        "idle": (COLORS["card_alt"], COLORS["text_muted"]),
    }
    return mapping.get(kind, mapping["idle"])
