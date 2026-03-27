# PRD-004: Werewolf — Framer Archives Hack

## §1. Context & Purpose

**Feature:** Framer Archives Hack
**Depends on:** PRD-001 §2 (Framer role), `roles.json` (Framer definition), PRD-002 §3.4 (Mobile Night Phase), `roles.json` `archivePuzzleSystem`, `data_dictionary.md` `HintPayload`

The Framer currently has one night action mode: choose a player, and if the Seer inspects that player tonight, they appear as Werewolf. This is a direct counter to the Seer.

This PRD extends the Framer with a **second mode**: instead of framing a player, the Framer can **hack The Archives** — the Villager night puzzle system (introduced in `roles.json` `archivePuzzleSystem`). When the Framer hacks The Archives, any `wakeOrder=0` player who solves their puzzle that round receives the Framer's **fabricated hint** instead of a real one.

**The false hint is indistinguishable from a real hint.** Same `HintPayload` schema, same Mobile UI rendering. Villagers have no mechanism to detect fabrication.

**Trade-off:** Choosing to hack Archives means the Framer does NOT frame a player that round. The wolves must decide each night: suppress the Seer, or corrupt the village's intelligence network.

**Architecture decision:** See ADR-002 (`docs/architecture/adr/ADR-002_framer_dual_target_architecture.md`).

---

## §2. Mechanic Specification

### §2.1 Framer Action Choice

Each night the Framer submits exactly one `framer_action`. The two modes are mutually exclusive.

| `framer_action` | Effect | Existing behavior? |
|----------------|--------|-------------------|
| `"frame"` | Sets `is_framed_tonight = true` on `target_id`. Seer inspecting that player sees `"werewolf"` regardless of true `investigationResult`. | Yes — unchanged |
| `"hack_archives"` | Sets `false_hint_queued = true` in `MasterGameState`. Stores crafted `false_hint_payload` (server-only). No player is framed. | New |

The `framer_target_id` field is only populated when `framer_action == "frame"`. When hacking Archives, `framer_target_id` is `null`.

### §2.2 False Hint Crafting

The Framer crafts the false hint text before submitting. They choose from a **restricted subset** of hint categories — composition-based categories only. Behavioral categories (`seer_blocked_last_night`, `neutral_exists`) cannot be fabricated because they reference prior-round server events the Framer cannot control.

| Allowed category | Template | Framer input |
|-----------------|----------|-------------|
| `wolf_count` | `"There are {N} Wolves total in this game."` | Choose N: integer 1–6 |
| `no_role_present` | `"There is NO {role_name} in this game."` | Choose role name from high-impact list |
| `role_present` | `"There IS a {role_name} in this game."` | Choose role name from high-impact list |

**High-impact role list** (roles worth lying about): `alpha_wolf`, `framer`, `infector`, `doctor`, `tracker`, `serial_killer`, `arsonist`.

#### §2.2.1 Preset Templates

Ten pre-crafted templates are available as Quick Pick options in the Framer's UI. Each template has a `template_id` (static, client-side), a pre-filled category, and a pre-filled text string. The Framer can tap a preset to auto-fill the builder, then submit immediately or adjust the parameter before injecting.

Presets are organized by strategic intent to help wolves make fast decisions under night-timer pressure.

| # | `template_id` | Category | Rendered text | Strategic intent |
|---|--------------|----------|---------------|-----------------|
| 1 | `wolf_count_one` | `wolf_count` | "There is only 1 Wolf in this game." | Breeds complacency — village hunts less aggressively, assumes the threat is small |
| 2 | `wolf_count_two` | `wolf_count` | "There are 2 Wolves total in this game." | Safe undercount for any game with 3+ wolves; plausible enough to believe |
| 3 | `wolf_count_four` | `wolf_count` | "There are 4 Wolves total in this game." | Overcount panic — village suspects everyone, votes split unpredictably, chaos benefits wolves |
| 4 | `no_doctor` | `no_role_present` | "There is NO Doctor in this game." | Village abandons attempts to identify or protect the Doctor; wolves plan kills without fear of a save |
| 5 | `no_seer` | `no_role_present` | "There is NO Seer in this game." | Discredits the real Seer if they reveal info — "but the clue said there's no Seer here" |
| 6 | `no_tracker` | `no_role_present` | "There is NO Tracker in this game." | Wolves act more boldly; real Tracker's evidence is dismissed as impossible during day discussion |
| 7 | `no_alpha` | `no_role_present` | "There is NO Alpha Wolf in this game." | Village overtrusts every "village" Seer result; the real Alpha Wolf hides in unquestioned safety |
| 8 | `sk_present` | `role_present` | "There IS a Serial Killer in this game." | Village suspects neutral players and wastes day votes eliminating non-wolves |
| 9 | `alpha_present` | `role_present` | "There IS an Alpha Wolf in this game." | Village questions every Seer "village" result — even real innocents — and the real Alpha Wolf hides in the doubt |
| 10 | `infector_present` | `role_present` | "There IS an Infector in this game." | Conversion paranoia — village second-guesses any player who changes behavior or opinion overnight |

**Presets are client-side only.** They are a static array in the Framer's Mobile client component. The server never receives the `template_id` — only the resolved `false_hint_category` and `false_hint_text` fields. No new endpoint or server-side template registry is needed.

**Custom input remains available.** After selecting a preset, the Framer can still adjust the parameter (e.g., change the wolf count from 2 to 3, or swap the role name) before submitting. Presets pre-fill, not lock, the builder.

**Server does NOT validate truth.** The server queues whatever the Framer crafts without checking whether it is actually false. If the Framer accidentally crafts a true hint, it is delivered as-is. The wolves are responsible for constructing a plausible lie. This design keeps server logic simple and introduces human error as a game factor.

### §2.3 Delivery Pipeline (Deferred Injection)

The false hint is not delivered at step 2 of `nightResolutionOrder`. It is **queued** and fires later — only when a `wakeOrder=0` player successfully solves their Archives puzzle.

Resolution sequence:

```
Night phase begins
  └─ Framer submits hack_archives + false hint text
        └─ Step 2 (resolve_night): false_hint_queued = true; false_hint_payload stored (server-only)

During night phase (concurrent with resolution):
  └─ wakeOrder=0 player solves puzzle
        └─ hint_delivery_handler checks false_hint_queued
              ├─ true  → deliver false_hint_payload to solving player (is_fabricated stripped)
              └─ false → generate and deliver real hint (existing behavior)

Night phase ends → false_hint_queued reset to false; false_hint_payload cleared
```

All `wakeOrder=0` puzzle-solvers that round receive the **same** false hint — injection is not targeted at a specific player.

If no `wakeOrder=0` player solves a puzzle that round, `false_hint_queued` is cleared unused. The Framer's action is wasted. This is intentional — it creates strategic risk for the wolf team.

### §2.4 Constraints

| Constraint | Behavior |
|-----------|----------|
| **Roleblock (Wolf Shaman hex)** | If the Framer is roleblocked this round, their submitted `framer_action` is discarded at step 1. No player is framed and no Archives hack occurs. |
| **Tracker observation** | When the Framer hacks Archives, the Tracker (if tracking the Framer) sees `tracker_result: []` — an empty array. `"archives"` is not a player ID and is not reported as a target. The hack is **invisible to the Tracker**, identical to a `wakeOrder=0` player with no action. |
| **No delivery confirmation** | The Framer never learns whether any Villager solved a puzzle or received the false hint. Information flows one way: Framer → server → (possibly) Villager. |
| **Max uses** | `null` — unlimited. The Framer may hack Archives every round. |
| **Simultaneous solvers** | If two `wakeOrder=0` players both solve puzzles in the same night, both receive the same `false_hint_payload` (same `hint_id`, same text). This is by design — consistent misinformation across the village. |
| **Balance weight** | Unchanged at `-3`. Archives hack is a trade-off: the Framer gains an influence vector against the archive system but loses the ability to corrupt the Seer that round. Net power is approximately equivalent. |

---

## §3. UI Specification

### §3.1 Framer Mobile Night Screen

The Framer's night screen becomes a two-step flow.

**Step 1 — Mode selection**

```
┌─────────────────────────────────────────────┐
│  [moon icon]  Night  [dim white]            │
│                                             │
│        "What is your move tonight?"         │
│              [dim, small text]              │
│                                             │
│  ┌───────────────────┐ ┌─────────────────┐  │
│  │  Frame a Player   │ │ Hack the        │  │
│  │  [red border]     │ │ Archives        │  │
│  │                   │ │ [amber border]  │  │
│  └───────────────────┘ └─────────────────┘  │
└─────────────────────────────────────────────┘
```

- Background: `#0a0e1a` (night substrate) — anti-cheat constraint from `archivePuzzleSystem.antiCheatConstraint` maintained.
- Glass panel: `--glass-bg` token (PRD-003 §5). Same silhouette as wolf vote screen.
- "Frame a Player" button: border `--role-wolf: #e53e3e` (dim, not bright enough to read at distance).
- "Hack the Archives" button: border `--timer-warning: #f6ad55` (amber, PRD-003 §5).
- Tapping either button advances to Step 2. No confirm required at Step 1.

**Step 2a — Frame a Player (existing flow)**

Unchanged from current Framer behavior: scrollable living-player list, tap to select, `"Frame"` confirm button.

**Step 2b — Hack the Archives**

```
┌─────────────────────────────────────────────┐
│         "Craft your false clue"             │
│              [dim, small text]              │
│                                             │
│  Quick Pick: ──────────────────────────     │
│  ┌──────────────┐ ┌──────────────────────┐  │
│  │ Only 1 Wolf  │ │ No Doctor in game    │  │
│  └──────────────┘ └──────────────────────┘  │
│  ┌──────────────┐ ┌──────────────────────┐  │
│  │ No Seer here │ │ Serial Killer exists │  │
│  └──────────────┘ └──────────────────────┘  │
│  [ + 6 more... ]  (horizontal scroll)       │
│                                             │
│  ── or build your own ──────────────────    │
│  Category:  [ There IS a ▾ ]               │
│  Role:      [ Doctor       ▾ ]             │
│                                             │
│  Preview:                                   │
│  "There IS a Doctor in this game."          │
│  [dim italic, amber color]                  │
│                                             │
│            [ Inject Hint ]                  │
│         [amber, full-width button]          │
└─────────────────────────────────────────────┘
```

- **Quick Pick strip:** horizontally scrollable row of chip buttons, one per preset (§2.2.1). Tapping a chip pre-fills the Category and Parameter pickers below and renders the Preview immediately. The Framer can submit as-is or adjust before injecting.
  - Chip label: short form of the rendered text (e.g., `"Only 1 Wolf"`, `"No Doctor in game"`, `"SK exists"`).
  - Max 4 chips visible without scrolling. Scroll indicator `"+ 6 more..."` at the right edge.
  - No chip is pre-selected on screen entry — builder starts empty.
- **Category picker:** dropdown — `"There are {N} Wolves"` / `"There is NO {role}"` / `"There IS a {role}"`.
- **Parameter picker:** context-sensitive — number stepper 1–6 for wolf count; role name dropdown for role categories. Role list: `alpha_wolf, framer, infector, doctor, tracker, serial_killer, arsonist`.
- **Preview line:** live-rendered. Updates as category or parameter changes. Color: `--timer-warning: #f6ad55` (amber — visually suggests "caution / fabricated").
- **"Inject Hint"** button: disabled until category + parameter are filled (either via Quick Pick or manual entry). Submits the intent. Haptic: 300ms pattern on submit (matching wolf pack confirm pattern).
- **After submit:** idle state shows `"False clue injected. Let the chaos begin."` in dim amber.

### §3.2 Villager / Mayor / Jester Mobile Night Screen — No Change

The Villager's Archives puzzle screen and hint display are **unchanged**. The `HintPayload` delivered by a Framer hack is schema-identical to a real hint. The Mobile client renders it identically. Villagers have no UI indicator that a hint may be fabricated.

This is a deliberate design constraint. Adding any "hint confidence" indicator would give Villagers a detection mechanism that doesn't exist in the physical card game.

---

## §4. Server State JSON Examples

All fields shown are server-internal. Stripped versions sent to clients are noted inline.

### §4.1 Normal Round — Framer Frames a Player

```jsonc
// Round 2, Night — Framer chose "frame". No Archives hack queued.
// Villager p1 solves puzzle → receives REAL hint from composition truth.
{
  "phase": "night",
  "round": 2,

  // NightActions (server-internal)
  "night_actions": {
    "framer_action": "frame",          // server-only
    "framer_target_id": "p4",          // server-only
    "false_hint_queued": false,        // server-only
    "false_hint_payload": null,        // server-only
    "wolf_votes": { "p2": "p7", "p5": "p7" },
    "seer_target_id": "p4",
    "seer_result": "werewolf"          // p4 is framed → Seer forced to see "werewolf"
  },

  // Unicast to p1 after puzzle solve — REAL hint
  "_hint_unicast_to_p1": {
    "type": "hint_reward",
    "hint_id": "a1b2c3d4-real-0001",
    "category": "wolf_count",
    "text": "There are 3 Wolves total in this game.",
    "round": 2,
    "expires_after_round": null
    // is_fabricated field does NOT appear — this is the stripped client payload
  }
}
```

### §4.2 Framer Hacks Archives — False Hint Queued and Delivered

```jsonc
// Round 3, Night — Framer chose "hack_archives".
// No player is framed. False hint queued server-side.
// Villager p1 solves puzzle → receives FALSE hint.
// Actual composition has NO Doctor.
{
  "phase": "night",
  "round": 3,

  // NightActions (server-internal — never sent to any client as-is)
  "night_actions": {
    "wolf_votes": { "p2": "p7", "p5": "p7" },
    "roleblock_target_id": null,
    "seer_target_id": "p6",
    "seer_result": "village",
    "doctor_target_id": null,           // no Doctor in this game

    "framer_action": "hack_archives",  // server-only
    "framer_target_id": null,          // no player framed this round
    "false_hint_queued": true,         // server-only

    // Server-internal FalseHintPayload — is_fabricated stripped before unicast
    "false_hint_payload": {
      "type": "hint_reward",
      "hint_id": "fh-9x2k5m7n-fabricated",
      "category": "role_present",
      "text": "There IS a Doctor in this game.",
      "round": 3,
      "expires_after_round": null,
      "is_fabricated": true            // server-only flag — NEVER sent to client
    },

    "tracker_target_id": "p3",         // Tracker is following the Framer (p3)
    "tracker_result": [],              // Framer targeted "archives" not a player → empty
    "actions_submitted_count": 5,
    "actions_required_count": 6
  },

  // p1 (Villager) solves puzzle.
  // hint_delivery_handler: false_hint_queued == true → substitute false_hint_payload.
  // is_fabricated stripped. p1 receives:
  "_hint_unicast_to_p1": {
    "type": "hint_reward",
    "hint_id": "fh-9x2k5m7n-fabricated",  // same hint_id as server record
    "category": "role_present",
    "text": "There IS a Doctor in this game.",
    "round": 3,
    "expires_after_round": null
    // is_fabricated absent — client payload is schema-identical to a real HintPayload
  },

  // Actual game composition (truth the village will never know from this hint):
  "_composition_truth": {
    "werewolf": 2, "alpha_wolf": 1, "framer": 1, "seer": 1,
    "villager": 3, "jester": 1, "tracker": 1
    // "doctor": 0 — the false hint claims otherwise
  }
}
```

### §4.3 Framer Hacks Archives — No Puzzle Solved (Wasted Action)

```jsonc
// Round 4, Night — Framer hacks Archives, but no Villager solves a puzzle in time.
// false_hint_queued is set but no delivery occurs. Cleared at phase end.
{
  "phase": "night",
  "round": 4,
  "night_actions": {
    "framer_action": "hack_archives",
    "framer_target_id": null,
    "false_hint_queued": true,
    "false_hint_payload": {
      "type": "hint_reward",
      "hint_id": "fh-wasted-0002",
      "category": "wolf_count",
      "text": "There are 2 Wolves total in this game.",
      "round": 4,
      "expires_after_round": null,
      "is_fabricated": true
    }
    // No puzzle solved this round → false_hint_payload never unicast
    // At phase transition: false_hint_queued reset to false, false_hint_payload = null
  }
}
```

---

## §5. Resolution Order Impact

`nightResolutionOrder` step 2 is unchanged in sequence position. Its effect branches on `framer_action`:

```
Step 2 — framer → manipulate_or_hack
  if framer_action == "frame" AND framer not roleblocked:
    players[framer_target_id].is_framed_tonight = true
    (existing path — Seer at step 6 will see "werewolf")

  if framer_action == "hack_archives" AND framer not roleblocked:
    MasterGameState.false_hint_queued = true
    MasterGameState.false_hint_payload = { crafted payload from intent }
    (no player state is modified)

  if framer roleblocked (Wolf Shaman hex):
    no-op — both paths skipped
```

Steps 3–13 are unaffected.

---

## §6. User Stories

| As a | I want to | So that |
|------|-----------|---------|
| Mobile Player (Framer) | choose each night between framing a player or hacking The Archives | I can adapt my strategy — suppress the Seer on some rounds, corrupt village intelligence on others |
| Mobile Player (Framer) | craft a specific false hint from a template before submitting | I can design misinformation that exploits the village's current suspicions |
| Mobile Player (Villager) | receive a hint that looks identical regardless of its source | I must rely on cross-referencing hints with other players, not on visual cues |
| Game Server | queue the false hint at step 2 and deliver it only when a puzzle is solved | the injection is decoupled from resolution order and fires at the correct moment |
| Game Server | strip `is_fabricated: true` from the payload before unicast delivery | the receiving client has no programmatic way to detect fabrication |
| Game Server | return `tracker_result: []` when the Framer hacks Archives | the Tracker receives no information that reveals the Archives hack occurred |

---

## §7. Open Questions

| # | Question | Status |
|---|----------|--------|
| 1 | Should the Framer's hack be a limited resource (e.g., 2 uses per game) to balance against unlimited framing? | Open — current spec is unlimited. |
| 2 | If both a Framer and a real hint would be delivered in the same round (e.g., Framer hacks but another system also generates hints), which wins? | Resolved — false hint always wins (`false_hint_queued` check is the first branch). |
| 3 | Should the Display TV show any indication that "hint system may be compromised"? | Open — current spec: Display is never told about hint content or integrity. |
