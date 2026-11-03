import base64
import json
import os
import re
import zipfile

from . import RUNTIME_ROOT, bootstrap, find_model


RUNTIME_SCRIPTS = ('fflate.js', 'FreeMoteDriver.js', 'emoteplayer.js')


def _model_bytes(model) -> tuple[bytes, bool]:
    with open(model.model_file, 'rb') as handle:
        data = handle.read()
    if not model.model_file.lower().endswith('.zip'):
        return data, False
    with zipfile.ZipFile(model.model_file) as bundle:
        if not any(info.filename.lower().endswith('.psb') for info in bundle.infolist() if not info.is_dir()):
            raise ValueError('压缩包里没有 .psb')
    return data, True


def _inline_scripts(template: str) -> str:
    for name in RUNTIME_SCRIPTS:
        path = os.path.join(RUNTIME_ROOT, name)
        with open(path, 'r', encoding='utf-8') as handle:
            code = handle.read().replace('</script', '<\\/script')
        template = template.replace(f'<script src="/runtime/{name}"></script>',
                                    f'<script>\n{code}\n</script>')
    return template


def inline_page(model, size, opacity, rotate, render_ratio, tracking_interval) -> bytes:
    """把运行时、模型、config.js 内联成单页，绕过 WebEngine 导航。"""
    if model is None:
        model = find_model('')
    if model is None:
        raise FileNotFoundError('没有 Emote 模型')

    with open(os.path.join(RUNTIME_ROOT, 'index.html'), 'r', encoding='utf-8') as handle:
        template = handle.read()
    template = _inline_scripts(template)

    model_bytes, is_zip = _model_bytes(model)
    data = bootstrap(model, size, opacity, rotate, render_ratio, tracking_interval)
    data['modelUrl'] = ''
    data['configUrl'] = ''
    data['modelBase64'] = base64.b64encode(model_bytes).decode('ascii')
    data['modelIsZip'] = is_zip
    data['configText'] = ''
    if model.config_file:
        with open(model.config_file, 'r', encoding='utf-8') as handle:
            data['configText'] = handle.read()

    payload = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    html = template.replace('/*__EMOTE_BOOTSTRAP__*/', f'window.EMOTE_CONFIG = {payload};')
    html = re.sub(r'<script src="/runtime/[^"]+"></script>', '', html)
    return html.encode('utf-8')


__all__ = ['RUNTIME_SCRIPTS', 'inline_page']
