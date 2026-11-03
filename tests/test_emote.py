import os
import urllib.request
import zipfile

import pytest

import stlibs.emote as emote


def test_sample_model_is_discovered():
    model = emote.find_model('chocola-maid')

    assert model is not None
    assert model.model_file.lower().endswith('.zip')
    assert os.path.isfile(model.config_file)


def test_bootstrap_urls_are_relative():
    model = emote.find_model('chocola-maid')
    data = emote.bootstrap(model, 90, 1.0, 0, 2.0, 50)

    assert data['modelUrl'].startswith('model/chocola-maid/')
    assert data['configUrl'] == 'model/chocola-maid/config.js'
    assert data['sizePercent'] == 90


def test_import_model_extracts_config(tmp_path):
    archive = tmp_path / 'probe.pure.psb.zip'
    with zipfile.ZipFile(archive, 'w') as handle:
        handle.writestr('probe.psb', b'fake-psb')
        handle.writestr('config.js', 'function getConfig(){return {};}')

    model = emote.import_model(str(archive), name='_test_emote')
    try:
        assert model.name == '_test_emote'
        assert os.path.isfile(model.model_file)
        assert os.path.isfile(model.config_file)
        assert emote.find_model('_test_emote') is not None
    finally:
        emote.remove_model('_test_emote')

    assert emote.find_model('_test_emote') is None


def test_asset_server_serves_page_and_model():
    model = emote.find_model('chocola-maid')
    from stlibs.emote.server import EmoteAssetServer

    server = EmoteAssetServer(emote.bootstrap(model, 100, 1.0, 0, 2.0, 50)).start()
    try:
        with urllib.request.urlopen(server.base_url + '/', timeout=5) as response:
            html = response.read().decode('utf-8')
        assert 'window.EMOTE_CONFIG' in html
        assert 'chocola-maid' in html
        with urllib.request.urlopen(server.base_url + '/runtime/emoteplayer.js', timeout=5) as response:
            assert response.status == 200
            assert len(response.read()) > 1000
        with urllib.request.urlopen(server.base_url + '/model/chocola-maid/chocola-maid.pure.psb.zip', timeout=5) as response:
            assert response.status == 200
    finally:
        server.stop()


def test_scheme_page_contains_bootstrap():
    pytest.importorskip('PySide6.QtWebEngineCore')
    from stlibs.emote.scheme import page_html

    model = emote.find_model('chocola-maid')
    html = page_html(emote.bootstrap(model, 100, 1.0, 0, 2.0, 50)).decode('utf-8')

    assert 'window.EMOTE_CONFIG' in html


def test_inline_page_keeps_model_compressed():
    from stlibs.emote.render import inline_page

    model = emote.find_model('chocola-maid')
    html = inline_page(model, 100, 1.0, 0, 2.0, 50).decode('utf-8')

    assert 'modelIsZip' in html
    assert '<script src="/runtime/' not in html
    assert len(html.encode('utf-8')) < 12 * 1024 * 1024
