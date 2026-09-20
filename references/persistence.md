# Session persistence

Use `scripts/session_store.py` from the installed skill directory. Python 3.9+
with a POSIX filesystem (macOS/Linux), standard library only. It operates on the
campaign directory explicitly provided; never save personal campaign data in the
public skill repository.

## Workflow

1. Run `status --campaign /absolute/campaign`. A `prepared` record means an
   interrupted save: run `recover --week N` before reading aggregate totals.
   A `draft` means resume its payload/conversation, not a missed week. The helper
   does not retrieve chats: use available host tools if the user identifies one.
2. After the first substantive answer, create an incomplete payload containing
   `week`, `source`, and `notes` with reported events, chosen focus, unresolved
   questions and corrections. Run `draft --input /path/payload.json`. Checkpoint
   after each substantive answer. This writes only `.retro/sessions/weekN.json`.
3. At closing, complete the payload below with accepted conclusions, stat
   evidence/criterion versions, and full target Markdown documents. Preserve
   unrelated existing content. Read the current files before preparing targets.
4. Run `draft`, then `validate`, then `commit --week N`, then `validate` again.
   All take `--campaign /absolute/campaign`. Only report a saved session after
   the final validation passes. `history.csv` is generated, never hand-appended.
5. If interrupted after preparation, run `recover --week N`. Repeating a completed
   commit is a no-op, even after later weeks; it never reapplies deltas.

Example commands (replace paths):

```sh
python3 /path/to/skill/scripts/session_store.py draft --campaign /path/to/campaign --input /path/to/payload.json
python3 /path/to/skill/scripts/session_store.py validate --campaign /path/to/campaign --week 1
python3 /path/to/skill/scripts/session_store.py commit --campaign /path/to/campaign --week 1
python3 /path/to/skill/scripts/session_store.py validate --campaign /path/to/campaign --week 1
```

## Completed payload

```json
{
  "week": 1,
  "date_start": "2026-01-05",
  "date_end": "2026-01-11",
  "rating": 4,
  "source": "Current conversation, closing summary accepted by user",
  "notes": {
    "facts": ["User reports two early bedtimes"],
    "hypotheses": [],
    "pending": []
  },
  "stats": [
    {
      "id": "rest_boundaries",
      "label": "🔥 Rest boundaries",
      "before": 40,
      "delta": 1,
      "after": 41,
      "criterion_version": "v1",
      "evidence": "User reports two bedtimes at the preselected time; v1 small-action criterion."
    }
  ],
  "artifacts": {
    "week1_log.md": "# Week 1\n\nReported events, explained deltas, supports, decisions and accepted experiment cards.\n",
    "character_sheet.md": "# Character sheet\n\n- 🔥 Rest boundaries: 41 (start 40)\n",
    "achievements.md": "# Achievements\n\nNo new achievements this session.\n",
    "supports.md": "# Working supports\n\nNo confirmed support added yet.\n",
    "gm_feedback.md": "# GM feedback\n\nNo corrections this session.\n"
  }
}
```

Include every existing stat/specialization in the same column order as history,
including zero deltas. A specialization label can be `🤝 Connections → ⚔️ Negotiation`.
The character sheet must contain exactly one `- LABEL: TOTAL` line per stat.
The specialization's points are already included in the parent delta.
`rating` may be null if the user supplied none; never invent it.
Use `evidence: "Unknown this session; total unchanged"` for unobserved stats.
Optional artifacts: `profile.md`, `supports.md`, `gm_feedback.md`. Update the
profile only for authorized criterion/preference changes. Put accepted quest
cards in the log; do not invent missing details to pass numeric validation.
The helper checks file/numeric consistency, not the truth of observations or
whether the user accepted an interpretation; those remain the GM's responsibility.

## Recovery and conflict handling

The session record stores the baseline, final payload, target artifacts, and a
payload checksum before touching campaign outputs. Each file is replaced
atomically; the multi-file save is **recoverable, not globally atomic**. Readers
must check session status first. A process lock serializes helper invocations;
it does not lock out a text editor or another program that ignores the lock.

Recovery accepts only baseline or already-written target contents. An unexpected
edit stops the save before any further writes. Do not force it, delete the edit,
or replace the record to bypass this check. Inspect the conflict and reconcile
with its author; keep a backup before any user-authorized manual repair.
A changed completed record or artifact is reported as a validation failure.
Correct a historical factual claim in a later session and `gm_feedback.md`, with
the source session and superseded claim explicitly cited; update current
aggregate summaries through that session. Do not edit the old completed record
or log in place. Apply these later correction notes when reading old logs.

Incomplete drafts are intentionally allowed. A draft whose aggregate baseline
has changed needs explicit reconciliation; do not discard its conversation notes.
Do not modify a prepared record in place: finish or reconcile the interrupted
transaction first. Records contain personal data, including baseline copies;
apply the same access controls as the campaign itself.

## Existing campaigns

The first helper-managed session can follow an existing `history.csv`; historical
rows are preserved, including legacy ratings such as `2-3`. Verify the latest
log and sheet against history before starting. If history is absent or incomplete,
rebuild it from actual logs with provenance first; do not invent missing weeks.
If a log already exists for the proposed session, reconcile it instead of overwriting.

Criterion revisions do not change historical scores: keep the old definition in
profile, add its replacement with the effective session, and store the applicable
version in each new record. New stat IDs require an explicit schema migration before drafting, preserving
old columns/values and keeping blanks where historical measurements do not exist.
Include a `baseline_reason` recording the user-authorized initial value and a
profile update for a new stat whose previous history value is blank. Retired
columns remain as zero-delta historical totals; display names may change without
renaming stable IDs. Do not force a schema migration as part of
an ordinary weekly review. Historical logs and criterion changes remain auditable.

If execution is unavailable, preserve a portable draft and explain that a
validated save could not complete. Do not claim that ordinary chat alone provides
persistent files or silently skip validation.
