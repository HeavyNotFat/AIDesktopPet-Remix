import json
import shutil
import subprocess

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="需要 node 才能跑网页端脚本")

PRELUDE = r"""
const fs = require('fs');
const vm = require('vm');

function element(tag) {
  return {
    tag,
    hidden: false,
    textContent: '',
    title: '',
    className: '',
    children: [],
    handlers: {},
    classList: {add() {}, remove() {}},
    setAttribute() {},
    appendChild(child) { this.children.push(child); return child; },
    contains() { return false; },
    addEventListener(type, fn) { (this.handlers[type] = this.handlers[type] || []).push(fn); },
    fire(type, event) { for (const fn of this.handlers[type] || []) fn(event); }
  };
}
const dom = {
  modelBtn: element('button'),
  modelMenu: element('div'),
  modelLabel: element('span')
};
// index.html 里这个菜单默认是 hidden 的
dom.modelMenu.hidden = true;
const store = {state: {models: [], model: null}, saveModel() {}};
const document = {
  createElement: element,
  addEventListener() {}
};
const sandbox = {console, JSON, Object, String, Array};
sandbox.window = {QW: {dom, store}};
sandbox.QW = sandbox.window.QW;
sandbox.document = document;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), sandbox);
const {dom: d, store: s} = sandbox.QW;
const picker = sandbox.QW.modelPicker;
const out = {};
"""
HARNESS = PRELUDE + r"""
let refreshes = 0;
let selects = 0;
let retries = 0;
picker.init({
  onRetry() { retries += 1; },
  onSelect() { selects += 1; },
  onRefresh() { refreshes += 1; }
});
s.state.models = [{value: 'a', label: 'A (API)'}, {value: 'b', label: 'B'}];
s.state.model = 'b';
picker.render();
out.label = d.modelLabel.textContent;
out.options = d.modelMenu.children.length;
out.selected = d.modelMenu.children.filter(o => o.className.includes('on')).length;
d.modelBtn.fire('click', {stopPropagation() {}, target: d.modelBtn});
out.refreshOnOpen = refreshes;
out.openedOnOpen = d.modelMenu.hidden === false;
d.modelBtn.fire('click', {stopPropagation() {}, target: d.modelBtn});
out.hiddenAfterSecondClick = d.modelMenu.hidden;
out.refreshAfterClose = refreshes;
// 重新打开并选另一个模型，选中态要跟着变
d.modelBtn.fire('click', {stopPropagation() {}, target: d.modelBtn});
d.modelMenu.children[0].fire('click', {stopPropagation() {}, target: d.modelMenu.children[0]});
out.modelAfterPick = s.state.model;
out.selects = selects;
out.closedAfterPick = d.modelMenu.hidden === true;
// 模型列表刷新后当前选中项没了，应该退回第一个
s.state.models = [{value: 'c', label: 'C'}];
picker.render();
out.fallbackLabel = d.modelLabel.textContent;
// 出错态：点击应该走重试，而不是展开菜单
picker.showError('炸了');
out.errorLabel = d.modelLabel.textContent;
const refreshesBeforeError = refreshes;
d.modelBtn.fire('click', {stopPropagation() {}, target: d.modelBtn});
out.retries = retries;
out.refreshesInErrorState = refreshes - refreshesBeforeError;
console.log(JSON.stringify(out));
"""


@pytest.fixture
def run_picker(repo_root, tmp_path):
    script_path = repo_root / "resources/web/onlinechat/js/model-picker.js"

    def run():
        script = tmp_path / "picker-harness.js"
        script.write_text(HARNESS, encoding="utf-8")
        result = subprocess.run(
            [NODE, str(script), str(script_path)],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    return run


def test_picker_renders_options_and_marks_selection(run_picker):
    out = run_picker()

    assert out["label"] == "B"
    assert out["options"] == 2
    assert out["selected"] == 1, "选中项应该只有一个"


def test_opening_the_menu_refreshes_the_model_list(run_picker):
    out = run_picker()

    assert out["openedOnOpen"] is True
    assert out["refreshOnOpen"] == 1, "每次展开都要重新拉模型列表（桌面端刚加的模型才能立刻出现）"
    assert out["refreshAfterClose"] == 1, "收起时不用再拉一次"
    assert out["hiddenAfterSecondClick"] is True


def test_picking_a_model_updates_state_and_closes(run_picker):
    out = run_picker()

    assert out["modelAfterPick"] == "a"
    assert out["selects"] == 1
    assert out["closedAfterPick"] is True


def test_picker_falls_back_when_saved_model_disappears(run_picker):
    out = run_picker()

    assert out["fallbackLabel"] == "C"


def test_error_state_click_retries_instead_of_opening(run_picker):
    out = run_picker()

    assert "失败" in out["errorLabel"]
    assert out["retries"] == 1
    assert out["refreshesInErrorState"] == 0, "出错时点击是重试，不该走静默刷新"
