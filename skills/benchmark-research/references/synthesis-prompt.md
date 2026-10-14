# Reusable synthesis prompt

Use as the per-company synthesis instruction once the source archive is
populated.

---

You are producing a strategy-grade reverse-engineering memo for one
benchmark company using the structured source archive already
collected.

Industry: **[INDUSTRY]**
Company: **[COMPANY]**
Source archive: `source-harvest-phase/<company>/`

Goal — explain:

- the company's growth machine
- why it worked
- how the commercial logic worked
- what the case demonstrates for the benchmark
- what is broadly transferable to similar companies
- what should not be copied blindly

Required deliverables:

- `<company>-playbook-analysis.md`
- `<company>-playbook-slides-outline.md`

Standard memo sections:

1. Executive summary
2. Core motion
3. Growth system decomposition
4. Unit economics and commercial logic
5. Sales cycle reverse engineering
6. Implementation / deployment model
7. Why the company won
8. Benchmark relevance and transferability boundaries
9. McKinsey-style factor analysis
10. Risks and fragilities
11. Final benchmark assessment / inclusion rationale

Evidence discipline — every substantive claim must be labelled as one
of:

- `[E]` sourced
- `[I]` inference
- `[UV]` unverified estimate
- `[OQ]` open question
- `[H]` hypothesis to test

Do not blur this distinction. Use tables where useful. Prefer evidence
over elegance.
