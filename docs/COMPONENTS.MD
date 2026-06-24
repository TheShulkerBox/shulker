# Components

This is the practical reference for the item component system. Item definitions
are class bodies, component names are class attributes, and the metaclass in
`src/item/type.py` resolves those attributes into validated Minecraft item
components.

## Item Definitions

Items usually inherit from `Item`, `KitItem`, or a more specific base item:

```bolt
class RageJuice(KitItem):
    item_model = "potion"
    item_name = "Rage Juice"
    potion_contents = {custom_color: "#750303"}
    useable = {
        delay: 1.6,
        callback: JUICE_DRINK,
        animation: "drink",
        sound: "minecraft:entity.generic.drink",
    }
    use_remainder = KitItem(id="glass_bottle").as_dict()
```

Every non-private, non-callable class attribute becomes candidate component data.
`id` is special: it is used as the base Minecraft item id, then removed from the
final component map.

Use vanilla components directly when they already say what you mean:

```bolt
item_name = "Maul"
enchantments = {knockback: 1}
enchantment_glint_override = true
```

Use custom components when one intent needs multiple vanilla components or
supporting datapack resources:

```bolt
melee = {
    damage: 8,
    speed: 0.6,
    weight: "heavy",
}
useable = {
    delay: 0.5,
    callback: LEAP_ACTIVATE,
    animation: "spyglass",
}
```

## Build Lifecycle

1. Discover item class attributes and deep-copy them into the original component
   map.
2. Merge item identity into `custom_data`: the concrete item name plus its item
   type inheritance path.
3. Build registered `Component` classes whose snake-case names exist in the map.
   Their original custom key is removed before vanilla validation.
4. Deep-merge each component's output into the resolved map. If a component
   outputs `RecursiveComponent(SomeComponent, data)`, that nested custom
   component is queued and built too.
5. Build registered per-component `Transformer` classes whose snake-case names
   exist in the map. A transformer returning `None` preserves the original value.
6. Extract `id` from the component map and assign it to the item.
7. Run `post_build()` for built components and per-component transformers.
8. Build all registered `GlobalTransformer` classes, then run their
   `post_build()` hooks.
9. Validate resolved components against the cached mcdoc schemas, except
   `custom_data`, which intentionally has no schema.
10. Cache the final components and the constructed custom component/transformer
    objects on the item class.

## Component Classes

Custom components live in `src/component`. They subclass `Component` and are
auto-registered on import. The component key is the class name in snake case:
`Useable` becomes `useable`, `LeftClick` becomes `left_click`.

```bolt
class AlwaysEdible(Component):
    def build(self):
        return {
            "food": {"can_always_eat": True},
            "enchantment_glint_override": True,
        }
```

Component fields are validated before `build()` runs. If a component declares
`base_type`, the item may pass the base value directly instead of a dict:

```bolt
class Resupply(Component):
    only_on_empty: bool = False
    callback: FunctionPath | None = None

    def build(self):
        return {"custom_data": {"component": {"resupply": {
            only_on_empty: self.only_on_empty,
            callback: self.callback,
        }}}}

resupply = {only_on_empty: true}
```

`build()` should return a dict of resolved components or `None`. Use
`ComponentBuildError` or `CustomComponentError` for deliberate user-facing build
errors.

`post_build(resolved_components, item_obj)` is for work that needs the full
resolved item. `Throwable` uses this to generate throw behavior after visual
components such as `item_model` and `enchantment_glint_override` are known.

## Transformers

Transformers live in `src/component/transformers` and subclass `Transformer`.
They are for nicer input formats on existing component names, not for new
behavior.

Current built-ins:

- `dyed_color`: accepts `"#191919"` and converts it to the integer color format.
- `potion_contents`: accepts `custom_color` as hex inside the vanilla
  `potion_contents` component.
- `lore`: accepts a string or list of strings and formats strings with the
  project secondary color and `italic: false`.

Example:

```bolt
class SneakyBoots(Armor):
    id = "leather_boots"
    dyed_color = "#191919"
    sneaking = {during: SNEAK_HANDLER, end: END_SNEAK}
```

If a transformer cannot or should not change the value, return `None`; the
original component value is restored.

## Common Components

`armor`
: Adds `attribute_modifiers` for armor, toughness, knockback resistance, and/or
  movement speed across armor slots.

`always_edible`
: Sets `food.can_always_eat` and forces glint. Used by simple food items like
  rations and witch stew.

`bow`
: Bow-only hooks for nock, charging, charged, unnock, fire, and hit. It creates
  advancements/functions and uses `ItemEnchant` for projectile and attack
  effects.

`droppable`
: Stores drop handling metadata in `custom_data.component.droppable`; currently
  supports disabled/team-item style behavior and optional callbacks.

`item_enchant`
: Internal composition component for custom item enchantment effects. Other
  components usually reach it with `RecursiveComponent(ItemEnchant, effects)`.

`kill`
: Runs exactly one callback for `killer` or `victim` when a player is killed.
  Defaults to matching the item in `hotbar.*`.

`left_click`
: Runs a function through `post_piercing_attack`. Optional `cooldown` also
  adjusts reach, minimum attack charge, and attack speed.

`melee`
: Defines weapon damage, speed, knockback, crit boost, and weight. Damage and
  speed override vanilla base attributes; weight is stored in `custom_data`.

`resupply`
: Customizes kit resupply behavior. `only_on_empty` skips replacing the item
  while the player already has it, and `callback` runs whenever the kit
  resupplies that item.

`sneaking`
: Runs start/during/end callbacks while a matching player is sneaking. Optional
  `slot` narrows where the item must be.

`strike`
: Like `kill`, but for hurting a player instead of killing one. Use exactly one
  of `attacker` or `victim`.

`throwable`
: Extends `Using` to turn an item into a thrown item. Supports charge time,
  minimum charge, motion customization, and item entity data.

`ticking`
: List-based component that runs functions periodically while the item matches,
  optionally restricted to a slot.

`two_handed`
: Enforces mainhand-only use and clears or swaps offhand conflicts.

`useable`
: General right-click/consume abstraction. It configures `consumable`,
  `use_cooldown`, optional infinite-use behavior, and a consume callback.

`using`
: Lower-level hold-right-click lifecycle with start/during/end callbacks. Used
  directly by some components and as the base for `Throwable`.

## Validation Notes

- Custom component keys must match registered component class names in snake
  case.
- Unknown final component names are reported with mcdoc suggestions.
- Custom component field errors are shown before vanilla schema errors.
- `Remove` is valid for negative components and serializes as `!component`.
- `custom_data` is free-form, but component identity is always merged into it.
- Components are cached per item unless declared as `class X(Component,
  cache=False)`.
- All component modules are imported through `component:all`, generated by
  `plugins/component_import.py`.

When in doubt, check the component source first. Many components also create
functions, advancements, enchantments, scoreboards, or runtime storage state;
the item attribute is only the front door.
