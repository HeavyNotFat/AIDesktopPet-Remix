import relation


class GirlFriend(relation.Female):
    def __init__(self, age: int, name: str):
        super().__init__(age, name)



class BoyFriend(relation.Male):
    def __init__(self, age: int, name: str):
        super().__init__(age, name)



Lily = GirlFriend(18, 'Lily')
Macos = BoyFriend(19, 'Macos')

while True:
    is_pregnant = Macos.sex(Lily)
    if is_pregnant:
        break
