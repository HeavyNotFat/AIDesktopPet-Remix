from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterable, Sequence

if TYPE_CHECKING:  # pragma: no cover - 仅类型
    from .settings import Settings
    from .source import SourceIndex


class Severity(enum.StrEnum):
    """问题等级，``ERROR`` 会让 CI 失败。"""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self]

    @classmethod
    def parse(cls, value: str) -> "Severity":
        value = (value or "").strip().lower()
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(f"未知等级：{value!r}（可选 error/warning/info）")


_SEVERITY_RANK = {Severity.ERROR: 3, Severity.WARNING: 2, Severity.INFO: 1}


@dataclass(frozen=True, slots=True)
class Location:

    path: str
    line: int = 1
    symbol: str | None = None
    column: int = 0

    def __str__(self) -> str:
        text = f"{self.path}:{self.line}"
        if self.symbol:
            text += f" ({self.symbol})"
        return text

    @classmethod
    def of(cls, node, path: str, symbol: str | None = None) -> "Location":
        return cls(
            path=path,
            line=getattr(node, "lineno", 1) or 1,
            symbol=symbol,
            column=getattr(node, "col_offset", 0) or 0,
        )


@dataclass(frozen=True, slots=True)
class Finding:
    """一条检查结果。"""
    check: str
    severity: Severity
    message: str
    location: Location
    hint: str = ""

    @property
    def sort_key(self) -> tuple:
        return (
            self.location.path,
            self.location.line,
            -self.severity.rank,
            self.check,
            self.message,
        )

    def as_dict(self) -> dict:
        return {
            "check": self.check,
            "severity": self.severity.value,
            "message": self.message,
            "path": self.location.path,
            "line": self.location.line,
            "column": self.location.column,
            "symbol": self.location.symbol,
            "hint": self.hint,
        }


def finding(
    check: str,
    severity: Severity,
    message: str,
    location: Location,
    hint: str = "",
) -> Finding:
    return Finding(check=check, severity=severity, message=message, location=location, hint=hint)


@dataclass(slots=True)
class Context:
    """传给每个检查的上下文。"""
    root: Path
    settings: "Settings"
    sources: "SourceIndex"
    _contract: object = field(default=None, init=False, repr=False, compare=False)

    @property
    def contract(self):
        """主题契约，惰性构建。"""
        if self._contract is None:
            from .contract import build_contract

            self._contract = build_contract(self.sources)
        return self._contract


@dataclass(slots=True)
class CheckResult:
    id: str
    title: str
    category: str
    findings: list[Finding] = field(default_factory=list)
    skipped: str | None = None
    crash: str | None = None
    duration: float = 0.0
    suppressed: int = 0

    @property
    def ok(self) -> bool:
        return not self.crash and not any(f.severity is Severity.ERROR for f in self.findings)

    def counts(self) -> dict[str, int]:
        out = {sev.value: 0 for sev in Severity}
        for f in self.findings:
            out[f.severity.value] += 1
        return out


@dataclass(frozen=True, slots=True)
class Check:
    id: str
    title: str
    category: str
    func: Callable[[Context], Iterable[Finding]]
    docs: str = ""


_REGISTRY: dict[str, Check] = {}


def register(id: str, title: str, category: str, docs: str = ""):
    """把一个检查函数登记进注册表。"""
    def decorator(func: Callable[[Context], Iterable[Finding]]):
        if id in _REGISTRY:
            raise ValueError(f"检查 id 重复：{id}")
        _REGISTRY[id] = Check(id=id, title=title, category=category, func=func, docs=docs)
        return func

    return decorator


def registered_checks() -> list[Check]:
    return list(_REGISTRY.values())


def select(names: Sequence[str] | None) -> list[Check]:
    checks = registered_checks()
    if not names:
        return checks
    chosen: dict[str, Check] = {}
    for pattern in names:
        pattern = pattern.strip()
        if not pattern:
            continue
        matched = False
        for chk in checks:
            if pattern == chk.id or pattern == chk.category:
                chosen[chk.id] = chk
                matched = True
            elif pattern.endswith("*") and chk.id.startswith(pattern[:-1]):
                chosen[chk.id] = chk
                matched = True
        if not matched:
            raise KeyError(f"没有匹配的检查：{pattern}")
    return [chk for chk in checks if chk.id in chosen]


def run_check(chk: Check, ctx: Context) -> CheckResult:
    started = time.perf_counter()
    result = CheckResult(id=chk.id, title=chk.title, category=chk.category)
    try:
        produced = list(chk.func(ctx) or ())
    except Exception as exc:  # noqa: BLE001 - 检查自身崩溃要报出来而不是静默
        import traceback

        result.crash = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
    else:
        kept = []
        for item in produced:
            if ctx.settings.is_disabled(item.check):
                continue
            reason = ctx.settings.suppression(item, ctx.sources)
            if reason:
                result.suppressed += 1
                continue
            kept.append(item)
        result.findings = sorted(kept, key=lambda f: f.sort_key)
    result.duration = time.perf_counter() - started
    return result


@dataclass(slots=True)
class Report:
    root: Path
    results: list[CheckResult] = field(default_factory=list)

    @property
    def findings(self) -> list[Finding]:
        out: list[Finding] = []
        for result in self.results:
            out.extend(result.findings)
        return sorted(out, key=lambda f: f.sort_key)

    def counts(self) -> dict[str, int]:
        out = {sev.value: 0 for sev in Severity}
        for item in self.findings:
            out[item.severity.value] += 1
        return out

    @property
    def crashes(self) -> list[CheckResult]:
        return [r for r in self.results if r.crash]

    @property
    def suppressed(self) -> int:
        return sum(r.suppressed for r in self.results)

    def exit_code(self, fail_on: Severity = Severity.ERROR) -> int:
        if self.crashes:
            return 3
        worst = max((f.severity.rank for f in self.findings), default=0)
        return 1 if worst >= fail_on.rank else 0
