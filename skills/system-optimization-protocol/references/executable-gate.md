# Executable gate path (pilot)

Referenced from step 3 of `system-optimization-protocol`.

**Executable path (pilot, design 03/04 only).** `scripts/golden_exec.py` runs the real validator
headlessly on `golden/exec/<domain>/<scenario>/` fixtures, baseline vs edited agent, and grades
the output in code (`--selftest` first). On a haiku validator an edit's effect appears in only a
fraction of runs: KB-design-01 was invisible at 3 and at 10 reps per arm and separated at 20
(floor scenario flagged 0/20 vs 9/20). Budget ~20 reps per arm and read the engagement count, not
only the pass rate. The effect is model-dependent: after the validator moved to sonnet the same
edit fired 1/10, because the stronger model applied WCAG correctly despite the wrong rule. A
clean executable run therefore never makes a wrong rule safe; it confirms a rubric verdict on a
high-blast validator edit and does not replace it. Write gate evidence in MR bodies
accordingly: "no regression on N scenarios", never "improves".
