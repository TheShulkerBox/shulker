# Custom Items

All items on the Shulker gets defined and processed via our `Item` abstraction. Define custom pythonic classes which gets translated into runtime Minecraft items with vanilla and custom components, all validated by the time you run `beet`!

## Overview

```py
from item:meta import Item

class Dart(Item):
    id = "arrow"
    item_name = "Dart"
    on_use = {callback: ~/on_use}
```

Define items

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User's Item Class                       │
│  class Dart(Item):                                              │
│      id = "arrow"                                               │
│      item_name = "Dart"                                         │
│      on_use = {callback: ~/on_use}                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      ItemType Metaclass                         │
│  - Intercepts class creation                                    │
│  - Discovers components via introspection                       │
│  - Tracks source information for error messages                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Component Resolution                         │
│  1. Discover: Find all non-callable, non-private attributes     │
│  2. Transform: Apply custom components/transformers             │
│  3. Validate: Check against mcdoc schemas                       │
│  4. Finalize: Merge and cache results                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      Final Item Object                          │
│  {                                                              │
│    "minecraft:item_name": "Dart",                               │
│    "minecraft:use_cooldown": {...},                             │
│    "minecraft:custom_data": {                                   │
│      "item_id": "dart",                                         │
│      "custom_components": {"on_use": {...}}                     │
│    }                                                            │
│  }                                                              │
└─────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. ItemType Metaclass ([meta.py:32](../src/item/meta.py#L32))

The metaclass is the heart of the system. It:
- Transforms class definitions into item objects
- Manages component discovery and resolution
- Handles validation and error reporting
- Maintains a registry of all items

**Why a metaclass?** Items are never instantiated - they're used directly as classes. The metaclass lets us define items declaratively while still having rich behavior.

### 2. Component Discovery ([meta.py:272-285](../src/item/meta.py#L272-L285))

The system discovers components by:
1. Iterating over all class attributes via `dir()`
2. Filtering out private members (starting with `_`)
3. Filtering out callable members (methods)
4. Tracking source information for each component

**Trade-off:** Using `dir()` is implicit, but it keeps the user API clean. No decorators or registration needed.

### 3. Custom Components & Transformers

**Components** ([component/base.py:11](../src/component/base.py#L11)): Create new components from user input
- Example: `on_use` → `minecraft:use_cooldown` + custom_data

**Transformers** ([component/base.py:35](../src/component/base.py#L35)): Modify existing component values
- Example: `dyed_color: "#ff0000"` → `dyed_color: 16711680`

Both use:
- Dataclass-based field validation
- Auto-registration via `__init_subclass__`
- Lazy rendering (only when needed)

### 4. Validation Pipeline

```python
# For each component:
1. Custom component/transformer processing
   ├─ Field validation (dataclass fields)
   ├─ Rendering (transform to vanilla components)
   └─ Post-processing (optional cleanup)

2. Schema validation (mcdoc)
   ├─ Type checking
   ├─ Structure validation
   └─ Enum/constraint validation

3. Error collection & reporting
   ├─ Source tracking
   ├─ Error summarization
   └─ Helpful suggestions
```

## Error Handling

The system prioritizes **developer experience** when things go wrong:

### Source Tracking
Every component remembers where it was defined:
```python
self._component_sources[member] = {
    'class': self.__name__,
    'module': self.__module__,
    'original_value': val,
}
```

This enables error messages like:
```
Component 'on_use' failed validation
  Defined in: Dart (src/items/combat.bolt:42)
```

### Error Hierarchy

```
ItemError (base)
├─ ComponentError
│  ├─ NonExistentComponentError (with suggestions)
│  ├─ CustomComponentError
│  └─ CustomTransformerError
└─ ValidationError
   ├─ MissingValidationError
   └─ UnexpectedValidationError
```

Each error stores:
- The component name and value
- Sub-errors (for nested validation)
- Source information (class, module, line)
- Hints (actionable suggestions)

### Error Display

Errors are displayed in three parts:

1. **Summary** - One-line overview
   ```
   ❌ on_use: 1 missing, 1 wrong type | item_name: 1 wrong type
   ```

2. **Details** - Rich tree structure showing nested errors

3. **Context** - Source location, suggestions, hints

## Component Lifecycle

### 1. Definition
```python
class MyItem(Item):
    on_use = {callback: ~/my_callback, cooldown: 20}
```

### 2. Discovery (Lazy)
The `.components` property triggers discovery:
```python
item_components = MyItem.components  # First access
```

### 3. Resolution
```python
# For each discovered component:
if is_custom_component(name):
    component = CustomComponent(item=MyItem, **data)
    output = component.render()  # Transform to vanilla
    merge(resolved_components, output)
```

### 4. Validation
```python
for name, value in resolved_components.items():
    schema = get_schema(name)
    validate(value, schema)  # Raises ValidationError if invalid
```

### 5. Caching
```python
# Results are cached to avoid recomputation
if name not in self._component_cache:
    self._component_cache[name] = component.render()
```

### 6. Finalization
```python
# Components are merged into final dict
{
    "minecraft:item_name": "...",
    "minecraft:custom_data": {
        "item_id": "my_item",
        "custom_components": {...}
    }
}
```

## Design Patterns

### Registry Pattern
Components and transformers auto-register via `__init_subclass__`:
```python
class Component:
    registered: ClassVar[list[Self]] = []

    def __init_subclass__(cls):
        cls.registered.append(dataclass(cls))
```

### Lazy Evaluation
Components aren't resolved until accessed:
```python
@property
def components(self):
    if self._components:
        return self._components  # Cached
    # ... expensive computation ...
```

### Deep Merging
Custom components output is deeply merged with existing components:
```python
deep_merge_dicts(resolved_components, custom_output, inplace=True)
```

This allows multiple components to contribute to the same nested structure.

## Common Patterns

### Creating a Custom Component

```python
from component.base import Component
from dataclasses import dataclass

@dataclass
class MyCustomComponent(Component):
    """Docstring explaining what this does"""

    # Define fields with type hints
    value: str
    enabled: bool = True  # Optional with default

    def render(self) -> dict[str, Any] | None:
        """Transform to vanilla components"""
        if not self.enabled:
            return None

        return {
            "minecraft:custom_data": {
                "my_component": {
                    "value": self.value
                }
            }
        }

    def post_render(self, resolved_components: dict[str, Any]):
        """Optional: Modify resolved_components after rendering"""
        pass
```

### Creating a Transformer

```python
from component.base import Transformer
from dataclasses import dataclass

@dataclass
class MyTransformer(Transformer):
    """Docstring explaining transformation"""

    value: str | int  # Accept multiple types

    def render(self) -> Any | None:
        """Return transformed value"""
        if isinstance(self.value, str):
            return int(self.value, 16)  # Convert hex to int
        return self.value
```

### Debugging Items

Use the `.debug()` method to inspect item construction:
```python
MyItem.debug()
```

This shows:
- Original attributes
- Applied components/transformers
- Final resolved components

## Performance Considerations

### Caching
- Components are cached after first render
- Use `cache=False` parameter to disable: `class MyComponent(Component, cache=False)`
- Cache is per-item-class, not per-instance

### Lazy Evaluation
- Components are only resolved when `.components` is accessed
- Item classes are created eagerly (at import time)
- Validation happens during component resolution

### Deep Copying
- Original components are deep-copied to prevent mutations
- Use `inplace=True` for deep_merge when safe to mutate

## Gotchas & Edge Cases

### 1. Callable Attributes
Methods and other callables are ignored during discovery. To include a callable in components:
```python
# ❌ This won't work
class MyItem(Item):
    callback = lambda: print("hi")  # Filtered out

# ✅ Do this instead
class MyItem(Item):
    callback = {"function": "~/my_function"}
```

### 2. Private Attributes
Anything starting with `_` is ignored:
```python
class MyItem(Item):
    _internal = "hidden"  # Not included in components
    public = "visible"    # Included
```

### 3. Inheritance
Items can inherit from other items:
```python
class BaseItem(Item):
    id = "stone"
    item_name = "Base"

class DerivedItem(BaseItem):
    item_name = "Derived"  # Overrides parent
    # id = "stone" inherited
```

### 4. Dynamic Items
Use the callable syntax to create variants:
```python
variant = MyItem(item_name="Variant", custom_field="value")
# Creates an anonymous subclass with overrides
```

## Extending the System

### Adding New Error Types

1. Define error class in [errors.py](../src/lib/errors.py):
```python
class MyCustomError(ComponentError):
    my_field: str

    def __init__(self, name: str, my_field: str):
        super().__init__(name, None, [])
        self.my_field = my_field
```

2. Add rendering logic in `calculate_errors()`:
```python
case MyCustomError(name=name, my_field=field):
    messages.append(f"Custom error for {name}: {field}")
```

### Adding Component Discovery Hooks

To customize discovery, override in ItemType:
```python
def discover_components(self) -> dict[str, Any]:
    """Custom discovery logic"""
    # Your implementation
```

## Testing

Currently, testing is ad-hoc via in-game validation. To test an item:

```python
# 1. Define your item
class TestItem(Item):
    id = "stone"
    # ... components ...

# 2. Inspect it
TestItem.debug()

# 3. Give it in-game
/function server:item/give/test_item

# 4. Check for errors during build
beet  # Errors will show in console
```

## Future Improvements

Potential enhancements to consider:

1. **Explicit Registration** - Replace `dir()` with explicit decorators for clarity
2. **Component Composition** - Allow components to depend on each other
3. **Automated Testing** - Unit tests for component transformations
4. **Type Hints** - Better type checking for component values
5. **Schema Generation** - Auto-generate mcdoc schemas from components
6. **Performance Profiling** - Identify slow validation/rendering steps
