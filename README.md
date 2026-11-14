# cardgame

Pure-logic skill engine for a turn-based card roguelike. No UI.

Milestone 1 provides the data structures (`Card`, `Effect`, `Status`, `Unit`)
and a JSON loader for cards. Milestone 2 adds the turn flow in
`cardgame.battle.Battle`: draw, play cards, discard the hand, enemy acts,
status resolution, next turn. Milestone 3 adds status effects (poison, weak,
shield). Milestone 4 adds data-driven enemy AI: enemies pick intents from
JSON patterns, and their next intent is visible during the player's turn.
Without an enemy AI, the enemy performs a fixed placeholder attack.

```python
from cardgame import Battle, Unit, load_default_cards

cards = load_default_cards()
hero = Unit(name="Hero", max_hp=40, max_energy=3, deck=list(cards.values()) * 2)
slime = Unit(name="Slime", max_hp=30, max_energy=0)

battle = Battle(hero, slime, seed=42)   # same seed + same actions = same battle
battle.start_turn()
battle.play_card(0)                     # index into battle.hand
battle.end_turn()
```

## Development

```sh
uv sync          # install dependencies (pytest is a dev dependency)
uv run pytest    # run the test suite
```

## Adding cards

Cards are data, not code. Add an entry to `src/cardgame/data/cards.json`:

```json
{"name": "Strike", "cost": 1, "effects": [{"type": "damage", "amount": 6}]}
```

Supported effect types: `damage`, `shield`, `draw` (use `amount`), and
`apply_status` (use `status` = `poison` | `weak` | `shield`, plus `stacks`
and `duration`, both >= 1). Damage, shield and status effects also accept an
optional `"target"`: `"self"` or `"opponent"`. By default `shield` targets the
performing unit and everything else targets the opponent.

## Status effects

Statuses are defined in `src/cardgame/data/statuses.json`, one entry per status
kind, and loaded into `StatusRules`. Each rule is a generic behaviour the engine
already knows how to run:

| Field | Meaning |
| --- | --- |
| `absorbs_damage` | Stacks are HP-equivalent shield, consumed before HP. |
| `turn_end_damage_per_stack` | Unit takes damage equal to its stacks at status resolution. |
| `stacks_lost_per_turn` | Stacks removed at status resolution; removed at 0 stacks. |
| `outgoing_damage_reduction_per_stack` | Percent less damage dealt per stack (capped at 100, rounded down). |

Current definitions:

- `poison`: at status resolution deals damage equal to its stacks, then loses 1 stack.
- `weak`: each stack reduces damage the holder deals by 25%.
- `shield`: stacks are absorbed damage. A `shield` effect grants a shield that
  lasts one turn; an `apply_status` shield lasts its `duration`.

Every status's duration ticks down by one at status resolution and the status
is removed at 0. Status resolution runs after the enemy acts, for the player
first and then the enemy. Battles can be given custom rules via
`Battle(..., status_rules=...)`.

## Enemies

Enemies are defined in `src/cardgame/data/enemies.json`. Each has a name, `max_hp`,
optional `max_energy` (default 0), and a `pattern`:

- `"mode": "cycle"`: intents are used in order, wrapping around.
- `"mode": "weighted"`: each intent has a `weight` (default 1), chosen with the
  battle's seeded RNG.

Each intent has a `name` (shown to the player) and `effects` that use the same
effect format as cards. Enemy intents may not use `draw`, since enemies have no hand.

```json
{
  "name": "Slime",
  "max_hp": 30,
  "pattern": {
    "mode": "cycle",
    "intents": [
      {"name": "Tackle", "effects": [{"type": "damage", "amount": 4}]},
      {"name": "Harden", "effects": [
        {"type": "apply_status", "status": "shield", "stacks": 5, "duration": 2, "target": "self"}
      ]}
    ]
  }
}
```

Bundled examples are `Slime` (a cycle of attack then shield) and `Cultist` (a
weighted mix of attack, poison and shield). To use one:

```python
from cardgame import Battle, Unit, load_default_cards, load_default_enemies

enemy = load_default_enemies()["Slime"]
battle = Battle(hero, enemy.create_unit(), seed=42, enemy_ai=enemy.create_ai())
battle.enemy_intent  # the Intent the enemy will perform at end_turn()
```

Enemy intents are chosen when the battle starts and again after each enemy action.

