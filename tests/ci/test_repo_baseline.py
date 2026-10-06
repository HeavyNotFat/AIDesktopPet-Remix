"""仓库基线：真实代码必须能过门禁。

这是 CI 里真正卡合并的那个测试；单条规则的行为验证在别的文件里。
"""

from __future__ import annotations

from tools.ci import run


def test_repo_passes_gate(repo_root):
    report = run(root=repo_root)
    assert report.crashes == [], [r.crash for r in report.crashes]
    errors = [f for f in report.findings if f.severity.value == "error"]
    assert errors == [], [f"{f.check} {f.location} {f.message}" for f in errors]
    warnings = [f for f in report.findings if f.severity.value == "warning"]
    assert warnings == [], [f"{f.check} {f.location} {f.message}" for f in warnings]
    assert report.exit_code() == 0


def test_repo_has_no_parse_errors(repo_root):
    report = run(root=repo_root, only=["hygiene/parse-error"])
    assert report.findings == []


def test_every_check_runs_without_crashing(repo_root):
    report = run(root=repo_root)
    assert len(report.results) >= 54, "检查项被意外删掉了？"
    for result in report.results:
        assert result.crash is None, f"{result.id}: {result.crash}"
        assert result.duration >= 0
