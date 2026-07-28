# Probes (canonical — reference by name, never restate)

## probes.md#test-runner-discovery
Manifest in the repo root -> the project's FULL test command (Glob/Read; first hit wins):
package-lock.json|pnpm-lock.yaml|yarn.lock|bun.lockb -> `npm|pnpm|yarn|bun test` (a "test"
script must exist in package.json; missing -> keep searching); deno.json(c) -> `deno test`;
Cargo.toml -> `cargo test`; go.mod -> `go test ./...`; pyproject.toml|pytest.ini|tox.ini|
setup.cfg with [tool:pytest] -> `pytest`; Gemfile with spec/ -> `bundle exec rspec`, Rakefile
alone -> `bundle exec rake test`; pom.xml -> `mvn test`; build.gradle(.kts) -> `gradle test`;
*.sln|*.csproj -> `dotnet test`; composer.json with phpunit.xml(.dist) -> `vendor/bin/phpunit`;
mix.exs -> `mix test`; Package.swift -> `swift test`; pubspec.yaml -> `flutter test` when
flutter is a dependency else `dart test`; build.zig -> `zig build test`; CMakeLists.txt with
enable_testing() -> `ctest`; Makefile with a `test:` target -> `make test`.
Fallback, any language: .github/workflows/*.yml -> the run: line of a test step — the project
declares its own command there, so an unlisted ecosystem is still covered.
NONE FOUND -> a "tests pass" claim specifically is impossible (never guess a command); the
turn is not automatically BLOCKED: an inline execution proof (node/python invocation of the
changed path) may serve as the gate's proving run — claim it narrowly.

## probes.md#caller-count
Grep tool: pattern = the exported symbol name (word-boundary), output_mode = files_with_matches.
Callers = matching files minus the defining file. Result feeds the >5-callers re-tier trigger
(core). Grep tool unavailable -> shell fallback:
PowerShell: `(git grep -l "\b<symbol>\b" | Measure-Object).Count`
bash:       `git grep -l "\b<symbol>\b" | wc -l`
Both fallbacks count the defining file — callers = count - 1. The -1 is mandatory before
comparing to the >5 trigger.

## probes.md#dirty-tree
Run BEFORE any merge/discard/branch-switch:
PowerShell: `git status --porcelain`   # any output = dirty
bash:       `git status --porcelain`   # any output = dirty
# Dirty -> stop: commit, stash, or get an explicit user decision first. Never discard silently.

## probes.md#hidden-coupling
Mechanical detectors for connections no import reveals. Run when investigating cross-module
behavior, and before editing a module at T2+ where blast radius matters:
1. Co-change archaeology — files that repeatedly change in the same commits as the target are
   coupled even with zero static links:
   bash: `git log --follow --pretty=format:'%H' -50 -- <target> | while read c; do git show --name-only --pretty=format: $c; done | sort | uniq -c | sort -rn | head -10`
   PowerShell: `git log --follow --pretty=format:'%H' -50 -- <target> | % { git show --name-only --pretty=format: $_ } | ? { $_ } | Group-Object | Sort Count -Desc | Select -First 10`
   Appears in >=3 shared commits -> treat as coupled.
2. Shared writes: Grep the DB table/collection name -> every other writer is coupled.
3. Events/topics: Grep the event name -> emitters + listeners are one system.
4. Shared env/config keys: Grep the key -> every reader is blast radius.
5. Duplicated magic strings: Grep the literal -> copy-paste coupling.
Findings feed the enumeration list (investigating) and the re-tier decision (core).

Shell choice rule: use the shell this session already used; default bash.
