import pytest

from cardgame.battle import Battle
from cardgame.loader import CardDataError, parse_cards
from cardgame.models import Card, Effect, EffectKind, StatusKind, Target, Unit


class TestDefaultTargets:
    def test_defaults_match_the_original_card_semantics(self):
        assert Effect(kind=EffectKind.DAMAGE, amount=1).effective_target is Target.OPPONENT
        assert Effect(kind=EffectKind.SHIELD, amount=1).effective_target is Target.SELF
        assert Effect(kind=EffectKind.DRAW, amount=1).effective_target is Target.SELF
        apply = Effect(kind=EffectKind.APPLY_STATUS, status=StatusKind.WEAK, stacks=1, duration=1)
        assert apply.effective_target is Target.OPPONENT

    def test_explicit_target_overrides_default(self):
        shield_on_opponent = Effect(kind=EffectKind.SHIELD, amount=2, target=Target.OPPONENT)
        assert shield_on_opponent.effective_target is Target.OPPONENT
        damage_self = Effect(kind=EffectKind.DAMAGE, amount=2, target=Target.SELF)
        assert damage_self.effective_target is Target.SELF

    def test_target_must_be_a_target(self):
        with pytest.raises(TypeError):
            Effect(kind=EffectKind.DAMAGE, amount=1, target="self")  # type: ignore[arg-type]

    def test_draw_must_not_set_target(self):
        with pytest.raises(ValueError, match="draw"):
            Effect(kind=EffectKind.DRAW, amount=1, target=Target.SELF)


class TestLoaderTarget:
    def _card(self, effect: dict) -> dict:
        return {"cards": [{"name": "X", "cost": 0, "effects": [effect]}]}

    def test_card_apply_status_accepts_target(self):
        cards = parse_cards(
            self._card(
                {"type": "apply_status", "status": "shield", "stacks": 2,
                 "duration": 2, "target": "self"}
            )
        )
        assert cards["X"].effects[0].target is Target.SELF

    def test_card_damage_accepts_target(self):
        cards = parse_cards(self._card({"type": "damage", "amount": 2, "target": "opponent"}))
        assert cards["X"].effects[0].target is Target.OPPONENT

    def test_unknown_target_is_rejected(self):
        with pytest.raises(CardDataError, match="unknown target"):
            parse_cards(self._card({"type": "damage", "amount": 2, "target": "ally"}))

    def test_draw_with_target_is_rejected(self):
        with pytest.raises(CardDataError):
            parse_cards(self._card({"type": "draw", "amount": 1, "target": "self"}))


class TestCardSelfTargetInBattle:
    def test_card_apply_status_self_shield_lands_on_player(self):
        card = Card(
            name="Brace",
            cost=0,
            effects=(
                Effect(kind=EffectKind.APPLY_STATUS, status=StatusKind.SHIELD,
                       stacks=3, duration=2, target=Target.SELF),
            ),
        )
        hero = Unit("Hero", 40, 3, deck=[card])
        battle = Battle(hero, Unit("Dummy", 10, 0), seed=1, enemy_attack=0)
        battle.start_turn()
        battle.play_card(0)
        assert hero.get_status(StatusKind.SHIELD).stacks == 3
        assert battle.enemy.get_status(StatusKind.SHIELD) is None

    def test_card_damage_targeting_self_hurts_player(self):
        card = Card(
            name="Backfire",
            cost=0,
            effects=(Effect(kind=EffectKind.DAMAGE, amount=4, target=Target.SELF),),
        )
        hero = Unit("Hero", 40, 3, deck=[card])
        enemy = Unit("Dummy", 10, 0)
        battle = Battle(hero, enemy, seed=1, enemy_attack=0)
        battle.start_turn()
        battle.play_card(0)
        assert hero.hp == 36
        assert enemy.hp == 10
