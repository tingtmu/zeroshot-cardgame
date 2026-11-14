"""Declarative behaviour rules for status effects.

Each ``StatusKind`` (the set of statuses the engine knows about) gets one
``StatusRules`` entry from ``data/statuses.json``. The rules describe *what* a
status does; the battle engine implements the generic behaviours they name, so
adding a status that reuses existing behaviours needs only a data entry.

Expected format::

    {
      "statuses": [
        {"kind": "poison", "turn_end_damage_per_stack": true, "stacks_lost_per_turn": 1},
        {"kind": "weak", "outgoing_damage_reduction_per_stack": 25},
        {"kind": "shield", "absorbs_damage": true}
      ]
    }

Every ``StatusKind`` must appear exactly once.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cardgame.models import StatusKind

DEFAULT_STATUSES_PATH = Path(__file__).parent / "data" / "statuses.json"

_RULE_KEYS = {
    "kind",
    "absorbs_damage",
    "turn_end_damage_per_stack",
    "stacks_lost_per_turn",
    "outgoing_damage_reduction_per_stack",
}


class StatusDataError(ValueError):
    """Raised when status rule data is malformed."""


@dataclass(frozen=True)
class StatusRules:
    """What a status does, expressed as generic engine behaviours.

    * ``absorbs_damage``: stacks are a pool of HP absorbed before the unit's HP.
    * ``turn_end_damage_per_stack``: at status resolution the unit takes damage
      equal to the status's stacks.
    * ``stacks_lost_per_turn``: stacks removed at status resolution (after any
      damage). A status whose stacks reach 0 is removed.
    * ``outgoing_damage_reduction_per_stack``: each stack reduces damage dealt
      by the holder by this many percent (total reduction capped at 100).

    Every status's duration (in turns) ticks down at status resolution and the
    status is removed when it reaches 0.
    """

    kind: StatusKind
    absorbs_damage: bool = False
    turn_end_damage_per_stack: bool = False
    stacks_lost_per_turn: int = 0
    outgoing_damage_reduction_per_stack: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.kind, StatusKind):
            raise TypeError(f"kind must be a StatusKind, got {self.kind!r}")
        for name in ("absorbs_damage", "turn_end_damage_per_stack"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a bool")
        if isinstance(self.stacks_lost_per_turn, bool) or not isinstance(
            self.stacks_lost_per_turn, int
        ):
            raise TypeError("stacks_lost_per_turn must be an int")
        if self.stacks_lost_per_turn < 0:
            raise ValueError("stacks_lost_per_turn must be >= 0")
        reduction = self.outgoing_damage_reduction_per_stack
        if isinstance(reduction, bool) or not isinstance(reduction, int):
            raise TypeError("outgoing_damage_reduction_per_stack must be an int")
        if not 0 <= reduction <= 100:
            raise ValueError("outgoing_damage_reduction_per_stack must be in 0..100")


def _parse_rule(raw: Any, index: int) -> StatusRules:
    where = f"statuses[{index}]"
    if not isinstance(raw, Mapping):
        raise StatusDataError(f"{where}: status must be an object")
    unknown = set(raw) - _RULE_KEYS
    if unknown:
        raise StatusDataError(f"{where}: unknown keys {sorted(unknown)}")
    if "kind" not in raw:
        raise StatusDataError(f"{where}: missing 'kind'")
    try:
        kind = StatusKind(raw["kind"])
    except ValueError:
        raise StatusDataError(f"{where}: unknown status {raw['kind']!r}") from None
    where = f"status {kind.value!r}"
    kwargs: dict[str, Any] = {}
    for key in _RULE_KEYS - {"kind"}:
        if key in raw:
            kwargs[key] = raw[key]
    try:
        return StatusRules(kind=kind, **kwargs)
    except (TypeError, ValueError) as exc:
        raise StatusDataError(f"{where}: {exc}") from exc


def parse_status_rules(data: Any) -> dict[StatusKind, StatusRules]:
    """Build status rules from already-decoded JSON data, keyed by status kind."""
    if not isinstance(data, Mapping) or "statuses" not in data:
        raise StatusDataError("top level must be an object with a 'statuses' list")
    unknown = set(data) - {"statuses"}
    if unknown:
        raise StatusDataError(f"top level: unknown keys {sorted(unknown)}")
    raw_rules = data["statuses"]
    if not isinstance(raw_rules, list):
        raise StatusDataError("'statuses' must be a list")

    rules: dict[StatusKind, StatusRules] = {}
    for index, raw in enumerate(raw_rules):
        rule = _parse_rule(raw, index)
        if rule.kind in rules:
            raise StatusDataError(f"duplicate status {rule.kind.value!r}")
        rules[rule.kind] = rule

    missing = [kind.value for kind in StatusKind if kind not in rules]
    if missing:
        raise StatusDataError(f"no rules defined for statuses {missing}")
    return rules


def load_status_rules(path: str | Path) -> dict[StatusKind, StatusRules]:
    """Load status rules from a JSON file, keyed by status kind."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise StatusDataError(f"{path}: invalid JSON: {exc}") from exc
    return parse_status_rules(data)


def load_default_status_rules() -> dict[StatusKind, StatusRules]:
    """Load the status rules bundled with the package."""
    return load_status_rules(DEFAULT_STATUSES_PATH)
