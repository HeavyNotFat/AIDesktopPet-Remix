"""配置结构 / 资源 / 网页契约 / 卫生检查的行为验证。"""

from __future__ import annotations

import json

from conftest import findings_of, run_checks


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------
CONFIG_JSON = json.dumps(
    {
        "models": {},
        "memory": {"shortterm": True, "longterm": True},
        "rag": {"enable": False, "top_k": 3},
        "mcp": {"enable": False, "mcp": []},
        "name": "Neko",
        "model_live2d": "",
        "static_model": "",
        "opacity": 1,
        "size": 110,
        "rotate": 0,
        "theme": "hacker",
    },
    ensure_ascii=False,
)

CONFIG_DATACLASS = '''
from dataclasses import dataclass


@dataclass
class _BaseModelConfig:
    models: dict
    memory: dict
    rag: dict
    mcp: dict
    name: str
    model_live2d: str
    static_model: str
    opacity: int
    size: int
    rotate: int
    theme: str = "hacker"
'''


def _config_repo(files: dict[str, str]) -> dict[str, str]:
    return {"resources/configure.json": CONFIG_JSON, "stlibs/__init__.py": CONFIG_DATACLASS, **files}


def test_config_schema_extra_key(mini_repo):
    data = json.loads(CONFIG_JSON)
    data["legacy"] = 1
    root = mini_repo(_config_repo({}) | {"resources/configure.json": json.dumps(data)})
    findings = findings_of(root, "config/schema")
    assert len(findings) == 1
    assert "legacy" in findings[0].message


def test_config_schema_missing_key(mini_repo):
    data = json.loads(CONFIG_JSON)
    del data["rotate"]
    root = mini_repo(_config_repo({}) | {"resources/configure.json": json.dumps(data)})
    findings = findings_of(root, "config/schema")
    assert len(findings) == 1
    assert "rotate" in findings[0].message


def test_config_missing_key_used_by_code(mini_repo):
    root = mini_repo(
        _config_repo(
            {"stlibs/ai/rag/__init__.py": "from ... import Config\n\n\ndef get():\n    return Config.rag['chunks']\n"}
        )
    )
    findings = findings_of(root, "config/missing-key")
    assert len(findings) == 1
    assert "chunks" in findings[0].message


def test_config_key_present_is_clean(mini_repo):
    root = mini_repo(
        _config_repo(
            {"stlibs/ai/rag/__init__.py": "from ... import Config\n\n\ndef get():\n    return Config.rag['top_k']\n"}
        )
    )
    assert findings_of(root, "config/missing-key") == []


def test_animation_mapping(mini_repo):
    animation = json.dumps(
        {
            "smart_control": True,
            "ai_control": False,
            "animation": {"ClickEar": {}},
            "special": {"AppInitial": ""},
        }
    )
    root = mini_repo(
        {
            "resources/animation/live2d.json": animation,
            "stlibs/__init__.py": (
                "from dataclasses import dataclass\n"
                "\n"
                "\n"
                "@dataclass\n"
                "class _BaseModelAnimation:\n"
                "    smart_control: bool\n"
                "    ai_control: bool\n"
                "    ClickEar: dict\n"
                "    AppInitial: str\n"
                "    path: str\n"
            ),
            "stlibs/themes/hacker/__init__.py": (
                "MAPPING_ANIMATION = {'捏耳朵': 'ClickEar', '拍拍头': 'ClickHead'}\n"
                "MAPPING_SPECTIAL_ANIMATION = {'程序启动': 'AppInitial'}\n"
            ),
        }
    )
    findings = findings_of(root, "config/animation")
    messages = " | ".join(f.message for f in findings)
    assert "ClickHead" in messages
    assert "AppInitial" not in messages


def test_prompts_missing_key(mini_repo):
    root = mini_repo(
        {
            "resources/prompts.json": json.dumps({"rag": "x"}),
            "stlibs/ai/rag/context.py": "import json\n\nprompts = json.load(open('./resources/prompts.json'))\n\n\ndef get():\n    return prompts['general']\n",
        }
    )
    findings = findings_of(root, "config/prompts")
    assert len(findings) == 1
    assert "general" in findings[0].message


# --------------------------------------------------------------------------
# resources
# --------------------------------------------------------------------------
def test_resource_missing(mini_repo):
    root = mini_repo({"pkg/mod.py": "P = './resources/icons/nope.png'\nQ = './resources/icons/'\n"})
    findings = findings_of(root, "resource/missing")
    assert len(findings) == 2
    assert all(f.severity.value == "error" for f in findings)


def test_resource_fstring_fragments_are_ignored(mini_repo):
    root = mini_repo({"pkg/mod.py": "def p(name):\n    return f'./resources/character/{name}/3'\n"})
    assert findings_of(root, "resource/missing") == []


def test_resource_web_asset(mini_repo):
    root = mini_repo(
        {
            "resources/web/site/index.html": '<script src="js/app.js"></script>\n<link href="css/missing.css">\n',
            "resources/web/site/js/app.js": "// app\n",
        }
    )
    findings = findings_of(root, "resource/web-asset")
    assert len(findings) == 1
    assert "missing.css" in findings[0].message


def test_resource_character_structure(mini_repo):
    root = mini_repo({"resources/character/model/Mao/mao.model3.json": "{}"})
    findings = findings_of(root, "resource/character")
    messages = " | ".join(f.message for f in findings)
    assert "moc3" in messages
    assert "版本标记" in messages


def test_static_model_frames(mini_repo):
    root = mini_repo(
        {
            "resources/static.json": json.dumps({"fox": {"idle": {"frames": ["idle_"], "op": None}}}),
            "resources/character/static/fox/idle/idle_1.png": "",
        }
    )
    assert findings_of(root, "resource/static-model") == []


def test_json_resources_must_parse(mini_repo):
    root = mini_repo(
        {
            "resources/good.json": json.dumps({"a": 1}),
            "resources/broken.json": '{"a": 1,}',
        }
    )
    findings = findings_of(root, "resource/json-valid")
    assert len(findings) == 1
    assert findings[0].location.path == "resources/broken.json"
    assert findings[0].severity.value == "error"


# --------------------------------------------------------------------------
# web contract
# --------------------------------------------------------------------------
def test_web_api_route_missing(mini_repo):
    root = mini_repo(
        {
            "stlibs/mproc/onlinechat/__init__.py": (
                "from fastapi import APIRouter\n\napi = APIRouter(prefix='/api')\n\n\n@api.post('/chat')\ndef chat(): pass\n"
            ),
            "resources/web/onlinechat/js/api.js": "post('/chat', {});\npost('/gone', {});\n",
        }
    )
    findings = findings_of(root, "web/api-route")
    assert len(findings) == 1
    assert "/gone" in findings[0].message


def test_web_api_port_mismatch(mini_repo):
    root = mini_repo(
        {
            "resources/web/onlinechat/js/config.js": "QW.config = { API_BASE: 'http://127.0.0.1:1/api' };\n",
            "stlibs/mproc/onlinechat/__init__.py": "from fastapi import APIRouter\n\napi = APIRouter(prefix='/api')\n",
            "stlibs/mproc/onlinechat/config.py": "import os\n\nPORT = int(os.getenv('ONLINECHAT_PORT', '52493'))\n",
        }
    )
    findings = findings_of(root, "web/api-port")
    assert len(findings) == 1


def test_web_config_key_undefined(mini_repo):
    root = mini_repo(
        {
            "resources/web/onlinechat/js/config.js": "QW.config = { API_BASE: 'x' };\n",
            "resources/web/onlinechat/js/store.js": "const { STORE_KEY } = QW.config;\n",
        }
    )
    findings = findings_of(root, "web/config-key")
    assert len(findings) == 1
    assert "STORE_KEY" in findings[0].message


def test_web_config_key_defined_is_clean(mini_repo):
    root = mini_repo(
        {
            "resources/web/onlinechat/js/config.js": "QW.config = { STORE_KEY: 'k', MODEL_KEY: 'm' };\n",
            "resources/web/onlinechat/js/store.js": "const { STORE_KEY, MODEL_KEY } = QW.config;\n",
        }
    )
    assert findings_of(root, "web/config-key") == []


def test_web_dom_id(mini_repo):
    root = mini_repo(
        {
            "resources/web/onlinechat/index.html": '<div id="app"></div><script src="js/dom.js"></script>\n',
            "resources/web/onlinechat/js/dom.js": "const $ = id => document.getElementById(id);\nQW.dom = { a: $('app'), b: $('ghost') };\n",
        }
    )
    findings = findings_of(root, "web/dom-id")
    assert len(findings) == 1
    assert "ghost" in findings[0].message


def test_web_namespace_member(mini_repo):
    root = mini_repo(
        {
            "resources/web/onlinechat/index.html": '<script src="js/a.js"></script>\n<script src="js/b.js"></script>\n',
            "resources/web/onlinechat/js/a.js": "QW.api = { chat, resetSession };\n",
            "resources/web/onlinechat/js/b.js": "QW.api.chat(1);\nQW.api.gone(2);\n",
        }
    )
    findings = findings_of(root, "web/namespace")
    assert len(findings) == 1
    assert "gone" in findings[0].message


def test_web_script_not_loaded(mini_repo):
    root = mini_repo(
        {
            "resources/web/onlinechat/index.html": '<script src="js/a.js"></script>\n',
            "resources/web/onlinechat/js/a.js": "// a\n",
            "resources/web/onlinechat/js/b.js": "// b\n",
        }
    )
    findings = findings_of(root, "web/script-loaded")
    assert len(findings) == 1
    assert "b.js" in findings[0].message


# --------------------------------------------------------------------------
# hygiene / imports
# --------------------------------------------------------------------------
def test_bare_except(mini_repo):
    root = mini_repo({"pkg/mod.py": "try:\n    pass\nexcept:\n    pass\n"})
    assert len(findings_of(root, "hygiene/bare-except")) == 1


def test_attribute_typo(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": (
                "class Rect:\n"
                "    def bottom(self):\n"
                "        return 0\n"
                "\n"
                "\n"
                "def f(bounds):\n"
                "    return bounds.ottom()\n"
            )
        }
    )
    findings = findings_of(root, "hygiene/attr-typo")
    assert len(findings) == 1
    assert "ottom" in findings[0].message


def test_attribute_typo_allowlist(mini_repo):
    root = mini_repo({"pkg/mod.py": "def f(bounds):\n    return bounds.ottom()\n"})
    from tools.ci import run

    report = run(root=root, only=["hygiene/attr-typo"], allow=("hygiene/attr-typo:ottom",))
    assert report.findings == []


def test_parse_error_reported(mini_repo):
    root = mini_repo({"pkg/broken.py": "def f(:\n    pass\n"})
    findings = findings_of(root, "hygiene/parse-error")
    assert len(findings) == 1
    assert findings[0].severity.value == "error"


def test_requirements_missing_declaration(mini_repo):
    root = mini_repo(
        {
            "requirements.txt": "PySide6==6.0\n# comment\nrequests>=2\n",
            "pkg/mod.py": "import httpx\nimport requests\nimport os\n",
        }
    )
    findings = findings_of(root, "import/requirements")
    assert len(findings) == 1
    assert "httpx" in findings[0].message


def test_sibling_module_is_not_treated_as_third_party(mini_repo):
    """``python mcp_servers/live2d_motion.py`` 里的 ``from sdk import client``
    指的是同目录的 sdk 包，不是第三方依赖。"""
    root = mini_repo(
        {
            "requirements.txt": "userpath==1.0\n",
            "mcp_servers/__init__.py": "",
            "mcp_servers/sdk/__init__.py": "",
            "mcp_servers/sdk/client.py": "",
            "mcp_servers/live2d_motion.py": "from sdk import client\n",
        }
    )
    assert findings_of(root, "import/requirements") == []
    unused = findings_of(root, "import/unused-req")
    assert all("userpath" in f.message for f in unused)


def test_imported_package_is_not_reported_as_unused(mini_repo):
    root = mini_repo(
        {
            "requirements.txt": "mcp==2.1.1\n",
            "pkg/mod.py": "import mcp\n",
        }
    )
    assert findings_of(root, "import/unused-req") == []


def test_prompts_check_ignores_unrelated_local_dicts(mini_repo):
    """别的文件里恰好叫 prompts 的局部字典不该拿 prompts.json 去比。"""
    root = mini_repo(
        {
            "resources/prompts.json": json.dumps({"rag": "x"}),
            "pkg/mod.py": "prompts = {'local': 'value'}\n\n\ndef get():\n    return prompts['local']\n",
        }
    )
    assert findings_of(root, "config/prompts") == []


def test_prompts_check_only_scans_files_loading_the_json(mini_repo):
    root = mini_repo(
        {
            "resources/prompts.json": json.dumps({"rag": "x"}),
            "pkg/mod.py": (
                "import json\n"
                "prompts = json.load(open('./resources/prompts.json', encoding='utf-8'))\n"
                "\n"
                "def get():\n"
                "    return prompts['missing']\n"
            ),
        }
    )
    findings = findings_of(root, "config/prompts")
    assert len(findings) == 1
    assert "missing" in findings[0].message


def test_unused_requirement_is_info(mini_repo):
    root = mini_repo({"requirements.txt": "PySide6==6.0\nmarkdown==3.0\n", "pkg/mod.py": "import os\n"})
    findings = findings_of(root, "import/unused-req")
    assert any("markdown" in f.message for f in findings)
    assert all(f.severity.value == "info" for f in findings)


def test_import_cycle_detected(mini_repo):
    root = mini_repo(
        {
            "pkg/__init__.py": "",
            "pkg/a.py": "from . import b\n",
            "pkg/b.py": "from . import a\n",
        }
    )
    findings = findings_of(root, "import/cycle")
    assert findings
    assert "pkg.a" in findings[0].message


def test_deferred_import_is_not_a_cycle(mini_repo):
    root = mini_repo(
        {
            "pkg/__init__.py": "",
            "pkg/a.py": "from . import b\n",
            "pkg/b.py": "def later():\n    from . import a\n    return a\n",
        }
    )
    assert findings_of(root, "import/cycle") == []


# --------------------------------------------------------------------------
# 真实仓库
# --------------------------------------------------------------------------
def test_config_resource_web_checks_clean_on_real_repo(repo_root):
    report = run_checks(repo_root, ["config/*", "resource/*", "web/*"])
    assert report.crashes == [], [r.crash for r in report.crashes]
    assert [f for f in report.findings if f.severity.value == "error"] == []
