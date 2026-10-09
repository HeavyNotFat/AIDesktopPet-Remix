class PluginError(RuntimeError):
    """插件自身出错（加载失败、hook 抛异常、超时、参数不合法）。"""
