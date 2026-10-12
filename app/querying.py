from __future__ import annotations


def escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def contains_pattern(text: str) -> str:
    return f"%{escape_like(text)}%"
