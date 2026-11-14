import pytest

from cardgame.battle import Battle
from cardgame.enemies import load_default_enemies, parse_enemies
from cardgame.loader import load_default_cards
from cardgame.models import Card, Effect, EffectKind, StatusKind, Unit


def _strike() -> Card:
    return load_default_cards()["Strike"]


def _hero(deck, max_energy=3, max_hp=40) -> Unit:
    return Unit(name="Hero", max_hp=max_hp, max_energy=max_energy, deck=list(deck))


def _enemy_from(name: str, data: dict | None = None):
    """Build an enemy Unit and its AI from bundled data or inline JSON."""
    definitions = parse_enemies(data) if data is not None else load_default_enemies()
    definition = definitions[name]
    return definition.create_unit(), definition.create_ai()


def _battle(deck, enemy_name="Slime", seed=1, data=None, **kwargs) -> Battle:
    enemy, ai = _enemy_from(enemy_name, data)
    return Battle(_hero(deck), enemy, seed=seed, enemy_ai=ai, **kwargs)


def _custom(intents, mode="cycle", max_hp=50):
    return {
        "enemies": [
            {
                "name": "Custom",
                "max_hp": max_hp,
                "pattern": {"mode": mode, "intents": intents},
            }
        ]
    }


def _card(name, cost=0, *effects) -> Card:
    return Card(name=name, cost=cost, effects=tuple(effects))


class TestEnemyIntentVisibility:
    def test_no_ai_means_no_intent_and_placeholder_attack(self):
        battle = Battle(_hero([_strike()]), Unit("Slime", 30, 0), seed=1, enemy_attack=7)
        assert battle.enemy_intent is None
        battle.start_turn()
        battle.end_turn()
        assert battle.player.hp == 33

    def test_first_intent_is_visible_before_any_turn(self):
        battle = _battle([_strike()], "Slime")
        assert battle.enemy_intent is not None
        assert battle.enemy_intent.name == "Tackle"

    def test_cycle_intent_advances_after_each_enemy_action(self):
        battle = _battle([_strike()], "Slime")
        names = []
        for _ in range(3):
            battle.start_turn()
            names.append(battle.enemy_intent.name)
            battle.end_turn()
        assert names == ["Tackle", "Harden", "Tackle"]
        assert battle.enemy_intent.name == "Harden"

    def test_weighted_intent_is_chosen_from_the_pattern(self):
        battle = _battle([_strike()], "Cultist", seed=3)
        assert battle.enemy_intent.name in {"Dark Strike", "Venom Spit", "Ward"}

    def test_enemy_ai_must_be_an_enemy_ai(self):
        with pytest.raises(TypeError):
            Battle(_hero([_strike()]), Unit("Slime", 30, 0), seed=1, enemy_ai="cycle")  # type: ignore[arg-type]


class TestEnemyIntentEffects:
    def test_attack_intent_damages_player(self):
        battle = _battle([_strike()], "Slime")  # first intent: Tackle, 4 damage
        battle.start_turn()
        battle.end_turn()
        assert battle.player.hp == 36

    def test_shield_intent_gives_enemy_a_shield_that_lasts_into_next_player_turn(self):
        battle = _battle([_strike()], "Slime")
        battle.start_turn()
        battle.end_turn()  # Tackle; intent becomes Harden
        battle.start_turn()
        battle.end_turn()  # Harden resolves at enemy act, lasts through player phase
        shield = battle.enemy.get_status(StatusKind.SHIELD)
        assert shield is not None and shield.stacks == 5 and shield.duration == 1

    def test_enemy_shield_absorbs_players_attack_in_following_turn(self):
        battle = _battle([_strike(), _strike(), _strike()], "Slime", seed=2)
        battle.start_turn()
        battle.end_turn()  # Tackle
        battle.start_turn()
        battle.end_turn()  # Harden: enemy gains 5 shield
        battle.start_turn()
        hand_size_before = len(battle.hand)
        assert hand_size_before >= 1
        battle.play_card(0)  # Strike deals 6; shield absorbs 5, 1 gets through
        assert battle.enemy.hp == 29
        assert battle.enemy.get_status(StatusKind.SHIELD) is None

    def test_enemy_shield_expires_after_its_duration(self):
        battle = _battle([_strike()], "Slime")
        battle.start_turn()
        battle.end_turn()
        battle.start_turn()
        battle.end_turn()  # Harden: shield duration 2
        battle.start_turn()
        battle.end_turn()  # Tackle again; shield ticks to duration 0 and is removed
        assert battle.enemy.get_status(StatusKind.SHIELD) is None

    def test_apply_status_intent_poisons_player_and_poison_ticks(self):
        data = _custom(
            [
                {
                    "name": "Spit",
                    "effects": [
                        {"type": "apply_status", "status": "poison", "stacks": 2, "duration": 3}
                    ],
                }
            ]
        )
        battle = _battle([_strike()], "Custom", data=data)
        battle.start_turn()
        battle.end_turn()
        # Enemy applied poison (2 stacks). Status resolution: player takes 2, stacks go to 1.
        assert battle.player.hp == 38
        poison = battle.player.get_status(StatusKind.POISON)
        assert poison is not None and poison.stacks == 1

    def test_intent_damage_is_reduced_by_enemy_weak(self):
        data = _custom([{"name": "Hit", "effects": [{"type": "damage", "amount": 8}]}])
        weak_card = _card(
            "Hex",
            0,
            Effect(kind=EffectKind.APPLY_STATUS, status=StatusKind.WEAK, stacks=1, duration=2),
        )
        battle = _battle([weak_card], "Custom", data=data)
        battle.start_turn()
        battle.play_card(0)  # weak on enemy: 25% less damage
        battle.end_turn()
        assert battle.player.hp == 40 - 6

    def test_intent_damage_is_absorbed_by_player_shield_first(self):
        data = _custom([{"name": "Hit", "effects": [{"type": "damage", "amount": 8}]}])
        guard = _card("Guard", 0, Effect(kind=EffectKind.SHIELD, amount=5))
        battle = _battle([guard], "Custom", data=data)
        battle.start_turn()
        battle.play_card(0)
        battle.end_turn()
        assert battle.player.hp == 40 - 3

    def test_enemy_self_shield_stacks_with_existing_shield(self):
        data = _custom(
            [
                {
                    "name": "Ward",
                    "effects": [
                        {"type": "apply_status", "status": "shield", "stacks": 3,
                         "duration": 2, "target": "self"}
                    ],
                }
            ]
        )
        battle = _battle([_strike()], "Custom", data=data)
        battle.start_turn()
        battle.end_turn()
        battle.start_turn()
        battle.end_turn()
        shield = battle.enemy.get_status(StatusKind.SHIELD)
        # First Ward gives 3 stacks (duration 2, ticks to 1 at resolution);
        # the second merges in: 3 + 3 stacks.
        assert shield is not None and shield.stacks == 6

    def test_damage_intent_does_not_touch_enemy_hp(self):
        data = _custom([{"name": "Hit", "effects": [{"type": "damage", "amount": 5}]}])
        battle = _battle([_strike()], "Custom", data=data)
        battle.start_turn()
        battle.end_turn()
        assert battle.enemy.hp == 50
        assert battle.player.hp == 35


class TestEnemyBehaviourFromData:
    def test_new_enemy_defined_only_in_data_plays_in_battle(self):
        data = _custom(
            [
                {"name": "Bite", "effects": [{"type": "damage", "amount": 9}]},
            ],
            max_hp=12,
        )
        battle = _battle([_strike()], "Custom", data=data)
        battle.start_turn()
        battle.end_turn()
        assert battle.player.hp == 31

    def test_weighted_enemy_sequence_is_reproducible_for_a_seed(self):
        def run(seed):
            battle = _battle([_strike()], "Cultist", seed=seed)
            names = [battle.enemy_intent.name]
            for _ in range(6):
                if battle.is_over:
                    break
                battle.start_turn()
                battle.end_turn()
                if not battle.is_over:
                    names.append(battle.enemy_intent.name)
            return names

        assert run(7) == run(7)

    def test_ai_progress_is_per_battle_not_shared_through_definition(self):
        definition = load_default_enemies()["Slime"]
        first = Battle(_hero([_strike()]), definition.create_unit(), seed=1,
                       enemy_ai=definition.create_ai())
        first.start_turn()
        first.end_turn()
        assert first.enemy_intent.name == "Harden"
        second = Battle(_hero([_strike()]), definition.create_unit(), seed=1,
                        enemy_ai=definition.create_ai())
        assert second.enemy_intent.name == "Tackle"
