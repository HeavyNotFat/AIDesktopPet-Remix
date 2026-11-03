from stlibs.animation_utils import action_at, action_rect, motion_parts


class _Animation:
    ClickHead = {'x': 10, 'y': 20, 'dx': 100, 'dy': 120, 'anim': '', 'expr': ''}
    TorchHead = {'x': 0, 'y': 0, 'dx': 0, 'dy': 0, 'anim': '', 'expr': ''}


def test_action_rect_normalizes_points():
    assert action_rect({'x': 100, 'y': 120, 'dx': 10, 'dy': 20}) == (10, 20, 100, 120)
    assert action_rect({'x': 10, 'y': 20, 'dx': 10, 'dy': 20}) is None
    assert action_rect(None) is None


def test_action_at_matches_prefix():
    label, action = action_at(_Animation(), 50, 60, 'Click')

    assert label == '拍拍头'
    assert action is _Animation.ClickHead
    assert action_at(_Animation(), 50, 60, 'Torch') == ('', None)


def test_motion_parts_returns_group_and_index(monkeypatch):
    import stlibs

    monkeypatch.setattr(stlibs.SharingData, 'motions', ['idle;a', 'idle;b', 'tap;c'], raising=False)

    assert motion_parts('idle;b') == ('idle', 1)
    assert motion_parts('tap;c') == ('tap', 0)
    assert motion_parts('') == ('', 0)
