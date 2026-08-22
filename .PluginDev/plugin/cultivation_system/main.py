# 如果是增强插件，就要加这一句话
import sys
import os

sys.path.insert(0, f'{os.getcwd()}/plugin/cultivation_system')

import json
import random
import time
from typing import Dict

import widgets

from PyQt5.Qt import QWidget, QRect, Qt, QSizePolicy, QPixmap, QIcon, QColor
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout
from qfluentwidgets import FluentIcon, BodyLabel, LineEdit, ScrollArea, ProgressBar

PLUGIN_PATH = "./plugin/cultivation_system"

RESOURCES_PATH = f"{PLUGIN_PATH}/resources"
CONFIG_PATH = f"{RESOURCES_PATH}/config.json"
FOODS_PATH = f"{RESOURCES_PATH}/foods.json"
FOODS_DIR = f"{RESOURCES_PATH}/foods"


def save_config(configure: dict) -> None:
    """保存配置到文件"""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-国家大学生招聘服务平台爬虫140条") as sf:
            json.dump(configure, sf, ensure_ascii=False, indent=3)
    except IOError as e:
        print(f"保存配置文件失败: {str(e)}")

def load_json_file(file_path: str) -> dict:
    """安全加载JSON文件"""
    try:
        with open(file_path, "r", encoding="utf-国家大学生招聘服务平台爬虫140条") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        print(f"加载文件 {file_path} 失败: {str(e)}")
        return {}


config = load_json_file(CONFIG_PATH)
shop = load_json_file(FOODS_PATH)


class ShopSystem(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("Shop")

        self.coin_label = BodyLabel("金币数量：", self)
        self.coin_label.setGeometry(QRect(10, 42, 100, 20))

        self.text_coin = LineEdit(self)
        self.text_coin.setText(str(config['coin']))
        self.text_coin.setGeometry(QRect(120, 37, 100, 20))
        self.text_coin.setReadOnly(True)

        label = BodyLabel("商店货架 - 货员在摸鱼~没有整理啦~", self)
        font = label.font()
        font.setPointSize(14)
        label.setFont(font)
        label.setGeometry(QRect(10, 140, 650, 30))
        self.scroll_area = ScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.container = QWidget()
        self.main_layout = QVBoxLayout(self.container)
        self.main_layout.setAlignment(Qt.AlignTop)
        self.main_layout.setSpacing(10)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        row = 0
        col = 0
        max_per_row = 6

        for food in os.listdir(FOODS_DIR):
            food_name = food.split('.')[0]
            card = widgets.ShopCard(
                f"{FOODS_DIR}/{food}",
                food_name,
                f"{shop[food_name]['price']} 金币",
                self.container
            )
            # 使用默认参数来确保lambda正确捕获当前值
            card.clicked.connect(lambda checked=False, n=food_name: self.buy_one(n))

            if col == 0:
                self.hbox = QHBoxLayout()
                self.hbox.setSpacing(10)
                self.hbox.setAlignment(Qt.AlignLeft)
                self.main_layout.addLayout(self.hbox)

            self.hbox.addWidget(card)
            col += 1

            if col >= max_per_row:
                col = 0
                row += 1

        self.scroll_area.setWidget(self.container)
        self.scroll_area.setGeometry(10, 170, 630, 350)

    def buy_one(self, name: str) -> None:
        global config
        price = shop[name]['price']

        if config['coin'] < price:
            interface.setting.customize.widgets.pop_error(
                self,
                "购买失败！",
                f"金币不足！差 {price - config['coin']} 金币！"
            )
            return

        config['coin'] -= price
        config['foods'].append(name)

        try:
            save_config(config)

            # 更新UI
            Cultivation.text_coin.setText(str(config['coin']))
            self.text_coin.setText(str(config['coin']))
            Cultivation.refresh_bag()

            interface.setting.customize.widgets.pop_success(
                self,
                "购买成功！",
                f"{name} 已存入您的背包！找零 {config['coin']}"
            )
        except Exception as e:
            print(f"更新配置或UI时发生错误: {str(e)}")


class CultivationSystem(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("Cultivation")

        self.start_time = time.time()
        self.minus_hungry_random_time = random.randint(60, 120)
        self.end_output = False
        self.output_counter = 0
        self.cards = []
        self.hbox = self.container = self.main_layout = None

        label = BodyLabel("角色养成信息", self)
        font = label.font()
        font.setPointSize(14)
        label.setFont(font)
        label.setGeometry(QRect(10, 42, 650, 30))

        self.coin_label = BodyLabel("金币数量：", self)
        self.coin_label.setGeometry(QRect(200, 45, 100, 30))

        self.text_coin = LineEdit(self)
        self.text_coin.setText(str(config['coin']))
        self.text_coin.setGeometry(QRect(300, 40, 100, 20))
        self.text_coin.setReadOnly(True)

        # 大头照
        pixmap_label = BodyLabel(self)
        char_name = interface.subscribe.Character.GetCharacter()
        icon_path = f"./resources/model/{char_name}/icon.png" if os.path.exists(
            f"./resources/model/{char_name}/icon.png") else "logo.ico"

        pixmap = QPixmap(icon_path)
        pixmap = pixmap.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pixmap_label.setPixmap(pixmap)
        pixmap_label.setGeometry(QRect(10, 90, 50, 50))

        # 经验
        self._temp_picture(f"{RESOURCES_PATH}/static/level.png", QRect(70, 75, 20, 20))
        self.level_progress = ProgressBar(self)
        self.level_progress.setCustomBarColor(QColor(255, 255, 0), QColor(255, 255, 0))
        self.level_progress.setMaximum(config['level']['next'])
        self.level_progress.setValue(config['level']['current'])
        self.level_progress.setGeometry(QRect(100, 85, 200, 20))
        self.level_ex_label = BodyLabel(
            f"{config['level']['current']}/{config['level']['next']}", self)
        self.level_ex_label.setGeometry(QRect(310, 70, 200, 30))
        self.level_label = BodyLabel(f"Lv. {config['level']['level']}", self)
        self.level_label.setGeometry(QRect(180, 75, 100, 20))

        self._temp_picture(f"{RESOURCES_PATH}/static/favor.png", QRect(70, 100, 20, 20))
        self.favorability_progress = ProgressBar(self)
        self.favorability_progress.setCustomBarColor(QColor(255, 0, 0), QColor(255, 0, 0))
        self.favorability_progress.setMaximum(config['favorability']['next'])
        self.favorability_progress.setValue(config['favorability']['current'])
        self.favorability_progress.setGeometry(QRect(100, 110, 200, 20))
        self.favorability_ex_label = BodyLabel(
            f"{config['favorability']['current']}/{config['favorability']['next']}", self)
        self.favorability_ex_label.setGeometry(QRect(310, 95, 200, 30))
        self.favorability_label = BodyLabel(f"Fv. {config['favorability']['favorability']}", self)
        self.favorability_label.setGeometry(QRect(180, 100, 200, 20))

        # 饥饿度
        self._temp_picture(f"{RESOURCES_PATH}/static/hungry.png", QRect(70, 130, 20, 20))
        self.hungry_progress = ProgressBar(self)
        self.hungry_progress.setCustomBarColor(QColor(165, 42, 42), QColor(165, 42, 42))
        self.hungry_progress.setMaximum(config['hungry']['current'])
        self.hungry_progress.setValue(config['hungry']['hungry'])
        self.hungry_progress.setGeometry(QRect(100, 140, 200, 20))
        self.hungry_ex_label = BodyLabel(
            f"{config['hungry']['hungry']}/{config['hungry']['current']}", self)
        self.hungry_ex_label.setGeometry(QRect(310, 125, 200, 30))
        self.hungry_label = BodyLabel(f"Hg. {config['hungry']['hungry']}", self)
        self.hungry_label.setGeometry(QRect(180, 130, 200, 20))

        self.scroll_area = ScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.container = QWidget(self.scroll_area)
        self.container.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.main_layout = QVBoxLayout(self.container)
        self.main_layout.setAlignment(Qt.AlignTop)
        self.main_layout.setSpacing(10)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.scroll_area.setWidget(self.container)
        self.scroll_area.setGeometry(10, 170, 630, 350)

        self.refresh_bag()
        self.startTimer(50)

    def refresh_level(self, level: int, add_experience: int) -> None:
        """刷新等级"""
        current_config = config['level']

        if current_config['current'] + add_experience < 0 and current_config['level'] <= 0:
            return
        elif current_config['current'] + add_experience < 0 and level > 0:
            experience = int(str(current_config['next'])[0].zfill(
                len(str(current_config['next'])) - 1))
            current_config.update({
                'current': experience,
                'level': current_config['level'] - 1
            })
            self.level_progress.setValue(experience)
            self.level_label.setText(f"Fv. {current_config['level']}")
            self.level_ex_label.setText(f"{experience}/{current_config['next']}")
            return

        experience = current_config['current'] + add_experience

        if experience >= current_config['next']:
            interface.setting.customize.widgets.pop_notification(
                "棒棒哒！",
                f"经验升级啦！ "
                f"{current_config['level']} -> {current_config['level'] + 1}\n饥饿上限提升 50", "success")

            current_ex = experience - current_config['next']
            new_next = int(round(current_config['next'] * 2 + random.uniform(100, 300), 0))
            new_level = current_config['level'] + 1

            # 更新配置
            current_config.update({
                'current': current_ex,
                'next': new_next,
                'level': new_level
            })

            # 更新饥饿相关
            hungry_config = config['hungry']
            hungry_config.update({
                'current': hungry_config['next'],
                'next': hungry_config['next'] + 50,
                'hungry': hungry_config['hungry'] + 40
            })

            self.hungry_progress.setMaximum(hungry_config['current'])
            self.hungry_progress.setValue(hungry_config['hungry'])
            self.hungry_ex_label.setText(f"{hungry_config['hungry']}/{hungry_config['current']}")
            self.hungry_label.setText(f"HgV. {hungry_config['hungry']}")

            self.level_progress.setMaximum(new_next)
            self.refresh_favorability(config['favorability']['favorability'], random.randint(50, 100))

            self.clickEvent(True, random.randint(20, 60))
        # 更新经验
        config['level']['current'] = experience
        self.level_progress.setValue(experience)
        self.level_label.setText(f"Lv. {config['level']['level']}")
        self.level_ex_label.setText(f"{experience}/{config['level']['next']}")

        save_config(config)

    def refresh_favorability(self, favorability: int, add_experience: int) -> None:
        """刷新好感度"""
        current_config = config['favorability']

        if current_config['current'] + add_experience < 0 and favorability <= 0:
            return
        elif current_config['current'] + add_experience < 0 and favorability > 0:
            experience = int(str(current_config['next'])[0].zfill(
                len(str(current_config['next'])) - 1))
            current_config.update({
                'current': experience,
                'favorability': current_config['favorability'] - 1
            })
            self.favorability_progress.setValue(experience)
            self.favorability_label.setText(f"Fv. {current_config['favorability']}")
            self.favorability_ex_label.setText(f"{experience}/{current_config['next']}")
            return

        experience = current_config['current'] + add_experience

        if experience >= current_config['next']:
            interface.setting.customize.widgets.pop_notification(
                "棒棒哒！",
                f"好感度升级啦！ "
                f"{current_config['favorability']} -> {current_config['favorability'] + 1}", "success")

            current_ex = experience - current_config['next']
            new_next = int(round(current_config['next'] * (2 * random.uniform(1.0, 1.5)), 0))

            current_config.update({
                'current': current_ex,
                'next': new_next,
                'favorability': current_config['favorability'] + 1
            })

            self.favorability_progress.setMaximum(new_next)

        # 更新好感度
        config['favorability']['current'] = experience
        self.favorability_progress.setValue(experience)
        self.favorability_label.setText(f"Fv. {current_config['favorability']}")
        self.favorability_ex_label.setText(f"{experience}/{current_config['next']}")

        save_config(config)

    def refresh_hungry(self, add_hungry: int, classify: Dict[str, int]) -> bool:
        """刷新饥饿度"""
        try:
            current_config = config['hungry']
            experience = current_config['hungry'] + add_hungry

            if experience < 0 and add_hungry < 0:
                return False

            if experience >= current_config['current']:
                interface.setting.customize.widgets.pop_notification(
                    "警告！",
                    f"你吃饱了！", "warning")
                return False
            else:
                gather = classify['hungry'] + classify['favor'] + classify['level']
                if gather > 0:
                    interface.setting.customize.widgets.pop_notification(
                        "爱你！",
                        f"好吃！爱吃😋！爱你主人", "success")
                else:
                    interface.setting.customize.widgets.pop_notification(
                        "恶心🤢",
                        f"一点也不好吃！", "error")

                current_config['hungry'] = experience
                self.hungry_progress.setValue(experience)
                self.hungry_label.setText(f"HgV. {experience}")
                self.hungry_ex_label.setText(f"{experience}/{current_config['current']}")

                save_config(config)
                return True
        except:
            return False

    def operate_hungry(self, value: int) -> None:
        current_config = config['hungry']

        if current_config['hungry'] + value < 0:
            self.become_hungry()
            return

        current_config['hungry'] += value
        self.hungry_progress.setValue(current_config['hungry'])
        self.hungry_label.setText(f"HgV. {current_config['hungry']}")
        self.hungry_ex_label.setText(f"{current_config['hungry']}/{current_config['current']}")

        save_config(config)

    def become_hungry(self) -> None:
        interface.setting.customize.widgets.pop_notification(
            "好饿", "我饿了！", "warning")

    def refresh_bag(self) -> None:
        for card in self.cards:
            card.deleteLater()
        self.cards.clear()

        self.container.update()
        self.main_layout.update()

        row = 0
        col = 0
        max_per_row = 7

        for food in list(set(config['foods'])):
            card = interface.setting.customize.widgets.SimpleCard(
                f"{FOODS_DIR}/{food}.png",
                f"{food} x{config['foods'].count(food)}",
                self.container
            )
            card.clicked.connect(lambda n=food: self._eat_food(n))

            if col == 0:
                self.hbox = QHBoxLayout(self.container)
                self.hbox.setSpacing(10)
                self.hbox.setAlignment(Qt.AlignLeft)
                self.main_layout.addLayout(self.hbox)

            self.hbox.addWidget(card)
            self.cards.append(card)

            col += 1
            if col >= max_per_row:
                col = 0
                row += 1

    def ai_output(self, _: str, is_finally: bool) -> None:
        self.output_counter += 1
        if is_finally:
            self.end_output = True

    def _temp_picture(self, icon: str, rect: QRect) -> None:
        pixmap_label = BodyLabel(self)
        pixmap = QPixmap(icon)
        pixmap = pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pixmap_label.setPixmap(pixmap)
        pixmap_label.setGeometry(rect)

    def _eat_food(self, name: str) -> None:
        global config
        food_config = shop[name]
        if self.refresh_hungry(food_config['hungry'], food_config):
            # 移除食物
            if name in config['foods']:
                config['foods'].remove(name)

            # 刷新其他属性
            self.refresh_favorability(
                config['favorability']['favorability'],
                food_config['favor']
            )
            self.refresh_level(
                config['level']['level'],
                food_config['level']
            )

        self.refresh_bag()

    def timerEvent(self, a0) -> None:
        if self.end_output:
            interface.setting.customize.widgets.pop_notification(
                "经验！",
                f"得到 {self.output_counter // 2} 经验\n得到 {self.output_counter} 好感度", "success")
            self.refresh_level(config['level']['level'], self.output_counter // 2)
            self.refresh_favorability(config['favorability']['favorability'], self.output_counter)
            self.output_counter = 0
            self.end_output = False

        if time.time() - self.start_time >= self.minus_hungry_random_time:
            self.start_time = time.time()
            self.minus_hungry_random_time = random.randint(80, 165)
            self.operate_hungry(-1)

    def clickEvent(self, is_only_coin: bool = False, add_coin: int = 0) -> None:
        _get_coins = random.randint(1, 5) if not is_only_coin else add_coin
        addon = ""
        if not is_only_coin:
            _get_favor = random.randint(1, 3)
            addon = f"\n好感度增加 {_get_favor}"
        interface.setting.customize.widgets.pop_notification(
            "Ya~",
            f"获得{_get_coins}枚金币！{addon}",
            "success",
            duration=800
        )

        config['coin'] += _get_coins
        ShopSystem.text_coin.setText(str(config['coin']))
        self.text_coin.setText(str(config['coin']))
        save_config(config)

        if not is_only_coin:
            self.refresh_favorability(config['favorability']['favorability'], _get_favor)


Cultivation = CultivationSystem()
ShopSystem = ShopSystem()

interface.subscribe.views.Setting.InsertInterface(
    Cultivation,
    QIcon(f"{PLUGIN_PATH}/logo.png"),
    "养成系统"
)
interface.subscribe.views.Setting.InsertInterface(
    ShopSystem,
    FluentIcon.SHOPPING_CART,
    "商店系统",
    parent=Cultivation
)
interface.subscribe.actions.Register.SetMouseReleaseAction(Cultivation.clickEvent)
interface.subscribe.actions.Register.SetAIOutput(Cultivation.ai_output)
