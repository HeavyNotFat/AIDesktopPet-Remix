MAPPING_ANIMATION = {
    "捏耳朵": "ClickEar",
    "拍拍头": "ClickHead",
    "拍胸脯": "ClickChest",
    "按肚子": "ClickBody",
    "捏捏腿": "ClickLeg",
    "摸耳朵": "TorchEar",
    "摸摸头": "TorchHead",
    "摸肚子": "TorchBody",
    "摸摸腿": "TorchLeg",
}

MAPPING_SPECIAL_ANIMATION = {
    "程序启动": "AppInitial",
    "程序退出": "AppExit",
}

MAPPING_SPECTIAL_ANIMATION = MAPPING_SPECIAL_ANIMATION

CLICK_ACTIONS = tuple(name for name in MAPPING_ANIMATION if name.startswith("Click"))
HOVER_ACTIONS = tuple(name for name in MAPPING_ANIMATION if name.startswith("Torch"))

__all__ = [
    "CLICK_ACTIONS",
    "HOVER_ACTIONS",
    "MAPPING_ANIMATION",
    "MAPPING_SPECIAL_ANIMATION",
    "MAPPING_SPECTIAL_ANIMATION",
]
