import json
import shutil
import subprocess

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="需要 node 才能跑网页端脚本")

PRELUDE = r"""
const fs = require('fs');
const vm = require('vm');

// 够用的浏览器替身：FileReader 直接吐 data URL，Image 立即 onload，canvas 给个 1x1
function FileReaderStub() {}
FileReaderStub.prototype.readAsDataURL = function (file) {
  this.result = 'data:' + (file.type || 'application/octet-stream') + ';base64,' + file._b64;
  if (this.onload) this.onload();
};
FileReaderStub.prototype.readAsText = function (file) {
  this.result = file._text || '';
  if (this.onload) this.onload();
};
function ImageStub() {
  const self = this;
  Object.defineProperty(this, 'src', {
    set() { self.width = 40; self.height = 20; if (self.onload) self.onload(); }
  });
}
const document = {
  createElement(tag) {
    if (tag !== 'canvas') return {};
    return {
      width: 0, height: 0,
      getContext() { return {drawImage() {}}; },
      toDataURL() { return 'data:image/jpeg;base64,dGh1bWI='; }
    };
  }
};
function File(name, size, type) {
  return {
    name, size, type, _b64: 'QUJD', _text: '文件内容',
    text() { return Promise.resolve(this._text); }
  };
}
const sandbox = {
  console, JSON, Object, String, Array, Promise, setTimeout,
  Image: ImageStub, FileReader: FileReaderStub, document
};
sandbox.window = {QW: {config: JSON.parse(process.argv[3])}};
sandbox.QW = sandbox.window.QW;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), sandbox);
const attach = sandbox.QW.attach;
const out = {};
"""
HARNESS = PRELUDE + r"""
out.sizes = [0, 999, 2048, 5 * 1024 * 1024].map(attach.humanSize);
out.isImage = [
  attach.isImage({name: 'a.png', type: ''}),
  attach.isImage({name: 'a.txt', type: 'text/plain'}),
  attach.isImage({name: 'x', type: 'image/webp'})
];
let changes = 0;
let notices = [];
attach.init({onChange() { changes += 1; }, onNotice(t, l) { notices.push([l, t]); }});
(async () => {
  out.added = await attach.addFiles([
    File('cat.png', 100, 'image/png'),
    File('说明.md', 20, 'text/markdown'),
    File('大文件.bin', 999999999, 'application/octet-stream')
  ]);
  out.pending = attach.pending.map(i => i.kind + ':' + i.name);
  out.changesAfterAdd = changes;
  out.noticeAfterAdd = notices[notices.length - 1];
  const payload = attach.pending.map(attach.toPayload);
  out.payloadKeys = Object.keys(payload[0]).sort();
  out.payloadName = payload[0].name;
  const stored = attach.pending.map(attach.toStored);
  out.storedImageKeys = Object.keys(stored[0]).sort();
  out.storedHasThumb = typeof stored[0].thumb === 'string' && stored[0].thumb.length > 0;
  out.storedText = stored[1].preview;
  const taken = attach.take();
  out.taken = taken.length;
  out.afterTake = attach.pending.length;
  // 粘贴：只要图片，纯文本不该被吃掉
  const tick = () => new Promise(resolve => setTimeout(resolve, 0));
  await attach.addFiles([File('one.png', 10, 'image/png'), File('two.png', 10, 'image/png')]);
  const pasteEvent = {
    clipboardData: {files: [File('pasted.png', 10, 'image/png')], items: []},
    preventDefault() { out.pastePrevented = true; }
  };
  out.pasteHandled = attach.handlePaste(pasteEvent);
  await tick();
  out.afterPaste = attach.pending.length;
  // Firefox 那类只给 items 不给 files 的情况
  const itemsOnly = {
    clipboardData: {
      files: [],
      items: [
        {kind: 'string', getAsFile: () => null},
        {kind: 'file', getAsFile: () => File('from-items.png', 12, 'image/png')}
      ]
    },
    preventDefault() { out.itemsPastePrevented = true; }
  };
  out.itemsPasteHandled = attach.handlePaste(itemsOnly);
  await tick();
  out.afterItemsPaste = attach.pending.length;
  // files 和 items 指向同一张图时不能加两次
  const duplicated = {
    clipboardData: {
      files: [File('same.png', 30, 'image/png')],
      items: [{kind: 'file', getAsFile: () => File('same.png', 30, 'image/png')}]
    },
    preventDefault() {}
  };
  out.collected = attach.collectFiles(duplicated.clipboardData).length;
  // 纯文字粘贴：不拦
  out.textPasteHandled = attach.handlePaste({
    clipboardData: {files: [], items: [{kind: 'string', getAsFile: () => null}]},
    preventDefault() { out.textPastePrevented = true; }
  });
  const dropEvent = {
    dataTransfer: {files: [File('dropped.png', 10, 'image/png')]},
    preventDefault() { out.dropPrevented = true; }
  };
  out.dropHandled = attach.handleDrop(dropEvent);
  await tick();
  out.afterDrop = attach.pending.length;
  out.removeIndex = (() => { attach.remove(0); return attach.pending.length; })();
  attach.clear();
  out.afterClear = attach.pending.length;
  // 上限：超过 MAX 就不再收
  const many = [];
  for (let i = 0; i < 10; i += 1) many.push(File('m' + i + '.txt', 10, 'text/plain'));
  await attach.addFiles(many);
  out.capped = attach.pending.length;
  out.capNotice = notices[notices.length - 1][1];
  console.log(JSON.stringify(out));
})();
"""


@pytest.fixture
def run_attach(repo_root, tmp_path):
    script_path = repo_root / "resources/web/onlinechat/js/attach.js"

    def run(config=None):
        script = tmp_path / "attach-harness.js"
        script.write_text(HARNESS, encoding="utf-8")
        result = subprocess.run(
            [NODE, str(script), str(script_path),
             json.dumps(config or {"MAX_ATTACHMENTS": 3, "MAX_ATTACHMENT_BYTES": 1024 * 1024})],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    return run


def test_human_size_and_image_detection(run_attach):
    out = run_attach()

    assert out["sizes"] == ["0 B", "999 B", "2.0 KB", "5.0 MB"]
    assert out["isImage"] == [True, False, True]


def test_add_files_keeps_images_and_documents(run_attach):
    out = run_attach()

    assert out["added"] == 2, "超大文件要被挡掉"
    assert out["pending"] == ["image:cat.png", "file:说明.md"]
    assert out["changesAfterAdd"] == 1
    assert out["noticeAfterAdd"][0] == "warning"
    assert "太大" in out["noticeAfterAdd"][1]


def test_payload_and_stored_shapes(run_attach):
    out = run_attach()

    assert out["payloadKeys"] == ["data", "mime", "name"]
    assert out["payloadName"] == "cat.png"
    assert out["storedImageKeys"] == ["kind", "mime", "name", "size", "thumb"]
    assert out["storedHasThumb"] is True, "历史记录里要留缩略图"
    assert out["storedText"] == "文件内容"


def test_take_clears_pending(run_attach):
    out = run_attach()

    assert out["taken"] == 2
    assert out["afterTake"] == 0


def test_paste_and_drop_add_images(run_attach):
    out = run_attach()

    assert out["pasteHandled"] is True
    assert out["pastePrevented"] is True
    assert out["afterPaste"] == 3, "两张 + 粘贴一张（上限以内）"
    assert out["itemsPasteHandled"] is True, "只有 items 的浏览器也要能粘"
    assert out["itemsPastePrevented"] is True
    assert out["afterItemsPaste"] == 3
    assert out["collected"] == 1, "files 和 items 里同一张图不能算两次"
    assert out["textPasteHandled"] is False, "纯文字粘贴不该被拦"
    assert "textPastePrevented" not in out
    assert out["dropHandled"] is True
    assert out["dropPrevented"] is True
    assert out["afterDrop"] == 3, "到上限后不再加"


def test_remove_and_clear(run_attach):
    out = run_attach()

    assert out["removeIndex"] == 2
    assert out["afterClear"] == 0


def test_cap_notice_mentions_limit(run_attach):
    out = run_attach()

    assert out["capped"] == 3
    assert "最多" in out["capNotice"]


def test_attach_is_loaded_before_app(repo_root):
    html = (repo_root / "resources/web/onlinechat/index.html").read_text(encoding="utf-8")
    lines = [line for line in html.splitlines() if "js/" in line and "script" in line]
    names = [line.split('src="')[1].split('"')[0].split("/")[-1] for line in lines]

    assert names.index("attach.js") < names.index("render.js")
    assert names.index("attach.js") < names.index("app.js")
