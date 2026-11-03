import json

import stlibs
from stlibs import secrets
from stlibs.mproc.onlinechat import registry


def test_secret_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets, 'SECRETS_DIR', str(tmp_path / '.env'))

    assert secrets.sync_model_keys({'A': 'sk-test'}) is True
    assert secrets.model_keys() == {'A': 'sk-test'}
    merged = secrets.merge_models({'A': {'name': 'm', 'baseurl': 'u'}})
    assert merged['A']['apikey'] == 'sk-test'
    stripped = secrets.strip_models({'A': {'name': 'm', 'apikey': 'sk-test', 'baseurl': 'u'}})
    assert 'apikey' not in stripped['A']


def test_config_save_moves_key_to_env(tmp_path, monkeypatch):
    config_path = str(tmp_path / 'configure.json')
    monkeypatch.setattr(stlibs, 'CONFIG_PATH', config_path)
    monkeypatch.setattr(secrets, 'SECRETS_DIR', str(tmp_path / '.env'))
    monkeypatch.setattr(stlibs.Config, 'models', {
        'A': {'name': 'm', 'apikey': 'sk-test', 'baseurl': 'https://api'},
    }, raising=False)

    stlibs.ConfigLoader.save_config()

    with open(config_path, 'r', encoding='utf-8') as handle:
        saved = json.load(handle)
    assert 'apikey' not in saved['models']['A']
    assert secrets.model_keys() == {'A': 'sk-test'}

    loaded = stlibs.ConfigLoader.load_config()
    assert loaded.models['A']['apikey'] == 'sk-test'


def test_environment_variable_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets, 'SECRETS_DIR', str(tmp_path / '.env'))
    monkeypatch.setenv('ADP_API_KEY_MY_MODEL', 'sk-env')

    merged = secrets.merge_models({'my-model': {'name': 'm'}})

    assert merged['my-model']['apikey'] == 'sk-env'


def test_removing_model_clears_secret(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets, 'SECRETS_DIR', str(tmp_path / '.env'))
    secrets.sync_model_keys({'A': 'sk-test'})

    assert secrets.sync_model_keys({}) is True
    assert secrets.model_keys() == {}


def test_webchat_registry_merges_secret(tmp_path, monkeypatch):
    config_path = tmp_path / 'configure.json'
    config_path.write_text(json.dumps({'models': {'A': {'name': 'm', 'baseurl': 'u'}}}), encoding='utf-8')
    monkeypatch.setattr(registry, 'CONFIG_PATH', str(config_path))
    monkeypatch.setattr(secrets, 'SECRETS_DIR', str(tmp_path / '.env'))
    secrets.sync_model_keys({'A': 'sk-test'})

    models = registry.cloud_models()
    assert models['A']['apikey'] == 'sk-test'


def test_sdk_config_hides_key(monkeypatch):
    from stlibs.sdk.methods import HostMethods

    monkeypatch.setattr(stlibs.Config, 'models', {
        'A': {'name': 'm', 'apikey': 'sk-test', 'baseurl': 'u'},
    }, raising=False)
    public = HostMethods.get_config('models')['models']
    assert 'apikey' not in public['A']
