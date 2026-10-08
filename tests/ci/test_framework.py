from __future__ import annotations

import json

import pytest

from tools.ci import reporters
from tools.ci.core import Finding, Location, Report, Severity, registered_checks, select
from tools.ci.settings import Settings

from conftest import write_mini_repo


def test_registry_is_loaded_and_unique():
    checks = registered_checks()
    assert len(checks) >= 54
    ids = [chk.id for chk in checks]
    assert len(ids) == len(set(ids))
    for chk in checks:
        assert chk.category
        assert chk.title


def test_select_by_id_category_and_glob():
    assert {chk.id for chk in select(["ui/*"])} == {chk.id for chk in registered_checks() if chk.id.startswith("ui/")}
    assert all(chk.category == "theme" for chk in select(["theme"]))
    assert [chk.id for chk in select(["abs/contract"])] == ["abs/contract"]
    with pytest.raises(KeyError):
        select(["does/not-exist"])


def test_select_does_not_do_substring_matching():
    """``theme`` 只能选中 theme 分类，不能顺带命中 id 里含 theme 的其它检查。"""
    selected = {chk.id for chk in select(["theme"])}
    assert selected == {chk.id for chk in registered_checks() if chk.category == "theme"}
    assert all(chk.id.startswith("theme/") for chk in select(["theme"]))

    # 前缀通配符仍然可用
    assert {chk.id for chk in select(["hygiene*"])} == {
        chk.id for chk in registered_checks() if chk.id.startswith("hygiene")
    }


def test_severity_parse():
    assert Severity.parse("ERROR") is Severity.ERROR
    assert Severity.parse(" warning ") is Severity.WARNING
    with pytest.raises(ValueError):
        Severity.parse("fatal")
    assert Severity.ERROR.rank > Severity.WARNING.rank > Severity.INFO.rank


def test_finding_sort_and_dict():
    first = Finding("a", Severity.ERROR, "m", Location("b.py", 2))
    second = Finding("a", Severity.ERROR, "m", Location("a.py", 5))
    assert sorted([first, second], key=lambda f: f.sort_key)[0].location.path == "a.py"
    payload = first.as_dict()
    assert payload["severity"] == "error"
    assert payload["path"] == "b.py"


def test_location_third_positional_is_symbol_not_column():
    """``Location(path, line, "符号")`` 必须落在 symbol 上，否则列号会变成字符串。"""
    location = Location("a.py", 7, "SomeClass")
    assert location.symbol == "SomeClass"
    assert location.column == 0
    assert str(location) == "a.py:7 (SomeClass)"

    from_node = Location.of(_node_at_line_7(), "a.py", "Sym")
    assert from_node.symbol == "Sym"
    assert isinstance(from_node.column, int)


def _node_at_line_7():
    import ast

    source = "\n".join(["pass"] * 6 + ["x = 1"])
    node = ast.parse(source, "a.py").body[-1]
    assert node.lineno == 7
    assert isinstance(node.col_offset, int)
    return node


def test_reporters_survive_three_arg_locations(mini_repo):
    """回归：所有输出格式都要能吃 ``Location(path, line, symbol)``。"""
    root = mini_repo({"stlibs/__init__.py": "SharingData = None\n"})
    from tools.ci import run

    report = run(root=root, only=["theme/protocol-declared"])
    assert report.findings, "该样例应该产生一条问题"
    assert report.findings[0].location.symbol == "_ThemeTypingProtocol"
    for renderer in (reporters.render_text, reporters.render_markdown, reporters.render_github):
        assert renderer(report)
    json.loads(reporters.render_sarif(report))


BARE_EXCEPT = "try:\n    pass\nexcept:\n    pass\n"


def test_inline_suppression_all_and_targeted(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": (
                "try:\n"
                "    pass\n"
                "except:  # ci: ignore\n"
                "    pass\n"
                "\n"
                "try:\n"
                "    pass\n"
                "except:  # ci: ignore=hygiene/bare-except\n"
                "    pass\n"
            )
        }
    )
    from tools.ci import run

    report = run(root=root, only=["hygiene/bare-except"])
    assert report.findings == []
    assert report.suppressed == 2


def test_targeted_suppression_does_not_mask_other_checks(mini_repo):
    root = mini_repo({"pkg/mod.py": "try:\n    pass\nexcept:  # ci: ignore=other/check\n    pass\n"})
    from tools.ci import run

    report = run(root=root, only=["hygiene/bare-except"])
    assert len(report.findings) == 1
    assert report.suppressed == 0


def test_global_ignore_from_settings(mini_repo):
    """``ignore``：照跑但不计入报告；``disable``：根本不跑。"""
    root = mini_repo({"pkg/mod.py": BARE_EXCEPT})
    from tools.ci import run

    assert len(run(root=root, only=["hygiene/bare-except"]).findings) == 1

    ignored = run(root=root, only=["hygiene/bare-except"], ignore=("hygiene/bare-except",))
    assert ignored.findings == []
    assert ignored.suppressed == 1, "ignore 的条目要计入 suppressed"
    assert ignored.results[0].crash is None

    disabled = run(root=root, only=["hygiene/bare-except"], disable=("hygiene/bare-except",))
    assert disabled.findings == []
    assert disabled.suppressed == 0


def test_exclude_is_additive_with_defaults(mini_repo):
    """pyproject 里的 exclude 不能把默认排除项顶掉。"""
    root = mini_repo({"pkg/mod.py": BARE_EXCEPT, "test/local.py": BARE_EXCEPT})
    (root / "pyproject.toml").write_text(
        '[tool.adpci]\nexclude = ["vendor/*"]\n', encoding="utf-8"
    )
    from tools.ci import run

    report = run(root=root, only=["hygiene/bare-except"])
    paths = {item.location.path for item in report.findings}
    assert paths == {"pkg/mod.py"}, "test/ 仍应被默认排除项挡住"


def test_allow_tokens(mini_repo):
    root = mini_repo({})
    settings = Settings.load(root)
    settings.allow = ("ui/x:Token", "other:Y")
    assert settings.allow_tokens("ui/x") == {"Token"}
    assert settings.allow_tokens("ui/y") == set()


def test_settings_excludes_hidden_directories():
    settings = Settings(root=__import__("pathlib").Path("."))
    assert settings.is_excluded(".venv/Lib/site-packages/x.py")
    assert settings.is_excluded(".PluginDevOld/plugin/main.py")
    assert settings.is_excluded("test/test.py")
    assert not settings.is_excluded("stlibs/themes/hacker/__init__.py")


def test_report_counts_and_exit_code(mini_repo):
    root = mini_repo({"pkg/mod.py": BARE_EXCEPT})
    from tools.ci import run

    report = run(root=root, only=["hygiene/bare-except"])
    assert isinstance(report, Report)
    assert report.counts()["warning"] == 1
    assert report.exit_code(Severity.ERROR) == 0
    assert report.exit_code(Severity.WARNING) == 1
    assert report.crashes == []


def test_reporters_shapes(mini_repo):
    root = mini_repo({"pkg/mod.py": BARE_EXCEPT})
    from tools.ci import run

    report = run(root=root, only=["hygiene/bare-except"])
    text = reporters.render_text(report)
    assert "hygiene/bare-except" in text

    payload = json.loads(reporters.render_json(report))
    assert payload["summary"]["warning"] == 1
    assert payload["results"][0]["findings"][0]["check"] == "hygiene/bare-except"

    markdown = reporters.render_markdown(report)
    assert "hygiene/bare-except" in markdown

    sarif = json.loads(reporters.render_sarif(report))
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["results"][0]["ruleId"] == "hygiene/bare-except"

    github = reporters.render_github(report)
    assert github.startswith("::warning file=")


def test_reporter_text_limit(mini_repo):
    source = BARE_EXCEPT * 3
    root = mini_repo({"pkg/mod.py": source})
    from tools.ci import run

    report = run(root=root, only=["hygiene/bare-except"])
    assert len(report.findings) == 3
    assert "另有 1 条问题未显示" in reporters.render_text(report, limit=2)


# --- 文件头部不许写模块 docstring（见 AGENTS.md） ---------------------------
def test_module_docstring_is_flagged(mini_repo):
    root = mini_repo({
        "pkg/with_header.py": '"""这个文件干什么的。"""\n\nVALUE = 1\n',
        "pkg/without_header.py": "# 说明写在注释里\nVALUE = 2\n",
    })
    from tools.ci import run

    report = run(root=root, only=["hygiene/module-docstring"])
    findings = report.findings

    assert len(findings) == 1, [f.message for f in findings]
    assert findings[0].location.path == "pkg/with_header.py"
    assert findings[0].location.line == 1
    assert findings[0].severity is Severity.ERROR


def test_class_and_function_docstrings_are_not_flagged(mini_repo):
    """只拦"文件开头那一大段"，类/函数自己的 docstring 照常写。"""
    root = mini_repo({
        "pkg/ok.py": (
            "# 模块级说明用注释\n"
            "class Thing:\n"
            '    """类的说明。"""\n'
            "\n"
            "    def run(self):\n"
            '        """方法的说明。"""\n'
            "        return 1\n"
        ),
    })
    from tools.ci import run

    assert run(root=root, only=["hygiene/module-docstring"]).findings == []


def test_real_repo_has_no_module_docstrings(repo_root):
    """本仓库自己必须干净（清理过一遍，这条防回退）。"""
    from tools.ci import run

    report = run(root=repo_root, only=["hygiene/module-docstring"])

    assert report.crashes == [], [r.crash for r in report.crashes]
    assert report.findings == [], [str(f.location) for f in report.findings]
