# Structural Quality Gates

Three deterministic checks on the code you changed, run after the tests are green and before the
reviewers. They answer what a reviewer can only guess at: is this function too complex for how
little it is tested (CRAP), did I write something that already exists (dryer), and would my tests
notice if the code were wrong (mutator).

Contents: Setup · Changed files · Commands the tools run · 1. CRAP · 2. Duplication ·
3. Mutation · Leave no residue · Report

Tools: [unclebob/crapper](https://github.com/unclebob/crapper),
[unclebob/dryer](https://github.com/unclebob/dryer),
[unclebob/mutator](https://github.com/unclebob/mutator). Languages: Python, TypeScript/JavaScript,
Go, Rust, Java, Clojure. A changed source file in any other language gets no gate; say so in the
report.

## Setup

```bash
UBPY=$(bash ~/.claude/scripts/install-quality-gates.sh)
```

Installs the pinned commits into `~/.claude/tools/unclebob/` once and prints the venv python.
Call the tools only as `"$UBPY" -m crapper|dryer|mutator`; the upstream `./crapper` launchers
hard-code `.venv/bin/python` and fail on Windows. Run every command below from the repository
root, in bash.

## Changed files

```bash
mapfile -d '' -t CHANGED < <(
  { git diff -z --name-only --diff-filter=d <base>...HEAD
    git diff -z --name-only --diff-filter=d HEAD
    git ls-files -z --others --exclude-standard; } |
  sort -zu | grep -zE '\.(py|ts|tsx|mts|cts|js|jsx|mjs|cjs|go|rs|java|clj|cljc|cljs|bb)$' |
  grep -zvE '(^|/)(tests?|specs?|__tests__|testdata)/|(^|/)(test_[^/]*\.py|conftest\.py)$|_test\.(py|go|clj|cljc|cljs|bb)$|\.(test|spec)\.[cm]?[jt]sx?$')
```

`<base>` is the branch your worktree was cut from. The three sources cover committed, uncommitted
and new files; the last filter drops tests, which crapper would otherwise score when named
explicitly. Pass the list as `"${CHANGED[@]}"` (quoted: paths may contain spaces). If the list is
empty, skip the gates and write `no gate-able source files changed`: called with no paths, the
tools scan the whole project. Do not use the tools' own `--changed`: it reads `git status` only.

## Commands the tools run

crapper's `--coverage-command` and mutator's `--test-command` are strings the tools hand to the
system shell, which on Windows is `cmd.exe`. Two consequences:

- Write paths with backslashes there (`C:\proj\.venv\Scripts\python.exe`); forward-slash relative
  paths fail.
- In `--test-command`, give the interpreter as an **absolute** path. mutator runs each mutant in a
  worker directory that does not link `.venv` or `venv`, and it counts any non-zero exit as a
  killed mutant. A relative `.venv\Scripts\python` therefore fails in every worker and reports
  every mutant killed. Test file paths stay relative.

Pass the project's own coverage command. Without `--coverage-command` or
`--use-existing-coverage`, crapper and mutator install `coverage` and `pytest` into whatever
`python3` resolves to (on Windows that can be another interpreter than the project's), and add
`@vitest/coverage-v8` to `node_modules` or install `cargo-llvm-cov`. That edits the environment
outside the task.

| Stack | `--coverage-command` (writes the LCOV or profile crapper reads) |
|---|---|
| Python + pytest | `<abs-venv-python> -m coverage run -m pytest -q <tests> && <abs-venv-python> -m coverage lcov -o target/coverage/python/lcov.info` |
| TS/JS | the project's `npm run coverage`, if it writes `coverage/lcov.info` |
| Go | `go test ./... -coverprofile=target/coverage/go/coverage.out`, after `mkdir -p target/coverage/go` |

If the project has no coverage tool installed, run crapper with `--no-coverage` (complexity only),
record that CRAP was not computed, and skip mutation (it needs the coverage report). Do not
install a coverage tool to make the gate pass.

**A failed coverage command is a tool failure, not a finding.** crapper then prints
`Coverage command exited N` and scores every function at 0% coverage, so the CRAP numbers explode.
Fix the command and re-run; discard any scores printed after that line.

## 1. CRAP (complexity × untested)

```bash
"$UBPY" -m crapper --coverage-command "<cmd>" "${CHANGED[@]}"
```

`CRAP = CC² × (1 − coverage)³ + CC`. Gate: every function you added or changed scores under 10.
Bring it down by splitting the function, by testing it, or both. A flat dispatch (`match`/`switch`
with one line per arm) can sit above 10 honestly; keep it and write one line in the report saying
why. Functions in the table you did not touch are out of scope: list the worst ones as a note,
do not refactor them.

## 2. Duplication (dryer)

```bash
"$UBPY" -m dryer --threshold 0.8 <source-root>
```

Run it on the whole source tree, not only the changed files: duplication of your new code against
existing code is the case that matters, and comparing only your files misses it. It is fast.
Then keep only the `DUPLICATE` pairs where at least one side is a file in `CHANGED`.

Gate: no pair at 0.8 or above that includes code you wrote. Merge it into one place (reuse the
existing function), or write one line saying why the shapes match by accident (two unrelated
three-step pipelines). Pairs between two files you did not touch are out of scope.

## 3. Mutation (mutator)

```bash
"$UBPY" -m mutator --use-existing-coverage --mutate-all --test-command "<test cmd>" "${CHANGED[@]}"
```

Run it after crapper, whose coverage command left the report this reads. `--mutate-all` is
required: without it mutator keeps the kills of its previous run for functions whose text did not
change, even if the tests did, and a rework iteration would report stale evidence. `<test cmd>` is
the narrowest command that runs the tests for the changed code, with the absolute interpreter path
(see above); the timeout per mutant is ten times its baseline, so a slow full suite makes the gate
slow.

Read the counts, not only the exit code. Exit `0` means no executed mutant survived, which is also
what you get when nothing executed: if killed + survived is 0, mutation did not run. Exit `3` means
a mutant survived; exit `2` means the baseline tests failed (fix that first). If every mutant is
killed, check that `<test cmd>` reaches nothing the workers do not link (`.venv`, `venv`,
`target`, `dist`, `build`, `out`, `coverage`) through a relative path; such a command fails in
every worker and the 100% is false.

Gate, for code you wrote:
- Survivor: add or sharpen a test that kills it, or delete the code if no behaviour needs it.
- Uncovered site: cover it, or delete it.
- Equivalent mutant (the mutation does not change behaviour, e.g. `>` vs `>=` on a value that
  can never be equal): leave it, and name it in the report with the one-line reason.

What mutation does not catch: behaviour that is missing altogether. A function with no branch for
`inf` produces no mutant about `inf`. Edge-case thinking stays your job and the reviewers'.

Windows without Developer Mode: mutator builds its workers from symlinks and stops with
`WinError 1314`. Record `mutation: not run, symlinks unavailable` in the report. On Linux and in CI
it runs as is.

## Leave no residue

The tools write `.metrics/`, `.coverage`, `target/coverage/` and `target/mutation-workers/` into
the project. These are scratch: do not commit them. Check `git status` before committing and remove
the ones that were not there before you started.

## Report

One block in your executor report (or in the findings log when standalone), with the evidence
rules of `engagement-contract` applied:

```
Quality gates (changed: <n> files)
- CRAP: max <score> in <function>; <k> changed functions >= 10: <names + action or reason>
- dryer: <k> pairs >= 0.8 touching changed code: <pair + action or reason>
- mutator: killed <a>, survived <b>, uncovered <c>; survivors: <site + action>
  | not run: <reason>
```
