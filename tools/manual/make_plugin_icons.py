
import math
import os
import sys

from PIL import Image, ImageDraw

OUT_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "plugins"))
SIZE = 128
SS = 4  # 超采样倍数：先画 4 倍再缩回来，避免锯齿

GREEN = (0, 255, 0, 255)
GREEN_DIM = (0, 180, 0, 255)
DARK = (8, 20, 8, 235)
RED = (255, 70, 90, 255)


def canvas():
    image = Image.new("RGBA", (SIZE * SS, SIZE * SS), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image)


def finish(image, path):
    image = image.resize((SIZE, SIZE), Image.LANCZOS)
    image.save(path)
    print(f"  {os.path.relpath(path, OUT_ROOT)}  {image.width}x{image.height}  {os.path.getsize(path)} 字节")


def scaler(value):
    return value * SS


def polyline(draw, points, color, width, round_caps=True):
    """圆头折线。"""
    draw.line(points, fill=color, width=width, joint="curve")
    if not round_caps:
        return
    radius = width // 2
    for x, y in points:
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=color)


def heart_shape(draw, cx, cy, size, color):
    """用参数方程画的心形多边形。"""
    half = size / 2
    points = []
    for index in range(121):
        t = math.pi * 2 * index / 120
        # 心形参数方程，y 取负号是因为屏幕坐标向下
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        points.append((cx + x * half / 17.0, cy + y * half / 17.0))
    draw.polygon(points, fill=color)


def bowl_icon(path):
    """画饭碗图标：碗身、饭、热气、小红心。"""
    image, draw = canvas()
    unit = SS  # 1 个"设计像素"

    # 三缕热气：S 形
    for offset in (-20, 0, 20):
        x0 = scaler(64 + offset)
        step = scaler(6)
        points = [
            (x0, scaler(41)),
            (x0 - step, scaler(35)),
            (x0 - step, scaler(29)),
            (x0, scaler(23)),
            (x0 + step, scaler(17)),
            (x0 + step, scaler(11)),
            (x0, scaler(5)),
        ]
        polyline(draw, points, GREEN, 3 * unit)

    # 碗身：上宽下窄
    rim_y, base_y = 52, 100
    rim_left, rim_right = 22, 106
    base_left, base_right = 36, 92
    draw.polygon(
        [
            (scaler(rim_left), scaler(rim_y)),
            (scaler(rim_right), scaler(rim_y)),
            (scaler(base_right), scaler(base_y)),
            (scaler(base_left), scaler(base_y)),
        ],
        fill=DARK,
        outline=GREEN,
        width=4 * unit,
    )

    # 碗里的饭：贴着碗沿的一条浅色弧
    draw.pieslice(
        [scaler(rim_left + 3), scaler(rim_y - 9), scaler(rim_right - 3), scaler(rim_y + 9)],
        start=0,
        end=180,
        fill=(60, 200, 90, 210),
    )

    # 碗沿：粗横线 + 两端圆头
    polyline(
        draw,
        [(scaler(rim_left), scaler(rim_y)), (scaler(rim_right), scaler(rim_y))],
        GREEN,
        5 * unit,
        round_caps=False,
    )
    for x in (rim_left, rim_right):
        radius = 4 * unit
        draw.ellipse(
            [scaler(x) - radius, scaler(rim_y) - radius, scaler(x) + radius, scaler(rim_y) + radius],
            fill=GREEN,
        )

    # 碗底的托
    polyline(
        draw,
        [(scaler(48), scaler(base_y + 7)), (scaler(80), scaler(base_y + 7))],
        GREEN_DIM,
        5 * unit,
        round_caps=False,
    )

    # 右上角的小红心：喂食涨好感
    heart_x, heart_y, badge_r = 100, 28, 15
    draw.ellipse(
        [scaler(heart_x - badge_r), scaler(heart_y - badge_r),
         scaler(heart_x + badge_r), scaler(heart_y + badge_r)],
        fill=(24, 10, 14, 240),
        outline=RED,
        width=2 * unit,
    )
    heart_shape(draw, scaler(heart_x), scaler(heart_y + 1), scaler(19), RED)

    finish(image, path)


def main():
    targets = [
        (os.path.join(OUT_ROOT, "cultivation_system", "icon.png"), bowl_icon),
    ]
    print("生成插件图标：")
    for path, builder in targets:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        builder(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
