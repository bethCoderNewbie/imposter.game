# ADR-002: Framer Dual-Target Architecture — Deferred False Hint Injection

## Status
Proposed

## Date
2026-03-26

## Context

The Framer Archives Hack feature (PRD-004) requires that the Framer's `hack_archives` night action inject a fabricated `HintPayload` into the Archives puzzle system. The core architectural question is:

**At what point in the night does the false hint fire, and to whom is it delivered?**

The Framer's action resolves at step 2 of `nightResolutionOrder` — early in the pipeline, before puzzles are solved. Puzzle solves happen asynchronously during the night phase window, driven by player interaction on Mobile devices. This creates a timing mismatch: the Framer commits to a false hint at step 2, but the delivery target (which `wakeOrder=0` players solve their puzzle) is not known until later.

Two additional questions drive the decision:

1. **Should the Framer know who received the false hint?** (Information asymmetry)
2. **Should injection be targeted (one player) or broadcast (all solvers)?** (Attack surface)

---

## Decision

### Chosen: Deferred Broadcast Injection via Queued Payload

The server queues the false hint at step 2 as a server-only `FalseHintPayload` in `MasterGameState`. The hint delivery handler — which runs when any `wakeOrder=0` player successfully solves their puzzle — checks `false_hint_queued` and substitutes the queued payload for the real one.

**Delivery target:** All `wakeOrder=0` players who solve a puzzle that round receive the same false hint. Injection is not targeted at a specific player.

**Framer confirmation:** The Framer receives no feedback about delivery. They never learn if any Villager solved a puzzle or received the false hint.

**`is_fabricated` flag:** The server-internal `FalseHintPayload` carries `is_fabricated: true` for audit logging. This field is stripped before unicast delivery. The client receives a schema-identical standard `HintPayload` with no fabrication indicator.

**Tracker behavior:** When the Framer hacks Archives, `framer_target_id` is `null`. The Tracker observing the Framer sees `tracker_result: []` — consistent with "no player targeted." No new Tracker logic is needed.

**Phase reset:** `false_hint_queued` and `false_hint_payload` are reset at the start of each new night phase, regardless of whether any delivery occurred.

---

## Rejected Alternatives

### Alternative 1: Synchronous Delivery at Step 2 (Unconditional)

Deliver the false hint to all `wakeOrder=0` players immediately at resolution step 2, without requiring puzzle completion.

**Rejected because:**
- It breaks the puzzle-reward loop. Villagers who did not solve receive a hint they did not earn. This makes The Archives feel broken — players learn that hints arrive regardless of effort.
- It removes the strategic uncertainty for the wolf team ("did the Villagers even solve tonight?"). The Framer's action becomes a guaranteed broadcast, which is more powerful than intended.
- It requires the server to enumerate `wakeOrder=0` players and unicast to each at resolution time — a more complex delivery path than the existing hint handler.

### Alternative 2: Targeted Injection (Framer Picks a Specific Villager)

The Framer selects a specific player to receive the false hint, rather than broadcasting to all solvers.

**Rejected because:**
- It requires the Framer to know — or guess — which players have `wakeOrder=0` (i.e., are Villager/Mayor/Jester rather than a special role). This is a role inference leak. The Framer should not have a mechanism to confirm another player's role.
- Targeted injection is trivially exploitable: wolves always target the most vocal day-phase player, amplifying their influence over discussion. Broadcast injection applies pressure uniformly and does not give wolves targeted intelligence.
- The Framer already has one targeted ability (frame a player). Adding a second targeted ability in the same role creates an asymmetric power spike.

---

## Consequences

**Positive:**
- No new WebSocket message types. The `hint_reward` unicast already exists; the false hint uses the same channel.
- The `HintPayload` schema is unchanged. Clients require no update to handle false hints — they are schema-identical.
- A single boolean check (`false_hint_queued`) in the existing hint delivery handler is the only new branching logic.
- Clean separation of concerns: step 2 commits to the lie; the puzzle solver triggers the delivery. The two events are independent.

**Negative:**
- If no `wakeOrder=0` player solves their puzzle that round, the Framer's Archives hack is wasted with no effect. This is intentional — it creates meaningful strategic risk. The wolf team must judge whether village puzzle engagement is high enough to make the hack worthwhile.
- A Framer who hacks Archives cannot also frame a player that round. Wolves must coordinate: use the Framer for Archives on rounds when the Seer is less of a threat (e.g., Seer is dead or roleblocked by the Wolf Shaman).
- Two `wakeOrder=0` players solving in the same round both receive the identical false hint (same `hint_id`). This is detectable if players compare hints during the day. This is acceptable — the risk of comparison is a counterbalance to the Framer's power.

---

## Implementation Notes

### `nightResolutionOrder` step 2 — branch on `framer_action`

```python
# resolve_night() step 2
if framer.is_roleblocked:
    pass  # no-op — both paths skipped

elif night_actions.framer_action == "frame":
    players[night_actions.framer_target_id].is_framed_tonight = True

elif night_actions.framer_action == "hack_archives":
    G.false_hint_queued = True
    G.false_hint_payload = FalseHintPayload(
        hint_id=uuid4(),
        category=night_actions.false_hint_category,
        text=night_actions.false_hint_text,
        round=G.round,
        expires_after_round=None,
        is_fabricated=True,           # server-only; stripped before delivery
    )
```

### Hint delivery handler — check queue before generating real hint

```python
# deliver_hint(player_id, G) — called when wakeOrder=0 player solves puzzle
if G.false_hint_queued:
    payload = strip_fabricated_flag(G.false_hint_payload)
else:
    payload = generate_real_hint(player_id, G)

unicast(player_id, payload)
record_hint_delivered(player_id, payload.hint_id, G)
```

### Stripping `is_fabricated`

```python
def strip_fabricated_flag(false_hint: FalseHintPayload) -> HintPayload:
    return HintPayload(
        type=false_hint.type,
        hint_id=false_hint.hint_id,
        category=false_hint.category,
        text=false_hint.text,
        round=false_hint.round,
        expires_after_round=false_hint.expires_after_round,
        # is_fabricated intentionally excluded
    )
```

---

## Preset Template UX Decision

**Decision: Preset templates are stored client-side as a static array. The server never receives a `template_id`.**

The Framer submits a `hack_archives` intent with `false_hint_category` and `false_hint_text` — the same two fields regardless of whether a preset or custom input was used. The server has no knowledge of which preset (if any) the Framer selected.

**Why presets:**

The night phase runs under a countdown timer. Crafting a false hint from scratch — choosing a category, picking a role from a dropdown, reading the preview — can consume 15–20 seconds under social pressure. Without presets, the Framer risks either submitting a hasty and unconvincing lie or running out of time and having their action discarded.

Preset templates also allow wolf-team coordination during the day phase ("if you get a hack opportunity tonight, use the No Seer template — we need to discredit p7"). Without shared template IDs, this coordination requires the Framer to memorize phrasing verbatim.

**Why client-side only:**

Server-side template registry introduces a maintenance surface: templates would need versioning, validation, and a fetch endpoint. The same result is achieved by embedding the static array in the Mobile client bundle — it ships with the app and requires no network round-trip. The rendered `false_hint_text` string is the only thing the server processes.

**Rejected alternative: Server-side template registry with `template_id` field in the intent.**

This would allow server-side analytics ("which template was used most often"), but introduces a new endpoint, a new intent field, and schema coupling between the client template list and the server validator. The analytics benefit does not justify the complexity for a party game with ephemeral Redis sessions.

**The 10 shipped presets** (see PRD-004 §2.2.1 for the full table with strategic intent):

| `template_id` | Short label | Rendered text |
|--------------|------------|---------------|
| `wolf_count_one` | Only 1 Wolf | "There is only 1 Wolf in this game." |
| `wolf_count_two` | 2 Wolves | "There are 2 Wolves total in this game." |
| `wolf_count_four` | 4 Wolves | "There are 4 Wolves total in this game." |
| `no_doctor` | No Doctor | "There is NO Doctor in this game." |
| `no_seer` | No Seer | "There is NO Seer in this game." |
| `no_tracker` | No Tracker | "There is NO Tracker in this game." |
| `no_alpha` | No Alpha Wolf | "There is NO Alpha Wolf in this game." |
| `sk_present` | SK exists | "There IS a Serial Killer in this game." |
| `alpha_present` | Alpha exists | "There IS an Alpha Wolf in this game." |
| `infector_present` | Infector exists | "There IS an Infector in this game." |
