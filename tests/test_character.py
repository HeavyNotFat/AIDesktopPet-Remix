import stlibs
from stlibs import character


def test_natural_key_orders_numbers():
    names = ['frame10.png', 'frame2.png', 'frame1.png']
    assert sorted(names, key=character.natural_key) == ['frame1.png', 'frame2.png', 'frame10.png']


def test_discover_finds_three_kinds():
    kinds = {item.kind for item in character.discover()}

    assert character.LIVE2D in kinds
    assert character.STATIC in kinds


def test_emote_sample_is_discovered():
    names = {item.name for item in character.discover() if item.kind == character.EMOTE}

    assert 'chocola-maid' in names


def test_select_updates_config_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(stlibs, 'CONFIG_PATH', str(tmp_path / 'configure.json'))
    monkeypatch.setattr(stlibs.Config, 'model_live2d', 'Mao', raising=False)
    monkeypatch.setattr(stlibs.Config, 'static_model', '', raising=False)
    monkeypatch.setattr(stlibs.Config, 'model_emote', '', raising=False)
    monkeypatch.setattr(stlibs.Config, 'size', 110, raising=False)
    monkeypatch.setattr(stlibs.Config, 'opacity', 1, raising=False)
    monkeypatch.setattr(stlibs.Config, 'rotate', 0, raising=False)

    selected = character.select('chocola-maid · Emote')

    assert selected is not None and selected.kind == character.EMOTE
    assert stlibs.Config.model_emote == 'chocola-maid'
    assert stlibs.Config.model_live2d == ''
    assert stlibs.Config.static_model == ''
    assert character.kind() == character.EMOTE


def test_select_static_clears_other_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(stlibs, 'CONFIG_PATH', str(tmp_path / 'configure.json'))
    monkeypatch.setattr(stlibs.Config, 'model_live2d', '', raising=False)
    monkeypatch.setattr(stlibs.Config, 'static_model', 'fox', raising=False)
    monkeypatch.setattr(stlibs.Config, 'model_emote', 'chocola-maid', raising=False)
    monkeypatch.setattr(stlibs.Config, 'size', 110, raising=False)
    monkeypatch.setattr(stlibs.Config, 'opacity', 1, raising=False)
    monkeypatch.setattr(stlibs.Config, 'rotate', 0, raising=False)

    selected = character.select('fox')

    assert selected is not None and selected.kind == character.STATIC
    assert stlibs.Config.static_model == 'fox'
    assert stlibs.Config.model_emote == ''
    assert stlibs.Config.model_live2d == ''


def test_animation_path_follows_kind():
    assert character.animation_path(character.EMOTE) == stlibs.ANIMATION_EMOTE_PATH
    assert character.animation_path(character.STATIC) == stlibs.ANIMATION_STATIC_PATH
    assert character.animation_path(character.LIVE2D) == stlibs.ANIMATION_LIVE2D_PATH


def test_resolve_unknown_returns_none():
    assert character.resolve('绝对不存在的形象') is None
