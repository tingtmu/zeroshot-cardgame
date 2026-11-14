"""Load card definitions from JSON data files.

Expected format::

    {
      "cards": [
        {
          "name": "Strike",
          "cost": 1,
          "effects": [{"type": "damage", "amount": 6}]
        },
        {
          "name": "Venom Dart",
          "cost": 1,
          "effects": [
            {"type": "damage", "amount": 3},
            {"type": "apply_status", "status": "poison", "stacks": 2, "duration": 3}
          ]
        }
      ]
    }
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cardgame.models import Card, Effect, EffectKind, StatusKind, Target

DEFAULT_CARDS_PATH = Path(__file__).parent / "data" / "cards.json"

_CARD_KEYS = {"name", "cost", "effects"}
_AMOUNT_EFFECT_KEYS = {"type", "amount", "target"}
_STATUS_EFFECT_KEYS = {"type", "status", "stacks", "duration", "target"}


class CardDataError(ValueError):
    """Raised when card data is malformed."""


def _check_keys(obj: Mapping[str, Any], allowed: set[str], where: str) -> None:
    unknown = set(obj) - allowed
    if unknown:
        raise CardDataError(f"{where}: unknown keys {sorted(unknown)}")


def _int_field(obj: Mapping[str, Any], key: str, where: str) -> int:
    if key not in obj:
        raise CardDataError(f"{where}: missing '{key}'")
    value = obj[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise CardDataError(f"{where}: '{key}' must be an integer")
    return value


def _target_field(raw: Mapping[str, Any], where: str) -> Target | None:
    if "target" not in raw:
        return None
    try:
        return Target(raw["target"])
    except ValueError:
        raise CardDataError(f"{where}: unknown target {raw['target']!r}") from None


def parse_effect(raw: Any, where: str) -> Effect:
    """Parse one effect object (``{"type": ...}``) from decoded JSON.

    Shared by card and enemy-intent data, so both use the same Effect system.
    """
    if not isinstance(raw, Mapping):
        raise CardDataError(f"{where}: effect must be an object")
    if "type" not in raw:
        raise CardDataError(f"{where}: missing 'type'")
    try:
        kind = EffectKind(raw["type"])
    except ValueError:
        raise CardDataError(f"{where}: unknown effect type {raw['type']!r}") from None

    try:
        if kind is EffectKind.APPLY_STATUS:
            _check_keys(raw, _STATUS_EFFECT_KEYS, where)
            if "status" not in raw:
                raise CardDataError(f"{where}: missing 'status'")
            try:
                status = StatusKind(raw["status"])
            except ValueError:
                raise CardDataError(
                    f"{where}: unknown status {raw['status']!r}"
                ) from None
            return Effect(
                kind=kind,
                status=status,
                stacks=_int_field(raw, "stacks", where),
                duration=_int_field(raw, "duration", where),
                target=_target_field(raw, where),
            )
        _check_keys(raw, _AMOUNT_EFFECT_KEYS, where)
        return Effect(
            kind=kind,
            amount=_int_field(raw, "amount", where),
            target=_target_field(raw, where),
        )
    except (TypeError, ValueError) as exc:
        if isinstance(exc, CardDataError):
            raise
        raise CardDataError(f"{where}: {exc}") from exc


def _parse_card(raw: Any, index: int) -> Card:
    where = f"cards[{index}]"
    if not isinstance(raw, Mapping):
        raise CardDataError(f"{where}: card must be an object")
    _check_keys(raw, _CARD_KEYS, where)
    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise CardDataError(f"{where}: 'name' must be a non-empty string")
    where = f"card {name!r}"
    cost = _int_field(raw, "cost", where)
    effects_raw = raw.get("effects")
    if not isinstance(effects_raw, list):
        raise CardDataError(f"{where}: 'effects' must be a list")
    effects = tuple(
        parse_effect(effect, f"{where} effects[{i}]")
        for i, effect in enumerate(effects_raw)
    )
    try:
        return Card(name=name, cost=cost, effects=effects)
    except (TypeError, ValueError) as exc:
        raise CardDataError(f"{where}: {exc}") from exc


def parse_cards(data: Any) -> dict[str, Card]:
    """Build cards from already-decoded JSON data, keyed by card name."""
    if not isinstance(data, Mapping) or "cards" not in data:
        raise CardDataError("top level must be an object with a 'cards' list")
    _check_keys(data, {"cards"}, "top level")
    raw_cards = data["cards"]
    if not isinstance(raw_cards, list):
        raise CardDataError("'cards' must be a list")
    cards: dict[str, Card] = {}
    for index, raw in enumerate(raw_cards):
        card = _parse_card(raw, index)
        if card.name in cards:
            raise CardDataError(f"duplicate card name {card.name!r}")
        cards[card.name] = card
    return cards


def load_cards(path: str | Path) -> dict[str, Card]:
    """Load cards from a JSON file, keyed by card name."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CardDataError(f"{path}: invalid JSON: {exc}") from exc
    return parse_cards(data)


def load_default_cards() -> dict[str, Card]:
    """Load the example cards bundled with the package."""
    return load_cards(DEFAULT_CARDS_PATH)
