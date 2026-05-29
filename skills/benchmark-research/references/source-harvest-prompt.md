# Reusable source-harvest prompt

Use as the per-company harvest instruction.

---

You are extending a structured primary-source archive for a benchmark
company in **[INDUSTRY]**.

Company: **[COMPANY]**
Benchmark project goal: reverse-engineer how the strongest companies in
[INDUSTRY] actually grew.

This is NOT a final analysis task. This is a source-harvest task.

Maintain this structure:

```
source-harvest-phase/<company>/
  company.md
  TODO-sources.md
  people/
  sources/
```

Rules:

- Prefer primary / operator sources first.
- Preserve existing files.
- Do not collapse everything into one giant report.
- If a source is gated, unclear, inaccessible, or unsourced, add it to
  `TODO-sources.md` instead of inventing details.
- Extract only facts useful for reverse-engineering growth, GTM,
  pricing, implementation, trust, and expansion.

For each useful source, capture:

- title
- URL
- date
- who is speaking
- why this source matters
- key facts
- direct quotes
- what it reveals about the company's growth machine
- caveats / uncertainty

Deliverable quality bar: the archive should become
**synthesis-ready**, not merely larger.
