# Shulker Rewrite

## Objective

Create a MVP of CTF with atleast footman.

## Tasks
- basic CTF game mode
- active game manager (start, stop, loop)
  - joining game via lobby box
  - leaving game

### Events
- `leave_game`
- `join_game`
- `start_game`
- `stop_game`
- `player_death`
- `player_respawn`
- `player_kill`

### CTF

![chart](image.png)

### State
- Team[]
    - Points
    - Flag Bearer
    - Winner
    - Players[]
      - `carrying_flag`
      - `stats`
- Map
  - `stats`

### Transitions
- event: `start_game(map)`

- event: `end_game(map)`

- event: `close_game(map)`

- event: `on_kill(killer, victim)`
  - `killer.team.points += 1`
  - `victim.carrying_flag = false`
  - `victim.respawn`

- event: `on_flag_pickup(player, victim_team)`
  - `player.carrying_flag = true`

- event: `on_flag_cap(player)`
  - `player.team.points += 20`
  - `player.carrying_flag = false`

- event: `leave_game(player)`

- event: `join_game(player)`
