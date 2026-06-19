from component.type import Component

class AlwaysEdible(Component):
    """This component binds always edible to the enchantment glint.
    
    Sets a subcomponent of `food` and enchantment_glint_override.
    """

    def build(self):
        # setup base vanilla components        
        return {
            "food": {
                "can_always_eat": True
            },
            "enchantment_glint_override": True
        }
