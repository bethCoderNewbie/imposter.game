/** All tooltip copy for the Night Grid + Wolf Radar feature.
 *  Keep each string ≤ 2 short sentences. Plain language — no jargon. */

// ── Grid (Villager side) ──────────────────────────────────────────────────────

export const TOOLTIP_GRID_OVERVIEW =
  "Data Nodes you can solve for intelligence clues. " +
  "Tap a node to start a puzzle — but beware, the Wolves can detect when one is completed."

export const TOOLTIP_NODE_GREEN =
  "5-second puzzle. " +
  "Earns a Tier 1 clue: general info about the game's roles and composition."

export const TOOLTIP_NODE_YELLOW =
  "10-second puzzle. " +
  "Earns a Tier 2 clue: a relational hint that links two players by alignment."

export const TOOLTIP_NODE_RED =
  "20-second puzzle. " +
  "Earns the most powerful intel — but the Wolves' radar is almost certainly watching this spot."

export const TOOLTIP_NODE_COMPLETED =
  "Already solved tonight. Pick another node."

// ── Radar (Wolf side) ─────────────────────────────────────────────────────────

export const TOOLTIP_RADAR_OVERVIEW =
  "Shows where Villagers are solving puzzles. " +
  "Ripples fire live the moment a node is completed."

export const TOOLTIP_HEAT_NUMBER =
  "How many puzzles have been completed in this area tonight."

export const TOOLTIP_RIPPLE_COLORS =
  "Ripple color = hint tier earned. " +
  "Green = basic info, Yellow = player links, Red = powerful intel — act fast."

export const TOOLTIP_PING_OVERVIEW =
  "Scan a quadrant to see exactly how many nodes were solved and at what tier. " +
  "Your pack shares 4 pings per night."

export const TOOLTIP_PING_RESULT =
  "T1 = general hint, T2 = relational clue, T3 = someone now knows a confirmed-safe player. " +
  "Counter it during the day."

export const TOOLTIP_PING_BUDGET =
  "All wolves share this budget. " +
  "Once it's gone, rely on live ripples for the rest of the night."
