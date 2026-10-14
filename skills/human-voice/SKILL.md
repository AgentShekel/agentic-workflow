---
name: human-voice
domain: meta
description: |
  Rules for Russian text a human will read: what makes agency output sound machine-written,
  and which of those rules survive a change of medium. Covers intake questions, chat replies,
  lead plans, manager verdicts, consilium summaries, human-readable docs and RU copy. Applies
  as a constraint on generation, not as a rewriting pass over finished text.

  Use when: writing or reviewing any Russian text a person reads (intake questions, план,
  вердикт, отчёт, README, лендинг, письмо); loaded by human-facing agents via skills
  frontmatter; also "проверь текст на нейрослоп", "почему текст звучит как ИИ".
---

# human-voice

Derived from the analysis of [humanizer-ru](https://github.com/Vladimir-Human/humanizer-ru)
by Vladimir-Human (MIT). Its `PERSONA.md` and content patterns are the source of the reasoning
below. Its 40 forensic regexes (leaked service artefacts: `turn0search0`, `【1†source】`,
zero-width characters) are deliberately not carried over: text here is generated inside agents
rather than pasted from a model's raw output, so those markers have nothing to match.

## What this is for

Three failure modes, in order of how much damage they do:

1. Text asserts something it has not earned. Softest signals get stated as verdicts.
2. Text invents specifics. A number, date, name or unit appears that no source contained.
3. Text is padded. Opening phrases with no content, moralising wrap-ups, degree adverbs
   standing in for measurements.

The third is the visible one and the least important. Fix it last.

## Surfaces: which rules survive which medium

The trap in any borrowed voice guide is that it was written for dialogue. Rules like "no lists,
no headings, no bold" are right for chat and wrong for `acceptance-log.md`, where the list IS
the answer. Match the rule to the medium.

| surface | what it is | rules that apply |
|---|---|---|
| chat, RU copy for an outside reader | replies to the user, README, landing, pitch, letters | everything below, including shape and dashes |
| plans, verdicts, summaries | `plan.md`, `acceptance-log.md`, `consilium-summary.md`, handoffs | substance rules only: no padding, no unearned claims, no invented specifics. Structure stays: lists, headings and bold are how these documents work |
| technical docs | project-knowledge, `docs-pipeline` output | substance rules only, plus "facts before style". Nothing about conversational tone |
| specialist prompts | task text handed to a dispatched agent | the invented-specifics rule, as a hard refusal |

Internal notes a person writes for themselves are not a target surface at all.

## The rules

### Claim only what the text can show

State what was checked and what it showed. When the signal is soft, say it is soft and name
what a check would settle. Certainty adverbs (`очевидно, что`, `безусловно`, `несомненно`,
`разумеется`) assert a proof that is not on the page; either the proof exists, in which case
cite it, or the sentence is a guess wearing a verdict's clothes. `однозначно` is deliberately
absent: in technical Russian it usually means "deterministically", as in `однозначно определяем
маршрут по заголовку`, and flagging that reads as pedantry rather than help.

The source guide puts this best in its own domain: soft signals give no verdict about
authorship. Three matched patterns earn "worth checking by hand", not "written by a machine".

### Invent no specifics

A number, date, name, title or unit that was not in the source does not appear in the output.
This holds hardest in specialist prompts, where a plausible invented figure survives review
precisely because it is plausible. When a figure is needed and absent, say it is absent.

### Cut the padding

- Openings that carry nothing: `важно отметить`, `стоит отметить`, `следует учитывать`,
  `как известно`. Begin with the fact instead.
- Moralising closings: `в конечном счёте`, `подводя итог`, `таким образом, можно сделать
  вывод`. End on the last fact.
- Bureaucratic connectives: `является`, `осуществляется`, `представляет собой`, demonstrative
  `данный`, `на сегодняшний день`. Name the actor and the verb.
- Degree adverbs used as measurements: `значительно`, `существенно`, `кардинально`,
  `полностью`. Give the number, or drop the adverb.
- Quality claims with no observable criterion: `работает корректно`, `удобный интерфейс`,
  `улучшить UX`, `повысить эффективность`. State what is measured and how it is checked.
- Stock phrases that read as machine-written: `бесшовно`, `из коробки`, `на лету`,
  `в современном мире`, `ключевая особенность`, `под капотом`, `не чёрный ящик`,
  `помогает, а не заменяет`, `в связке с человеком`.

### Shape, on the chat and RU-copy surface only

Write in sentences. Use colons, periods, commas and parentheses; em and en dashes in Russian
prose read as a machine stamp. Avoid triads assembled for rhythm. Avoid marketing superlatives.

This section stops at the surface boundary. Applying it to a structured document produces a
document that visibly avoids something, which is its own tell.

## What is deliberately absent

- **Counting rules.** "No more than one dash per answer" targets a symptom. Applied
  mechanically it makes text that is conspicuously avoiding a character. Carry causes, not
  counts.
- **A rewriting pass.** Nothing here runs over a finished answer to improve it. A second
  author with no responsibility for the content is exactly what an earlier pipeline rejected: one
  step, one judgement. These rules constrain generation and inform review; they never
  post-process.
- **Dialogue-shape rules for documents.** See the surface table.

## Measuring, before trusting

Rules that fire on nothing are dead weight. Rules that fire on everything describe the
language rather than the text. Check with the detector from
[voice-check.py](scripts/voice-check.py), which reports hits per 1000 Russian prose lines and
never edits anything:

```bash
python ~/.claude/skills/human-voice/scripts/voice-check.py <path> --surface artefact
```

Run it over your own archived engagements to get a baseline before trusting any rule.

What the output is: a hit count over the detector's own filtered sample. It is not precision,
not recall, and it was never compared against human-labelled Russian. The denominator moves
with formatting alone (table rows and indented code are stripped), so the same text can give a
different rate after a reformat. Treat the number as a way to see whether a rule is alive, and
nothing more.

A rule that scores zero on dense engineering prose is unexercised rather than proven harmless:
that is not the surface most of these rules were written for. The dash rule is excluded from the
artefact surface entirely, because there almost every hit is a structural dash after a bold
lead-in.

Negative fixture: a hand-written brief in plain Russian should score 0 on the artefact surface.
The detector strips quoted material, so a table that quotes the banned phrases does not count
against the text that quotes them.

## Anti-patterns

- Rewriting a finished answer to comply. Generate in this voice instead.
- Applying dash and shape rules to `acceptance-log.md`, a tech-spec or a handoff.
- Reporting a hit count as a quality score. The detector locates candidates; a person decides.
- Removing a fact because its phrasing tripped a rule. Rephrase and keep the fact.
