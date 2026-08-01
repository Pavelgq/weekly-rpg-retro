# Weekly RPG Retro 🎲

A Claude skill that turns weekly reflection into an RPG campaign: you are the
character, Claude is the Game Master. Under the hood — the classic agile
retrospective structure (five stages, checking last week's action items,
experiments against recurring problems). On top — lore, stats, bosses, and
achievements, so the ritual is one you want to repeat instead of abandoning
after a month.

The GM speaks whatever language you speak.

## What it looks like

Once a week you tell Claude "let's run my weekly session". The Game Master:

1. opens your character sheet and tells you **itself** what worries it —
   sagging stats, bosses growing stronger, the fate of last week's quests;
2. asks questions one at a time (what was valuable, what drained you, what you
   learned, what got done for the main quests, when you felt proud) and reacts
   to each answer in two layers: narrative + an honest observation about the
   pattern;
3. proposes its own interpretation of the week: stat deltas, achievements,
   bosses moving between stages;
4. helps you pick 1–3 small quests for the coming week;
5. closes with a "GM's observation" and writes everything to files.

## Core mechanics

**Personal stats.** No fixed set — during onboarding the Game Master derives
4–6 stats from your goals and values. The starting value comes from a 1–100
self-assessment; after that, weekly deltas of ±1…3. No silent minuses: the GM
must voice and discuss every decline.

**Bosses.** A recurring difficulty is a boss with a stage and a level. The
cycle mirrors a retrospective loop: **Spotted → Studied** (a hypothesis about
the trigger) **→ Fighting** (a one-week experiment quest) **→ Retreating →
Defeated**. If a boss sits without an experiment for three weeks, or returns
after a victory, it **grows stronger**: its level rises and the GM raises it at
the start of the session. A conscious "not fighting this one right now" is
recorded in the decision register and freezes the level.

**Closing the loop.** Every session starts with the fate of last week's quests.
"Not done" is material for observation, not for guilt: the campaign's Prime
Directive is that the character acted in the best way they could given what
they knew, the resources they had, and the state they were in.

**Quarterly review.** Every ~12 weeks — the view from above: progress on the
main quests, how fast bosses get defeated, the rating trend, the shift in how
the character speaks about themselves, and next quarter's goals.

## Installation

A skill is a folder with a `SKILL.md`. Put it where your Claude looks for
skills:

- **Claude Code**: `.claude/skills/weekly-rpg-retro/` inside the campaign
  repository (or `~/.claude/skills/` for all projects);
- **Claude.ai / Cowork**: upload `SKILL.md` to a chat and click "Save skill",
  or add it via Settings → Capabilities → Skills.

## Important: the campaign needs a folder

The skill describes the process, but the state (profile, character sheet, week
logs) lives in files. Create a dedicated directory or repository for the
campaign — and run sessions where Claude can reach it: Claude Code, Cowork, or
a chat with a connected GitHub repository. In a plain chat with no file system,
the campaign won't survive between conversations.

The structure the skill maintains on its own:

```
my-campaign/
├── profile.md            # setting, goals, values, your stat set
├── character_sheet.md    # current state: stats, bosses, achievements
├── week1_log.md          # one log per week
├── week2_log.md
└── quarter1_review.md    # quarter summaries
```

See [`examples/`](examples/) for a fictional sample profile and week log that
show the intended tone and format.

## Quick start

1. Create an empty campaign folder/repository and install the skill.
2. Tell Claude: **"Let's set up my campaign"** — the Game Master runs
   onboarding (~20 minutes): a setting to your taste, main quests for the
   quarter, your values, known adversaries, your personal stats.
3. A week later: **"Let's run my weekly session."** Full format ~30 minutes,
   short ~15.

The skill never launches itself — only when you ask.

## Philosophy

- A retrospective that never checks past decisions is an empty ritual.
- Bosses describe a recurring difficulty, not a character flaw.
- Lore is packaging: every GM line must carry a real observation, not just
  atmosphere.
- A small quest doable under any shape of week beats a big plan.

## License

MIT — take it, adapt it, play it.
