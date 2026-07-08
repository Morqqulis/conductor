# Probes (canonical — reference by name, never restate)

## probes.md#test-runner-discovery
Mechanical sequence (Glob/Read; first hit wins):
1. package-lock.json -> `npm test`; pnpm-lock.yaml -> `pnpm test`; yarn.lock -> `yarn test`
   (confirm a "test" script exists in package.json; missing -> keep searching)
2. Cargo.toml -> `cargo test`; go.mod -> `go test ./...`; pyproject.toml / pytest.ini /
   setup.cfg with [tool:pytest] -> `pytest`
3. .github/workflows/*.yml -> the run: line of a test step
NONE FOUND -> a "tests pass" claim is impossible -> status BLOCKED (never guess a command).
An inline execution proof (node/python invocation of the changed path) may substitute for the
gate's proving run — claim it narrowly.

## probes.md#caller-count
Grep tool: pattern = the exported symbol name (word-boundary), output_mode = files_with_matches.
Callers = matching files minus the defining file. Result feeds the >5-callers re-tier trigger
(core). Grep tool unavailable -> shell fallback:
PowerShell: `(git grep -l "\b<symbol>\b" | Measure-Object).Count`
bash:       `git grep -l "\b<symbol>\b" | wc -l`

## probes.md#dirty-tree
Run BEFORE any merge/discard/branch-switch:
PowerShell: `git status --porcelain`   # any output = dirty
bash:       `git status --porcelain`   # any output = dirty
# Dirty -> stop: commit, stash, or get an explicit user decision first. Never discard silently.

Shell choice rule: use the shell this session already used; default PowerShell on this host.
