# Attribution and lesson format (step 7)

Step 3's gate shows that an edit breaks nothing; it cannot show that the edit helps. Step 7a is
where the loop finds out, once real engagements have run on the edited text. Step 7b turns those
rows into lessons. Without 7a, meta lessons rest on gate verdicts alone and the loop cannot tell
an edit that worked from one that only passed.

## 7a. Which edits get a row

An edit is eligible when all of these hold:

- an earlier `### CYCLE` block lists it under `Accepted`, and it was applied to the corpus (not
  rolled back). Its apply date is that CYCLE's date; `#<n>` is its position in the Accepted
  list (CYCLE blocks number them `(1)…(n)`);
- at least one engagement has run since that date in which the agent reached the edited text;
- its latest `### ATTRIBUTION` row is `confounded`, or it has no row yet.

An engagement that ran the target agent but never reached the edited section (a different branch
of the skill, an early stop) does not count: no row, the edit stays eligible.

Read what ran since the apply date: later `### SIGNAL` entries and reflections in the log, and
those engagements' `engagement-reflections.md`, `acceptance-log.md` and executor reports. Find
the point where the agent applied, skipped or tripped over the edited text.

## Verdicts

| Verdict | When | Final? |
|---|---|---|
| `helped` | At least two engagements show the agent applying the edited text, and the failure the edit targeted did not recur where the old text let it through. Cite both points. | yes |
| `hurt` | A later failure traces to the edited text itself. | yes |
| `no observed effect` | The agent reached the edited text and the behaviour did not change, or the targeted class recurred. | yes |
| `confounded` | Several edits from the same cycle touch the behaviour and nothing isolates one; one engagement is all that stands behind the difference; or the agent's model or tier changed in between. Prefer it whenever one of these holds: an invented attribution misleads every later cycle that reads it. | no, revisited |

Gate PASS, promotion and the human's merge are not evidence that an edit helped.

`hurt` and `no observed effect` must reach step 1 of a later cycle, which reads signals, not
attribution rows. If the failure or the recurrence is already a `### SIGNAL` in the log, cite it
in `observed:`. Otherwise mint one, keeping that engagement and its evidence, so it is counted
once: `rule_wrong` on the target for `hurt`, the targeted class for `no observed effect`.

`no observed effect` records the outcome, not the cause. Before the next edit, bucket the cause
as step 5 does for `persistent_fail`. Recurrence alone does not make it `rule_ignored`: a
structural fix needs evidence that correct text was skipped or unreachable.

## Row format

Appended to `skill-evolution-log.md`. The header is not `### SIGNAL`, so the readiness checkers
skip it.

```
### ATTRIBUTION | domain: <domain> | YYYY-MM-DD | by: <director or session>
edit: <CYCLE date> #<n> | <target> | <what the edit changed, one line>
observed: <engagement(s) + the point where behaviour diverged or did not; SIGNAL cited or minted>
verdict: helped | hurt | no observed effect | confounded
```

Rows are not edited later. When a later engagement isolates a `confounded` edit, write a new row
with the final verdict.

## 7b. Lesson format

At most one new lesson in the shared section and one in the domain section per cycle:

```
- cue: <the shape of optimisation situation it applies to, not this cycle's facts>
  lesson: <the editing operation to perform, naming the kind of target it concerns>
  evidence: <the attribution rows, gate verdicts or rollbacks it rests on>
  confidence: high | medium — <why>
```

- `high`: two or more final attribution rows agree.
- `medium`: one final attribution row, or this cycle's gate verdicts and rollback agreeing with
  each other.
- Anything less is a guess, including a lesson resting only on `confounded` rows or on a single
  gate verdict: narrow it to what the record shows, or write none.

Aim between too generic to change an edit ("write clearer rules") and too specific to fire again
(one sentence of one file). When no record supports a lesson, record `NO_ENTRY: <why>`: in the
`### CYCLE` block on the interactive path, in the META result's `detail` on the workflow path. A
cycle with nothing to learn is a normal outcome, and the line keeps it distinguishable from a
cycle that skipped the step. When a cycle keeps an older free-form lesson, rewrite it in this
format in the same pass.
