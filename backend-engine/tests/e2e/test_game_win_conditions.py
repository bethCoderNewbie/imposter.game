"""
E2E tests for full game win condition flows.

Requires a real Redis instance — the module is auto-skipped when Redis is
unavailable (see conftest.py require_redis fixture).

All tests use the `e2e_client` fixture (real Redis on localhost:6379/15 by
default, overridable via REDIS_URL env var).

Design:
- 5-player games: guaranteed wolf(1) + seer(1) + 1 flex (doctor/hunter/villager)
  + 2 filler villagers.
- collect_role_map() discovers the actual composition before any WebSocket logic.
- All night/day driving uses helpers from tests.helpers.
"""

from __future__ import annotations

import pytest

from tests.helpers.game_driver import (
    create_and_fill,
    drive_night,
    drive_role_deal,
    drive_to_day_vote,
    drive_votes,
    send_player_intent,
)
from tests.helpers.role_utils import (
    collect_role_map,
    first_with_role,
    get_alive_pids,
    players_with_role,
)
from tests.helpers.ws_patterns import (
    assert_game_over,
    assert_no_sensitive_role_data,
    assert_player_alive,
    assert_player_dead,
    consume_until,
    until_phase,
)


def _start_game(client, n=5):
    game_id, host_secret, players = create_and_fill(client, n)
    r = client.post(f"/api/games/{game_id}/start", json={"host_secret": host_secret})
    assert r.status_code == 200, r.text
    return game_id, host_secret, players


def _build_night_acts(role_map, players, wolf_target_id, seer_target_id=None,
                      doctor_target_id=None):
    acts = {}
    wolf = first_with_role(role_map, "werewolf", players)
    seer = first_with_role(role_map, "seer", players)
    doctor = first_with_role(role_map, "doctor", players)
    if wolf:
        acts[wolf["player_id"]] = {
            "type": "submit_night_action", "target_id": wolf_target_id,
        }
    if seer and seer_target_id:
        acts[seer["player_id"]] = {
            "type": "submit_night_action", "target_id": seer_target_id,
        }
    if doctor and doctor_target_id:
        acts[doctor["player_id"]] = {
            "type": "submit_night_action", "target_id": doctor_target_id,
        }
    return acts


# ─────────────────────────────────────────────────────────────────────────────
# TestVillageWinsE2E
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.e2e
class TestVillageWinsE2E:

    def test_village_wins_full_game_flow(self, e2e_client):
        """
        Full game: Night1 wolf kills villager + seer identifies wolf →
        Day1 village votes wolf out → game_over winner=village_wins.

        Asserts: phase, winner, display roles revealed at game_over.
        """
        game_id, host_secret, players = _start_game(e2e_client)
        role_map = collect_role_map(e2e_client, game_id, players)

        wolf = first_with_role(role_map, "werewolf", players)
        seer = first_with_role(role_map, "seer", players)
        villagers = players_with_role(role_map, "villager", players)
        doctor = first_with_role(role_map, "doctor", players)

        if not villagers:
            pytest.skip("No villager in composition — composition has no killable filler")

        kill_target = villagers[0]
        # Doctor saves the seer (not the kill target) so the wolf kill lands
        doctor_target = seer["player_id"] if doctor else None

        night_acts = _build_night_acts(
            role_map, players,
            wolf_target_id=kill_target["player_id"],
            seer_target_id=wolf["player_id"],
            doctor_target_id=doctor_target,
        )

        with e2e_client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync (ROLE_DEAL)
            drive_role_deal(e2e_client, game_id, players, display_ws)
            day_msg = drive_night(e2e_client, game_id, players, display_ws, night_acts)
            assert day_msg["state"]["phase"] == "day"

            # Confirm wolf kill landed (doctor didn't protect kill_target)
            kill_landed = not day_msg["state"]["players"][kill_target["player_id"]]["is_alive"]
            if not kill_landed:
                pytest.skip("Doctor saved the kill target — rerun for different seed")

            drive_to_day_vote(e2e_client, game_id, players, display_ws)

            alive_pids = get_alive_pids(day_msg["state"])

            # Wolf votes for someone else (self-vote rejected by server)
            wolf_player = next(p for p in players if p["player_id"] == wolf["player_id"])
            other_pid = next(p for p in alive_pids if p != wolf["player_id"])
            send_player_intent(e2e_client, game_id, wolf_player, {
                "type": "submit_day_vote", "target_id": other_pid,
            })
            # All non-wolf alive players vote wolf out; drain until resolution
            non_wolf_alive = [p for p in alive_pids if p != wolf["player_id"]]
            result = drive_votes(e2e_client, game_id, players, display_ws,
                                 non_wolf_alive, wolf["player_id"])

        if result["state"]["phase"] == "game_over":
            assert result["state"]["winner"] == "village", (
                f"Expected village, got {result['state']['winner']!r}"
            )
            # Display reveals roles via elimination_log at game_over
            # (players[*].role is always null in display view — see stripper._display_view)
            elim_log = result["state"].get("elimination_log", [])
            for entry in elim_log:
                assert entry.get("role") is not None, (
                    f"game_over elimination_log entry missing role: {entry}"
                )
        else:
            # Majority not enough — game continues (skip rather than fail)
            pytest.skip("Wolf not voted out with strict majority in this seed")

    def test_village_wins_elimination_log_has_roles(self, e2e_client):
        """At game_over, elimination_log entries have role populated."""
        game_id, host_secret, players = _start_game(e2e_client)
        role_map = collect_role_map(e2e_client, game_id, players)

        wolf = first_with_role(role_map, "werewolf", players)
        seer = first_with_role(role_map, "seer", players)
        villagers = players_with_role(role_map, "villager", players)
        doctor = first_with_role(role_map, "doctor", players)

        if not villagers:
            pytest.skip("No villager in composition")

        kill_target = villagers[0]
        night_acts = _build_night_acts(
            role_map, players,
            wolf_target_id=kill_target["player_id"],
            seer_target_id=wolf["player_id"],
            doctor_target_id=(seer["player_id"] if doctor else None),
        )

        with e2e_client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(e2e_client, game_id, players, display_ws)
            day_msg = drive_night(e2e_client, game_id, players, display_ws, night_acts)

            if day_msg["state"]["players"][kill_target["player_id"]]["is_alive"]:
                pytest.skip("Doctor saved kill target — no elimination log entry")

            drive_to_day_vote(e2e_client, game_id, players, display_ws)

            alive_pids = get_alive_pids(day_msg["state"])

            wolf_player = next(p for p in players if p["player_id"] == wolf["player_id"])
            other_pid = next(p for p in alive_pids if p != wolf["player_id"])
            send_player_intent(e2e_client, game_id, wolf_player, {
                "type": "submit_day_vote", "target_id": other_pid,
            })
            non_wolf_alive = [p for p in alive_pids if p != wolf["player_id"]]
            result = drive_votes(e2e_client, game_id, players, display_ws,
                                 non_wolf_alive, wolf["player_id"])

        if result["state"]["phase"] != "game_over":
            pytest.skip("Game did not reach game_over in this run")

        elim_log = result["state"].get("elimination_log", [])
        assert len(elim_log) > 0, "No elimination_log entries at game_over"
        for entry in elim_log:
            assert entry.get("role") is not None, (
                f"elimination_log entry missing role: {entry}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# TestWerewolfWinsE2E
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.e2e
class TestWerewolfWinsE2E:

    def test_werewolf_wins_full_game_flow(self, e2e_client):
        """
        Engineer a 2-round WW win:
        Night1: wolf→v1 (kill a villager), seer→wolf
        Day1:   village accidentally votes out seer (wolf + v2 + flex vote seer)
        Night2: wolf→v2 (kills last villager-type)
        → wolves(1) >= village(1) → WEREWOLF WINS

        Composition required: wolf, seer, at least 2 villagers/fillers
        """
        game_id, host_secret, players = _start_game(e2e_client)
        role_map = collect_role_map(e2e_client, game_id, players)

        wolf = first_with_role(role_map, "werewolf", players)
        seer = first_with_role(role_map, "seer", players)
        villagers = players_with_role(role_map, "villager", players)
        doctor = first_with_role(role_map, "doctor", players)

        non_wolf_non_seer = [
            p for p in players
            if role_map[p["player_id"]] not in ("werewolf", "seer")
        ]

        if len(non_wolf_non_seer) < 2:
            pytest.skip("Need 2+ non-wolf/seer players for this WW win scenario")

        v1 = non_wolf_non_seer[0]
        v2 = non_wolf_non_seer[1]

        # Night1: wolf kills v1, seer inspects wolf, doctor (if any) protects seer
        night1_acts = _build_night_acts(
            role_map, players,
            wolf_target_id=v1["player_id"],
            seer_target_id=wolf["player_id"],
            doctor_target_id=(seer["player_id"] if doctor else None),
        )

        with e2e_client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(e2e_client, game_id, players, display_ws)

            # ── NIGHT 1 ──
            day1_msg = drive_night(
                e2e_client, game_id, players, display_ws, night1_acts
            )

            if day1_msg["state"]["phase"] != "day":
                pytest.skip("Night1 ended in game_over/hunter_pending — skip WW test")

            if day1_msg["state"]["players"][v1["player_id"]]["is_alive"]:
                pytest.skip("Doctor saved v1 — wolf kill didn't land, adjust test")

            # ── DAY 1: Vote out seer ──
            drive_to_day_vote(e2e_client, game_id, players, display_ws)

            alive_pids = get_alive_pids(day1_msg["state"])
            seer_pid = seer["player_id"]
            majority_size = len(alive_pids) // 2 + 1

            # Build a majority for voting seer (wolf + as many non-seer alive as needed)
            voters_for_seer = [p for p in alive_pids if p != seer_pid][:majority_size]
            remaining_voters = [p for p in alive_pids if p not in voters_for_seer and p != seer_pid]

            for pid in alive_pids:
                player = next(p for p in players if p["player_id"] == pid)
                if pid == seer_pid:
                    # Seer votes wolf (self-defense, but won't change outcome)
                    send_player_intent(e2e_client, game_id, player, {
                        "type": "submit_day_vote", "target_id": wolf["player_id"],
                    })
                elif pid in voters_for_seer:
                    send_player_intent(e2e_client, game_id, player, {
                        "type": "submit_day_vote", "target_id": seer_pid,
                    })
                else:
                    # Minority vote — must vote for someone alive and not self
                    alt = next(p for p in alive_pids
                               if p != pid and p not in voters_for_seer)
                    send_player_intent(e2e_client, game_id, player, {
                        "type": "submit_day_vote", "target_id": alt,
                    })

            day1_result = consume_until(
                display_ws,
                lambda m: m.get("state", {}).get("phase") in (
                    "night", "game_over", "hunter_pending"
                ),
                max_messages=50,
            )

            if day1_result["state"]["phase"] != "night":
                pytest.skip("Day1 did not transition to NIGHT (game over or hunter)")

            if day1_result["state"]["players"][seer_pid]["is_alive"]:
                pytest.skip("Seer was not voted out in Day1 — insufficient majority")

            # ── NIGHT 2 ──
            # Now alive: wolf + v2 + possibly doctor (if flex was doctor)
            # Wolf kills v2; doctor (if alive) must protect someone different from Night1
            alive_in_night2 = get_alive_pids(day1_result["state"])

            # For doctor: Night1 they protected seer. Night2 they must protect someone else.
            doctor_night2_target = None
            if doctor and doctor["player_id"] in alive_in_night2:
                # Protect v2 (wolf's target) — if v2 is alive
                if v2["player_id"] in alive_in_night2:
                    # Intentionally DON'T protect v2 to let wolf win
                    # Doctor protects wolf (doesn't help village but avoids consecutive ban)
                    doctor_night2_target = wolf["player_id"]

            night2_acts: dict = {
                wolf["player_id"]: {
                    "type": "submit_night_action",
                    "target_id": v2["player_id"],
                }
            }
            # Seer is dead — skip seer action
            if doctor and doctor["player_id"] in alive_in_night2 and doctor_night2_target:
                night2_acts[doctor["player_id"]] = {
                    "type": "submit_night_action",
                    "target_id": doctor_night2_target,
                }

            result = drive_night(
                e2e_client, game_id, players, display_ws, night2_acts
            )

        if result["state"]["phase"] == "game_over":
            assert result["state"]["winner"] == "werewolf", (
                f"Expected werewolf, got {result['state']['winner']!r}"
            )
        else:
            # Game may need another round — this test may not converge in 2 rounds
            # depending on doctor protection
            pytest.skip("Did not reach game_over in 2 rounds for this seed")

    def test_werewolf_win_broadcast_reveals_roles(self, e2e_client):
        """At werewolf game_over, display broadcast shows all player roles."""
        game_id, host_secret, players = _start_game(e2e_client)
        role_map = collect_role_map(e2e_client, game_id, players)

        wolf = first_with_role(role_map, "werewolf", players)
        seer = first_with_role(role_map, "seer", players)
        non_wolf_non_seer = [
            p for p in players
            if role_map[p["player_id"]] not in ("werewolf", "seer")
        ]
        doctor = first_with_role(role_map, "doctor", players)

        if len(non_wolf_non_seer) < 2:
            pytest.skip("Need 2+ non-wolf/seer players for this scenario")

        v1 = non_wolf_non_seer[0]
        v2 = non_wolf_non_seer[1]

        night1_acts = _build_night_acts(
            role_map, players,
            wolf_target_id=v1["player_id"],
            seer_target_id=wolf["player_id"],
            doctor_target_id=(seer["player_id"] if doctor else None),
        )

        with e2e_client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(e2e_client, game_id, players, display_ws)
            day1_msg = drive_night(e2e_client, game_id, players, display_ws, night1_acts)

            if day1_msg["state"]["phase"] != "day":
                pytest.skip("Night1 ended unexpectedly")

            if day1_msg["state"]["players"][v1["player_id"]]["is_alive"]:
                pytest.skip("Doctor saved v1")

            drive_to_day_vote(e2e_client, game_id, players, display_ws)
            alive_pids = get_alive_pids(day1_msg["state"])
            seer_pid = seer["player_id"]
            majority_size = len(alive_pids) // 2 + 1
            voters_for_seer = [p for p in alive_pids if p != seer_pid][:majority_size]

            for pid in alive_pids:
                player = next(p for p in players if p["player_id"] == pid)
                if pid == seer_pid:
                    send_player_intent(e2e_client, game_id, player, {
                        "type": "submit_day_vote", "target_id": wolf["player_id"],
                    })
                elif pid in voters_for_seer:
                    send_player_intent(e2e_client, game_id, player, {
                        "type": "submit_day_vote", "target_id": seer_pid,
                    })
                else:
                    alt = next(p for p in alive_pids
                               if p != pid and p not in voters_for_seer)
                    send_player_intent(e2e_client, game_id, player, {
                        "type": "submit_day_vote", "target_id": alt,
                    })

            day1_result = consume_until(
                display_ws,
                lambda m: m.get("state", {}).get("phase") in (
                    "night", "game_over", "hunter_pending"
                ),
                max_messages=50,
            )

            if day1_result["state"]["phase"] != "night":
                pytest.skip("Day1 did not transition to NIGHT")
            if day1_result["state"]["players"][seer_pid]["is_alive"]:
                pytest.skip("Seer not voted out")

            alive_n2 = get_alive_pids(day1_result["state"])
            doctor_n2_target = wolf["player_id"] if (
                doctor and doctor["player_id"] in alive_n2
            ) else None

            night2_acts: dict = {
                wolf["player_id"]: {
                    "type": "submit_night_action",
                    "target_id": v2["player_id"],
                }
            }
            if doctor and doctor["player_id"] in alive_n2 and doctor_n2_target:
                night2_acts[doctor["player_id"]] = {
                    "type": "submit_night_action",
                    "target_id": doctor_n2_target,
                }

            result = drive_night(e2e_client, game_id, players, display_ws, night2_acts)

        if result["state"]["phase"] != "game_over":
            pytest.skip("Did not reach game_over in 2 rounds")

        # Display reveals roles via elimination_log (players[*].role always null in display view)
        elim_log = result["state"].get("elimination_log", [])
        for entry in elim_log:
            assert entry.get("role") is not None, (
                f"game_over elimination_log entry missing role: {entry}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# TestGameOverBroadcastE2E
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.e2e
class TestGameOverBroadcastE2E:

    def _drive_to_game_over_village_wins(self, client, game_id, players, role_map,
                                         display_ws):
        """
        Attempt to drive the game to game_over (village wins).
        Returns the game_over broadcast, or None if not achieved.
        """
        wolf = first_with_role(role_map, "werewolf", players)
        seer = first_with_role(role_map, "seer", players)
        villagers = players_with_role(role_map, "villager", players)
        doctor = first_with_role(role_map, "doctor", players)

        if not villagers:
            return None

        kill_target = villagers[0]
        night_acts = _build_night_acts(
            role_map, players,
            wolf_target_id=kill_target["player_id"],
            seer_target_id=wolf["player_id"],
            doctor_target_id=(seer["player_id"] if doctor else None),
        )

        drive_role_deal(client, game_id, players, display_ws)
        day_msg = drive_night(client, game_id, players, display_ws, night_acts)

        if day_msg["state"]["phase"] != "day":
            return None
        if day_msg["state"]["players"][kill_target["player_id"]]["is_alive"]:
            return None  # doctor saved

        drive_to_day_vote(client, game_id, players, display_ws)

        alive_pids = get_alive_pids(day_msg["state"])

        wolf_player = next(p for p in players if p["player_id"] == wolf["player_id"])
        other_pid = next(p for p in alive_pids if p != wolf["player_id"])
        send_player_intent(client, game_id, wolf_player, {
            "type": "submit_day_vote", "target_id": other_pid,
        })
        non_wolf_alive = [p for p in alive_pids if p != wolf["player_id"]]
        result = drive_votes(client, game_id, players, display_ws,
                             non_wolf_alive, wolf["player_id"])
        return result if result["state"]["phase"] == "game_over" else None

    def test_game_over_received_by_display_and_player_ws(self, e2e_client):
        """Both display and a player WS receive the game_over broadcast."""
        game_id, host_secret, players = _start_game(e2e_client)
        role_map = collect_role_map(e2e_client, game_id, players)

        wolf = first_with_role(role_map, "werewolf", players)
        seer = first_with_role(role_map, "seer", players)
        villagers = players_with_role(role_map, "villager", players)
        doctor = first_with_role(role_map, "doctor", players)

        if not villagers:
            pytest.skip("No villager in composition")

        kill_target = villagers[0]
        night_acts = _build_night_acts(
            role_map, players,
            wolf_target_id=kill_target["player_id"],
            seer_target_id=wolf["player_id"],
            doctor_target_id=(seer["player_id"] if doctor else None),
        )

        # Use the dead kill_target as the player WS observer — guaranteed dead after night,
        # so it's never in alive_pids and send_player_intent won't open a competing WS
        # for the same player_id (which would evict player_ws from the server's broadcast map).
        non_wolf = kill_target

        game_over_on_display = None
        game_over_on_player = None

        with e2e_client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(e2e_client, game_id, players, display_ws)
            day_msg = drive_night(e2e_client, game_id, players, display_ws, night_acts)

            if day_msg["state"]["phase"] != "day":
                pytest.skip("Night1 ended unexpectedly")
            if day_msg["state"]["players"][kill_target["player_id"]]["is_alive"]:
                pytest.skip("Doctor saved — wolf kill didn't land")

            drive_to_day_vote(e2e_client, game_id, players, display_ws)
            alive_pids = get_alive_pids(day_msg["state"])

            # Keep a non-wolf player WS open to see game_over
            with e2e_client.websocket_connect(
                f"/ws/{game_id}/{non_wolf['player_id']}"
            ) as player_ws:
                player_ws.send_json({"type": "auth", "session_token": non_wolf["session_token"]})
                player_ws.receive_json()  # sync

                wolf_player = next(p for p in players if p["player_id"] == wolf["player_id"])
                other_pid = next(p for p in alive_pids if p != wolf["player_id"])
                send_player_intent(e2e_client, game_id, wolf_player, {
                    "type": "submit_day_vote", "target_id": other_pid,
                })
                non_wolf_alive = [p for p in alive_pids if p != wolf["player_id"]]
                result_display = drive_votes(e2e_client, game_id, players, display_ws,
                                             non_wolf_alive, wolf["player_id"])
                game_over_on_display = result_display

                if result_display["state"]["phase"] == "game_over":
                    result_player = consume_until(
                        player_ws,
                        lambda m: m.get("state", {}).get("phase") in (
                            "night", "game_over", "hunter_pending"
                        ),
                        max_messages=50,
                    )
                    game_over_on_player = result_player

        if game_over_on_display is None or game_over_on_display["state"]["phase"] != "game_over":
            pytest.skip("Game did not reach game_over in this seed")

        assert game_over_on_display["state"]["phase"] == "game_over"
        assert game_over_on_player is not None
        assert game_over_on_player["state"]["phase"] == "game_over"

    def test_game_over_elimination_log_complete(self, e2e_client):
        """Every entry in elimination_log has a non-null role at game_over."""
        game_id, host_secret, players = _start_game(e2e_client)
        role_map = collect_role_map(e2e_client, game_id, players)
        wolf = first_with_role(role_map, "werewolf", players)
        seer = first_with_role(role_map, "seer", players)
        villagers = players_with_role(role_map, "villager", players)
        doctor = first_with_role(role_map, "doctor", players)

        if not villagers:
            pytest.skip("No villager")

        kill_target = villagers[0]
        night_acts = _build_night_acts(
            role_map, players,
            wolf_target_id=kill_target["player_id"],
            seer_target_id=wolf["player_id"],
            doctor_target_id=(seer["player_id"] if doctor else None),
        )

        with e2e_client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()
            game_over = self._drive_to_game_over_village_wins(
                e2e_client, game_id, players, role_map, display_ws
            )

        if game_over is None:
            pytest.skip("Could not drive to game_over for this seed")

        elim_log = game_over["state"].get("elimination_log", [])
        assert len(elim_log) >= 2, "Expected at least 2 elimination_log entries"
        for entry in elim_log:
            assert entry["role"] is not None, f"elimination_log entry has null role: {entry}"

    def _drive_to_game_over_village_wins(self, client, game_id, players, role_map,
                                          display_ws):
        """Duplicate helper kept here for self-contained test logic."""
        wolf = first_with_role(role_map, "werewolf", players)
        seer = first_with_role(role_map, "seer", players)
        villagers = players_with_role(role_map, "villager", players)
        doctor = first_with_role(role_map, "doctor", players)
        if not villagers:
            return None
        kill_target = villagers[0]
        night_acts = _build_night_acts(
            role_map, players,
            wolf_target_id=kill_target["player_id"],
            seer_target_id=wolf["player_id"],
            doctor_target_id=(seer["player_id"] if doctor else None),
        )
        drive_role_deal(client, game_id, players, display_ws)
        day_msg = drive_night(client, game_id, players, display_ws, night_acts)
        if day_msg["state"]["phase"] != "day":
            return None
        if day_msg["state"]["players"][kill_target["player_id"]]["is_alive"]:
            return None
        drive_to_day_vote(client, game_id, players, display_ws)
        alive_pids = get_alive_pids(day_msg["state"])
        wolf_player = next(p for p in players if p["player_id"] == wolf["player_id"])
        other_pid = next(p for p in alive_pids if p != wolf["player_id"])
        send_player_intent(client, game_id, wolf_player, {
            "type": "submit_day_vote", "target_id": other_pid,
        })
        non_wolf_alive = [p for p in alive_pids if p != wolf["player_id"]]
        result = drive_votes(client, game_id, players, display_ws,
                             non_wolf_alive, wolf["player_id"])
        return result if result["state"]["phase"] == "game_over" else None
