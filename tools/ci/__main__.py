from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core import Context, Report, Severity, run_check, select
from .settings import Settings
from .source import SourceIndex


def discover_root(start: Path | None = None) -> Path:
    """从当前目录往上找带 pyproject.toml 或 stlibs/ 的目录。"""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file() or (candidate / "stlibs").is_dir():
            return candidate
    return current


def run(root: Path | None = None, only: list[str] | None = None, **overrides) -> Report:
    """跑一遍检查并返回报告。"""
    root = (root or discover_root()).resolve()
    settings = Settings.load(root)
    for key, value in overrides.items():
        if value is not None and hasattr(settings, key):
            setattr(settings, key, value)

    sources = SourceIndex(root, settings)

    # 延迟导入：注册表靠 import 的副作用填充
    from . import checks  # noqa: F401  pylint: disable=unused-import

    ctx = Context(root=root, settings=settings, sources=sources)
    report = Report(root=root)
    for chk in select(only):
        report.results.append(run_check(chk, ctx))
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adpci",
        description="ADPRemix UI / 架构质量门禁（静态分析，无第三方依赖）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "检查项按「分类/名字」选择，也可以只写分类或 前缀*（例如 theme/*）。\n"
            "默认全部跑一遍；--strict 时 warning 也算失败，--fail-on 可以指定门槛。\n"
            "用法示例：python -m tools.ci ui/* --no-color --quiet"
        ),
    )
    parser.add_argument("checks", nargs="*", help="要跑的检查 id / 分类（支持 ui/* 形式），默认全部")
    parser.add_argument("--root", type=Path, default=None, help="仓库根目录，默认自动探测")
    parser.add_argument("--list", action="store_true", help="列出所有检查项后退出")
    parser.add_argument(
        "--format",
        default="text",
        choices=("text", "json", "markdown", "github", "sarif"),
        help="输出格式",
    )
    parser.add_argument("--output", type=Path, default=None, help="写入文件而不是 stdout")
    parser.add_argument("--json", dest="format", action="store_const", const="json", help="等价 --format json")
    parser.add_argument("--sarif", dest="format", action="store_const", const="sarif", help="等价 --format sarif")
    parser.add_argument("--no-color", action="store_true", help="关闭彩色输出")
    parser.add_argument("--strict", action="store_true", help="warning 也视为失败")
    parser.add_argument("--quiet", action="store_true", help="只显示有问题的检查")
    parser.add_argument("--fail-on", choices=("error", "warning", "info"), default=None)
    parser.add_argument("--max-findings", type=int, default=None, help="最多输出多少条问题（0 表示不限）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = (args.root or discover_root()).resolve()

    from . import checks  # noqa: F401

    try:
        selected = select(args.checks or None)
    except KeyError as exc:
        print(f"参数错误：{exc.args[0] if exc.args else exc}", file=sys.stderr)
        print("用 --list 查看全部检查项。", file=sys.stderr)
        return 2

    if args.list:
        settings = Settings.load(root)
        for chk in selected:
            flags = []
            if settings.is_disabled(chk.id):
                flags.append("已禁用")
            elif chk.id in settings.ignore:
                flags.append("已忽略")
            suffix = f"  [{', '.join(flags)}]" if flags else ""
            reference = f"  契约/文档：{chk.docs}" if chk.docs else ""
            print(f"{chk.id:34s} [{chk.category}] {chk.title}{suffix}{reference}")
        return 0

    fail_on = Severity.parse(args.fail_on) if args.fail_on else (Severity.WARNING if args.strict else None)
    report = run(root, args.checks or None, fail_on=fail_on, max_findings=args.max_findings)

    from . import reporters

    if args.format == "text":
        output = reporters.render_text(
            report,
            color=not args.no_color and sys.stdout.isatty(),
            show_ok=not args.quiet,
            limit=args.max_findings,
        )
    else:
        output = reporters.render(report, args.format)

    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
        print(f"报告已写入 {args.output}")
    else:
        print(output)

    if report.crashes:
        return 3
    return report.exit_code(fail_on or Severity.ERROR)


if __name__ == "__main__":
    raise SystemExit(main())
