from typing import Literal, List

import reproduction


class Mankind:
    def __init__(self, gender: Literal['male', 'female'], age: int, name: str):
        # Properties
        self.gender = gender
        self.age = age
        self.name = name

        # Attributes
        self.height: float
        self.height_crease_rate: List[float]
        self.weight: float
        self.weight_crease_rate: List[float]

    @staticmethod
    def sex(other_animal) -> bool:
        """
        Boolean returned is whether the reproduction was successful or not.
        """
        return reproduction.Human.sex(other_animal)

    def __repr__(self):
        return f'{self.name} is a {self.gender} {self.age} years old.'


class Female(Mankind):
    def __init__(self, age: int, name: str):
        super().__init__('female', age, name)


class Male(Mankind):
    def __init__(self, age: int, name: str):
        super().__init__('male', age, name)
