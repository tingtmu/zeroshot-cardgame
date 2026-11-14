import pytest

from cardgame.models import Card, Effect, EffectKind, Status, StatusKind, Unit


class TestEffect:
    def test_damage_effect(self):
        effect = Effect(kind=EffectKind.DAMAGE, amount=6)
        assert effect.kind is EffectKind.DAMAGE
        assert effect.amount == 6

    def test_apply_status_effect(self):
        effect = Effect(
            kind=EffectKind.APPLY_STATUS,
            status=StatusKind.POISON,
            stacks=2,
            duration=3,
        )
        assert effect.status is StatusKind.POISON
        assert effect.stacks == 2
        assert effect.duration == 3

    @pytest.mark.parametrize("kind", [EffectKind.DAMAGE, EffectKind.SHIELD, EffectKind.DRAW])
    def test_amount_effects_require_positive_amount(self, kind):
        with pytest.raises(ValueError):
            Effect(kind=kind, amount=0)

    def test_apply_status_requires_status(self):
        with pytest.raises(ValueError):
            Effect(kind=EffectKind.APPLY_STATUS, stacks=1, duration=1)

    def test_apply_status_requires_positive_stacks_and_duration(self):
        with pytest.raises(ValueError):
            Effect(kind=EffectKind.APPLY_STATUS, status=StatusKind.WEAK, stacks=0, duration=1)
        with pytest.raises(ValueError):
            Effect(kind=EffectKind.APPLY_STATUS, status=StatusKind.WEAK, stacks=1, duration=0)

    def test_damage_rejects_status_fields(self):
        with pytest.raises(ValueError):
            Effect(kind=EffectKind.DAMAGE, amount=3, status=StatusKind.POISON)

    def test_rejects_bool_amount(self):
        with pytest.raises(TypeError):
            Effect(kind=EffectKind.DAMAGE, amount=True)

    def test_is_immutable(self):
        effect = Effect(kind=EffectKind.DRAW, amount=1)
        with pytest.raises(AttributeError):
            effect.amount = 2  # type: ignore[misc]


class TestCard:
    def test_card_holds_name_cost_and_effects(self):
        effects = [Effect(kind=EffectKind.SHIELD, amount=5)]
        card = Card(name="Guard", cost=1, effects=effects)
        assert card.name == "Guard"
        assert card.cost == 1
        assert card.effects == (effects[0],)

    def test_effects_default_to_empty_tuple(self):
        assert Card(name="Nothing", cost=0).effects == ()

    def test_effects_are_stored_as_tuple(self):
        card = Card(name="X", cost=0, effects=[Effect(kind=EffectKind.DRAW, amount=1)])
        assert isinstance(card.effects, tuple)

    def test_rejects_empty_name(self):
        with pytest.raises(ValueError):
            Card(name="", cost=0)

    def test_rejects_negative_cost(self):
        with pytest.raises(ValueError):
            Card(name="X", cost=-1)

    def test_rejects_non_effect_entries(self):
        with pytest.raises(TypeError):
            Card(name="X", cost=0, effects=["damage"])  # type: ignore[list-item]


class TestStatus:
    def test_defaults_to_one_stack_one_turn(self):
        status = Status(kind=StatusKind.POISON)
        assert status.stacks == 1
        assert status.duration == 1

    def test_merge_adds_stacks_and_refreshes_duration(self):
        status = Status(kind=StatusKind.POISON, stacks=2, duration=3)
        status.merge(stacks=1, duration=5)
        assert status.stacks == 3
        assert status.duration == 5

    def test_merge_keeps_longer_remaining_duration(self):
        status = Status(kind=StatusKind.WEAK, stacks=1, duration=4)
        status.merge(stacks=1, duration=2)
        assert status.stacks == 2
        assert status.duration == 4

    def test_rejects_zero_stacks(self):
        with pytest.raises(ValueError):
            Status(kind=StatusKind.SHIELD, stacks=0)

    def test_rejects_zero_duration(self):
        with pytest.raises(ValueError):
            Status(kind=StatusKind.SHIELD, duration=0)


class TestUnit:
    def test_new_unit_starts_full_hp_and_energy(self):
        unit = Unit(name="Hero", max_hp=40, max_energy=3)
        assert unit.hp == 40
        assert unit.energy == 3
        assert unit.deck == []
        assert unit.statuses == {}
        assert unit.is_alive

    def test_explicit_hp_and_energy(self):
        unit = Unit(name="Slime", max_hp=20, max_energy=2, hp=7, energy=0)
        assert unit.hp == 7
        assert unit.energy == 0

    def test_hp_cannot_exceed_max(self):
        with pytest.raises(ValueError):
            Unit(name="Hero", max_hp=10, max_energy=3, hp=11)

    def test_energy_cannot_exceed_max(self):
        with pytest.raises(ValueError):
            Unit(name="Hero", max_hp=10, max_energy=3, energy=4)

    def test_is_alive_false_at_zero_hp(self):
        unit = Unit(name="Hero", max_hp=10, max_energy=3, hp=0)
        assert not unit.is_alive

    def test_deck_holds_cards(self):
        card = Card(name="Strike", cost=1)
        unit = Unit(name="Hero", max_hp=10, max_energy=3, deck=[card])
        assert unit.deck == [card]

    def test_deck_rejects_non_cards(self):
        with pytest.raises(TypeError):
            Unit(name="Hero", max_hp=10, max_energy=3, deck=["Strike"])  # type: ignore[list-item]

    def test_apply_status_creates_new_status(self):
        unit = Unit(name="Hero", max_hp=10, max_energy=3)
        status = unit.apply_status(StatusKind.POISON, stacks=2, duration=3)
        assert unit.get_status(StatusKind.POISON) is status
        assert status.stacks == 2
        assert status.duration == 3

    def test_apply_status_merges_existing_status(self):
        unit = Unit(name="Hero", max_hp=10, max_energy=3)
        unit.apply_status(StatusKind.POISON, stacks=2, duration=3)
        status = unit.apply_status(StatusKind.POISON, stacks=1, duration=4)
        assert status.stacks == 3
        assert status.duration == 4
        assert len(unit.statuses) == 1

    def test_get_status_returns_none_when_absent(self):
        unit = Unit(name="Hero", max_hp=10, max_energy=3)
        assert unit.get_status(StatusKind.WEAK) is None
