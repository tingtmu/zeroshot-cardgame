import pytest

from cardgame.battle import Battle
from cardgame.loader import load_default_cards
from cardgame.models import Card, Effect, EffectKind, StatusKind, Unit
from cardgame.statuses import StatusRules, load_default_status_rules


def _strike() -> Card:
    return load_default_cards()["Strike"]


def _guard() -> Card:
    return load_default_cards()["Guard"]


def _venom() -> Card:
    return load_default_cards()["Venom Dart"]


def _hero(deck, max_energy=3, max_hp=40) -> Unit:
    return Unit(name="Hero", max_hp=max_hp, max_energy=max_energy, deck=list(deck))


def _enemy(max_hp=100) -> Unit:
    return Unit(name="Dummy", max_hp=max_hp, max_energy=0)


def _battle(deck, enemy=None, seed=1, **kwargs) -> Battle:
    """A battle where the enemy does no attack unless a test asks for one."""
    kwargs.setdefault("enemy_attack", 0)
    return Battle(_hero(deck), enemy or _enemy(), seed=seed, **kwargs)


def _card(name, *effects, cost=0) -> Card:
    return Card(name=name, cost=cost, effects=list(effects))


def _apply(status, stacks, duration) -> Effect:
    return Effect(kind=EffectKind.APPLY_STATUS, status=status, stacks=stacks, duration=duration)


def _index_of(battle: Battle, name: str) -> int:
    for index, card in enumerate(battle.hand):
        if card.name == name:
            return index
    raise AssertionError(f"{name!r} not in hand {[c.name for c in battle.hand]}")


def _end_turns(battle: Battle, count: int) -> None:
    for _ in range(count):
        battle.start_turn()
        battle.end_turn()


class TestRulesWiring:
    def test_default_rules_are_loaded_when_none_given(self):
        battle = _battle([_strike()])
        assert battle.status_rules == load_default_status_rules()

    def test_missing_rules_are_rejected(self):
        rules = {StatusKind.POISON: StatusRules(kind=StatusKind.POISON)}
        with pytest.raises(ValueError, match="missing entries"):
            _battle([_strike()], status_rules=rules)


class TestPoison:
    def test_poison_from_venom_dart_ticks_at_end_of_turn(self):
        battle = _battle([_venom()])
        battle.start_turn()
        battle.play_card(0)
        assert battle.enemy.hp == 97  # card damage only; no tick yet
        battle.end_turn()
        # 2 stacks -> 2 damage, then one stack is lost; 2 turns of duration left.
        assert battle.enemy.hp == 95
        poison = battle.enemy.get_status(StatusKind.POISON)
        assert (poison.stacks, poison.duration) == (1, 2)

    def test_poison_stacks_decrease_each_turn_and_status_is_removed_at_zero(self):
        battle = _battle([_venom()])
        battle.start_turn()
        battle.play_card(0)
        battle.end_turn()  # deals 2, stacks 2 -> 1
        _end_turns(battle, 1)  # deals 1, stacks 1 -> 0
        assert battle.enemy.hp == 100 - 3 - 2 - 1
        assert battle.enemy.get_status(StatusKind.POISON) is None

    def test_poison_expires_when_duration_runs_out_before_stacks(self):
        battle = _battle([_venom()])
        battle.enemy.apply_status(StatusKind.POISON, stacks=10, duration=2)
        _end_turns(battle, 1)  # deals 10, stacks 9, duration 1
        poison = battle.enemy.get_status(StatusKind.POISON)
        assert (poison.stacks, poison.duration) == (9, 1)
        _end_turns(battle, 1)  # deals 9, stacks 8, duration 0 -> removed
        assert battle.enemy.hp == 100 - 10 - 9
        assert battle.enemy.get_status(StatusKind.POISON) is None

    def test_poison_damage_is_absorbed_by_shield_first(self):
        battle = _battle([_strike()])
        battle.player.apply_status(StatusKind.POISON, stacks=4, duration=2)
        battle.player.apply_status(StatusKind.SHIELD, stacks=3, duration=1)
        _end_turns(battle, 1)
        # Poison deals 4: 3 absorbed by the shield, 1 reaches HP.
        assert battle.player.hp == 39
        assert battle.player.get_status(StatusKind.SHIELD) is None

    def test_poison_can_kill_and_ends_the_battle(self):
        battle = _battle([_venom()], enemy=_enemy(max_hp=2))
        battle.enemy.apply_status(StatusKind.POISON, stacks=2, duration=3)
        _end_turns(battle, 1)
        assert battle.enemy.hp == 0
        assert battle.is_over
        assert battle.winner is battle.player

    def test_player_poison_ticks_at_end_of_turn(self):
        battle = _battle([_strike()])
        battle.player.apply_status(StatusKind.POISON, stacks=3, duration=1)
        _end_turns(battle, 1)
        assert battle.player.hp == 37
        assert battle.player.get_status(StatusKind.POISON) is None

    def test_venom_dart_played_twice_stacks_poison_and_damage(self):
        battle = _battle([_venom()] * 2)
        battle.start_turn()
        battle.play_card(0)
        battle.play_card(0)
        poison = battle.enemy.get_status(StatusKind.POISON)
        assert (poison.stacks, poison.duration) == (4, 3)
        assert battle.enemy.hp == 100 - 6

    def test_reapplying_poison_refreshes_duration_to_the_longer_one(self):
        short = _card("Short Sting", _apply(StatusKind.POISON, 1, 1))
        battle = _battle([short, short])
        battle.start_turn()
        battle.play_card(0)
        battle.play_card(0)
        poison = battle.enemy.get_status(StatusKind.POISON)
        assert (poison.stacks, poison.duration) == (2, 1)


class TestWeak:
    def test_weak_on_player_reduces_damage_dealt_by_cards(self):
        battle = _battle([_strike()])
        battle.player.apply_status(StatusKind.WEAK, stacks=1, duration=2)
        battle.start_turn()
        battle.play_card(0)
        # 6 damage with 25% reduction -> 4.5, rounded down to 4.
        assert battle.enemy.hp == 100 - 4

    def test_weak_on_enemy_reduces_enemy_attack(self):
        battle = _battle([_strike()], enemy_attack=8)
        battle.enemy.apply_status(StatusKind.WEAK, stacks=2, duration=2)
        _end_turns(battle, 1)
        # Two stacks -> 50% reduction of the 8 point attack.
        assert battle.player.hp == 40 - 4

    def test_weak_reduction_is_capped_at_full_reduction(self):
        battle = _battle([_strike()], enemy_attack=8)
        battle.enemy.apply_status(StatusKind.WEAK, stacks=10, duration=2)
        _end_turns(battle, 1)
        assert battle.player.hp == 40

    def test_weak_does_not_reduce_poison_damage(self):
        battle = _battle([_strike()])
        battle.enemy.apply_status(StatusKind.POISON, stacks=4, duration=2)
        battle.enemy.apply_status(StatusKind.WEAK, stacks=2, duration=2)
        _end_turns(battle, 1)
        assert battle.enemy.hp == 100 - 4

    def test_weak_stacks_do_not_decay_each_turn(self):
        battle = _battle([_strike()])
        battle.player.apply_status(StatusKind.WEAK, stacks=2, duration=3)
        _end_turns(battle, 1)
        weak = battle.player.get_status(StatusKind.WEAK)
        assert (weak.stacks, weak.duration) == (2, 2)

    def test_weak_expires_after_its_duration(self):
        battle = _battle([_strike()])
        battle.player.apply_status(StatusKind.WEAK, stacks=1, duration=2)
        _end_turns(battle, 2)
        assert battle.player.get_status(StatusKind.WEAK) is None
        battle.start_turn()
        battle.play_card(0)
        assert battle.enemy.hp == 100 - 6

    def test_weak_applied_by_cards_stacks_with_existing_weak(self):
        hex_card = _card("Hex", _apply(StatusKind.WEAK, 1, 2))
        battle = _battle([hex_card] * 2)
        battle.start_turn()
        battle.play_card(0)
        battle.play_card(0)
        weak = battle.enemy.get_status(StatusKind.WEAK)
        assert (weak.stacks, weak.duration) == (2, 2)


class TestShield:
    def test_shield_absorbs_enemy_attack_before_hp(self):
        battle = _battle([_guard()], enemy_attack=4)
        battle.start_turn()
        battle.play_card(0)
        battle.end_turn()
        assert battle.player.hp == 40
        assert battle.player.get_status(StatusKind.SHIELD) is None  # expired this turn

    def test_shield_partially_absorbs_and_remaining_damage_hits_hp(self):
        battle = _battle([_guard()], enemy_attack=7)
        battle.start_turn()
        battle.play_card(0)
        battle.end_turn()
        assert battle.player.hp == 40 - (7 - 5)

    def test_shield_stacks_from_multiple_guards_in_one_turn(self):
        battle = _battle([_guard()] * 2, enemy_attack=9)
        battle.start_turn()
        battle.play_card(0)
        battle.play_card(0)
        shield = battle.player.get_status(StatusKind.SHIELD)
        assert (shield.stacks, shield.duration) == (10, 1)
        battle.end_turn()
        assert battle.player.hp == 40

    def test_shield_absorbs_each_units_damage_independently(self):
        battle = _battle([_strike()], enemy_attack=3)
        battle.player.apply_status(StatusKind.SHIELD, stacks=5, duration=1)
        battle.enemy.apply_status(StatusKind.SHIELD, stacks=4, duration=1)
        battle.start_turn()
        battle.play_card(0)  # 6 damage: 4 absorbed by the enemy's shield, 2 hits HP
        assert battle.enemy.hp == 100 - 2
        assert battle.enemy.get_status(StatusKind.SHIELD) is None
        battle.end_turn()  # enemy hits for 3, all absorbed by the player's shield
        assert battle.player.hp == 40
        assert battle.player.get_status(StatusKind.SHIELD) is None

    def test_shield_with_longer_duration_survives_turn_end(self):
        battle = _battle([_strike()], enemy_attack=2)
        battle.player.apply_status(StatusKind.SHIELD, stacks=6, duration=2)
        battle.start_turn()
        battle.end_turn()  # absorbs 2, leaves 4, duration 2 -> 1
        shield = battle.player.get_status(StatusKind.SHIELD)
        assert (shield.stacks, shield.duration) == (4, 1)
        assert battle.player.hp == 40
        battle.start_turn()
        battle.end_turn()  # absorbs 2, leaves 2, duration 1 -> 0 -> expires
        assert battle.player.get_status(StatusKind.SHIELD) is None
        assert battle.player.hp == 40

    def test_shield_applied_to_enemy_by_card_absorbs_player_damage(self):
        ward = _card("Ward", _apply(StatusKind.SHIELD, 10, 2), cost=0)
        battle = _battle([ward, _strike()])
        battle.start_turn()
        battle.play_card(_index_of(battle, "Ward"))
        battle.play_card(_index_of(battle, "Strike"))
        assert battle.enemy.hp == 100
        shield = battle.enemy.get_status(StatusKind.SHIELD)
        assert (shield.stacks, shield.duration) == (4, 2)

    def test_leftover_shield_is_lost_when_it_expires(self):
        battle = _battle([_guard()], enemy_attack=0)
        battle.start_turn()
        battle.play_card(0)
        battle.end_turn()
        assert battle.player.statuses == {}
        assert battle.player.hp == 40


class TestStatusResolutionTiming:
    def test_enemy_attack_happens_before_status_resolution(self):
        battle = _battle([_guard()], enemy_attack=3)
        battle.player.apply_status(StatusKind.POISON, stacks=2, duration=2)
        battle.start_turn()
        battle.play_card(0)  # shield 5
        battle.end_turn()
        # Attack 3 leaves shield 2. Poison then deals 2, absorbed by the shield.
        assert battle.player.hp == 40
        assert battle.player.get_status(StatusKind.SHIELD) is None
        assert battle.player.get_status(StatusKind.POISON).stacks == 1

    def test_player_statuses_resolve_before_enemy_statuses(self):
        order: list[str] = []

        class Recording(Battle):
            def _tick_status(self, unit, kind, status):
                order.append(f"{unit.name}:{kind.value}")
                super()._tick_status(unit, kind, status)

        battle = Recording(_hero([_strike()]), Unit("Dummy", 100, 0), seed=1, enemy_attack=0)
        battle.player.apply_status(StatusKind.WEAK, stacks=1, duration=2)
        battle.enemy.apply_status(StatusKind.POISON, stacks=1, duration=2)
        _end_turns(battle, 1)
        assert order == ["Hero:weak", "Dummy:poison"]

    def test_statuses_do_not_resolve_once_the_player_dies_to_the_enemy(self):
        battle = _battle([_strike()], enemy_attack=40)
        battle.enemy.apply_status(StatusKind.POISON, stacks=5, duration=2)
        _end_turns(battle, 1)
        assert battle.is_over
        assert battle.enemy.hp == 100
        assert battle.enemy.get_status(StatusKind.POISON).stacks == 5


class TestDataDrivenRules:
    def test_poison_without_tick_damage_comes_from_rules(self):
        rules = dict(load_default_status_rules())
        rules[StatusKind.POISON] = StatusRules(kind=StatusKind.POISON)
        battle = _battle([_venom()], status_rules=rules)
        battle.start_turn()
        battle.play_card(0)
        battle.end_turn()
        assert battle.enemy.hp == 97
        poison = battle.enemy.get_status(StatusKind.POISON)
        assert (poison.stacks, poison.duration) == (2, 2)

    def test_weak_reduction_comes_from_rules(self):
        rules = dict(load_default_status_rules())
        rules[StatusKind.WEAK] = StatusRules(
            kind=StatusKind.WEAK, outgoing_damage_reduction_per_stack=50
        )
        battle = _battle([_strike()], status_rules=rules)
        battle.player.apply_status(StatusKind.WEAK, stacks=1, duration=2)
        battle.start_turn()
        battle.play_card(0)
        assert battle.enemy.hp == 100 - 3

    def test_shield_absorption_can_be_disabled_by_rules(self):
        rules = dict(load_default_status_rules())
        rules[StatusKind.SHIELD] = StatusRules(kind=StatusKind.SHIELD)
        battle = _battle([_guard()], enemy_attack=4, status_rules=rules)
        battle.start_turn()
        battle.play_card(0)
        battle.end_turn()
        assert battle.player.hp == 36

    def test_poison_without_stack_loss_keeps_ticking_until_duration_ends(self):
        rules = dict(load_default_status_rules())
        rules[StatusKind.POISON] = StatusRules(
            kind=StatusKind.POISON, turn_end_damage_per_stack=True, stacks_lost_per_turn=0
        )
        battle = _battle([_strike()], status_rules=rules)
        battle.enemy.apply_status(StatusKind.POISON, stacks=3, duration=2)
        _end_turns(battle, 2)
        assert battle.enemy.hp == 100 - 3 - 3
        assert battle.enemy.get_status(StatusKind.POISON) is None


class TestDeterminismWithStatuses:
    @staticmethod
    def _snapshot(seed: int) -> tuple:
        deck = [_strike()] * 3 + [_guard()] * 2 + [_venom()] * 3
        battle = Battle(
            _hero(deck), Unit("Dummy", 200, 0), seed=seed, cards_per_turn=4, enemy_attack=5
        )
        trace = []
        for _ in range(6):
            battle.start_turn()
            while battle.hand and battle.player.energy >= 1:
                battle.play_card(0)
            battle.end_turn()
            trace.append(
                (
                    battle.player.hp,
                    battle.enemy.hp,
                    _status_summary(battle.player),
                    _status_summary(battle.enemy),
                )
            )
        return tuple(trace)

    def test_same_seed_gives_identical_status_outcomes(self):
        assert self._snapshot(21) == self._snapshot(21)


def _status_summary(unit: Unit) -> tuple:
    return tuple(
        (kind.value, status.stacks, status.duration)
        for kind, status in sorted(unit.statuses.items(), key=lambda kv: kv[0].value)
    )
