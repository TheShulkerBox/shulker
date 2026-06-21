# Bolt Expressions

A library to make mathematical operations in Minecraft easier ✨.

This is a project-local reference for `bolt_expressions` as used in Shulker2.
It is based on the installed source at
`.venv/lib/python3.14/site-packages/bolt_expressions` version `0.19.2`.
Prefer that source over hosted docs when behavior is unclear.

## Mental Model

`bolt_expressions` builds expression trees from Python-looking operations and emits
Minecraft commands through Mecha. The public API is intentionally small:

- `Scoreboard` creates scoreboard objectives and `ScoreSource` values.
- `Data` creates `DataSource` values for storage, entities, and blocks.
- Operators on those sources produce expression nodes that resolve into commands.
- The optimizer rewrites those nodes before command generation.

In Bolt files, `Scoreboard` and `Data` are injected API objects, not the raw
Python classes shown in `api.py`. The plugin installs a module attribute handler
so this works:

```bolt
from bolt_expressions import Scoreboard, Data

COUNTER = Scoreboard("example.counter", criteria="dummy")
TEMP = Data.storage("shulker:temp")
```

Shulker2 auto-imports the common sources from `src/server/prelude.bolt`:

```bolt
SCORE.temp["#value"] = 10
STORAGE.temp.example.count = SCORE.temp["#value"] + 1
SELF.Health = 20
BLOCK.Items.append({Slot: 0b})
```

## Shulker2 Configuration

`beet.yaml` overrides the upstream defaults:

```yaml
bolt_expressions:
  temp_objective: "temp"
  const_objective: "const"
  temp_storage: "bolt:temp"
  init_path: "core/load/init_objectives"
```

That means generated temporary scores use the `temp` objective, constant
fakeplayers use `const`, scratch NBT uses `storage bolt:temp`, and objective
initialization is generated at `core/load/init_objectives`.

## Scoreboards

Create an objective with `Scoreboard(name, criteria="dummy")`. This returns an
`Objective`; indexing it returns a `ScoreSource`.

```bolt
POINTS = Scoreboard("game.points", criteria="dummy")

POINTS["@s"] = 5
POINTS["@s"] += SCORE.temp["#bonus"] * 2
SCORE.temp["#is_big"] = POINTS["@s"] >= 10
```

Supported score operations include:

- Assignment: `score = value`
- Arithmetic: `+`, `-`, `*`, `/`, `%`
- Comparisons: `<`, `<=`, `>`, `>=`, `==`, `!=`
- Boolean test: `if score:` or `if not score:`
- Score commands: `score.enable()` and `score.reset()`
- Text components: `score.component(**tags)`

Integer literals are converted to constant fakeplayers and initialized
automatically. Multiplication, division, modulus, min, and max ultimately need
score operands, so literal operands may become constants or temporaries.

Scoreboards are Minecraft scores, so they are always integers. When runtime math
needs decimals, use fixed-point values: scale up before storing in a score, do
integer operations at that larger precision, then scale down when storing into
NBT. `execute store ... data ... <type> <scale>` and `data get ... <scale>` are
the native command escape hatches, and `bolt_expressions` can optimize toward
those forms when a `DataSource` has an explicit scale.

```bolt
PRECISION = 1000

SCORE.temp["#scaled"] = STORAGE.temp.input * PRECISION
execute store result var STORAGE.temp.output double (1 / PRECISION) run scoreboard players get var SCORE.temp["#scaled"]
```

This pattern shows up in helpers that need partial precision, like motion or
display scaling. Prefer a named precision constant so the scale-up and
scale-down are visibly paired.

## Data Sources

Create data sources through `Data.storage(...)`, `Data.entity(...)`, or
`Data.block(...)`. Accessing attributes or items extends the NBT path.

```bolt
player = Data.entity("@s")
temp = Data.storage("shulker:temp")

temp.uuid = player.UUID
temp.names.append(player.CustomName)
temp.players[{id: "lobby"}].online = true
```

Data assignment writes through `data modify` or `execute store`, depending on
the right-hand side. The source can be modified in place:

```bolt
STORAGE.temp.items.append({id: "minecraft:stone", count: 1})
STORAGE.temp.items.prepend({id: "minecraft:apple", count: 3})
STORAGE.temp.items.insert(1, {id: "minecraft:stick", count: 2})
STORAGE.temp.items.remove(0)
STORAGE.temp.player.merge({Tags: ["READY"]})
```

Path access accepts names, list indexes, slices, and compound matches:

```bolt
STORAGE.rom.maps[:]
STORAGE.rom.maps[0]
STORAGE.rom.maps[{id: "arena"}]
STORAGE.temp.name[0:8]
```

`DataSource.__call__` changes how a source is read or written:

```bolt
STORAGE.temp.amount(type="double", scale=0.01)
STORAGE.rom.maps({id: "arena"})
```

## Types Matter

The operator surface for `DataSource` depends on the current NBT type.
Untyped data falls back to a generic handler, but adding a type gives the
compiler better checks and enables type-specific access.

```bolt
STORAGE.temp.count[int] += 1
STORAGE.temp.name[str][0:4]
STORAGE.temp.tags[list[str]].append("ready")
STORAGE.temp.meta[{id: str, value: int}].value
```

Accepted type forms include Python primitives, `typing.Any`, unions, `list[T]`,
`dict[str, T]`, fixed dict shapes, `TypedDict`, and nbtlib numeric types such as
`Byte`, `Short`, `Int`, `Long`, `Float`, and `Double`.

Literal assignment is cast through the target type when possible:

```bolt
STORAGE.temp.flag[bool] = true      # stored as a byte
STORAGE.temp.count["long"] = 100    # string aliases are accepted by Data.cast/dummy
```

Use `Data.cast(value, nbt_type)` or `Data.dummy(nbt_type)` when a temporary
typed storage value is clearer than relying on inference.

## Builtin Wrappers

The plugin wraps `min`, `max`, and `len` when expression nodes are involved.

```bolt
SCORE.temp["#clamped"] = max(0, min(100, SCORE.temp["#value"]))
SCORE.temp["#count"] = len(STORAGE.temp.items[:])
```

If no expression source is present, the normal Python builtin behavior is used.
This makes it possible to write helpers that accept compile-time literals and
runtime sources with the same code path.

```bolt
def clamp_percent(value: int | ScoreSource):
    return max(0, min(100, value))

SCORE.temp["#runtime"] = clamp_percent(SCORE.temp["#input"])
compile_time = clamp_percent(130)  # ordinary Python result: 100
```

See `src/lib/xp.bolt`: `XP.set_points()` accepts either an `int` or
`ScoreSource`, clamps it through `min`/`max`, and then uses macro storage to feed
the value into `xp` commands.

## Command Interpolation

`bolt_expressions.contrib.commands` lets commands accept expression sources via
the `var` keyword in places that normally take score or data target arguments.
Shulker2 requires the command helper explicitly, and the core plugin also
requires it unless `disable_commands` is set.

```bolt
execute store result score var SCORE.temp["#players"] if entity @a
data modify var STORAGE.temp.output set from var STORAGE.rom.maps[0]
store result score var SCORE.temp["#killed"] kill @n[type=marker,distance=..5]
```

When interpolating a `ScoreSource`, the transformer emits score holder and
objective arguments. When interpolating a `DataSource`, it emits the target type,
target, and NBT path.

## Branching And Laziness

Comparisons and boolean tests become temporary score/data sources, and `if`
statements become optimized branch command trees.

```bolt
if SCORE.temp["#count"] >= 2:
    say enough players

if STORAGE.temp.uuid:
    SELF.Owner = STORAGE.temp.uuid
```

Some operator methods are lazy. If a lazy source is later used in a command, it
is evaluated first; otherwise the deferred command may be skipped. This is why
source interpolation calls `evaluate()` before lowering command arguments.

## Practical Guidance

- Prefer `SCORE.temp` for numeric scratch work and `STORAGE.temp` for structured
  scratch work.
- Read `src/server/prelude.bolt` before writing new project code. `SCORE`,
  `STORAGE`, `SELF`, `BLOCK`, and several common type aliases are already in
  scope everywhere.
- Annotate data sources when assigning or comparing structured NBT. The type
  checker catches bad list elements, missing required compound keys, extra fixed
  keys, and unsafe numeric narrowing.
- Use `var <source>` inside commands instead of hand-formatting score/data target
  triples.
- Use `score.component()` and `data.component()` when building text components;
  the plugin also converts nested `Source` values in interpolated NBT.
- For public helper APIs, prefer Shulker's `IntLike`, `FloatLike`,
  `StringLike`, `TextComponentLike`, and `CompoundLike` aliases from
  `src/lib/types.py` when a value can be compile-time or runtime.
- When a helper needs different generation strategies, branch on
  `isinstance(value, DataSource)` or `isinstance(value, ScoreSource)`. For
  example, `src/lib/motion.bolt` emits literal enchantment data for
  compile-time vectors but generates scoreboard/data operations for runtime
  `DataSource` vectors.
- Keep expressions readable. The optimizer is capable, but a temporary score or
  storage value can make generated behavior easier to reason about.
