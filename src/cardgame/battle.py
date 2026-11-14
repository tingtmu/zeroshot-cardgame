"""Turn flow for a single battle between a player and an enemy.

Turn order::

    draw -> player plays cards (effects resolve as each card is played)
         -> player's hand is discarded -> enemy acts
         -> end-of-turn status hook -> next turn

Card effects are dispatched generically from ``EffectKind``; nothing here is
specific to a particular card. Status behaviour is likewise generic: each
status's ``StatusRules`` (loaded from ``data/statuses.json``) decide whether it
absorbs damage, deals damage at status resolution, loses stacks, or reduces
outgoing damage. All randomness comes from a ``random.Random`` seeded at
construction, so a battle is exactly reproducible from its seed and its
sequence of actions.

Status resolution runs at the end of each turn, after the enemy acts. For each
unit (player first, then enemy), each status in application order:

1. deals damage equal to its stacks, if its rules say so (poison);
2. loses ``stacks_lost_per_turn`` stacks; a status at 0 stacks is removed;
3. loses one turn of duration; a status at 0 duration is removed.

A status applied during a turn therefore first resolves at the end of that same
turn. A shield granted with duration 1 absorbs the enemy's attack in the same
turn and then expires.

Enemy AI (milestone 4) is not implemented: the enemy performs a fixed
placeholder attack.
"""

from __future__ import annotations

import random
from collections.abc import Mapping

from cardgame.models import Card, Effect, EffectKind, Status, StatusKind, Unit, _require_int
from cardgame.statuses import StatusRules, load_default_status_rules

DEFAULT_CARDS_PER_TURN = 5
DEFAULT_ENEMY_ATTACK = 4

# Duration given to a shield granted by a ``shield`` effect: it lasts until the
# end of the turn it was granted in (after the enemy has acted).
_SHIELD_DURATION = 1


class BattleError(RuntimeError):
    """Raised when an action is not legal in the current battle state."""


class Battle:
    """A battle between ``player`` and ``enemy`` driven by an explicit seed.

    The player's deck is copied into a draw pile and shuffled with the seeded
    RNG. The hand and discard pile are tracked alongside it. Only the player
    plays cards; the enemy's turn is a placeholder for now.
    """

    def __init__(
        self,
        player: Unit,
        enemy: Unit,
        seed: int,
        *,
        cards_per_turn: int = DEFAULT_CARDS_PER_TURN,
        enemy_attack: int = DEFAULT_ENEMY_ATTACK,
        status_rules: Mapping[StatusKind, StatusRules] | None = None,
    ) -> None:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError(f"seed must be an int, got {type(seed).__name__}")
        _require_int("cards_per_turn", cards_per_turn, 0)
        _require_int("enemy_attack", enemy_attack, 0)
        if status_rules is None:
            status_rules = load_default_status_rules()
        missing = [kind.value for kind in StatusKind if kind not in status_rules]
        if missing:
            raise ValueError(f"status_rules missing entries for {missing}")

        self.player = player
        self.enemy = enemy
        self.seed = seed
        self.cards_per_turn = cards_per_turn
        self.enemy_attack = enemy_attack
        self.status_rules: dict[StatusKind, StatusRules] = dict(status_rules)

        self.rng = random.Random(seed)
        self.draw_pile: list[Card] = list(player.deck)
        self.rng.shuffle(self.draw_pile)
        self.hand: list[Card] = []
        self.discard_pile: list[Card] = []

        # Number of turns started so far. 0 means no turn has begun yet.
        self.turn = 0
        self._player_phase = False

    # ----------------------------------------------------------------- state

    @property
    def is_over(self) -> bool:
        return not self.player.is_alive or not self.enemy.is_alive

    @property
    def winner(self) -> Unit | None:
        """The surviving unit once the battle is over, otherwise None."""
        if not self.is_over:
            return None
        return self.player if self.player.is_alive else self.enemy

    @property
    def in_player_phase(self) -> bool:
        return self._player_phase

    # ------------------------------------------------------------ turn flow

    def start_turn(self) -> None:
        """Begin a new turn: refill energy, then draw cards for the hand."""
        self._ensure_not_over()
        if self._player_phase:
            raise BattleError("a turn is already in progress")
        self.turn += 1
        self.player.energy = self.player.max_energy
        self._draw(self.cards_per_turn)
        self._player_phase = True

    def play_card(self, hand_index: int) -> Card:
        """Play the card at ``hand_index``, spending its cost and resolving effects."""
        self._ensure_player_phase()
        if isinstance(hand_index, bool) or not isinstance(hand_index, int):
            raise BattleError(f"hand index must be an int, got {hand_index!r}")
        if not 0 <= hand_index < len(self.hand):
            raise BattleError(f"no card at hand index {hand_index}")
        card = self.hand[hand_index]
        if card.cost > self.player.energy:
            raise BattleError(
                f"{card.name!r} costs {card.cost} energy, only {self.player.energy} left"
            )

        self.player.energy -= card.cost
        del self.hand[hand_index]
        self.discard_pile.append(card)
        for effect in card.effects:
            self._resolve_effect(effect)
        return card

    def end_turn(self) -> None:
        """Finish the player's turn: discard the hand, enemy acts, statuses resolve."""
        self._ensure_player_phase()
        self.discard_pile.extend(self.hand)
        self.hand.clear()
        self._player_phase = False

        if self.is_over:
            return
        self._enemy_act()
        if self.is_over:
            return
        self._resolve_end_of_turn_statuses()

    # -------------------------------------------------------------- helpers

    def _ensure_player_phase(self) -> None:
        self._ensure_not_over()
        if not self._player_phase:
            raise BattleError("no player turn is in progress; call start_turn() first")

    def _ensure_not_over(self) -> None:
        if self.is_over:
            raise BattleError("the battle is over")

    def _draw(self, count: int) -> None:
        """Move ``count`` cards from the top of the draw pile into the hand.

        When the draw pile runs out, the discard pile is shuffled into it with
        the seeded RNG. Drawing stops early if both piles are empty.
        """
        for _ in range(count):
            if not self.draw_pile:
                if not self.discard_pile:
                    return
                self.draw_pile = self.discard_pile
                self.discard_pile = []
                self.rng.shuffle(self.draw_pile)
            self.hand.append(self.draw_pile.pop())

    def _resolve_effect(self, effect: Effect) -> None:
        match effect.kind:
            case EffectKind.DAMAGE:
                self._deal_damage(self.enemy, self._outgoing_damage(self.player, effect.amount))
            case EffectKind.SHIELD:
                self.player.apply_status(
                    StatusKind.SHIELD, stacks=effect.amount, duration=_SHIELD_DURATION
                )
            case EffectKind.DRAW:
                self._draw(effect.amount)
            case EffectKind.APPLY_STATUS:
                assert effect.status is not None  # guaranteed by Effect validation
                self.enemy.apply_status(effect.status, effect.stacks, effect.duration)
            case _:  # pragma: no cover - every EffectKind is handled above
                raise AssertionError(f"unhandled effect kind {effect.kind!r}")

    def _enemy_act(self) -> None:
        """Placeholder enemy turn: a fixed attack on the player. AI comes in milestone 4."""
        self._deal_damage(self.player, self._outgoing_damage(self.enemy, self.enemy_attack))

    def _deal_damage(self, target: Unit, amount: int) -> None:
        """Deal ``amount`` damage to ``target``, absorbing it with absorbing statuses first.

        Absorbing statuses (shield) are consumed in application order. Whatever
        is left after they are exhausted is subtracted from HP, floored at 0.
        """
        remaining = amount
        for kind, status in list(target.statuses.items()):
            if remaining <= 0:
                break
            if not self.status_rules[kind].absorbs_damage:
                continue
            absorbed = min(status.stacks, remaining)
            status.stacks -= absorbed
            remaining -= absorbed
            if status.stacks == 0:
                del target.statuses[kind]
        target.hp = max(0, target.hp - remaining)

    def _outgoing_damage(self, source: Unit, amount: int) -> int:
        """Apply ``source``'s damage-dealt modifiers (e.g. weak) to ``amount``.

        Reduction is the sum over the source's statuses of
        ``stacks * outgoing_damage_reduction_per_stack`` percent, capped at 100.
        The result is rounded down.
        """
        reduction = 0
        for kind, status in source.statuses.items():
            per_stack = self.status_rules[kind].outgoing_damage_reduction_per_stack
            reduction += status.stacks * per_stack
        reduction = min(reduction, 100)
        return amount * (100 - reduction) // 100

    def _resolve_end_of_turn_statuses(self) -> None:
        """Status resolution step: tick every status on both units.

        The player is resolved first, then the enemy. Stops early if a unit
        dies, since the battle is then over.
        """
        for unit in (self.player, self.enemy):
            for kind, status in list(unit.statuses.items()):
                if self.is_over:
                    return
                self._tick_status(unit, kind, status)

    def _tick_status(self, unit: Unit, kind: StatusKind, status: Status) -> None:
        rules = self.status_rules[kind]
        if rules.turn_end_damage_per_stack:
            self._deal_damage(unit, status.stacks)
        status.stacks -= rules.stacks_lost_per_turn
        status.duration -= 1
        if status.stacks <= 0 or status.duration <= 0:
            unit.statuses.pop(kind, None)
