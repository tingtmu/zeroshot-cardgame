"""Data-driven enemies and their intent patterns.

An enemy is defined entirely in ``data/enemies.json``. Each enemy has an
intent pattern: a list of intents, each a set of ordinary effects (the same
Effect system cards use), chosen either in a fixed cycle or by weighted random
choice from the battle's seeded RNG.

Expected format::

    {
      "enemies": [
        {
          "name": "Slime",
          "max_hp": 30,
          "max_energy": 0,
          "pattern": {
            "mode": "cycle",
            "intents": [
              {"name": "Tackle", "effects": [{"type": "damage", "amount": 4}]},
              {"name": "Harden", "effects": [
                {"type": "apply_status", "status": "shield", "stacks": 5,
                 "duration": 2, "target": "self"}
              ]}
            ]
          }
        },
        {
          "name": "Cultist",
          "max_hp": 40,
          "pattern": {
            "mode": "weighted",
            "intents": [
              {"name": "Dark Strike", "weight": 2, "effects": [...]},
              {"name": "Ward", "weight": 1, "effects": [...]}
            ]
          }
        }
      ]
    }

``max_energy`` is optional and defaults to 0. ``weight`` is only allowed in
``weighted`` mode and defaults to 1. Enemy intents may not use ``draw``: enemies
have no hand.

Enemies choose their next intent when the battle starts and again after each
enemy action, so the upcoming intent is always visible to the player.
"""

from __future__ import annotations

import json
import random
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from cardgame.loader import CardDataError, parse_effect
from cardgame.models import Effect, EffectKind, Unit, _require_int

DEFAULT_ENEMIES_PATH = Path(__file__).parent / "data" / "enemies.json"

_ENEMY_KEYS = {"name", "max_hp", "max_energy", "pattern"}
_PATTERN_KEYS = {"mode", "intents"}
_INTENT_KEYS = {"name", "weight", "effects"}


class EnemyDataError(ValueError):
    """Raised when enemy data is malformed."""


class IntentMode(str, Enum):
    """How an enemy picks its next intent. Values match the JSON ``mode`` field."""

    CYCLE = "cycle"
    WEIGHTED = "weighted"


@dataclass(frozen=True)
class Intent:
    """One action an enemy may take: a name (for display) and its effects."""

    name: str
    effects: tuple[Effect, ...] = ()
    weight: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("intent name must be a non-empty string")
        if isinstance(self.weight, bool) or not isinstance(self.weight, int) or self.weight < 1:
            raise ValueError("intent weight must be an int >= 1")
        object.__setattr__(self, "effects", tuple(self.effects))
        for effect in self.effects:
            if not isinstance(effect, Effect):
                raise TypeError(f"intent effects must be Effect, got {effect!r}")
            if effect.kind is EffectKind.DRAW:
                raise ValueError(f"intent {self.name!r} must not use a draw effect")


@dataclass(frozen=True)
class IntentPattern:
    """The intents an enemy can choose from, and how to choose between them."""

    mode: IntentMode
    intents: tuple[Intent, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.mode, IntentMode):
            raise TypeError(f"mode must be an IntentMode, got {self.mode!r}")
        object.__setattr__(self, "intents", tuple(self.intents))
        if not self.intents:
            raise ValueError("an intent pattern needs at least one intent")
        for intent in self.intents:
            if not isinstance(intent, Intent):
                raise TypeError(f"intents must be Intent, got {intent!r}")


@dataclass(frozen=True)
class EnemyDefinition:
    """Static description of an enemy. Create fresh units and AI per battle."""

    name: str
    max_hp: int
    max_energy: int
    pattern: IntentPattern

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("enemy name must be a non-empty string")
        _require_int("max_hp", self.max_hp, 1)
        _require_int("max_energy", self.max_energy, 0)
        if not isinstance(self.pattern, IntentPattern):
            raise TypeError(f"pattern must be an IntentPattern, got {self.pattern!r}")

    def create_unit(self) -> Unit:
        return Unit(name=self.name, max_hp=self.max_hp, max_energy=self.max_energy)

    def create_ai(self) -> EnemyAI:
        return EnemyAI(self.pattern)


class EnemyAI:
    """Chooses an enemy's intents from its pattern, one per enemy action.

    Holds the cycle position, so use one instance per battle. Weighted choice
    draws from the battle's seeded RNG, which keeps battles reproducible.
    """

    def __init__(self, pattern: IntentPattern) -> None:
        if not isinstance(pattern, IntentPattern):
            raise TypeError(f"pattern must be an IntentPattern, got {pattern!r}")
        self.pattern = pattern
        self._step = 0

    def choose(self, rng: random.Random) -> Intent:
        """Return the next intent and advance the pattern."""
        intents = self.pattern.intents
        if self.pattern.mode is IntentMode.CYCLE:
            intent = intents[self._step % len(intents)]
        else:
            weights = [intent.weight for intent in intents]
            intent = rng.choices(intents, weights=weights, k=1)[0]
        self._step += 1
        return intent


def _parse_intent(raw: Any, where: str, mode: IntentMode) -> Intent:
    if not isinstance(raw, Mapping):
        raise EnemyDataError(f"{where}: intent must be an object")
    unknown = set(raw) - _INTENT_KEYS
    if unknown:
        raise EnemyDataError(f"{where}: unknown keys {sorted(unknown)}")
    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise EnemyDataError(f"{where}: 'name' must be a non-empty string")
    where = f"intent {name!r}"
    if mode is IntentMode.CYCLE and "weight" in raw:
        raise EnemyDataError(f"{where}: 'weight' is only allowed in weighted mode")
    weight = raw.get("weight", 1)
    effects_raw = raw.get("effects", [])
    if not isinstance(effects_raw, list):
        raise EnemyDataError(f"{where}: 'effects' must be a list")
    try:
        effects = tuple(
            parse_effect(effect, f"{where} effects[{i}]")
            for i, effect in enumerate(effects_raw)
        )
        return Intent(name=name, effects=effects, weight=weight)
    except CardDataError as exc:
        raise EnemyDataError(str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise EnemyDataError(f"{where}: {exc}") from exc


def _parse_pattern(raw: Any, where: str) -> IntentPattern:
    if not isinstance(raw, Mapping):
        raise EnemyDataError(f"{where}: 'pattern' must be an object")
    unknown = set(raw) - _PATTERN_KEYS
    if unknown:
        raise EnemyDataError(f"{where}: pattern has unknown keys {sorted(unknown)}")
    try:
        mode = IntentMode(raw.get("mode"))
    except ValueError:
        raise EnemyDataError(f"{where}: unknown pattern mode {raw.get('mode')!r}") from None
    intents_raw = raw.get("intents")
    if not isinstance(intents_raw, list) or not intents_raw:
        raise EnemyDataError(f"{where}: 'intents' must be a non-empty list")
    intents = tuple(
        _parse_intent(intent, f"{where} intents[{i}]", mode)
        for i, intent in enumerate(intents_raw)
    )
    try:
        return IntentPattern(mode=mode, intents=intents)
    except (TypeError, ValueError) as exc:
        raise EnemyDataError(f"{where}: {exc}") from exc


def _parse_enemy(raw: Any, index: int) -> EnemyDefinition:
    where = f"enemies[{index}]"
    if not isinstance(raw, Mapping):
        raise EnemyDataError(f"{where}: enemy must be an object")
    unknown = set(raw) - _ENEMY_KEYS
    if unknown:
        raise EnemyDataError(f"{where}: unknown keys {sorted(unknown)}")
    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise EnemyDataError(f"{where}: 'name' must be a non-empty string")
    where = f"enemy {name!r}"
    if "max_hp" not in raw:
        raise EnemyDataError(f"{where}: missing 'max_hp'")
    if "pattern" not in raw:
        raise EnemyDataError(f"{where}: missing 'pattern'")
    pattern = _parse_pattern(raw["pattern"], where)
    try:
        return EnemyDefinition(
            name=name,
            max_hp=raw["max_hp"],
            max_energy=raw.get("max_energy", 0),
            pattern=pattern,
        )
    except (TypeError, ValueError) as exc:
        raise EnemyDataError(f"{where}: {exc}") from exc


def parse_enemies(data: Any) -> dict[str, EnemyDefinition]:
    """Build enemy definitions from already-decoded JSON, keyed by name."""
    if not isinstance(data, Mapping) or "enemies" not in data:
        raise EnemyDataError("top level must be an object with an 'enemies' list")
    unknown = set(data) - {"enemies"}
    if unknown:
        raise EnemyDataError(f"top level: unknown keys {sorted(unknown)}")
    raw_enemies = data["enemies"]
    if not isinstance(raw_enemies, list):
        raise EnemyDataError("'enemies' must be a list")
    enemies: dict[str, EnemyDefinition] = {}
    for index, raw in enumerate(raw_enemies):
        enemy = _parse_enemy(raw, index)
        if enemy.name in enemies:
            raise EnemyDataError(f"duplicate enemy name {enemy.name!r}")
        enemies[enemy.name] = enemy
    return enemies


def load_enemies(path: str | Path) -> dict[str, EnemyDefinition]:
    """Load enemy definitions from a JSON file, keyed by name."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EnemyDataError(f"{path}: invalid JSON: {exc}") from exc
    return parse_enemies(data)


def load_default_enemies() -> dict[str, EnemyDefinition]:
    """Load the example enemies bundled with the package."""
    return load_enemies(DEFAULT_ENEMIES_PATH)
