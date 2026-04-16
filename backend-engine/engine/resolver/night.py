"""
Night resolver: 13-step deterministic night resolution engine.
Pure function — no I/O, no side effects.
"""

from __future__ import annotations

import random

from engine.resolver._win import check_win_condition
from engine.roles_loader import ROLE_REGISTRY
from engine.state.enums import EliminationCause, InvestigationResult, Phase
from engine.state.models import EliminationEvent, MasterGameState


def resolve_night(G: MasterGameState) -> MasterGameState:
    """
    Execute all 13 night resolution steps deterministically.
    Returns a new MasterGameState with all results applied.
    """
    G = G.model_copy(deep=True)

    G = _step0_lunatic_curse(G)
    G = _step1_roleblock(G)
    G = _step2_framer(G)
    G = _step3_cupid(G)
    G = _step4_infector(G)
    G = _step4b_witch(G)
    G = _step5_doctor(G)
    G = _step6_seer(G)
    G = _step6b_lunatic_redirect(G)
    G, infect_cancelled_wolf_kill = _step7_wolf_kill_or_infect(G)
    G = _step8_arsonist(G)
    G = _step9_serial_killer(G)
    G = _step10_lovers_death_chain(G)
    G = _step11_tracker(G)
    G = _step12_hunter_queue(G)
    if not G.hunter_queue:
        G = check_win_condition(G)

    return G


# ── Step 0: Lunatic curse (carry-over from previous night) ───────────────────

def _step0_lunatic_curse(G: MasterGameState) -> MasterGameState:
    """
    If a wolf was cursed by the Lunatic last night, they die at the start of
    this night — before any other actions, including roleblock.
    Bypasses Doctor protection.
    """
    wolf_pid = G.lunatic_cursed_wolf_id
    if not wolf_pid:
        return G
    G.lunatic_cursed_wolf_id = None  # consume regardless of outcome
    wolf = G.players.get(wolf_pid)
    if not wolf or not wolf.is_alive:
        return G
    wolf.is_alive = False
    G.elimination_log.append(EliminationEvent(
        round=G.round,
        phase="night",
        player_id=wolf_pid,
        cause=EliminationCause.LUNATIC_CURSE,
    ))
    return G


# ── Step 1: Wolf Shaman roleblock ──────────────────────────────────────────────

def _step1_roleblock(G: MasterGameState) -> MasterGameState:
    target_id = G.night_actions.roleblock_target_id
    if not target_id:
        return G
    # Wolf Shaman must not be roleblocked itself (only one roleblock source exists)
    G.night_actions.roleblocked_player_id = target_id
    return G


# ── Step 2: Framer ─────────────────────────────────────────────────────────────

def _step2_framer(G: MasterGameState) -> MasterGameState:
    framer_action = G.night_actions.framer_action
    if not framer_action:
        return G
    # Check if framer is roleblocked
    framer_pid = _find_role_player(G, "framer")
    if framer_pid and framer_pid == G.night_actions.roleblocked_player_id:
        return G  # action discarded if hex'd

    if framer_action == "frame":
        target_id = G.night_actions.framer_target_id
        if target_id and target_id in G.players:
            G.players[target_id].is_framed_tonight = True

    elif framer_action == "hack_archives":
        # Queue false hint — delivery triggered on puzzle solve by wakeOrder==0 player
        if G.night_actions.false_hint_payload is not None:
            G.night_actions.false_hint_queued = True
        # else: payload missing (malformed state) — silent no-op

    return G


# ── Step 3: Cupid (round 1 only, unblockable) ─────────────────────────────────

def _step3_cupid(G: MasterGameState) -> MasterGameState:
    if G.round != 1:
        return G
    if G.village_powers_cursed:
        cupid_pid = _find_role_player(G, "cupid")
        if cupid_pid and G.players[cupid_pid].team == "village":
            return G
    link = G.night_actions.cupid_link
    if not link or len(link) != 2:
        return G
    pid_a, pid_b = link[0], link[1]
    if pid_a not in G.players or pid_b not in G.players:
        return G
    G.lovers_pair = [pid_a, pid_b]
    G.players[pid_a].lovers_partner_id = pid_b
    G.players[pid_b].lovers_partner_id = pid_a
    return G


# ── Step 4: Infector ───────────────────────────────────────────────────────────

def _step4_infector(G: MasterGameState) -> MasterGameState:
    infector_pid = _find_role_player(G, "infector")
    if not infector_pid:
        return G
    target_id = G.night_actions.infector_target_id
    if not target_id:
        return G
    if infector_pid == G.night_actions.roleblocked_player_id:
        return G
    player = G.players.get(target_id)
    if not player or not player.is_alive:
        return G
    # Mark for conversion — actual conversion applied in step 7
    # (Infector uses maxUses=1 — server tracks infect_used)
    infector = G.players.get(infector_pid)
    if infector and not infector.infect_used:
        infector.infect_used = True
    return G


# ── Step 4b: Witch ────────────────────────────────────────────────────────────

def _step4b_witch(G: MasterGameState) -> MasterGameState:
    """
    Witch resolves after Infector but before Doctor.
    Heal sets is_protected=True (stacks with Doctor, saves from wolf kill).
    Kill eliminates the target immediately, bypassing is_protected.
    Skipped if the Witch is roleblocked or village powers are cursed.
    """
    witch_pid = _find_role_player(G, "witch")
    if not witch_pid:
        return G
    if witch_pid == G.night_actions.roleblocked_player_id:
        return G
    if G.village_powers_cursed and G.players[witch_pid].team == "village":
        return G
    target_id = G.night_actions.witch_target_id
    action = G.night_actions.witch_action
    if not target_id or not action:
        return G
    target = G.players.get(target_id)
    if not target or not target.is_alive:
        return G
    witch = G.players[witch_pid]
    if action == "heal":
        target.is_protected = True
        witch.witch_heal_used = True
    elif action == "kill":
        target.is_alive = False
        G.elimination_log.append(EliminationEvent(
            round=G.round,
            phase="night",
            player_id=target_id,
            cause=EliminationCause.WITCH_KILL,
        ))
        witch.witch_kill_used = True
    return G


# ── Step 5: Doctor ─────────────────────────────────────────────────────────────

def _step5_doctor(G: MasterGameState) -> MasterGameState:
    doctor_pid = _find_role_player(G, "doctor")
    if not doctor_pid:
        return G
    if G.village_powers_cursed and G.players[doctor_pid].team == "village":
        return G
    if doctor_pid == G.night_actions.roleblocked_player_id:
        # Roleblock prevented protection — clear consecutive-protect memory so the
        # doctor is not falsely locked out of the same target next night.
        doctor = G.players.get(doctor_pid)
        if doctor:
            doctor.last_protected_player_id = None
        return G
    target_id = G.night_actions.doctor_target_id
    if not target_id:
        return G
    doctor = G.players.get(doctor_pid)
    target = G.players.get(target_id)
    if not doctor or not target or not target.is_alive:
        return G
    # Consecutive-protect ban: cannot protect same player two nights in a row
    if doctor.last_protected_player_id == target_id:
        return G  # rejected — handler should have caught this, but double-check here
    target.is_protected = True
    doctor.last_protected_player_id = target_id
    return G


# ── Step 6: Seer ───────────────────────────────────────────────────────────────

def _step6_seer(G: MasterGameState) -> MasterGameState:
    seer_pid = _find_role_player(G, "seer")
    if not seer_pid:
        return G
    if G.village_powers_cursed and G.players[seer_pid].team == "village":
        return G
    if seer_pid == G.night_actions.roleblocked_player_id:
        return G
    target_id = G.night_actions.seer_target_id
    if not target_id:
        return G
    target = G.players.get(target_id)
    if not target:
        return G

    # Framer override: if target is framed tonight → result forced to "wolf"
    if target.is_framed_tonight:
        result = InvestigationResult.WOLF
    else:
        # Use role's investigationResult from role registry
        role_def = ROLE_REGISTRY.get(target.role or "", {})
        inv_result_str = role_def.get("investigationResult", "village")
        result = InvestigationResult(inv_result_str)

    G.night_actions.seer_result = result
    G.seer_knowledge[target_id] = result.value
    return G


# ── Step 6b: Lunatic redirect ─────────────────────────────────────────────────

def _step6b_lunatic_redirect(G: MasterGameState) -> MasterGameState:
    """
    If the Lunatic activated redirect this night and wolves have a valid majority kill:
    - Kill the Lunatic (bypasses protection — voluntary sacrifice)
    - Curse the lead wolf (first wolf who voted for the kill target); they die next night
    - Clear wolf_votes so step 7 has no kill to process
    No-op if:
      - No Lunatic in game / Lunatic is dead
      - Lunatic did not submit redirect
      - Lunatic is roleblocked
      - Wolves have no majority kill target
      - Infector is converting this night (no kill to redirect)
    """
    lunatic_pid = _find_role_player(G, "lunatic")
    if not lunatic_pid:
        return G
    if not G.night_actions.lunatic_redirect:
        return G
    if lunatic_pid == G.night_actions.roleblocked_player_id:
        return G

    # If Infector is converting this night, there is no wolf kill to redirect
    infector_pid = _find_role_player(G, "infector")
    if (
        infector_pid
        and G.night_actions.infector_target_id
        and G.players[infector_pid].infect_used
        and infector_pid != G.night_actions.roleblocked_player_id
    ):
        return G

    # Determine wolves' kill target
    wolf_votes = G.night_actions.wolf_votes
    if not wolf_votes:
        return G

    vote_counts: dict[str, int] = {}
    for _, voted_target in wolf_votes.items():
        vote_counts[voted_target] = vote_counts.get(voted_target, 0) + 1

    total_wolves = len(wolf_votes)
    kill_target = max(vote_counts, key=lambda t: vote_counts[t])
    if vote_counts[kill_target] <= total_wolves / 2:
        return G  # tie — no kill to redirect

    # Valid majority kill exists — execute redirect
    lunatic = G.players[lunatic_pid]
    lunatic.is_alive = False
    lunatic.lunatic_redirect_used = True
    G.elimination_log.append(EliminationEvent(
        round=G.round,
        phase="night",
        player_id=lunatic_pid,
        cause=EliminationCause.LUNATIC_SACRIFICE,
    ))

    # Curse the first wolf who voted for the kill target — they die next night
    for wolf_pid, voted_target in wolf_votes.items():
        if voted_target == kill_target:
            G.lunatic_cursed_wolf_id = wolf_pid
            break

    # Cancel the wolf kill so step 7 finds nothing to do
    G.night_actions.wolf_votes = {}
    return G


# ── Step 7: Wolf kill or Infector convert ─────────────────────────────────────

def _apply_wolf_kill(
    G: MasterGameState,
    target_id: str,
    cause: EliminationCause,
    attacker_pid: str | None = None,
) -> tuple[MasterGameState, bool]:
    """
    Apply a wolf-team kill attempt with the given cause.
    Protection sequence: Wise shield → Doctor → Bodyguard 50/50 → SK immunity.
    Returns (G, killed).
    attacker_pid is the wolf to die if the Bodyguard's coin flip eliminates the attacker.
    """
    target = G.players.get(target_id)
    if not target or not target.is_alive:
        return G, False

    # Wise one-use shield: deflects first wolf kill (disabled if village powers are cursed)
    if target.role == "wise" and not target.wise_shield_used and not G.village_powers_cursed:
        target.wise_shield_used = True
        return G, False  # silently deflected

    # Doctor protection check
    if target.is_protected:
        return G, False  # saved silently

    # Bodyguard protection: 50/50 — attacker dies OR bodyguard dies, target always survives
    bodyguard_pid = _find_role_player(G, "bodyguard")
    if (
        bodyguard_pid
        and G.night_actions.bodyguard_target_id == target_id
        and bodyguard_pid != G.night_actions.roleblocked_player_id
        and not (G.village_powers_cursed and G.players[bodyguard_pid].team == "village")
    ):
        rng = random.Random(f"{G.seed}_{G.round}_bodyguard")
        if rng.random() < 0.5:
            # Attacker dies
            if attacker_pid:
                attacker = G.players.get(attacker_pid)
                if attacker and attacker.is_alive:
                    attacker.is_alive = False
                    G.elimination_log.append(EliminationEvent(
                        round=G.round,
                        phase="night",
                        player_id=attacker_pid,
                        cause=EliminationCause.BODYGUARD_KILL,
                    ))
        else:
            # Bodyguard dies — unless Doctor also protected the Bodyguard
            bodyguard = G.players[bodyguard_pid]
            if bodyguard.is_alive and not bodyguard.is_protected:
                bodyguard.is_alive = False
                G.elimination_log.append(EliminationEvent(
                    round=G.round,
                    phase="night",
                    player_id=bodyguard_pid,
                    cause=EliminationCause.BODYGUARD_SACRIFICE,
                ))
        return G, False  # target always survives

    # Serial Killer is immune to wolf kills
    if target.role == "serial_killer":
        return G, False

    target.is_alive = False
    G.elimination_log.append(EliminationEvent(
        round=G.round,
        phase="night",
        player_id=target_id,
        cause=cause,
    ))
    return G, True


def _step7_wolf_kill_or_infect(G: MasterGameState) -> tuple[MasterGameState, bool]:
    """Returns (G, infect_cancelled_wolf_kill)."""
    infector_pid = _find_role_player(G, "infector")
    target_id = G.night_actions.infector_target_id

    # If Infector has a valid, non-roleblocked target → convert (no kill)
    if (
        infector_pid
        and target_id
        and infector_pid != G.night_actions.roleblocked_player_id
        and G.players.get(infector_pid, None) is not None
        and G.players[infector_pid].infect_used
    ):
        target = G.players.get(target_id)
        if target and target.is_alive:
            target.role = "werewolf"
            target.team = "werewolf"
            return G, True  # wolf kill cancelled

    # ── Charge kill takes priority over vote kill ──────────────────────────────
    charge_target_id = G.night_actions.charge_kill_target_id
    if charge_target_id:
        attacker_pid = next(
            (pid for pid, p in G.players.items() if p.is_alive and p.team == "werewolf"),
            None,
        )
        G, _ = _apply_wolf_kill(G, charge_target_id, EliminationCause.GRID_CHARGE_KILL, attacker_pid)
        G.night_actions.charge_kill_target_id = None
        return G, False  # charge kill doesn't interact with infector

    # ── Vote-tally logic ───────────────────────────────────────────────────────
    wolf_votes = G.night_actions.wolf_votes
    if not wolf_votes:
        return G, False

    # Count votes per target
    vote_counts: dict[str, int] = {}
    for wolf_pid, voted_target in wolf_votes.items():
        vote_counts[voted_target] = vote_counts.get(voted_target, 0) + 1

    total_wolves = len(wolf_votes)
    # Strict majority: count > total_wolves / 2
    kill_target = max(vote_counts, key=lambda t: vote_counts[t])
    if vote_counts[kill_target] <= total_wolves / 2:
        return G, False  # tie — no kill

    # Attacker for Bodyguard flip: first wolf who voted for the kill target
    attacker_pid = next(
        (pid for pid, voted in wolf_votes.items() if voted == kill_target),
        None,
    )
    G, _ = _apply_wolf_kill(G, kill_target, EliminationCause.WOLF_KILL, attacker_pid)
    return G, False


# ── Step 8: Arsonist ───────────────────────────────────────────────────────────

def _step8_arsonist(G: MasterGameState) -> MasterGameState:
    arsonist_pid = _find_role_player(G, "arsonist")
    if not arsonist_pid:
        return G
    if arsonist_pid == G.night_actions.roleblocked_player_id:
        return G

    action = G.night_actions.arsonist_action
    if action == "douse":
        douse_target = G.night_actions.arsonist_douse_target_id
        if douse_target and douse_target in G.players:
            arsonist = G.players[arsonist_pid]
            if douse_target not in arsonist.doused_player_ids:
                arsonist.doused_player_ids.append(douse_target)

    elif action == "ignite":
        arsonist = G.players[arsonist_pid]
        for doused_pid in list(arsonist.doused_player_ids):
            player = G.players.get(doused_pid)
            if player and player.is_alive:
                player.is_alive = False
                G.elimination_log.append(EliminationEvent(
                    round=G.round,
                    phase="night",
                    player_id=doused_pid,
                    cause=EliminationCause.ARSONIST_IGNITE,
                ))

    return G


# ── Step 9: Serial Killer ──────────────────────────────────────────────────────

def _step9_serial_killer(G: MasterGameState) -> MasterGameState:
    sk_pid = _find_role_player(G, "serial_killer")
    if not sk_pid:
        return G
    if sk_pid == G.night_actions.roleblocked_player_id:
        return G

    target_id = G.night_actions.serial_killer_target_id
    if not target_id:
        return G
    target = G.players.get(target_id)
    if not target or not target.is_alive:
        return G

    # SK ignores Doctor protection (immuneToWolfKill doesn't protect SK kill from Doctor)
    target.is_alive = False
    G.elimination_log.append(EliminationEvent(
        round=G.round,
        phase="night",
        player_id=target_id,
        cause=EliminationCause.SERIAL_KILLER,
    ))
    return G


# ── Step 10: Lovers death-chain ───────────────────────────────────────────────

def _step10_lovers_death_chain(G: MasterGameState) -> MasterGameState:
    if not G.lovers_pair:
        return G
    pid_a, pid_b = G.lovers_pair[0], G.lovers_pair[1]
    player_a = G.players.get(pid_a)
    player_b = G.players.get(pid_b)
    if not player_a or not player_b:
        return G

    a_dead = not player_a.is_alive
    b_dead = not player_b.is_alive

    if a_dead and player_b.is_alive:
        player_b.is_alive = False
        G.elimination_log.append(EliminationEvent(
            round=G.round, phase="night", player_id=pid_b, cause=EliminationCause.BROKEN_HEART,
        ))
    elif b_dead and player_a.is_alive:
        player_a.is_alive = False
        G.elimination_log.append(EliminationEvent(
            round=G.round, phase="night", player_id=pid_a, cause=EliminationCause.BROKEN_HEART,
        ))
    return G


# ── Step 11: Tracker ──────────────────────────────────────────────────────────

def _step11_tracker(G: MasterGameState) -> MasterGameState:
    tracker_pid = _find_role_player(G, "tracker")
    if not tracker_pid:
        return G
    if G.village_powers_cursed and G.players[tracker_pid].team == "village":
        return G
    if tracker_pid == G.night_actions.roleblocked_player_id:
        G.tracker_knowledge[str(G.round)] = []
        return G

    target_id = G.night_actions.tracker_target_id
    if not target_id:
        return G

    # Framer hack_archives: Tracker sees [] (hack is invisible)
    if G.night_actions.framer_action == "hack_archives":
        G.tracker_knowledge[str(G.round)] = []
        G.night_actions.tracker_result = []
        return G

    # Collect all player IDs who visited (targeted) the tracked player
    visited: list[str] = []
    na = G.night_actions

    # Wolves who voted to kill the tracked player
    for wolf_pid, kill_target in (na.wolf_votes or {}).items():
        if kill_target == target_id:
            visited.append(wolf_pid)
    # Seer who inspected the tracked player
    seer_pid = _find_role_player(G, "seer")
    if na.seer_target_id == target_id and seer_pid:
        visited.append(seer_pid)
    # Doctor who protected the tracked player
    doctor_pid = _find_role_player(G, "doctor")
    if na.doctor_target_id == target_id and doctor_pid:
        visited.append(doctor_pid)
    # Serial Killer who targeted the tracked player
    sk_pid = _find_role_player(G, "serial_killer")
    if na.serial_killer_target_id == target_id and sk_pid:
        visited.append(sk_pid)
    # Arsonist who doused the tracked player
    arsonist_pid = _find_role_player(G, "arsonist")
    if na.arsonist_douse_target_id == target_id and arsonist_pid:
        visited.append(arsonist_pid)
    # Witch who targeted the tracked player
    witch_pid = _find_role_player(G, "witch")
    if na.witch_target_id == target_id and witch_pid:
        visited.append(witch_pid)

    unique_visited = list(dict.fromkeys(visited))  # preserve order, deduplicate
    G.night_actions.tracker_result = unique_visited
    G.tracker_knowledge[str(G.round)] = unique_visited
    return G


# ── Step 12: Hunter queue ─────────────────────────────────────────────────────

def _step12_hunter_queue(G: MasterGameState) -> MasterGameState:
    """If any Hunter was eliminated this night, queue them for revenge."""
    night_log = [e for e in G.elimination_log if e.round == G.round and e.phase == "night"]
    for event in night_log:
        player = G.players.get(event.player_id)
        if player and player.role == "hunter" and not player.hunter_fired:
            if G.village_powers_cursed and player.team == "village":
                continue  # village powers disabled — hunter revenge blocked
            if event.player_id not in G.hunter_queue:
                G.hunter_queue.append(event.player_id)
    if G.hunter_queue:
        G.phase = Phase.HUNTER_PENDING
        G.timer_ends_at = None  # timer set by transition_phase caller
    return G


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_role_player(G: MasterGameState, role_id: str) -> str | None:
    """Return the player_id of the first living player with the given role, or None."""
    for pid, player in G.players.items():
        if player.role == role_id and player.is_alive:
            return pid
    return None
