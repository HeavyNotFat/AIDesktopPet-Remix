"""ADPRemix CI/CD 质量门禁。

    from tools.ci import run, Severity

    report = run()
    assert report.exit_code() == 0

对外只需要记三样东西：:func:`run`、:class:`Report`、:class:`Severity`。
"""

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
