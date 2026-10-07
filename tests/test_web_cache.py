import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="需要 node 才能跑网页端脚本")

PRELUDE = r"""
const fs = require('fs');
const vm = require('vm');

const storage = new Map();
const sandbox = {console, JSON, Date, Object, Math, String, parseInt, setTimeout};
sandbox.window = {QW: {config: JSON.parse(process.argv[3])}};
sandbox.QW = sandbox.window.QW;
sandbox.localStorage = {
  getItem: key => (storage.has(key) ? storage.get(key) : null),
  setItem: (key, value) => storage.set(key, String(value)),
  removeItem: key => storage.delete(key)
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), sandbox);
const cache = sandbox.QW.cache;
const out = {};
"""

HARNESS = PRELUDE + r"""
out.miss = cache.get('m1', '没问过');
cache.put('m1', '你好', '你好呀');
const firstHit = cache.get('m1', '你好');
out.hit = firstHit.answer;
out.hits = firstHit.hits;
out.perModel = cache.get('m2', '你好');

cache.put('m1', '你好', '改过的回答');
out.overwritten = cache.get('m1', '你好').answer;

out.beforeClear = cache.stats().entries;
out.cleared = cache.clear();
out.afterClear = cache.stats().entries;
out.getAfterClear = cache.get('m1', '你好');

for (let i = 0; i < 10; i += 1) cache.put('m1', 'q' + i, 'a' + i);
out.maxKept = cache.stats().entries;
out.newestKept = cache.get('m1', 'q9') !== null;
out.oldestEvicted = cache.get('m1', 'q0') === null;

out.dropMissing = cache.drop('m1', '不存在');
out.dropExisting = cache.drop('m1', 'q9');
out.afterDrop = cache.stats().entries;

out.emptyAnswerIgnored = cache.put('m1', '空回答', '');
console.log(JSON.stringify(out));
"""

EXPIRY_HARNESS = PRELUDE + r"""
cache.put('m1', 'q', 'a');
out.beforeExpiry = cache.get('m1', 'q') !== null;
setTimeout(() => {
  out.afterExpiry = cache.get('m1', 'q');
  out.left = cache.stats().entries;
  console.log(JSON.stringify(out));
}, JSON.parse(process.argv[3]).CACHE_TTL * 1000 + 300);
"""


@pytest.fixture
def run_harness(repo_root, tmp_path):
    cache_js = repo_root / "resources/web/onlinechat/js/cache.js"

    def run(source, config):
        script = tmp_path / f"harness-{abs(hash(source)) % 100000}.js"
        script.write_text(source, encoding="utf-8")
        result = subprocess.run(
            [NODE, str(script), str(cache_js), json.dumps(config)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    return run


def test_cache_hit_miss_and_overwrite(run_harness):
    out = run_harness(HARNESS, {"CACHE_KEY": "k", "CACHE_TTL": 3600, "CACHE_MAX": 200})

    assert out["miss"] is None
    assert out["hit"] == "你好呀"
    assert out["perModel"] is None, "不同模型的同名问题不能互相命中"
    assert out["hits"] == 1
    assert out["overwritten"] == "改过的回答"
    assert out["dropMissing"] is False
    assert out["dropExisting"] is True
    assert out["emptyAnswerIgnored"] is None


def test_cache_clear(run_harness):
    out = run_harness(HARNESS, {"CACHE_KEY": "k", "CACHE_TTL": 3600, "CACHE_MAX": 200})

    assert out["beforeClear"] == 1
    assert out["cleared"] == 1
    assert out["afterClear"] == 0
    assert out["getAfterClear"] is None


def test_cache_evicts_oldest_beyond_max(run_harness):
    out = run_harness(HARNESS, {"CACHE_KEY": "k", "CACHE_TTL": 3600, "CACHE_MAX": 3})

    assert out["maxKept"] == 3, "超过上限没有淘汰"
    assert out["newestKept"] is True
    assert out["oldestEvicted"] is True, "淘汰的应该是最久没用的那条"
    assert out["afterDrop"] == 2


def test_expired_entry_is_dropped(run_harness):
    out = run_harness(EXPIRY_HARNESS, {"CACHE_KEY": "k", "CACHE_TTL": 0.4, "CACHE_MAX": 200})

    assert out["beforeExpiry"] is True
    assert out["afterExpiry"] is None, "过期缓存不该命中"
    assert out["left"] == 0, "过期条目应该被顺手清掉"


def test_cache_survives_broken_storage(repo_root, tmp_path):
    script = tmp_path / "broken.js"
    script.write_text(PRELUDE + r"""
sandbox.localStorage.getItem = () => '{ 坏掉的 JSON';
out.put = cache.put('m1', 'q', 'a');
out.get = cache.get('m1', 'q');
console.log(JSON.stringify(out));
""", encoding="utf-8")

    result = subprocess.run(
        [NODE, str(script), str(repo_root / "resources/web/onlinechat/js/cache.js"),
         json.dumps({"CACHE_KEY": "k", "CACHE_TTL": 3600, "CACHE_MAX": 200})],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["put"] is not None
    assert out["get"]["answer"] == "a"


def test_script_loaded_before_app(repo_root):
    html = (repo_root / "resources/web/onlinechat/index.html").read_text(encoding="utf-8")
    ordered = [line for line in html.splitlines() if "js/" in line and "script" in line]
    names = [Path(line.split('src="')[1].split('"')[0]).name for line in ordered]
    assert names.index("cache.js") < names.index("app.js")
