# cardgame

Pure-logic skill engine for a turn-based card roguelike. No UI.

Milestone 1 provides the data structures (`Card`, `Effect`, `Status`, `Unit`)
and a JSON loader for cards. Turn flow, status resolution and enemy AI are
not implemented yet.

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
