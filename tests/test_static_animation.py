import os

import pytest
from PIL import Image

from stlibs import static_animation as sa


def _make_images(folder, names):
    folder = str(folder)
    os.makedirs(folder, exist_ok=True)
    paths = []
    for index, name in enumerate(names):
        path = os.path.join(folder, name)
        Image.new('RGBA', (8, 8), (index, 0, 0, 255)).save(path)
        paths.append(path)
    return paths


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(sa, 'ROOT', str(tmp_path / 'static'))
    monkeypatch.setattr(sa, 'CONFIG_PATH', str(tmp_path / 'static.json'))
    return tmp_path


def test_import_images_sorts_by_filename(library):
    paths = _make_images(library / 'src', ['walk10.png', 'walk2.png', 'walk1.png'])

    animation = sa.import_images('demo', 'walk', paths, fps=15)

    assert [os.path.basename(item) for item in animation.frames] == ['walk1.png', 'walk2.png', 'walk10.png']
    assert animation.fps == 15
    assert animation.loop is True
    saved = sa.find_animation('demo', 'walk')
    assert saved is not None and len(saved.frames) == 3


def test_import_rejects_duplicate_without_overwrite(library):
    paths = _make_images(library / 'src', ['a.png'])
    sa.import_images('demo', 'idle', paths)

    with pytest.raises(FileExistsError):
        sa.import_images('demo', 'idle', paths)

    animation = sa.import_images('demo', 'idle', paths, overwrite=True)
    assert len(animation.frames) == 1


def test_remove_and_rename(library):
    paths = _make_images(library / 'src', ['a.png', 'b.png'])
    sa.import_images('demo', 'walk', paths)

    renamed = sa.rename_animation('demo', 'walk', 'run')
    assert renamed.name == 'run'
    assert os.path.isdir(os.path.join(sa.ROOT, 'demo', 'run'))
    assert sa.find_animation('demo', 'walk') is None

    assert sa.remove_animation('demo', 'run') is True
    assert sa.list_animations('demo') == []
    assert sa.remove_animation('demo', 'run') is False


def test_invalid_names_are_rejected(library):
    paths = _make_images(library / 'src', ['a.png'])

    with pytest.raises(ValueError):
        sa.import_images('../escape', 'idle', paths)
    with pytest.raises(ValueError):
        sa.import_images('demo', '../escape', paths)


def test_animation_record_keeps_model_and_loop(library):
    paths = _make_images(library / 'src', ['a.png', 'b.png'])
    animation = sa.import_images('demo', 'walk', paths, loop=False)

    public = animation.public()
    assert public['model'] == 'demo'
    assert public['loop'] is False
    assert public['frames'] == list(animation.frames)
