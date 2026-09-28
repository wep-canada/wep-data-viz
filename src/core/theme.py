"""Single source of truth for colour.

The CSS custom properties, the Plotly charts and the map all read from here, so
light and dark mode can never drift apart. Categorical slots, the sequential blue,
and the status palette come from the validated reference palette; the three
categorical slots used (blue, orange, violet) pass every check in both modes
(``validate_palette.js``). Status colours are reserved for status meanings and
are always paired with an icon and a label, never colour alone.
"""

from __future__ import annotations

LIGHT = {
    "page": "#f4f3f0",
    "surface": "#fcfcfb",
    "text": "#0b0b0b",
    "text_2": "#52514e",
    "muted": "#5f5e5a",
    "grid": "#e6e5e1",
    "border": "#dcdad4",
    "accent": "#2a78d6",        # categorical slot 1 / sequential step 450
    "orange": "#eb6834",        # categorical slot 2
    "violet": "#4a3aa7",        # categorical slot 7
    "context": "#a8a7a2",       # de-emphasis grey for emphasis charts
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

DARK = {
    "page": "#121211",
    "surface": "#1a1a19",
    "text": "#ffffff",
    "text_2": "#c3c2b7",
    "muted": "#a5a49a",
    "grid": "#333331",
    "border": "#3a3a37",
    "accent": "#3987e5",        # dark step of categorical slot 1 / sequential 400
    "orange": "#d95926",
    "violet": "#9085e9",
    "context": "#6a6964",
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}


def tokens(mode: str | None) -> dict[str, str]:
    return DARK if mode == "dark" else LIGHT


def _block(selector: str, values: dict[str, str], scheme: str) -> str:
    lines = [f"  color-scheme: {scheme};"]
    lines += [f"  --wd-{k.replace('_', '-')}: {v};" for k, v in values.items()]
    return f"{selector} {{\n" + "\n".join(lines) + "\n}\n"


def css() -> str:
    """CSS custom properties for both modes.

    ``ui.input_dark_mode`` stamps ``data-bs-theme`` on the root element; the media
    query covers the moment before that script runs.
    """
    return (
        _block(":root", LIGHT, "light")
        + "@media (prefers-color-scheme: dark) {\n"
        + _block(':root:not([data-bs-theme="light"])', DARK, "dark")
        + "}\n"
        + _block(':root[data-bs-theme="dark"]', DARK, "dark")
    )


def _luminance(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    r, g, b = (int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG 2 contrast ratio between two ``#rrggbb`` colours."""
    a, b = _luminance(foreground), _luminance(background)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)
