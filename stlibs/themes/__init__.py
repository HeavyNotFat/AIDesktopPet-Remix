import os
import importlib

from . import hacker

current_dir = os.path.dirname(__file__)
__all__ = ["hacker"]

for item in os.listdir(current_dir):
    item_path = os.path.join(current_dir, item)
    if os.path.isdir(item_path) and os.path.isfile(os.path.join(item_path, '__init__.py')):
        mod = importlib.import_module(f'.{item}', __name__)
        globals()[item] = mod
        __all__.append(item)
