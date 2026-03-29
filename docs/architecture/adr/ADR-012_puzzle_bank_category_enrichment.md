# ADR-012: Werewolf — Puzzle Bank Category Enrichment (4-Option Logic Puzzles)

## Status
Accepted

## Date
2026-03-29

## Context

The Archive puzzle system (`engine/puzzle_bank.py`) draws trivia questions from `puzzles.md` — a 400-entry Q&A bank organized into 11 named category sections (Classic Riddles, Geography & Nature, Science & Technology, History & Pop Culture, Food & Drink, Technology & Math, Food & Cooking, Travel & Geography, History & Art, Pop Culture, Animals & Nature).

The current parser (`BANK: list[tuple[str, str]]`) discards the category headers entirely — only `(question, answer)` pairs are retained:

```python
BANK = re.findall(r"\*\*Q:\*\* (.+?) \*\*A:\*\* (.+)", text)
```

The current `_make_logic_puzzle` function draws **one correct answer and one random distractor** from the full bank, producing a 2-option (binary) question:

```python
options = [correct_answer, distractor]  # 50% blind guess rate
```

Two problems result:

1. **Trivial guess rate.** A player who has no idea can guess correctly 50% of the time. In practice, logic puzzles are won by chance as often as by knowledge. The Archive puzzle is meant to be a meaningful cognitive decoy — binary guessing undermines this.

2. **Implausible distractors.** A distractor drawn from the full bank may be semantically unrelated to the question. For example, a riddle about a piano might show the distractor "Photosynthesis" — immediately identifiable as wrong by any player, collapsing the puzzle to a trivial match. Plausible distractors (other riddle answers, other geography facts) make elimination harder.

Both problems are solvable by:
- Parsing `puzzles.md` category headers to tag each entry
- Switching to 4-option puzzles with same-category distractors

---

## Decision

### 1. Parse category metadata from `puzzles.md`

Replace the single-pass regex with a line-by-line parser that tracks the current category header:

```python
# New representation
_BankEntry = tuple[str, str, str]   # (question, answer, category)
BANK: list[_BankEntry] = [...]
BANK_BY_CATEGORY: dict[str, list[int]] = {}  # category → indices into BANK
```

Category headers are lines matching `**Category Name**` or `### **Category Name**`. The parser assigns each Q&A entry the most recently seen header. All 400 entries are categorized across 11 sections.

The 11 categories and their approximate sizes:

| Category | Entries |
|---|---|
| Classic Riddles | 20 |
| Geography & Nature | 20 |
| Science & Technology | 20 |
| History & Pop Culture | 20 |
| Food, Drink & General Knowledge | 20 |
| Technology, Science & Math | 50 |
| Food, Drink & Cooking | 50 |
| Travel & Geography | 50 |
| History & Art | 50 |
| Pop Culture, Movies & Music | 50 |
| Animals & Nature | 50 |

Minimum category size: 20. Selecting 3 distractors from a 20-entry category (with 1 already used as the question) leaves 19 peers — sufficient.

### 2. Expand logic puzzles to 4 options with same-category distractors

`_make_logic_puzzle` picks 3 distractors from the **same category** as the chosen question:

```python
q_idx = rng.randrange(len(BANK))
question, correct_answer, category = BANK[q_idx]

# Peer indices: same category, not the question itself
peers = [i for i in BANK_BY_CATEGORY[category] if i != q_idx]
distractor_indices = rng.sample(peers, min(3, len(peers)))
distractors = [BANK[i][1] for i in distractor_indices]

# Pad with cross-category if the category had fewer than 3 peers (never happens with 20+ entries, but handled)
while len(distractors) < 3:
    d_idx = rng.randrange(len(BANK))
    if d_idx != q_idx and BANK[d_idx][1] not in distractors:
        distractors.append(BANK[d_idx][1])

options = [correct_answer] + distractors
rng.shuffle(options)
correct_index = options.index(correct_answer)
```

Result: `answer_options` becomes a 4-element array. Blind guess rate drops from 50% → 25%. Distractors are domain-coherent (e.g., a capitals question will have other capital cities as wrong answers, not "Metamorphosis").

### 3. Time limit unchanged at 20 seconds

20 seconds is adequate for a 4-option recognition task. The sequence puzzle (30 s) and math puzzle (15 s) time limits are unaffected. No `roles.json` changes needed.

### 4. `puzzle_data` schema is backward-compatible

The `answer_options` field is already a `list[str]` of variable length. The frontend `VillagerDecoyUI.tsx` renders it with `options.map(...)` — no frontend change needed. The `correct_index` stripping rule is unchanged.

### 5. Option "keep 2-option format" is rejected

A 2-option format was reasonable when the puzzle bank was small. With 400 categorized entries across 11 semantic domains, 4-option same-category puzzles are achievable with trivial implementation cost. Keeping 2-option format provides no advantage and leaves the guessing-exploit open.

---

## Implementation

### File: `backend-engine/engine/puzzle_bank.py`

**Replace** the `BANK` regex parser (lines 22–25) with a category-aware line-by-line parser:

```python
_BankEntry = tuple[str, str, str]  # (question, answer, category)

def _parse_bank(text: str) -> tuple[list[_BankEntry], dict[str, list[int]]]:
    bank: list[_BankEntry] = []
    by_category: dict[str, list[int]] = {}
    current_category = "Uncategorized"
    header_re = re.compile(r"^\s*(?:#{1,3}\s+)?\*\*([^*\d][^*]*)\*\*\s*$")
    qa_re = re.compile(r"\*\*Q:\*\*\s+(.+?)\s+\*\*A:\*\*\s+(.+)")
    for line in text.splitlines():
        header_match = header_re.match(line)
        if header_match:
            current_category = header_match.group(1).strip()
            continue
        qa_match = qa_re.search(line)
        if qa_match:
            idx = len(bank)
            bank.append((qa_match.group(1), qa_match.group(2), current_category))
            by_category.setdefault(current_category, []).append(idx)
    return bank, by_category

BANK, BANK_BY_CATEGORY = _parse_bank(_PUZZLES_MD.read_text(encoding="utf-8"))
```

**Replace** `_make_logic_puzzle` to use 4 options with same-category distractors.

### No other file changes

| File | Change |
|---|---|
| `puzzle_bank.py` | Parser + `_make_logic_puzzle` only |
| `engine/state/models.py` | None — `answer_options: list[str]` already variable-length |
| `engine/stripper.py` | None — `correct_index` stripping unchanged |
| `api/intents/handlers.py` | None — answer validation by index is length-agnostic |
| `frontend-mobile/` | None — `options.map(...)` renders any length |
| `frontend-display/` | None — display client never sees puzzle content |

---

## Consequences

### Positive

- **Blind guess rate 50% → 25%.** Logic puzzles become meaningful cognitive tasks.
- **Domain-coherent distractors.** Same-category answers are plausible wrong options — e.g., a geography question shows other capitals, not animal names.
- **All 400 entries fully utilized.** Category metadata that was previously discarded is now exploited. No entries are wasted.
- **Zero frontend changes.** `answer_options` length is already dynamic.
- **Determinism preserved.** `rng.sample(peers, 3)` is reproducible given the same seed.

### Negative

- **`BANK` type changes** from `list[tuple[str, str]]` to `list[tuple[str, str, str]]`. Any test or code accessing `BANK[i][0]` and `BANK[i][1]` continues to work; `BANK[i][2]` is the new category field. Tests asserting `len(BANK[q_idx]) == 2` would fail.
- **Tests asserting `len(answer_options) == 2`** must be updated to `== 4`.

### No impact on

- Math puzzles (procedurally generated, no BANK lookup)
- Sequence puzzles (color-based, no BANK lookup)
- Hint generation (`generate_hint` does not use BANK)
- Framer false hint delivery
- Night phase timing or resolution order
