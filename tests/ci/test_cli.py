"""命令行入口的行为验证。"""

from __future__ import annotations

import json

from tools.ci.__main__ import build_parser, discover_root, main
from tools.ci.core import Severity, select


def test_discover_root_from_subdirectory(repo_root, monkeypatch):
    monkeypatch.chdir(repo_root / "stlibs")
    assert discover_root() == repo_root


def test_list_prints_every_check(repo_root, capsys):
    assert main(["--root", str(repo_root), "--list"]) == 0
    output = capsys.readouterr().out
    for chk in select(None):
        assert chk.id in output
    assert "契约/文档" in output  # docs 字段会被带出来


def test_unknown_check_name_is_a_clean_error(repo_root, capsys):
    assert main(["--root", str(repo_root), "does/not-exist"]) == 2
    captured = capsys.readouterr()
    assert "参数错误" in captured.err
    assert "Traceback" not in captured.err


def test_json_output_written_to_file(repo_root, tmp_path):
    target = tmp_path / "report.json"
    code = main(["--root", str(repo_root), "--format", "json", "--output", str(target), "--quiet"])
    assert code in (0, 1)
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["summary"]["checks"] >= 50
    assert "results" in payload


def test_exit_code_reflects_findings(mini_repo):
    root = mini_repo({"pkg/mod.py": "try:\n    pass\nexcept:\n    pass\n"})
    # 默认只把 error 当失败 → warning 不影响退出码
    assert main(["--root", str(root), "hygiene/bare-except", "--no-color"]) == 0
    # --strict / --fail-on warning 才会失败
    assert main(["--root", str(root), "hygiene/bare-except", "--no-color", "--strict"]) == 1
    assert main(["--root", str(root), "hygiene/bare-except", "--no-color", "--fail-on", "warning"]) == 1


def test_fail_on_info(mini_repo):
    root = mini_repo({"requirements.txt": "markdown==3.0\n", "pkg/mod.py": "import os\n"})
    assert main(["--root", str(root), "import/unused-req", "--no-color"]) == 0
    assert main(["--root", str(root), "import/unused-req", "--no-color", "--fail-on", "info"]) == 1


def test_parser_defaults():
    args = build_parser().parse_args([])
    assert args.format == "text"
    assert args.checks == []
    assert args.strict is False
    assert args.output is None

    args = build_parser().parse_args(["--sarif", "--strict", "ui/*"])
    assert args.format == "sarif"
    assert args.strict is True
    assert args.checks == ["ui/*"]


def test_severity_choice_is_validated():
    import pytest

    with pytest.raises(SystemExit):
        build_parser().parse_args(["--fail-on", "fatal"])


def test_strict_flag_maps_to_warning_threshold(repo_root):
    from tools.ci.core import Severity as S

    assert S.parse("warning") is S.WARNING
