"""生成两个插件图标（128×128 PNG，透明底）。

* 养成系统：绿描边饭碗 + 三缕热气 + 碗沿一颗小红心（呼应"喂食涨好感"）
* 桌宠扭蛋机：绿描边扭蛋胶囊（上下两色壳）+ 中间四角星 + 壳缝高光（呼应"抽卡出货"）

用法：python tools/manual/make_plugin_icons.py
"""

import math
import os
import sys

from PIL import Image, ImageDraw

OUT_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "plugins"))
SIZE = 128
SS = 4  # 超采样倍数：先画 4 倍再缩回来，边缘才不会有锯齿

GREEN = (0, 255, 0, 255)
GREEN_DIM = (0, 180, 0, 255)
DARK = (8, 20, 8, 235)
RED = (255, 70, 90, 255)
GOLD = (255, 205, 60, 255)
WHITE = (235, 255, 235, 255)


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
    """圆头折线：segments 之间不留斜接尖角。"""
    draw.line(points, fill=color, width=width, joint="curve")
    if not round_caps:
        return
    radius = width // 2
    for x, y in points:
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=color)


def heart_shape(draw, cx, cy, size, color):
    """用多边形画的心：两个圆瓣 + 一个尖底，比两圆一三角更饱满。"""
    half = size / 2
    points = []
    for index in range(121):
        t = math.pi * 2 * index / 120
        # 经典心形参数方程，y 取负号是因为屏幕坐标向下
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        points.append((cx + x * half / 17.0, cy + y * half / 17.0))
    draw.polygon(points, fill=color)


def bowl_icon(path):
    """饭碗：碗身 + 碗里的饭 + 三缕 S 形热气 + 右上角一颗小红心。"""
    image, draw = canvas()
    unit = SS  # 1 个"设计像素"

    # 三缕热气：S 形（圆头折线拼出来，不会有斜接尖角）
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

    # 碗里的饭：贴着碗沿的一条浅色弧，说明这碗是满的
    draw.pieslice(
        [scaler(rim_left + 3), scaler(rim_y - 9), scaler(rim_right - 3), scaler(rim_y + 9)],
        start=0,
        end=180,
        fill=(60, 200, 90, 210),
    )

    # 碗沿：一根粗横线 + 两端圆头，看着像瓷碗的边
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

    # 右上角的小红心：喂食涨好感（挪到角上，不跟碗沿打架）
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


def four_point_star(draw, cx, cy, outer, inner, color):
    """四角星（扭蛋出货的那颗星）。"""
    points = []
    for index in range(8):
        radius = outer if index % 2 == 0 else inner
        rad = math.radians(index * 45 - 90)
        points.append((cx + radius * math.cos(rad), cy + radius * math.sin(rad)))
    draw.polygon(points, fill=color)


def capsule_icon(path):
    """扭蛋胶囊：上下两色壳 + 中间一道缝 + 缝心一颗四角星 + 壳上高光。

    画法：整颗胶囊先铺成上壳色，再把"下半壳"按同一个外形一次性裁着画上去。
    早先是上下两个圆角矩形各画各的，圆角对不齐，胶囊两侧会露出黑角。
    """
    image, draw = canvas()
    unit = SS

    left, top, right, bottom = scaler(22), scaler(10), scaler(106), scaler(118)
    radius = scaler(41)
    seam = scaler(64)
    box = [left, top, right, bottom]

    # 整颗胶囊 = 上壳色
    draw.rounded_rectangle(box, radius=radius, fill=(16, 112, 28, 245))

    # 下半壳：裁剪到胶囊外形里再画，左右两侧就不会溢出成直角
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=255)

    lower = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(lower).rectangle([0, seam + 1, image.width, image.height], fill=(12, 26, 14, 240))
    lower.putalpha(Image.composite(lower.getchannel("A"), Image.new("L", image.size, 0), mask))
    image.alpha_composite(lower)
    draw = ImageDraw.Draw(image)

    # 缝：横贯一条，两端收在壳里
    draw.line([(left + 9 * unit, seam), (right - 9 * unit, seam)], fill=GREEN, width=3 * unit)
    # 轮廓最后描一遍，保证外形干净
    draw.rounded_rectangle(box, radius=radius, outline=GREEN, width=4 * unit)

    # 上半壳的斜向高光（塑料壳反光），位置避开缝和星
    draw.line(
        [(scaler(38), scaler(50)), (scaler(58), scaler(28))],
        fill=(225, 255, 225, 150),
        width=3 * unit,
    )
    draw.line(
        [(scaler(44), scaler(53)), (scaler(62), scaler(33))],
        fill=(225, 255, 225, 90),
        width=2 * unit,
    )

    # 正中间那颗四角星：出货的象征，压在缝上
    four_point_star(draw, scaler(64), scaler(64), scaler(24), scaler(8), GOLD)
    four_point_star(draw, scaler(64), scaler(64), scaler(14), scaler(4.5), WHITE)

    finish(image, path)


def main():
    targets = [
        (os.path.join(OUT_ROOT, "cultivation_system", "icon.png"), bowl_icon),
        (os.path.join(OUT_ROOT, "lucky_pet", "icon.png"), capsule_icon),
    ]
    print("生成插件图标：")
    for path, builder in targets:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        builder(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
