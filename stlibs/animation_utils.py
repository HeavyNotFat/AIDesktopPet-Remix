import random

from .action_map import MAPPING_ANIMATION


def action_rect(action):
    if not isinstance(action, dict):
        return None
    try:
        x, y = int(action.get('x', 0)), int(action.get('y', 0))
        dx, dy = int(action.get('dx', 0)), int(action.get('dy', 0))
    except (TypeError, ValueError):
        return None
    left, right = min(x, dx), max(x, dx)
    top, bottom = min(y, dy), max(y, dy)
    if right - left < 2 or bottom - top < 2:
        return None
    return left, top, right, bottom


def action_at(animation, x, y, prefix='Click'):
    for label, attr in MAPPING_ANIMATION.items():
        if not attr.startswith(prefix):
            continue
        action = getattr(animation, attr, None)
        rect = action_rect(action)
        if rect is None:
            continue
        left, top, right, bottom = rect
        if left <= x <= right and top <= y <= bottom:
            return label, action
    return '', None


def motion_parts(value):
    text = str(value or '').strip()
    group, _sep, name = text.partition(';')
    group = group.strip()
    name = name.strip()
    try:
        from . import SharingData

        items = [str(item) for item in (getattr(SharingData, 'motions', None) or [])]
    except Exception:
        items = []
    index = 0
    for item in items:
        item_group, _sep, item_name = item.partition(';')
        if item_group.strip() != group:
            continue
        if item_name.strip() == name:
            break
        index += 1
    return group, max(0, index)


def random_motion(motions):
    items = [str(item) for item in (motions or []) if str(item).strip()]
    return random.choice(items) if items else ''


__all__ = ['action_at', 'action_rect', 'motion_parts', 'random_motion']
