import pytest

from cardgame.battle import Battle, BattleError
from cardgame.loader import load_default_cards, parse_cards
from cardgame.models import Card, Effect, EffectKind, StatusKind, Unit


def _strike() -> Card:
    return load_default_cards()["Strike"]


def _guard() -> Card:
    return load_default_cards()["Guard"]


def _venom() -> Card:
    return load_default_cards()["Venom Dart"]


def _hero(deck, max_energy=3, max_hp=40) -> Unit:
    return Unit(name="Hero", max_hp=max_hp, max_energy=max_energy, deck=list(deck))


def _enemy(max_hp=30) -> Unit:
    return Unit(name="Slime", max_hp=max_hp, max_energy=0)


def _battle(deck=None, seed=1, **kwargs) -> Battle:
    if deck is None:
        deck = [_strike()] * 3 + [_guard()] * 3 + [_venom()] * 2
    return Battle(_hero(deck), _enemy(), seed=seed, **kwargs)


def _card_index(battle: Battle, name: str) -> int:
    for index, card in enumerate(battle.hand):
        if card.name == name:
            return index
    raise AssertionError(f"{name!r} not in hand {[c.name for c in battle.hand]}")


class TestSetup:
    def test_draw_pile_holds_the_whole_deck_and_nothing_is_drawn_yet(self):
        battle = _battle()
        assert sorted(c.name for c in battle.draw_pile) == sorted(
            c.name for c in battle.player.deck
        )
        assert battle.hand == []
        assert battle.discard_pile == []
        assert battle.turn == 0
        assert not battle.in_player_phase

    def test_player_deck_is_not_mutated(self):
        battle = _battle()
        battle.start_turn()
        assert len(battle.player.deck) == 8

    def test_seed_must_be_an_int(self):
        with pytest.raises(TypeError):
            Battle(_hero([_strike()]), _enemy(), seed="1")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            Battle(_hero([_strike()]), _enemy(), seed=True)  # type: ignore[arg-type]

    def test_rejects_negative_cards_per_turn(self):
        with pytest.raises(ValueError):
            _battle(cards_per_turn=-1)

    def test_rejects_negative_enemy_attack(self):
        with pytest.raises(ValueError):
            _battle(enemy_attack=-1)


class TestTurnStart:
    def test_start_turn_draws_cards_and_refills_energy(self):
        battle = _battle()
        battle.player.energy = 0
        battle.start_turn()
        assert len(battle.hand) == 5
        assert len(battle.draw_pile) == 3
        assert battle.player.energy == battle.player.max_energy
        assert battle.turn == 1
        assert battle.in_player_phase

    def test_drawing_stops_when_both_piles_are_empty(self):
        battle = Battle(_hero([_strike(), _guard()]), _enemy(), seed=1)
        battle.start_turn()
        assert len(battle.hand) == 2
        assert battle.draw_pile == []
        assert battle.discard_pile == []

    def test_cannot_start_turn_twice(self):
        battle = _battle()
        battle.start_turn()
        with pytest.raises(BattleError, match="already in progress"):
            battle.start_turn()

    def test_turn_counter_increments_each_turn(self):
        battle = _battle()
        for expected in (1, 2, 3):
            battle.start_turn()
            assert battle.turn == expected
            battle.end_turn()


class TestPlayingCards:
    def test_playing_a_card_spends_energy_and_moves_it_to_discard(self):
        battle = _battle()
        battle.start_turn()
        index = _card_index(battle, "Strike")
        hand_size = len(battle.hand)
        card = battle.play_card(index)
        assert card.name == "Strike"
        assert battle.player.energy == 2
        assert len(battle.hand) == hand_size - 1
        assert battle.discard_pile == [card]

    def test_damage_effect_reduces_enemy_hp(self):
        battle = _battle()
        battle.start_turn()
        battle.play_card(_card_index(battle, "Strike"))
        assert battle.enemy.hp == 30 - 6

    def test_enemy_hp_is_clamped_at_zero(self):
        # Strike deals 6 to a 5 HP enemy; hp must floor at 0, not go negative.
        battle = Battle(_hero([_strike()]), Unit("Slime", 5, 0), seed=1)
        battle.start_turn()
        battle.play_card(0)
        assert battle.enemy.hp == 0
        assert battle.is_over

    def test_shield_effect_grants_shield_status_to_player(self):
        battle = _battle()
        battle.start_turn()
        battle.play_card(_card_index(battle, "Guard"))
        shield = battle.player.get_status(StatusKind.SHIELD)
        assert shield is not None
        assert shield.stacks == 5

    def test_apply_status_effect_applies_status_to_enemy(self):
        battle = _battle()
        battle.start_turn()
        battle.play_card(_card_index(battle, "Venom Dart"))
        poison = battle.enemy.get_status(StatusKind.POISON)
        assert poison is not None
        assert (poison.stacks, poison.duration) == (2, 3)
        assert battle.enemy.hp == 30 - 3

    def test_card_costing_more_than_remaining_energy_is_rejected(self):
        expensive = Card(name="Big", cost=4, effects=[Effect(kind=EffectKind.DAMAGE, amount=9)])
        battle = Battle(_hero([expensive]), _enemy(), seed=1)
        battle.start_turn()
        with pytest.raises(BattleError, match="costs 4 energy"):
            battle.play_card(0)
        assert battle.player.energy == 3
        assert battle.hand == [expensive]
        assert battle.enemy.hp == 30

    def test_energy_limits_how_many_cards_can_be_played(self):
        battle = _battle(seed=7)
        battle.start_turn()
        played = 0
        while battle.hand and battle.player.energy >= 1:
            battle.play_card(0)
            played += 1
        assert played == 3
        assert battle.player.energy == 0
        with pytest.raises(BattleError):
            battle.play_card(0)

    def test_zero_cost_card_is_playable_with_no_energy(self):
        free = Card(name="Free", cost=0, effects=[Effect(kind=EffectKind.DAMAGE, amount=1)])
        battle = Battle(_hero([free]), _enemy(), seed=1)
        battle.start_turn()
        battle.player.energy = 0
        battle.play_card(0)
        assert battle.enemy.hp == 29

    @pytest.mark.parametrize("index", [-1, 5, "0", True])
    def test_invalid_hand_index_is_rejected(self, index):
        battle = _battle()
        battle.start_turn()
        with pytest.raises(BattleError):
            battle.play_card(index)

    def test_cannot_play_before_turn_starts(self):
        battle = _battle()
        with pytest.raises(BattleError, match="start_turn"):
            battle.play_card(0)

    def test_cannot_play_after_turn_ends(self):
        battle = _battle()
        battle.start_turn()
        battle.end_turn()
        with pytest.raises(BattleError):
            battle.play_card(0)


class TestDrawEffect:
    def test_draw_effect_draws_cards_into_hand(self):
        cantrip = Card(
            name="Cantrip",
            cost=0,
            effects=[Effect(kind=EffectKind.DRAW, amount=2)],
        )
        # Every card is a Cantrip, so the drawn card is known regardless of seed.
        battle = Battle(_hero([cantrip] * 8), _enemy(), seed=3, cards_per_turn=1)
        battle.start_turn()
        assert len(battle.hand) == 1
        battle.play_card(0)
        assert len(battle.hand) == 2
        assert len(battle.draw_pile) == 5


class TestEndTurn:
    def test_end_turn_discards_unplayed_hand(self):
        battle = _battle()
        battle.start_turn()
        battle.play_card(0)
        battle.end_turn()
        assert battle.hand == []
        assert len(battle.discard_pile) == 5
        assert not battle.in_player_phase

    def test_end_turn_requires_a_turn_in_progress(self):
        battle = _battle()
        with pytest.raises(BattleError):
            battle.end_turn()

    def test_enemy_placeholder_attack_damages_player(self):
        battle = _battle(enemy_attack=7)
        battle.start_turn()
        battle.end_turn()
        assert battle.player.hp == 40 - 7

    def test_turn_order_is_enemy_then_status_hook(self):
        events: list[str] = []

        class Recording(Battle):
            def _enemy_act(self):
                events.append("enemy")
                super()._enemy_act()

            def _resolve_end_of_turn_statuses(self):
                events.append("statuses")

        battle = Recording(_hero([_strike()]), _enemy(), seed=1)
        battle.start_turn()
        assert events == []
        battle.end_turn()
        assert events == ["enemy", "statuses"]

    def test_status_hook_is_skipped_once_the_battle_is_over(self):
        events: list[str] = []

        class Recording(Battle):
            def _resolve_end_of_turn_statuses(self):
                events.append("statuses")

        battle = Recording(_hero([_strike()]), _enemy(), seed=1, enemy_attack=40)
        battle.start_turn()
        battle.end_turn()
        assert battle.is_over
        assert events == []


class TestReshuffle:
    def test_discard_pile_is_reshuffled_into_draw_pile_when_empty(self):
        deck = [_strike(), _guard(), _venom()]
        battle = Battle(_hero(deck), _enemy(), seed=5, cards_per_turn=2)

        battle.start_turn()
        battle.play_card(0)
        battle.play_card(0)
        battle.end_turn()
        # One card left in the draw pile, two in the discard pile.
        assert len(battle.draw_pile) == 1
        assert len(battle.discard_pile) == 2

        battle.start_turn()
        assert len(battle.hand) == 2
        assert len(battle.draw_pile) + len(battle.hand) + len(battle.discard_pile) == 3
        assert battle.discard_pile == []

    def test_no_cards_are_lost_or_duplicated_across_many_turns(self):
        deck = [_strike()] * 4 + [_guard()] * 4 + [_venom()] * 2
        battle = Battle(
            _hero(deck), Unit("Dummy", 10_000, 0), seed=11, cards_per_turn=3, enemy_attack=0
        )
        for _ in range(20):
            battle.start_turn()
            while battle.hand and battle.player.energy >= 1:
                battle.play_card(0)
            total = len(battle.draw_pile) + len(battle.hand) + len(battle.discard_pile)
            assert total == len(deck)
            battle.end_turn()


class TestDeterminism:
    @staticmethod
    def _play_script(seed: int) -> tuple:
        """Play a fixed sequence of turns and return a snapshot of the battle."""
        deck = [_strike()] * 4 + [_guard()] * 3 + [_venom()] * 3
        battle = Battle(_hero(deck), Unit("Dummy", 1000, 0), seed=seed, cards_per_turn=4)
        trace = []
        for _ in range(8):
            battle.start_turn()
            trace.append(tuple(c.name for c in battle.hand))
            while battle.hand and battle.player.energy >= 1:
                battle.play_card(0)
            trace.append(tuple(c.name for c in battle.draw_pile))
            battle.end_turn()
        return tuple(trace), battle.player.hp, battle.enemy.hp

    def test_same_seed_gives_identical_battle(self):
        assert self._play_script(42) == self._play_script(42)

    def test_different_seed_can_give_different_draw_order(self):
        assert self._play_script(1) != self._play_script(2)

    def test_initial_shuffle_uses_only_the_seeded_rng(self):
        first = _battle(seed=99)
        second = _battle(seed=99)
        assert [c.name for c in first.draw_pile] == [c.name for c in second.draw_pile]


class TestBattleEnd:
    def test_battle_is_over_when_enemy_dies(self):
        battle = Battle(_hero([_strike()] * 2), Unit("Slime", 6, 0), seed=1)
        battle.start_turn()
        battle.play_card(0)
        assert battle.is_over
        assert battle.winner is battle.player

    def test_winner_is_enemy_when_player_dies_to_enemy_attack(self):
        battle = _battle(enemy_attack=100)
        battle.start_turn()
        battle.end_turn()
        assert battle.is_over
        assert battle.winner is battle.enemy
        assert battle.player.hp == 0

    def test_no_winner_while_both_alive(self):
        battle = _battle()
        assert not battle.is_over
        assert battle.winner is None

    def test_cannot_start_turn_after_battle_is_over(self):
        battle = _battle(enemy_attack=100)
        battle.start_turn()
        battle.end_turn()
        with pytest.raises(BattleError, match="over"):
            battle.start_turn()


class TestDataOnlyCards:
    def test_new_card_defined_only_in_data_plays_without_engine_changes(self):
        data = {
            "cards": [
                {
                    "name": "Heavy Blow",
                    "cost": 2,
                    "effects": [
                        {"type": "damage", "amount": 10},
                        {"type": "apply_status", "status": "weak", "stacks": 1, "duration": 2},
                    ],
                }
            ]
        }
        heavy = parse_cards(data)["Heavy Blow"]
        battle = Battle(_hero([heavy]), _enemy(), seed=1)
        battle.start_turn()
        battle.play_card(0)
        assert battle.enemy.hp == 20
        assert battle.enemy.get_status(StatusKind.WEAK) is not None
        assert battle.player.energy == 1
