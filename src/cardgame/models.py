"""Core data structures: effects, cards, statuses and units.

These are plain typed data containers. They hold no turn flow, status
resolution or AI logic; those belong to later milestones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


def _require_int(name: str, value: object, minimum: int) -> None:
    """Validate that ``value`` is an int (not a bool) and at least ``minimum``."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int, got {type(value).__name__}")
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")


class EffectKind(str, Enum):
    """Kinds of effect a card can have. Values match the JSON ``type`` field."""

    DAMAGE = "damage"
    SHIELD = "shield"
    DRAW = "draw"
    APPLY_STATUS = "apply_status"


class StatusKind(str, Enum):
    """Kinds of status effect. Values match the JSON ``status`` field."""

    POISON = "poison"
    WEAK = "weak"
    SHIELD = "shield"


@dataclass(frozen=True)
class Effect:
    """A single effect of a card.

    ``amount`` is used by ``damage``, ``shield`` and ``draw``.
    ``status``, ``stacks`` and ``duration`` are used by ``apply_status`` only.
    """

    kind: EffectKind
    amount: int = 0
    status: StatusKind | None = None
    stacks: int = 0
    duration: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.kind, EffectKind):
            raise TypeError(f"kind must be an EffectKind, got {self.kind!r}")
        if self.kind is EffectKind.APPLY_STATUS:
            if not isinstance(self.status, StatusKind):
                raise ValueError("apply_status effect requires a StatusKind 'status'")
            _require_int("stacks", self.stacks, 1)
            _require_int("duration", self.duration, 1)
            if self.amount != 0:
                raise ValueError("apply_status effect must not set 'amount'")
        else:
            _require_int("amount", self.amount, 1)
            if self.status is not None or self.stacks != 0 or self.duration != 0:
                raise ValueError(
                    f"{self.kind.value} effect must not set status, stacks or duration"
                )


@dataclass(frozen=True)
class Card:
    """A card with a name, an energy cost and an ordered list of effects."""

    name: str
    cost: int
    effects: tuple[Effect, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("card name must be a non-empty string")
        _require_int("cost", self.cost, 0)
        # Normalise any sequence into a tuple so cards are immutable.
        object.__setattr__(self, "effects", tuple(self.effects))
        for effect in self.effects:
            if not isinstance(effect, Effect):
                raise TypeError(f"card effects must be Effect, got {effect!r}")


@dataclass
class Status:
    """A status applied to a unit, with a number of stacks and remaining turns."""

    kind: StatusKind
    stacks: int = 1
    duration: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.kind, StatusKind):
            raise TypeError(f"kind must be a StatusKind, got {self.kind!r}")
        _require_int("stacks", self.stacks, 1)
        _require_int("duration", self.duration, 1)

    def merge(self, stacks: int, duration: int) -> None:
        """Combine a new application into this status.

        Stacks are added together; duration is refreshed to the longer of the
        remaining and newly applied durations.
        """
        _require_int("stacks", stacks, 1)
        _require_int("duration", duration, 1)
        self.stacks += stacks
        self.duration = max(self.duration, duration)


@dataclass
class Unit:
    """A player or enemy unit with HP, energy, a deck and active statuses."""

    name: str
    max_hp: int
    max_energy: int
    deck: list[Card] = field(default_factory=list)
    hp: int | None = None
    energy: int | None = None
    statuses: dict[StatusKind, Status] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("unit name must be a non-empty string")
        _require_int("max_hp", self.max_hp, 1)
        _require_int("max_energy", self.max_energy, 0)
        if self.hp is None:
            self.hp = self.max_hp
        if self.energy is None:
            self.energy = self.max_energy
        _require_int("hp", self.hp, 0)
        _require_int("energy", self.energy, 0)
        if self.hp > self.max_hp:
            raise ValueError(f"hp {self.hp} exceeds max_hp {self.max_hp}")
        if self.energy > self.max_energy:
            raise ValueError(f"energy {self.energy} exceeds max_energy {self.max_energy}")
        for card in self.deck:
            if not isinstance(card, Card):
                raise TypeError(f"deck entries must be Card, got {card!r}")

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    def get_status(self, kind: StatusKind) -> Status | None:
        """Return the active status of ``kind``, or None if not applied."""
        return self.statuses.get(kind)

    def apply_status(self, kind: StatusKind, stacks: int, duration: int) -> Status:
        """Apply a status, merging with any existing status of the same kind."""
        existing = self.statuses.get(kind)
        if existing is None:
            existing = Status(kind=kind, stacks=stacks, duration=duration)
            self.statuses[kind] = existing
        else:
            existing.merge(stacks, duration)
        return existing
