# cardgame

Pure-logic skill engine for a turn-based card roguelike. No UI.

Milestone 1 provides the data structures (`Card`, `Effect`, `Status`, `Unit`)
and a JSON loader for cards. Milestone 2 adds the turn flow in
`cardgame.battle.Battle`: draw, play cards, discard the hand, enemy acts,
end-of-turn status hook, next turn. Status resolution and enemy AI are not
implemented yet (the enemy performs a fixed placeholder attack).

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
and `duration`, both >= 1).
