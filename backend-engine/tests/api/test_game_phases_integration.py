"""
Integration tests for the full game phase stack: ROLE_DEAL → NIGHT → DAY →
DAY_VOTE → HUNTER_PENDING → GAME_OVER.

Uses fakeredis via the `client` fixture — no real Redis required.
All tests are marked @pytest.mark.integration.

Key conventions:
- collect_role_map() is called BEFORE opening the display WebSocket to avoid
  disconnect-broadcast noise polluting the display WS buffer.
- send_player_intent() sends one intent and closes; the server processes it
  before the disconnect fires.
- consume_until() drains until a predicate matches, tolerating noise.
- state_id is omitted from test intents (missing field = fence bypassed).
- _build_night_acts() auto-fills doctor target (protect seer) so that
  auto-advance always fires when all waking roles submit.
- Voting patterns avoid self-votes: vote_target votes for someone else,
  all others vote for vote_target (guarantees majority for any N≥2 alive).
"""

from __future__ import annotations

import pytest

from tests.helpers.game_driver import (
    create_and_fill,
    drive_night,
    drive_role_deal,
    drive_to_day_vote,
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
    assert_phase,
    assert_player_alive,
    assert_player_dead,
    consume_until,
    until_phase,
)


# ── Shared setup helpers ───────────────────────────────────────────────────────

def _start_game(client, n=5):
    """Create+fill+start a game. Returns (game_id, host_secret, players)."""
    game_id, host_secret, players = create_and_fill(client, n)
    r = client.post(f"/api/games/{game_id}/start", json={"host_secret": host_secret})
    assert r.status_code == 200, r.text
    return game_id, host_secret, players


def _build_night_acts(role_map, players, wolf_target_id, seer_target_id=None,
                      doctor_target_id=None):
    """
    Build the night_acts dict for drive_night().

    Doctor is ALWAYS included if present in the composition — it defaults to
    protecting the seer (or wolf if seer is absent) so auto-advance reliably
    fires.  Pass an explicit doctor_target_id to override.
    """
    acts = {}
    wolf = first_with_role(role_map, "werewolf", players)
    seer = first_with_role(role_map, "seer", players)
    doctor = first_with_role(role_map, "doctor", players)

    if wolf:
        acts[wolf["player_id"]] = {
            "type": "submit_night_action",
            "target_id": wolf_target_id,
        }
    if seer and seer_target_id:
        acts[seer["player_id"]] = {
            "type": "submit_night_action",
            "target_id": seer_target_id,
        }
    if doctor:
        # Auto-fill: protect seer (or wolf if seer absent) as a safe default.
        dt = doctor_target_id
        if dt is None:
            dt = seer["player_id"] if seer else wolf["player_id"]
        acts[doctor["player_id"]] = {
            "type": "submit_night_action",
            "target_id": dt,
        }
    return acts


def _vote_everyone_for(client, game_id, players, alive_pids, target_pid):
    """
    Have every alive player vote for target_pid, except target_pid themselves
    who votes for the first other alive player.  Guarantees strict majority.
    """
    for pid in alive_pids:
        player = next(p for p in players if p["player_id"] == pid)
        if pid == target_pid:
            other = next(p for p in alive_pids if p != pid)
            send_player_intent(client, game_id, player, {
                "type": "submit_day_vote", "target_id": other,
            })
        else:
            send_player_intent(client, game_id, player, {
                "type": "submit_day_vote", "target_id": target_pid,
            })


# ─────────────────────────────────────────────────────────────────────────────
# TestRoleDealToNightTransition
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestRoleDealToNightTransition:

    def test_all_confirm_transitions_to_night(self, client):
        """All 5 players confirming roles advances the game to NIGHT."""
        game_id, host_secret, players = _start_game(client)
        collect_role_map(client, game_id, players)  # consume disconnect broadcasts

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync (ROLE_DEAL)
            msg = drive_role_deal(client, game_id, players, display_ws)
            assert_phase(msg, "night")

    def test_partial_confirms_stay_in_role_deal(self, client):
        """Only 4 of 5 players confirming leaves the game in ROLE_DEAL."""
        game_id, host_secret, players = _start_game(client)
        collect_role_map(client, game_id, players)

        # Confirm 4 of 5 players
        for player in players[:4]:
            send_player_intent(client, game_id, player, {"type": "confirm_role_reveal"})

        # Verify via a fresh display WS sync (all intent processing is done by now)
        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            sync = display_ws.receive_json()

        assert sync["state"]["phase"] == "role_deal"

    def test_confirm_wrong_phase_returns_error(self, client):
        """Sending confirm_role_reveal in NIGHT returns WRONG_PHASE error."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(client, game_id, players, display_ws)

        # Now in NIGHT — attempt to confirm again
        wolf = first_with_role(role_map, "werewolf", players)
        with client.websocket_connect(f"/ws/{game_id}/{wolf['player_id']}") as ws:
            ws.send_json({"type": "auth", "session_token": wolf["session_token"]})
            ws.receive_json()  # sync
            ws.send_json({"type": "confirm_role_reveal"})
            resp = ws.receive_json()

        assert resp.get("code") == "WRONG_PHASE"


# ─────────────────────────────────────────────────────────────────────────────
# TestNightPhaseFlow
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestNightPhaseFlow:

    def test_wolf_night_action_increments_submitted_count(self, client):
        """Wolf submitting a night action increments actions_submitted_count."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)
        wolf = first_with_role(role_map, "werewolf", players)
        villagers = players_with_role(role_map, "villager", players)
        target = villagers[0] if villagers else first_with_role(role_map, "seer", players)

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(client, game_id, players, display_ws)

            # Wolf submits action; drain until submitted_count reflects the action.
            # (There may be a leftover player_disconnected broadcast from role_deal.)
            send_player_intent(
                client, game_id, wolf,
                {"type": "submit_night_action", "target_id": target["player_id"]},
            )
            msg = consume_until(
                display_ws,
                lambda m: m.get("state", {}).get("night_actions", {}).get(
                    "actions_submitted_count", 0
                ) >= 1,
                max_messages=15,
            )
        na = msg.get("state", {}).get("night_actions", {})
        assert na.get("actions_submitted_count", 0) >= 1

    def test_all_night_actions_auto_advance_to_day(self, client):
        """Submitting all required night actions auto-advances to DAY."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)
        wolf = first_with_role(role_map, "werewolf", players)
        seer = first_with_role(role_map, "seer", players)
        villagers = players_with_role(role_map, "villager", players)
        v_target = villagers[0] if villagers else seer

        night_acts = _build_night_acts(
            role_map, players,
            wolf_target_id=v_target["player_id"],
            seer_target_id=wolf["player_id"],
        )

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(client, game_id, players, display_ws)
            msg = drive_night(client, game_id, players, display_ws, night_acts)
        assert_phase(msg, "day")

    def test_wolf_kill_reflected_in_day_broadcast(self, client):
        """Wolf kills a villager (no doctor save); DAY broadcast shows them dead."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)
        wolf = first_with_role(role_map, "werewolf", players)
        seer = first_with_role(role_map, "seer", players)
        villagers = players_with_role(role_map, "villager", players)

        if not villagers:
            pytest.skip("No villager in this composition")

        kill_target = villagers[0]
        doctor = first_with_role(role_map, "doctor", players)

        # Doctor protects seer (NOT kill_target) so wolf kill lands
        night_acts = _build_night_acts(
            role_map, players,
            wolf_target_id=kill_target["player_id"],
            seer_target_id=wolf["player_id"],
            doctor_target_id=(seer["player_id"] if doctor else None),
        )

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(client, game_id, players, display_ws)
            msg = drive_night(client, game_id, players, display_ws, night_acts)

        assert_phase(msg, "day")
        assert_player_dead(msg, kill_target["player_id"])

    def test_doctor_save_prevents_wolf_kill(self, client):
        """Doctor protecting the wolf's target keeps them alive in DAY broadcast."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)
        doctor = first_with_role(role_map, "doctor", players)

        if not doctor:
            pytest.skip("No doctor in this composition")

        wolf = first_with_role(role_map, "werewolf", players)
        seer = first_with_role(role_map, "seer", players)

        # Doctor protects seer; wolf kills seer → seer survives
        night_acts = _build_night_acts(
            role_map, players,
            wolf_target_id=seer["player_id"],
            seer_target_id=wolf["player_id"],
            doctor_target_id=seer["player_id"],
        )

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(client, game_id, players, display_ws)
            msg = drive_night(client, game_id, players, display_ws, night_acts)

        assert_phase(msg, "day")
        assert_player_alive(msg, seer["player_id"])

    def test_seer_result_in_seer_ws_view(self, client):
        """Seer inspecting the wolf receives seer_result='wolf' in their DAY sync."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)
        seer = first_with_role(role_map, "seer", players)
        wolf = first_with_role(role_map, "werewolf", players)
        villagers = players_with_role(role_map, "villager", players)
        doctor = first_with_role(role_map, "doctor", players)

        kill_target = villagers[0] if villagers else wolf

        # Keep seer WS open to receive the DAY broadcast with seer_result
        with client.websocket_connect(f"/ws/{game_id}/{seer['player_id']}") as seer_ws:
            seer_ws.send_json({"type": "auth", "session_token": seer["session_token"]})
            seer_ws.receive_json()  # sync (ROLE_DEAL)

            # Confirm all roles: seer via seer_ws, others via separate WS calls
            for player in players:
                if player["player_id"] == seer["player_id"]:
                    seer_ws.send_json({"type": "confirm_role_reveal"})
                else:
                    send_player_intent(
                        client, game_id, player, {"type": "confirm_role_reveal"}
                    )

            # Drain seer WS to NIGHT
            consume_until(seer_ws, until_phase("night"))

            # Seer inspects wolf (stays connected to receive result)
            seer_ws.send_json({
                "type": "submit_night_action",
                "target_id": wolf["player_id"],
            })

            # Wolf submits via separate WS
            send_player_intent(
                client, game_id, wolf,
                {"type": "submit_night_action", "target_id": kill_target["player_id"]},
            )

            # Doctor submits if present (protects kill_target to avoid ambiguity)
            if doctor:
                send_player_intent(
                    client, game_id, doctor,
                    {"type": "submit_night_action", "target_id": kill_target["player_id"]},
                )

            # Drain seer WS to DAY (has seer_result populated)
            day_msg = consume_until(seer_ws, until_phase("day"))

        na = day_msg["state"]["night_actions"]
        assert na.get("seer_result") == "wolf", (
            f"Expected seer_result='wolf', got {na.get('seer_result')!r}"
        )

    def test_seer_result_absent_from_display_ws(self, client):
        """Display view must NOT expose seer_result (must be null/absent)."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)
        wolf = first_with_role(role_map, "werewolf", players)
        seer = first_with_role(role_map, "seer", players)
        villagers = players_with_role(role_map, "villager", players)

        kill_target = villagers[0] if villagers else seer

        night_acts = _build_night_acts(
            role_map, players,
            wolf_target_id=kill_target["player_id"],
            seer_target_id=wolf["player_id"],
            # doctor auto-protects seer (default in _build_night_acts)
        )

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(client, game_id, players, display_ws)
            day_msg = drive_night(client, game_id, players, display_ws, night_acts)

        na = day_msg.get("state", {}).get("night_actions", {})
        assert na.get("seer_result") is None, (
            f"Display exposed seer_result={na.get('seer_result')!r}"
        )

    def test_duplicate_night_action_rejected(self, client):
        """Wolf submitting two night actions in the same round gets DUPLICATE_ACTION."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)
        wolf = first_with_role(role_map, "werewolf", players)
        villagers = players_with_role(role_map, "villager", players)
        target = villagers[0] if villagers else first_with_role(role_map, "seer", players)

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(client, game_id, players, display_ws)

        # Keep wolf WS open to submit twice
        with client.websocket_connect(f"/ws/{game_id}/{wolf['player_id']}") as ws:
            ws.send_json({"type": "auth", "session_token": wolf["session_token"]})
            ws.receive_json()  # sync

            ws.send_json({"type": "submit_night_action", "target_id": target["player_id"]})
            ws.send_json({"type": "submit_night_action", "target_id": target["player_id"]})

            error_msg = None
            for _ in range(15):
                msg = ws.receive_json()
                if msg.get("code") == "DUPLICATE_ACTION":
                    error_msg = msg
                    break

        assert error_msg is not None, "Expected DUPLICATE_ACTION error"


# ─────────────────────────────────────────────────────────────────────────────
# TestDayVoteFlow
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestDayVoteFlow:

    def _night_acts_for_game(self, role_map, players):
        """Build standard Night1 acts: wolf kills v1 (or seer), seer inspects wolf."""
        wolf = first_with_role(role_map, "werewolf", players)
        seer = first_with_role(role_map, "seer", players)
        villagers = players_with_role(role_map, "villager", players)
        kill_target = villagers[0] if villagers else seer
        return kill_target, _build_night_acts(
            role_map, players,
            wolf_target_id=kill_target["player_id"],
            seer_target_id=wolf["player_id"],
        )

    def test_advance_phase_moves_to_day_vote(self, client):
        """Host sending advance_phase from DAY moves to DAY_VOTE."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)
        kill_target, night_acts = self._night_acts_for_game(role_map, players)

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(client, game_id, players, display_ws)
            drive_night(client, game_id, players, display_ws, night_acts)
            msg = drive_to_day_vote(client, game_id, players, display_ws)

        assert_phase(msg, "day_vote")

    def test_non_host_advance_phase_rejected(self, client):
        """Non-host sending advance_phase receives NOT_HOST error."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)
        kill_target, night_acts = self._night_acts_for_game(role_map, players)

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(client, game_id, players, display_ws)
            drive_night(client, game_id, players, display_ws, night_acts)

        # Non-host (players[1]) sends advance_phase
        non_host = players[1]
        with client.websocket_connect(f"/ws/{game_id}/{non_host['player_id']}") as ws:
            ws.send_json({"type": "auth", "session_token": non_host["session_token"]})
            ws.receive_json()  # sync
            ws.send_json({"type": "advance_phase"})
            resp = ws.receive_json()

        assert resp.get("code") == "NOT_HOST"

    def test_majority_vote_eliminates_target(self, client):
        """Strict majority vote eliminates the target player."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)
        wolf = first_with_role(role_map, "werewolf", players)
        kill_target, night_acts = self._night_acts_for_game(role_map, players)

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(client, game_id, players, display_ws)
            day_msg = drive_night(client, game_id, players, display_ws, night_acts)
            drive_to_day_vote(client, game_id, players, display_ws)

            alive_pids = get_alive_pids(day_msg["state"])
            # Vote out wolf: everyone votes wolf, wolf votes for someone else
            _vote_everyone_for(client, game_id, players, alive_pids, wolf["player_id"])

            result = consume_until(
                display_ws,
                lambda m: m.get("state", {}).get("phase") in (
                    "night", "game_over", "hunter_pending"
                ),
                max_messages=50,
            )

        assert_player_dead(result, wolf["player_id"])

    def test_dead_target_vote_rejected(self, client):
        """Voting for a dead player returns TARGET_ALREADY_DEAD."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)
        villagers = players_with_role(role_map, "villager", players)

        if not villagers:
            pytest.skip("No villager in composition")

        wolf = first_with_role(role_map, "werewolf", players)
        kill_target = villagers[0]
        seer = first_with_role(role_map, "seer", players)

        # Doctor protects seer; wolf kills kill_target → kill_target dies
        night_acts = _build_night_acts(
            role_map, players,
            wolf_target_id=kill_target["player_id"],
            seer_target_id=wolf["player_id"],
            doctor_target_id=(seer["player_id"]
                              if first_with_role(role_map, "doctor", players) else None),
        )

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(client, game_id, players, display_ws)
            drive_night(client, game_id, players, display_ws, night_acts)
            drive_to_day_vote(client, game_id, players, display_ws)

        # Vote for the dead kill_target
        voter = next(p for p in players if p["player_id"] != kill_target["player_id"])
        with client.websocket_connect(f"/ws/{game_id}/{voter['player_id']}") as ws:
            ws.send_json({"type": "auth", "session_token": voter["session_token"]})
            ws.receive_json()  # sync
            ws.send_json({
                "type": "submit_day_vote",
                "target_id": kill_target["player_id"],
            })
            resp = ws.receive_json()

        assert resp.get("code") == "TARGET_ALREADY_DEAD"


# ─────────────────────────────────────────────────────────────────────────────
# TestHunterPendingFlow
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestHunterPendingFlow:

    def _get_hunter_game(self, client):
        """
        Create a game where hunter is in the composition.
        Tries up to 20 games with fresh seeds; skips if hunter never appears.
        """
        for _ in range(20):
            game_id, host_secret, players = _start_game(client)
            role_map = collect_role_map(client, game_id, players)
            if first_with_role(role_map, "hunter", players) is not None:
                return game_id, host_secret, players, role_map
        pytest.skip("Hunter not present in any of 20 compositions")

    def _vote_out_player(self, client, game_id, players, alive_pids, target_pid,
                         display_ws):
        """
        Drive all alive players to vote for target_pid (target votes elsewhere).
        Returns the resolution broadcast.
        """
        _vote_everyone_for(client, game_id, players, alive_pids, target_pid)
        return consume_until(
            display_ws,
            lambda m: m.get("state", {}).get("phase") in (
                "night", "game_over", "hunter_pending"
            ),
            max_messages=50,
        )

    def test_hunter_voted_out_triggers_hunter_pending(self, client):
        """Voting out the hunter moves the game to HUNTER_PENDING."""
        game_id, host_secret, players, role_map = self._get_hunter_game(client)
        hunter = first_with_role(role_map, "hunter", players)
        wolf = first_with_role(role_map, "werewolf", players)
        seer = first_with_role(role_map, "seer", players)
        villagers = players_with_role(role_map, "villager", players)
        kill_target = villagers[0] if villagers else seer

        night_acts = _build_night_acts(
            role_map, players,
            wolf_target_id=kill_target["player_id"],
            seer_target_id=wolf["player_id"],
        )

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(client, game_id, players, display_ws)
            day_msg = drive_night(client, game_id, players, display_ws, night_acts)
            drive_to_day_vote(client, game_id, players, display_ws)

            alive_pids = get_alive_pids(day_msg["state"])
            result = self._vote_out_player(
                client, game_id, players, alive_pids, hunter["player_id"], display_ws
            )

        # May be hunter_pending (wolf not simultaneously eliminated) or game_over
        assert result["state"]["phase"] in ("hunter_pending", "game_over")

    def test_hunter_revenge_eliminates_target(self, client):
        """Hunter fires revenge kill; the target is marked dead."""
        game_id, host_secret, players, role_map = self._get_hunter_game(client)
        hunter = first_with_role(role_map, "hunter", players)
        wolf = first_with_role(role_map, "werewolf", players)
        seer = first_with_role(role_map, "seer", players)
        villagers = players_with_role(role_map, "villager", players)
        kill_target = villagers[0] if villagers else seer

        night_acts = _build_night_acts(
            role_map, players,
            wolf_target_id=kill_target["player_id"],
            seer_target_id=wolf["player_id"],
        )

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(client, game_id, players, display_ws)
            day_msg = drive_night(client, game_id, players, display_ws, night_acts)
            drive_to_day_vote(client, game_id, players, display_ws)

            alive_pids = get_alive_pids(day_msg["state"])
            phase_msg = self._vote_out_player(
                client, game_id, players, alive_pids, hunter["player_id"], display_ws
            )

            if phase_msg["state"]["phase"] != "hunter_pending":
                pytest.skip("Game ended before hunter_pending")

            # Hunter fires revenge at wolf
            hunter_player = next(
                p for p in players if p["player_id"] == hunter["player_id"]
            )
            send_player_intent(client, game_id, hunter_player, {
                "type": "hunter_revenge",
                "target_id": wolf["player_id"],
            })

            revenge_msg = consume_until(
                display_ws,
                lambda m: m.get("state", {}).get("phase") in ("day", "game_over"),
                max_messages=20,
            )

        assert_player_dead(revenge_msg, wolf["player_id"])

    def test_hunter_revenge_wrong_phase_rejected(self, client):
        """Sending hunter_revenge in DAY returns WRONG_PHASE."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)
        wolf = first_with_role(role_map, "werewolf", players)
        villagers = players_with_role(role_map, "villager", players)
        seer = first_with_role(role_map, "seer", players)
        kill_target = villagers[0] if villagers else seer

        night_acts = _build_night_acts(
            role_map, players,
            wolf_target_id=kill_target["player_id"],
            seer_target_id=wolf["player_id"],
        )

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(client, game_id, players, display_ws)
            drive_night(client, game_id, players, display_ws, night_acts)

        # In DAY phase — hunter_revenge should be rejected
        player = players[0]
        with client.websocket_connect(f"/ws/{game_id}/{player['player_id']}") as ws:
            ws.send_json({"type": "auth", "session_token": player["session_token"]})
            ws.receive_json()  # sync
            ws.send_json({"type": "hunter_revenge", "target_id": wolf["player_id"]})
            resp = ws.receive_json()

        assert resp.get("code") == "WRONG_PHASE"


# ─────────────────────────────────────────────────────────────────────────────
# TestVillageWinsIntegration
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestVillageWinsIntegration:

    def _drive_to_wolf_vote_out(self, client, game_id, players, role_map, display_ws):
        """
        Drive ROLE_DEAL + NIGHT (wolf kills villager) + DAY + DAY_VOTE (vote wolf out).
        Returns the post-vote broadcast.
        """
        wolf = first_with_role(role_map, "werewolf", players)
        seer = first_with_role(role_map, "seer", players)
        villagers = players_with_role(role_map, "villager", players)

        if not villagers:
            return None, None

        kill_target = villagers[0]
        night_acts = _build_night_acts(
            role_map, players,
            wolf_target_id=kill_target["player_id"],
            seer_target_id=wolf["player_id"],
            doctor_target_id=(
                seer["player_id"]
                if first_with_role(role_map, "doctor", players) else None
            ),
        )

        drive_role_deal(client, game_id, players, display_ws)
        day_msg = drive_night(client, game_id, players, display_ws, night_acts)

        if day_msg["state"]["phase"] != "day":
            return day_msg, None
        if day_msg["state"]["players"][kill_target["player_id"]]["is_alive"]:
            # Doctor saved kill_target — skip, wolf didn't land
            return None, None

        drive_to_day_vote(client, game_id, players, display_ws)
        alive_pids = get_alive_pids(day_msg["state"])
        _vote_everyone_for(client, game_id, players, alive_pids, wolf["player_id"])

        result = consume_until(
            display_ws,
            lambda m: m.get("state", {}).get("phase") in (
                "night", "game_over", "hunter_pending"
            ),
            max_messages=50,
        )
        return result, wolf

    def test_village_wins_on_wolf_vote_out(self, client):
        """
        Village voting out the only wolf → game_over with winner='village_wins'.
        """
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            result, wolf = self._drive_to_wolf_vote_out(
                client, game_id, players, role_map, display_ws
            )

        if result is None or wolf is None:
            pytest.skip("Composition/doctor save prevented wolf-vote-out scenario")

        if result["state"]["phase"] == "game_over":
            assert result["state"]["winner"] == "village"
        else:
            # Wolf was voted out but game didn't end (e.g., hunter pending)
            assert_player_dead(result, wolf["player_id"])

    def test_game_over_reveals_roles_in_elimination_log(self, client):
        """
        After game_over, display's elimination_log entries have non-null roles.
        (Display always strips player.role to null; roles are only revealed via
        elimination_log at game_over — see stripper._display_view.)
        """
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            result, wolf = self._drive_to_wolf_vote_out(
                client, game_id, players, role_map, display_ws
            )

        if result is None or result["state"]["phase"] != "game_over":
            pytest.skip("Game did not reach game_over in this composition")

        elim_log = result["state"].get("elimination_log", [])
        assert len(elim_log) > 0, "Expected elimination_log entries at game_over"
        for entry in elim_log:
            assert entry.get("role") is not None, (
                f"elimination_log entry missing role at game_over: {entry}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# TestSecurityStripping
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestSecurityStripping:

    def test_display_never_sees_wolf_votes(self, client):
        """Display's night_actions must not contain wolf_votes field."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)
        wolf = first_with_role(role_map, "werewolf", players)
        villagers = players_with_role(role_map, "villager", players)
        target = villagers[0] if villagers else first_with_role(role_map, "seer", players)

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(client, game_id, players, display_ws)

            send_player_intent(
                client, game_id, wolf,
                {"type": "submit_night_action", "target_id": target["player_id"]},
            )
            msg = display_ws.receive_json()

        na = msg.get("state", {}).get("night_actions", {})
        assert "wolf_votes" not in na, "Display exposed wolf_votes"

    def test_display_never_sees_seer_result(self, client):
        """Display's night_actions.seer_result must be null/absent."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)
        wolf = first_with_role(role_map, "werewolf", players)
        villagers = players_with_role(role_map, "villager", players)
        kill_target = villagers[0] if villagers else first_with_role(role_map, "seer", players)

        night_acts = _build_night_acts(
            role_map, players,
            wolf_target_id=kill_target["player_id"],
            seer_target_id=wolf["player_id"],
        )

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(client, game_id, players, display_ws)
            day_msg = drive_night(client, game_id, players, display_ws, night_acts)

        na = day_msg.get("state", {}).get("night_actions", {})
        assert na.get("seer_result") is None

    def test_wolf_sees_own_role_non_null(self, client):
        """Wolf's WS sync shows their own role as 'werewolf' (non-null)."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)
        wolf = first_with_role(role_map, "werewolf", players)

        with client.websocket_connect(f"/ws/{game_id}/{wolf['player_id']}") as ws:
            ws.send_json({"type": "auth", "session_token": wolf["session_token"]})
            sync_msg = ws.receive_json()

        wolf_view_player = sync_msg["state"]["players"][wolf["player_id"]]
        assert wolf_view_player["role"] == "werewolf"

    def test_villager_sees_only_own_role(self, client):
        """Villager's WS sync shows own role, others as null."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)
        villagers = players_with_role(role_map, "villager", players)

        if not villagers:
            pytest.skip("No villager in this composition")

        villager = villagers[0]
        with client.websocket_connect(f"/ws/{game_id}/{villager['player_id']}") as ws:
            ws.send_json({"type": "auth", "session_token": villager["session_token"]})
            sync_msg = ws.receive_json()

        v_pid = villager["player_id"]
        state_players = sync_msg["state"]["players"]
        assert state_players[v_pid]["role"] == "villager"
        for pid, p in state_players.items():
            if pid != v_pid:
                assert p["role"] is None, (
                    f"Villager view exposed role={p['role']!r} for {pid}"
                )

    def test_host_secret_never_in_any_broadcast(self, client):
        """The host_secret value must never appear in any WebSocket broadcast."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)

        messages_collected = []
        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            messages_collected.append(display_ws.receive_json())  # sync
            drive_role_deal(client, game_id, players, display_ws)
            try:
                messages_collected.append(display_ws.receive_json())
            except Exception:
                pass

        for msg in messages_collected:
            assert host_secret not in str(msg), (
                f"host_secret leaked in broadcast"
            )


# ─────────────────────────────────────────────────────────────────────────────
# TestStateIdFence
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestStateIdFence:

    def test_stale_state_id_rejected(self, client):
        """Sending an intent with a stale state_id returns STALE_STATE error."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)
        wolf = first_with_role(role_map, "werewolf", players)
        villagers = players_with_role(role_map, "villager", players)
        target = villagers[0] if villagers else first_with_role(role_map, "seer", players)

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(client, game_id, players, display_ws)

        with client.websocket_connect(f"/ws/{game_id}/{wolf['player_id']}") as ws:
            ws.send_json({"type": "auth", "session_token": wolf["session_token"]})
            sync_msg = ws.receive_json()
            current_state_id = sync_msg["state_id"]

            ws.send_json({
                "type": "submit_night_action",
                "target_id": target["player_id"],
                "state_id": current_state_id - 1,  # stale
            })
            resp = ws.receive_json()

        assert resp.get("code") == "STALE_STATE"

    def test_correct_state_id_accepted(self, client):
        """Sending an intent with the exact current state_id is accepted."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)
        wolf = first_with_role(role_map, "werewolf", players)
        villagers = players_with_role(role_map, "villager", players)
        target = villagers[0] if villagers else first_with_role(role_map, "seer", players)

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(client, game_id, players, display_ws)

            # Keep wolf WS open to avoid disconnect bumping state_id
            with client.websocket_connect(f"/ws/{game_id}/{wolf['player_id']}") as ws:
                ws.send_json({"type": "auth", "session_token": wolf["session_token"]})
                sync_msg = ws.receive_json()
                current_state_id = sync_msg["state_id"]

                ws.send_json({
                    "type": "submit_night_action",
                    "target_id": target["player_id"],
                    "state_id": current_state_id,
                })
                resp = ws.receive_json()

        assert resp.get("code") != "STALE_STATE", (
            f"Correct state_id was unexpectedly rejected: {resp}"
        )

    def test_missing_state_id_accepted(self, client):
        """Intent without state_id field bypasses the fence and is accepted."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)
        wolf = first_with_role(role_map, "werewolf", players)
        villagers = players_with_role(role_map, "villager", players)
        target = villagers[0] if villagers else first_with_role(role_map, "seer", players)

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(client, game_id, players, display_ws)

            with client.websocket_connect(f"/ws/{game_id}/{wolf['player_id']}") as ws:
                ws.send_json({"type": "auth", "session_token": wolf["session_token"]})
                ws.receive_json()  # sync

                ws.send_json({
                    "type": "submit_night_action",
                    "target_id": target["player_id"],
                    # No state_id field
                })
                resp = ws.receive_json()

        assert resp.get("code") != "STALE_STATE"


# ─────────────────────────────────────────────────────────────────────────────
# TestMultiRoundLoop
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestMultiRoundLoop:

    def _drive_one_round(self, client, game_id, players, role_map, display_ws,
                         wolf_target_id, vote_target_id):
        """
        Drive one complete NIGHT → DAY → DAY_VOTE cycle.
        Returns the post-vote broadcast.
        """
        wolf = first_with_role(role_map, "werewolf", players)
        seer = first_with_role(role_map, "seer", players)

        # Build night acts — auto-fills doctor
        night_acts = _build_night_acts(
            role_map, players,
            wolf_target_id=wolf_target_id,
            seer_target_id=(wolf["player_id"] if seer else None),
        )

        day_msg = drive_night(client, game_id, players, display_ws, night_acts)
        if day_msg["state"]["phase"] != "day":
            return day_msg

        drive_to_day_vote(client, game_id, players, display_ws)

        alive_pids = get_alive_pids(day_msg["state"])
        _vote_everyone_for(client, game_id, players, alive_pids, vote_target_id)

        return consume_until(
            display_ws,
            lambda m: m.get("state", {}).get("phase") in (
                "night", "game_over", "hunter_pending"
            ),
            max_messages=50,
        )

    def test_two_rounds_increment_round_counter(self, client):
        """
        After ROLE_DEAL→NIGHT→DAY→VOTE the game enters Night2 with round==1.
        Round starts at 0 for the first NIGHT (transitioned from ROLE_DEAL, excluded
        from increment).  It increments to 1 on the second NIGHT entry.
        """
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)
        wolf = first_with_role(role_map, "werewolf", players)
        villagers = players_with_role(role_map, "villager", players)

        if len(villagers) < 2:
            pytest.skip("Need at least 2 villagers for a 2-round test")

        v1, v2 = villagers[0], villagers[1]

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(client, game_id, players, display_ws)

            # Round 1: wolf kills v1, village votes out v2
            result = self._drive_one_round(
                client, game_id, players, role_map, display_ws,
                wolf_target_id=v1["player_id"],
                vote_target_id=v2["player_id"],
            )

        if result["state"]["phase"] == "night":
            # round=0 for Night1 (from ROLE_DEAL), increments to 1 for Night2
            assert result["state"]["round"] == 1
        else:
            pytest.skip("Did not reach NIGHT 2 — game ended or hunter_pending")

    def test_night_actions_reset_between_rounds(self, client):
        """Round 2 NIGHT shows actions_submitted_count == 0 (reset on NIGHT entry)."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)
        villagers = players_with_role(role_map, "villager", players)

        if len(villagers) < 2:
            pytest.skip("Need at least 2 villagers for a 2-round test")

        v1, v2 = villagers[0], villagers[1]

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync
            drive_role_deal(client, game_id, players, display_ws)

            result = self._drive_one_round(
                client, game_id, players, role_map, display_ws,
                wolf_target_id=v1["player_id"],
                vote_target_id=v2["player_id"],
            )

        if result["state"]["phase"] == "night":
            na = result["state"]["night_actions"]
            assert na["actions_submitted_count"] == 0, (
                f"Expected 0 submitted at start of NIGHT 2, "
                f"got {na['actions_submitted_count']}"
            )
        else:
            pytest.skip("Did not reach NIGHT 2")
