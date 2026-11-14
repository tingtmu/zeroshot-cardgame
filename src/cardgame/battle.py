"""Turn flow for a single battle between a player and an enemy.

Turn order::

    draw -> player plays cards (effects resolve as each card is played)
         -> player's hand is discarded -> enemy acts
         -> end-of-turn status hook -> next turn

Card effects are dispatched generically from ``EffectKind``; nothing here is
specific to a particular card. All randomness comes from a ``random.Random``
seeded at construction, so a battle is exactly reproducible from its seed and
its sequence of actions.

Status resolution (milestone 3) and enemy AI (milestone 4) are not implemented
here: the end-of-turn status hook is an empty method and the enemy performs a
fixed placeholder attack.
"""

from __future__ import annotations

import random

from cardgame.models import Card, Effect, EffectKind, StatusKind, Unit, _require_int

DEFAULT_CARDS_PER_TURN = 5
DEFAULT_ENEMY_ATTACK = 4

# Duration given to a shield granted by a ``shield`` effect. Shield lifetime
# rules belong to milestone 3, so this is a placeholder.
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
    ) -> None:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError(f"seed must be an int, got {type(seed).__name__}")
        _require_int("cards_per_turn", cards_per_turn, 0)
        _require_int("enemy_attack", enemy_attack, 0)

        self.player = player
        self.enemy = enemy
        self.seed = seed
        self.cards_per_turn = cards_per_turn
        self.enemy_attack = enemy_attack

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
                self.enemy.hp = max(0, self.enemy.hp - effect.amount)
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
        self.player.hp = max(0, self.player.hp - self.enemy_attack)

    def _resolve_end_of_turn_statuses(self) -> None:
        """Hook for end-of-turn status resolution. Statuses are milestone 3."""
