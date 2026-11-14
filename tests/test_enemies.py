import random

import pytest

from cardgame.enemies import (
    DEFAULT_ENEMIES_PATH,
    EnemyAI,
    EnemyDataError,
    EnemyDefinition,
    Intent,
    IntentMode,
    IntentPattern,
    load_default_enemies,
    load_enemies,
    parse_enemies,
)
from cardgame.models import Effect, EffectKind, StatusKind, Target


def _dmg(amount: int) -> dict:
    return {"type": "damage", "amount": amount}


def _enemy_json(name="Dummy", mode="cycle", intents=None, **extra) -> dict:
    if intents is None:
        intents = [{"name": "Hit", "effects": [_dmg(1)]}]
    data = {"name": name, "max_hp": 10, "pattern": {"mode": mode, "intents": intents}}
    data.update(extra)
    return {"enemies": [data]}


def _pattern(mode=IntentMode.CYCLE, weights=(1, 1)) -> IntentPattern:
    intents = tuple(
        Intent(name=f"I{i}", effects=(Effect(kind=EffectKind.DAMAGE, amount=i + 1),), weight=w)
        for i, w in enumerate(weights)
    )
    return IntentPattern(mode=mode, intents=intents)


class TestDefaultEnemies:
    def test_bundled_file_exists_and_loads_two_enemies(self):
        assert DEFAULT_ENEMIES_PATH.exists()
        enemies = load_default_enemies()
        assert set(enemies) == {"Slime", "Cultist"}

    def test_slime_is_a_cycle_of_attack_then_shield(self):
        slime = load_default_enemies()["Slime"]
        assert slime.pattern.mode is IntentMode.CYCLE
        assert [i.name for i in slime.pattern.intents] == ["Tackle", "Harden"]
        assert slime.pattern.intents[0].effects == (Effect(kind=EffectKind.DAMAGE, amount=4),)
        harden = slime.pattern.intents[1].effects[0]
        assert harden.kind is EffectKind.APPLY_STATUS
        assert harden.status is StatusKind.SHIELD
        assert harden.effective_target is Target.SELF

    def test_cultist_is_weighted_and_can_poison(self):
        cultist = load_default_enemies()["Cultist"]
        assert cultist.pattern.mode is IntentMode.WEIGHTED
        assert sum(i.weight for i in cultist.pattern.intents) == 4
        venom = next(i for i in cultist.pattern.intents if i.name == "Venom Spit")
        assert venom.effects[1].status is StatusKind.POISON
        assert venom.effects[1].effective_target is Target.OPPONENT

    def test_create_unit_gives_fresh_unit_each_time(self):
        slime = load_default_enemies()["Slime"]
        a, b = slime.create_unit(), slime.create_unit()
        assert a is not b
        assert (a.name, a.max_hp, a.max_energy, a.hp) == ("Slime", 30, 0, 30)
        a.hp = 1
        assert b.hp == 30


class TestParsing:
    def test_parses_minimal_cycle_enemy_with_default_energy_and_weight(self):
        enemy = parse_enemies(_enemy_json())["Dummy"]
        assert enemy.max_energy == 0
        assert enemy.pattern.intents[0].weight == 1
        assert enemy.pattern.intents[0].effects == (Effect(kind=EffectKind.DAMAGE, amount=1),)

    def test_intent_without_effects_is_allowed(self):
        data = _enemy_json(intents=[{"name": "Wait"}])
        assert parse_enemies(data)["Dummy"].pattern.intents[0].effects == ()

    def test_parses_explicit_target(self):
        data = _enemy_json(
            intents=[
                {
                    "name": "Guard",
                    "effects": [
                        {"type": "apply_status", "status": "shield", "stacks": 2,
                         "duration": 2, "target": "self"}
                    ],
                }
            ]
        )
        effect = parse_enemies(data)["Dummy"].pattern.intents[0].effects[0]
        assert effect.target is Target.SELF

    def test_rejects_unknown_top_level_and_enemy_keys(self):
        with pytest.raises(EnemyDataError, match="top level"):
            parse_enemies({"enemies": [], "extra": 1})
        with pytest.raises(EnemyDataError, match="unknown keys"):
            parse_enemies(_enemy_json(speed=3))

    def test_rejects_missing_top_level_list(self):
        with pytest.raises(EnemyDataError):
            parse_enemies([])
        with pytest.raises(EnemyDataError):
            parse_enemies({"enemies": {}})

    def test_rejects_non_object_enemy(self):
        with pytest.raises(EnemyDataError, match="enemy must be an object"):
            parse_enemies({"enemies": ["Slime"]})

    def test_rejects_bad_name_and_missing_fields(self):
        with pytest.raises(EnemyDataError, match="'name'"):
            parse_enemies({"enemies": [{"name": "", "max_hp": 1, "pattern": {}}]})
        data = _enemy_json()
        del data["enemies"][0]["max_hp"]
        with pytest.raises(EnemyDataError, match="missing 'max_hp'"):
            parse_enemies(data)
        data = _enemy_json()
        del data["enemies"][0]["pattern"]
        with pytest.raises(EnemyDataError, match="missing 'pattern'"):
            parse_enemies(data)

    def test_rejects_invalid_max_hp(self):
        data = _enemy_json()
        data["enemies"][0]["max_hp"] = 0
        with pytest.raises(EnemyDataError, match="max_hp"):
            parse_enemies(data)
        data["enemies"][0]["max_hp"] = "10"
        with pytest.raises(EnemyDataError, match="max_hp"):
            parse_enemies(data)

    def test_rejects_unknown_mode(self):
        with pytest.raises(EnemyDataError, match="unknown pattern mode"):
            parse_enemies(_enemy_json(mode="random"))

    def test_rejects_pattern_with_unknown_keys_or_no_intents(self):
        data = _enemy_json()
        data["enemies"][0]["pattern"]["seed"] = 1
        with pytest.raises(EnemyDataError, match="unknown keys"):
            parse_enemies(data)
        with pytest.raises(EnemyDataError, match="non-empty list"):
            parse_enemies(_enemy_json(intents=[]))

    def test_rejects_weight_in_cycle_mode(self):
        intents = [{"name": "Hit", "weight": 2, "effects": []}]
        with pytest.raises(EnemyDataError, match="only allowed in weighted"):
            parse_enemies(_enemy_json(mode="cycle", intents=intents))

    def test_rejects_non_positive_weight(self):
        intents = [{"name": "Hit", "weight": 0, "effects": []}]
        with pytest.raises(EnemyDataError, match="weight"):
            parse_enemies(_enemy_json(mode="weighted", intents=intents))

    def test_rejects_draw_effect_in_intent(self):
        intents = [{"name": "Think", "effects": [{"type": "draw", "amount": 1}]}]
        with pytest.raises(EnemyDataError, match="draw"):
            parse_enemies(_enemy_json(intents=intents))

    def test_rejects_unknown_effect_type_and_bad_target(self):
        intents = [{"name": "Bad", "effects": [{"type": "heal", "amount": 1}]}]
        with pytest.raises(EnemyDataError, match="unknown effect type"):
            parse_enemies(_enemy_json(intents=intents))
        intents = [{"name": "Bad", "effects": [{"type": "damage", "amount": 1, "target": "ally"}]}]
        with pytest.raises(EnemyDataError, match="unknown target"):
            parse_enemies(_enemy_json(intents=intents))

    def test_rejects_duplicate_enemy_names(self):
        data = {"enemies": [_enemy_json()["enemies"][0], _enemy_json()["enemies"][0]]}
        with pytest.raises(EnemyDataError, match="duplicate"):
            parse_enemies(data)

    def test_rejects_invalid_json_file(self, tmp_path):
        path = tmp_path / "enemies.json"
        path.write_text("{nope", encoding="utf-8")
        with pytest.raises(EnemyDataError, match="invalid JSON"):
            load_enemies(path)

    def test_loads_from_file(self, tmp_path):
        import json

        path = tmp_path / "enemies.json"
        path.write_text(json.dumps(_enemy_json()), encoding="utf-8")
        assert set(load_enemies(path)) == {"Dummy"}


class TestModelValidation:
    def test_intent_needs_name_and_positive_weight(self):
        with pytest.raises(ValueError):
            Intent(name="")
        with pytest.raises(ValueError):
            Intent(name="x", weight=0)
        with pytest.raises(ValueError):
            Intent(name="x", weight=True)  # type: ignore[arg-type]

    def test_intent_rejects_draw_and_non_effects(self):
        with pytest.raises(ValueError, match="draw"):
            Intent(name="x", effects=(Effect(kind=EffectKind.DRAW, amount=1),))
        with pytest.raises(TypeError):
            Intent(name="x", effects=("damage",))  # type: ignore[arg-type]

    def test_pattern_needs_intents_and_a_mode(self):
        with pytest.raises(ValueError):
            IntentPattern(mode=IntentMode.CYCLE, intents=())
        with pytest.raises(TypeError):
            IntentPattern(mode="cycle", intents=(Intent(name="x"),))  # type: ignore[arg-type]

    def test_definition_validates_fields(self):
        pattern = _pattern()
        with pytest.raises(ValueError):
            EnemyDefinition(name="", max_hp=1, max_energy=0, pattern=pattern)
        with pytest.raises(ValueError):
            EnemyDefinition(name="x", max_hp=0, max_energy=0, pattern=pattern)
        with pytest.raises(ValueError):
            EnemyDefinition(name="x", max_hp=1, max_energy=-1, pattern=pattern)
        with pytest.raises(TypeError):
            EnemyDefinition(name="x", max_hp=1, max_energy=0, pattern=None)  # type: ignore[arg-type]


class TestEnemyAI:
    def test_cycle_walks_intents_in_order_and_wraps(self):
        ai = EnemyAI(_pattern(IntentMode.CYCLE, weights=(1, 1, 1)))
        rng = random.Random(0)
        names = [ai.choose(rng).name for _ in range(7)]
        assert names == ["I0", "I1", "I2", "I0", "I1", "I2", "I0"]

    def test_cycle_does_not_consume_rng(self):
        ai = EnemyAI(_pattern(IntentMode.CYCLE))
        rng = random.Random(5)
        before = rng.getstate()
        ai.choose(rng)
        ai.choose(rng)
        assert rng.getstate() == before

    def test_weighted_choice_is_reproducible_from_seed(self):
        pattern = _pattern(IntentMode.WEIGHTED, weights=(3, 1, 2))
        ai_a, ai_b = EnemyAI(pattern), EnemyAI(pattern)
        rng_a, rng_b = random.Random(9), random.Random(9)
        seq_a = [ai_a.choose(rng_a).name for _ in range(50)]
        seq_b = [ai_b.choose(rng_b).name for _ in range(50)]
        assert seq_a == seq_b

    def test_weighted_choice_respects_weights(self):
        pattern = _pattern(IntentMode.WEIGHTED, weights=(9, 1))
        ai = EnemyAI(pattern)
        rng = random.Random(123)
        names = [ai.choose(rng).name for _ in range(2000)]
        assert names.count("I0") > names.count("I1") * 4

    def test_single_weighted_intent_is_always_chosen(self):
        ai = EnemyAI(_pattern(IntentMode.WEIGHTED, weights=(1,)))
        rng = random.Random(1)
        assert {ai.choose(rng).name for _ in range(20)} == {"I0"}

    def test_rejects_non_pattern(self):
        with pytest.raises(TypeError):
            EnemyAI("cycle")  # type: ignore[arg-type]
