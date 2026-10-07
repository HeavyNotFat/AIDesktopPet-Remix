from .core import (
    Check,
    CheckResult,
    Context,
    Finding,
    Location,
    Report,
    Severity,
    register,
    registered_checks,
    run_check,
    select,
)

__all__ = [
    "Check",
    "CheckResult",
    "Context",
    "Finding",
    "Location",
    "Report",
    "Severity",
    "register",
    "registered_checks",
    "run_check",
    "select",
    "run",
    "main",
]

__version__ = "1.0.0"


def run(*args, **kwargs):
    """惰性转发到 :mod:`tools.ci.__main__`，避免 ``python -m tools.ci`` 双重导入。"""
    from .__main__ import run as _run

    return _run(*args, **kwargs)


def main(argv=None) -> int:
    from .__main__ import main as _main

    return _main(argv)
