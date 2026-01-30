# Bolt Style Guide

## Execute
Always use the full form of `execute` for better readability.

```bolt
# do this!
execute as @a run say hello!

# not this
as @a say bad 🥲
```

If the `execute` command spans multiple lines, indent subsequent lines for clarity.

```bolt
# do this!
execute as @a
    at @s
    run say hello!
```
