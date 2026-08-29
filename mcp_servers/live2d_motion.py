from typing import Annotated
from difflib import get_close_matches
from sdk import client

from mcp.server.mcpserver import MCPServer
from pydantic import Field

mcp = MCPServer(name="live2d_mot_exp")


@mcp.tool()
def get_live2d_motion() -> list:
    """获取Live2D的所有动画"""
    return client.get_live2d_motion()


@mcp.tool()
def get_live2d_expression() -> list:
    """获取Live2D的所有表情"""
    return client.get_live2d_expression()


@mcp.tool()
def play_live2d_motion(
    motion: Annotated[str, Field(
        description="完整行动画名字，比如「动画;motions/默认.motion3.json」。"
    )]) -> None:
    """播放Live2D的动画。注意：你需要预先执行「get_live2d_motion」获取所有的动画列表。"""
    _cat_idx = {}
    motions = client.get_live2d_motion()
    for _item in motions:
        _cat = _item.split(';')[0]
        _cat_idx[_item] = _cat_idx.get(_cat, 0)
        _cat_idx[_cat] = _cat_idx[_item] + 1

    # 模糊匹配
    matches = get_close_matches(motion, motions)
    if matches:
        motion = matches[0]

    index = _cat_idx.get(motion, 0)
    client.play_live2d_motion(motion.split(";")[0], index)


@mcp.tool()
def play_live2d_expression(
        expression: Annotated[str, Field(description="表情的确切名称，需通过 get_live2d_expression 获取"
    )]) -> None:
    """播放Live2D的表情。"""
    client.play_live2d_expression(expression)


if __name__ == "__main__":
    client = client.SDKClient("127.0.0.1", 9000)
    client.start()

    mcp.run(transport="stdio")
