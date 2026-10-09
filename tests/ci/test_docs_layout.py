from __future__ import annotations

from conftest import findings_of, write_mini_repo


def test_header_comment_is_flagged(work_root):
    root = write_mini_repo(work_root / "repo", {
        "pkg/header.py": "# 文件头说明\nimport os\n",
        "pkg/blank_first.py": "\n\n# 隔了几行也算头部\nimport os\n",
        "pkg/fine.py": "import os\n\n\n# 正文里的注释不管\nx = 1\n",
        "pkg/docstring.py": '"""头部 docstring 归 hygiene/module-docstring 管"""\nimport os\n',
        "pkg/shebang.py": "#!/usr/bin/env python\nimport os\n",
        "pkg/directive.py": "# noqa\nimport os\n",
        "web/app.js": "// 文件头说明\n'use strict';\n",
        "web/style.css": "/* 装饰性标题 */\nbody { color: red; }\n",
        ".github/workflows/ci.yml": "# 触发策略\nname: CI\n",
    })

    flagged = {finding.location.path for finding in findings_of(root, "docs/header-comment")}

    assert flagged == {
        "pkg/header.py",
        "pkg/blank_first.py",
        "web/app.js",
        "web/style.css",
        ".github/workflows/ci.yml",
    }


def test_markdown_location_is_flagged(work_root):
    root = write_mini_repo(work_root / "repo", {
        "README.md": "# 主页\n",
        "AGENTS.md": "# 规则\n",
        "docs/README.md": "# 目录\n",
        "docs/STRUCTURE.md": "# 结构\n",
        "plugins/README.md": "# 插件\n",
        "plugins/plugin_a/README.md": "# 插件里的说明\n",
        "notes.md": "# 乱放的文档\n",
        "plugins/plugin_a/玩法.md": "# 乱放的文档\n",
    })

    flagged = {finding.location.path for finding in findings_of(root, "docs/markdown-location")}

    assert flagged == {"notes.md", "plugins/plugin_a/玩法.md"}


def test_real_repo_has_no_header_comments(repo_root):
    assert findings_of(repo_root, "docs/header-comment") == []


def test_real_repo_keeps_docs_together(repo_root):
    assert findings_of(repo_root, "docs/markdown-location") == []
