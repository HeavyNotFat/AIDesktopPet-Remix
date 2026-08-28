from typing import Protocol, Callable
from types import ModuleType
from dataclasses import dataclass, fields
import subprocess
import inspect
import importlib
import json
import shutil

CONFIG_PATH = "./resources/configure.json"
ANIMATION_LIVE2D_PATH = "./resources/animation/live2d.json"
ANIMATION_STATIC_PATH = "./resources/animation/static.json"
EMBEDDING = ['bge-m3']


@dataclass(slots=True)
class Physics:
    """
    桌宠物理模拟器

    负责：
        位置
        速度
        加速度
        重力
        摩擦力
        边界碰撞
    """
    # 重力加速度
    GRAVITY: float = 1800.0
    # 空气阻力
    AIR_RESISTANCE: float = 0.995
    # 地面摩擦
    FRICTION: float = 0.82
    # 碰撞反弹系数
    BOUNCE: float = 0.65
    # 最小速度
    MIN_VELOCITY: float = 20.0

    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0

    enabled: bool = True
    dragging: bool = False

    def reset(self, x: float, y: float):
        """重置物理状态"""
        self.x = x
        self.y = y

        self.vx = 0.0
        self.vy = 0.0

    def set_position(self, x: float, y: float):
        """直接设置位置"""
        self.x = float(x)
        self.y = float(y)

    def set_velocity(self, vx: float, vy: float):
        """设置速度"""
        self.vx = float(vx)
        self.vy = float(vy)

    def add_velocity(self, vx: float, vy: float):
        """增加速度"""
        self.vx += vx
        self.vy += vy

    def update(
        self,
        dt: float,
        bounds,
        width: int,
        height: int,
    ):
        if not self.enabled or self.dragging:
            return

        self.vy += self.GRAVITY * dt

        self.vx *= self.AIR_RESISTANCE
        self.vy *= self.AIR_RESISTANCE

        self.x += self.vx * dt
        self.y += self.vy * dt

        left = bounds.left()
        right = bounds.right() - width

        bottom = bounds.bottom() - height

        # 左墙
        if self.x < left:
            self.x = left

            if self.vx < 0:
                self.vx = -self.vx * self.BOUNCE
        # 右墙
        elif self.x > right:
            self.x = right

            if self.vx > 0:
                self.vx = -self.vx * self.BOUNCE
        # 地面
        elif self.y > bottom:
            self.y = bottom

            if self.vy > 0:
                self.vy = -self.vy * self.BOUNCE

            # 地面摩擦
            self.vx *= self.FRICTION

        if abs(self.vx) < self.MIN_VELOCITY:
            self.vx = 0.0
        if abs(self.vy) < self.MIN_VELOCITY and self.y >= bottom:
            self.vy = 0.0

    def is_moving(self) -> bool:
        return (
            abs(self.vx) > self.MIN_VELOCITY
            or abs(self.vy) > self.MIN_VELOCITY
        )


@dataclass
class _BaseModelAnimation:
    smart_control: bool

    ClickEar: dict
    ClickHead: dict
    ClickChest: dict
    ClickBody: dict
    ClickLeg: dict
    TorchEar: dict
    TorchHead: dict
    TorchBody: dict
    TorchLeg: dict

    path: str

    def __setitem__(self, key, value):
        setattr(self, key, value)


class AnimationLoader:
    @staticmethod
    def load_config(path: str) -> _BaseModelAnimation:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            f.close()

        filtered = data['animation'] | {"smart_control": data['smart_control']}
        filtered.update({"path": path})
        animation_config = _BaseModelAnimation(**filtered)

        return animation_config

    @staticmethod
    def save_config(animation: _BaseModelAnimation | None = None) -> None:
        if animation is None: animation = Animation
        ani_dict = {field.name: getattr(animation, field.name) for field in fields(animation)}
        ani_dict = ani_dict.pop("path")
        with open(animation.path, "w", encoding="utf-8") as f:
            json.dump(ani_dict, f, ensure_ascii=False, indent=3)


# 配置文件
@dataclass
class _BaseModelConfig:
    models: dict
    memory: dict
    rag: dict
    mcp: dict
    name: str
    model_live2d: str
    static_model: str
    opacity: int
    size: int
    rotate: int

    def __setitem__(self, key, value):
        setattr(self, key, value)


class ConfigLoader:
    @staticmethod
    def load_config() -> _BaseModelConfig:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            f.close()

        valid_keys = {field.name for field in fields(_BaseModelConfig)}
        filtered = {k: v for k, v in data.items() if k in valid_keys}

        return _BaseModelConfig(**filtered)

    @staticmethod
    def save_config(config: _BaseModelConfig | None = None) -> None:
        if config is None: config = Config
        config = {field.name: getattr(config, field.name) for field in fields(config)}
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=3)


class _ThemeTypingProtocol(Protocol):
    """
    用于公开必须实现的方法
    """
    theme: ModuleType
    general: ModuleType
    llm: ModuleType
    tts: ModuleType
    settings: ModuleType
    animation: ModuleType

    Window: Callable
    Button: Callable
    Label: Callable
    Menu: Callable
    ScrollArea: Callable
    ChatWidget: Callable
    ChatBubble: Callable
    ModelChat: Callable


class SharingData:
    mainloop_ui = None
    chat_window = None
    setting_window = None
    theme: _ThemeTypingProtocol = None

    add_memory_to_ui: dict[Callable] = {}

    static_models: dict


class Signature:
    """
    参数冻结签名容错类
    用于驱动UI变量冻结的类
    """
    __slots__ = ("func", "kwargs")

    def __init__(self, func, **kwargs):
        self.func = func
        self.kwargs = kwargs

    def __call__(self, *args, **kwargs):
        return self.func(**self.kwargs)

    def run(self):
        return self.func(**self.kwargs)


def analyze_signature(func, **kwargs) -> Signature:
    function_args = {}
    signature = inspect.signature(func)
    for param_name, param in signature.parameters.items():
        if param_name in kwargs.keys():
            function_args[param_name] = kwargs[param_name]
        else:
            function_args[param_name] = param.default
    return Signature(func, **function_args)


def import_attributes(module: str, attribute: str):
    return getattr(importlib.import_module(module), attribute)


def get_model_lists() -> list:
    try:
        ollama_path = shutil.which("ollama")
        print(ollama_path)
        if ollama_path is None: ollama_path = "ollama"

        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10
        )
    except FileNotFoundError: return []

    if result.returncode != 0:
        return []

    lines = result.stdout.strip().splitlines()
    model_lines = [l for l in lines[1:] if l.split()]

    models = []
    for idx, line in enumerate(model_lines, 1):
        parts = line.split()
        if not parts:
            continue

        model_name = parts[0]
        if "emb" in model_name or model_name.split(':')[0] in EMBEDDING: continue
        models.append(model_name)
    return models


with open("./resources/static.json", "r", encoding="utf-8") as f:
    static_models = json.load(f)
    f.close()
SharingData.static_models = static_models
Config = ConfigLoader.load_config()
if Config.model_live2d.strip(): Animation = AnimationLoader.load_config(ANIMATION_LIVE2D_PATH)
else: Animation = AnimationLoader.load_config(ANIMATION_STATIC_PATH)
