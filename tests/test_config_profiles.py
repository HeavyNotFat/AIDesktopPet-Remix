import json
from pathlib import Path

import stlibs
from stlibs import config_profiles


ROOT = Path(__file__).resolve().parents[1]


def _copy_config(tmp_path, **changes):
    data = json.loads((ROOT / 'resources' / 'configure.json').read_text(encoding='utf-8'))
    data.update(changes)
    path = tmp_path / 'configure.json'
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return path


def test_default_size_ratios():
    assert config_profiles.default_size('live2d', 110) == 110
    assert config_profiles.default_size('static', 110) == 77
    assert config_profiles.default_size('emote', 110) == 28


def test_profile_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(stlibs, 'CONFIG_PATH', str(tmp_path / 'configure.json'))

    config_profiles.save('emote', 'chocola-maid', 1, 28, 0)
    profile = config_profiles.load('emote')

    assert profile['model'] == 'chocola-maid'
    assert profile['size'] == 28
    assert config_profiles.profile_root() == str(tmp_path / 'config')


def test_load_config_uses_active_profile(tmp_path, monkeypatch):
    config_path = _copy_config(tmp_path, model_live2d='Mao', static_model='', model_emote='', size=110)
    monkeypatch.setattr(stlibs, 'CONFIG_PATH', str(config_path))
    config_profiles.save('live2d', 'Mao', 1, 55, 0)

    config = stlibs.ConfigLoader.load_config()

    assert config.size == 55


def test_missing_profiles_get_ratio_defaults(tmp_path, monkeypatch):
    config_path = _copy_config(tmp_path, model_live2d='', static_model='fox', model_emote='', size=110)
    monkeypatch.setattr(stlibs, 'CONFIG_PATH', str(config_path))

    config = stlibs.ConfigLoader.load_config()

    assert config.size == 77


def test_switch_type_preserves_each_size(tmp_path, monkeypatch):
    config_path = _copy_config(tmp_path, model_live2d='Mao', static_model='', model_emote='', size=110)
    monkeypatch.setattr(stlibs, 'CONFIG_PATH', str(config_path))
    monkeypatch.setattr(stlibs, 'Config', stlibs.ConfigLoader.load_config())

    stlibs.character.select('chocola-maid · Emote')
    assert stlibs.Config.size == 28
    emote_size = stlibs.Config.size

    stlibs.character.select('Mao')
    assert stlibs.Config.size == 110
    stlibs.Config.size = 90
    stlibs.ConfigLoader.save_config()

    stlibs.character.select('chocola-maid · Emote')
    assert stlibs.Config.size == emote_size
    assert json.loads((tmp_path / 'config' / 'emote.json').read_text(encoding='utf-8'))['size'] == 28
    assert json.loads((tmp_path / 'config' / 'live2d.json').read_text(encoding='utf-8'))['size'] == 90
