"""
CLI Output Formatting Utilities

Provides colored output and formatting for CLI display.
"""
from __future__ import annotations

import sys
from typing import Any


# ANSI color codes
class Colors:
    """ANSI color codes for terminal output."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    ITALIC = "\033[3m"

    # Foreground colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright foreground colors
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"


def _supports_color() -> bool:
    """Check if terminal supports color output."""
    if not hasattr(sys.stdout, "fileno"):
        return False
    try:
        import os

        return os.isatty(sys.stdout.fileno())
    except (AttributeError, OSError):
        return False


_SUPPORTS_COLOR = _supports_color()


def _colorize(text: str, color: str) -> str:
    """Apply color to text if terminal supports it."""
    if not _SUPPORTS_COLOR:
        return text
    return f"{color}{text}{Colors.RESET}"


def print_info(message: str) -> None:
    """Print informational message."""
    print(_colorize(message, Colors.CYAN))


def print_success(message: str) -> None:
    """Print success message."""
    print(_colorize(message, Colors.GREEN))


def print_warning(message: str) -> None:
    """Print warning message."""
    print(_colorize(message, Colors.YELLOW))


def print_error(message: str) -> None:
    """Print error message."""
    print(_colorize(message, Colors.RED), file=sys.stderr)


def print_header(message: str) -> None:
    """Print header message (bold)."""
    print(_colorize(f"{Colors.BOLD}{message}{Colors.RESET}", ""))


def print_dim(message: str) -> None:
    """Print dimmed message."""
    print(_colorize(message, Colors.WHITE))


def format_table(headers: list[str], rows: list[list[Any]]) -> str:
    """Format data as ASCII table."""
    if not rows:
        return ""

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    lines = []

    # Header
    header_line = " | ".join(
        h.ljust(col_widths[i]) for i, h in enumerate(headers)
    )
    lines.append(header_line)
    lines.append("-" * len(header_line))

    # Rows
    for row in rows:
        row_line = " | ".join(
            str(cell).ljust(col_widths[i]) for i, cell in enumerate(row)
        )
        lines.append(row_line)

    return "\n".join(lines)


def format_key_value(items: dict[str, Any], indent: int = 2) -> str:
    """Format key-value pairs."""
    prefix = " " * indent
    lines = []
    for key, value in items.items():
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            lines.append(format_key_value(value, indent + 2))
        elif isinstance(value, list):
            lines.append(f"{prefix}{key}:")
            for item in value:
                lines.append(f"{prefix}  - {item}")
        else:
            lines.append(f"{prefix}{key}: {value}")
    return "\n".join(lines)
