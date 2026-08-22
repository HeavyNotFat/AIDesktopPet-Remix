import iostream as std


def include(module_name):
    def decorator(func):
        if module_name == "iostream":
            std.cout = std.cout()
            std.cin = std.cin(std)

        return func

    return decorator


class namespace:
    @property
    def std(self):
        return


# 在这里编写代码
@include("iostream")
def using(): namespace.std


def main():
    std.cout << "输入一个名字："
    std.cin >> "name"
    std.cout << f"你好{name}"





















# 命名空间
namespace = namespace()
using()
try:
    main()
except NameError:
    pass
