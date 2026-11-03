import json

from stlibs import AnimationLoader


def _template(path):
    data = {
        'smart_control': True,
        'ai_control': False,
        'animation': {
            name: {'x': 0, 'y': 0, 'dx': 0, 'dy': 0, 'anim': '', 'expr': ''}
            for name in ('ClickEar', 'ClickHead', 'ClickChest', 'ClickBody', 'ClickLeg',
                         'TorchEar', 'TorchHead', 'TorchBody', 'TorchLeg')
        },
        'special': {'AppInitial': '', 'AppExit': ''},
    }
    data['animation']['ClickHead'] = {'x': 10, 'y': 10, 'dx': 20, 'dy': 20, 'anim': '', 'expr': ''}
    path.write_text(json.dumps(data), encoding='utf-8')
    return path


def test_animation_round_trip_and_binding(tmp_path):
    path = _template(tmp_path / 'animation.json')
    animation = AnimationLoader.load_animation(str(path))

    animation.ClickEar = {'x': 1, 'y': 2, 'dx': 30, 'dy': 40, 'anim': 'idle;wave', 'expr': 'smile'}
    animation.AppInitial = 'idle;start'
    AnimationLoader.save_animation(animation)

    loaded = AnimationLoader.load_animation(str(path))
    assert loaded.ClickEar['anim'] == 'idle;wave'
    assert loaded.ClickEar['expr'] == 'smile'
    assert loaded.ClickEar['dx'] == 30
    assert loaded.AppInitial == 'idle;start'
    assert loaded.ClickHead['x'] == 10


def test_animation_path_is_recorded(tmp_path):
    path = _template(tmp_path / 'animation.json')
    animation = AnimationLoader.load_animation(str(path))

    assert animation.path == str(path)
