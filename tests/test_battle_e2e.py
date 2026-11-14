"""End-to-end: a full seeded battle against data-defined enemies is reproducible."""

import pytest

from cardgame.battle import Battle
from cardgame.enemies import load_default_enemies
from cardgame.loader import load_default_cards
from cardgame.models import StatusKind, Unit

MAX_TURNS = 200


def _deck():
    cards = load_default_cards()
    return [cards["Strike"]] * 3 + [cards["Guard"]] * 3 + [cards["Venom Dart"]] * 2


def _play_greedy(battle: Battle) -> list[str]:
    """Deterministic policy: play the first affordable card, then end the turn."""
    played: list[str] = []
    while not battle.is_over:
        index = next(
            (i for i, card in enumerate(battle.hand) if card.cost <= battle.player.energy),
            None,
        )
        if index is None:
            return played
        played.append(battle.play_card(index).name)


def _run_battle(enemy_name: str, seed: int) -> dict:
    definition = load_default_enemies()[enemy_name]
    battle = Battle(
        Unit(name="Hero", max_hp=40, max_energy=3, deck=_deck()),
        definition.create_unit(),
        seed=seed,
        enemy_ai=definition.create_ai(),
    )
    log = []
    while not battle.is_over and battle.turn < MAX_TURNS:
        battle.start_turn()
        intent = battle.enemy_intent.name
        played = _play_greedy(battle)
        if not battle.is_over:
            battle.end_turn()
        log.append(
            {
                "turn": battle.turn,
                "intent": intent,
                "played": played,
                "hero_hp": battle.player.hp,
                "enemy_hp": battle.enemy.hp,
                "hero_shield": _stacks(battle.player, "shield"),
                "enemy_shield": _stacks(battle.enemy, "shield"),
                "hero_poison": _stacks(battle.player, "poison"),
            }
        )
    winner = battle.winner
    return {
        "log": log,
        "over": battle.is_over,
        "winner": winner.name if winner else None,
        "turns": battle.turn,
    }


def _stacks(unit: Unit, kind: str) -> int:
    status = unit.get_status(StatusKind(kind))
    return status.stacks if status else 0


@pytest.mark.parametrize("enemy_name", ["Slime", "Cultist"])
@pytest.mark.parametrize("seed", [0, 1, 42, 2024])
def test_seeded_battle_has_identical_outcome_on_repeated_runs(enemy_name, seed):
    first = _run_battle(enemy_name, seed)
    second = _run_battle(enemy_name, seed)
    assert first == second
    assert first["over"], "battle should finish within the turn cap"
    assert first["winner"] in {"Hero", enemy_name}


def test_battle_exercises_enemy_intents_and_statuses():
    result = _run_battle("Slime", 42)
    intents = [entry["intent"] for entry in result["log"]]
    assert intents[:2] == ["Tackle", "Harden"]
    assert set(intents) <= {"Tackle", "Harden"}


def test_different_seeds_can_produce_different_battles():
    outcomes = {repr(_run_battle("Cultist", seed)["log"]) for seed in range(8)}
    assert len(outcomes) > 1
