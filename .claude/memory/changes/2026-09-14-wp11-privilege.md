# Change: WP11 — privileged scan (pkexec helper, event codec, PrivilegedScan)

**Date:** 2026-09-14
**Work package:** WP11
**Type:** feature

## Summary
Adds the pkexec path from `docs/CONCEPT-AND-TECHNICAL-DESIGN.md` §9/§16: a tiny root-run
launcher (`data/bin/lindrivespace-scan-helper`) that `execv`s `python3 -I core/scanner_cli.py`,
a polkit policy authorising it, an NDJSON codec matching `scanner_cli.py`'s wire format
(`core/event_codec.py`), and `services/privilege.PrivilegedScan` — a `Producer` (per
`services/scan_controller.py`'s protocol) that runs the helper (via `pkexec` or, for tests,
directly) and feeds its stdout onto a `queue.SimpleQueue` for `ScanController.consume()`.

## Files
- `src/lindrivespace/core/event_codec.py` — `encode_event`, `event_to_json_line`,
  `decode_event`, `parse_event_line`
- `src/lindrivespace/services/privilege.py` — `pkexec_available`, `helper_path`,
  `can_scan_as_admin`, `PrivilegedScan`
- `data/bin/lindrivespace-scan-helper` (chmod +x) — polkit-authorised launcher
- `data/polkit/com.mensuramedia.lindrivespace.policy`
- `tests/core/test_event_codec.py` (19 tests)
- `tests/services/test_privilege.py` (16 tests) — `tests/services/__init__.py` already existed
  (created concurrently by another WP's agent); reused as-is, not modified

## How the Explorer should call this
```python
from lindrivespace.services.privilege import PrivilegedScan

q: queue.SimpleQueue[ScanEvent] = queue.SimpleQueue()
producer = PrivilegedScan(path, options, q)   # use_pkexec=True by default
producer.start()
controller.consume(path, q, producer, options)
```
Before offering the action, gate it on `can_scan_as_admin()` (checks `pkexec` on `PATH` and
that the helper resolves to an existing file) and show its `reason` string when `False`.

**Merging a denied subtree into an already-displayed tree is out of scope for v1.** A "Scan as
administrator" click on a denied node re-scans that folder as a brand-new root via
`PrivilegedScan` + a fresh `controller.consume()` call (which itself calls `model.reset()`);
it does not attempt to splice results back into the node that was denied. Whoever picks up
tree-merging in a later work package will need a new `ScanTreeModel` entry point that grafts a
second root's events onto an existing node instead of resetting the model.

## Design decisions
- **`event_codec.py` duplicates `scanner_cli._event_to_json`'s logic rather than importing it.**
  The private helper (`dataclasses.asdict` + `top_files` tuple-of-`TopFile`-namedtuples ->
  list-of-4-lists + an `"event"` discriminator key) is reproduced verbatim in `encode_event`,
  keeping `event_codec.py`'s only dependency on `scanner_cli.py` being *the wire format it
  happens to produce*, not its internals. `tests/core/test_event_codec.py::
  test_decodes_every_line_from_real_cli` proves the two agree by running the real
  `scanner_cli.py --json` in a subprocess, decoding every line, and asserting
  `json.loads(line) == encode_event(decode_event(json.loads(line)))` — i.e. genuine
  byte-for-byte format equality, not just "both parse okay".
- **`decode_event`/`parse_event_line` do explicit `isinstance` narrowing per field** (`_as_int`,
  `_as_float`, `_as_str`, `_as_bool`, `_as_opt_int`) instead of `**kwargs` into the dataclass
  constructors. Two reasons: `mypy --strict` cannot verify a `dict[str, Any]` unpack against a
  frozen dataclass's precise field types without blanket `# type: ignore`s, and doing real
  per-field validation is exactly what makes "malformed line -> `None`" (a stray non-JSON line,
  a wrong-typed field, a `top_files` entry with 3 elements instead of 4) work correctly rather
  than just failing to crash by accident.
- **The helper (`data/bin/lindrivespace-scan-helper`) never imports `scanner_cli.py` or anything
  from `lindrivespace`.** It is the one thing polkit's `org.freedesktop.policykit.exec.path`
  authorises to run as root, so it stays a small, self-contained, auditable script: argument
  validation (allowed-flags allowlist, absolute-path requirement) is inlined rather than
  reusing `scanner_cli.build_parser()`, and `_ALLOWED_FLAGS` is a literal duplicate of
  `scanner_cli.py`'s own flags — noted here so a future flag added to `scanner_cli.py` without a
  matching update here fails closed (helper rejects the new flag) rather than open.
- **`os.execv`, not `subprocess`, inside the helper.** Preserves the PID so signals
  `PrivilegedScan.cancel/pause/resume` send after `pkexec` returns land on the actual scanner
  process, and runs the scanner under `python3 -I` (isolated mode: no `PYTHONPATH`, no user
  site-packages, no `.pth` files) so a compromised or merely unusual root environment can't
  redirect what code runs — this is the concrete mechanism behind "ignore PYTHON* env vars",
  there's no env-var-deletion code because `-I` makes it moot.
- **`PrivilegedScan` always terminates the controller's drain loop, even on a hard failure.**
  If the child's stdout closes without ever having produced a `Finished` line (pkexec dismissed
  = exit 126, not authorised = exit 127, helper rejected the arguments, scanner_cli crashed),
  the reader thread synthesizes `ScanError(path, message)` followed by
  `Finished(root_id, entries_seen, elapsed, cancelled=True)` using whatever `root_id`/`entries`
  were last seen (0 if the scan never even got a `DirStarted` out) — `ScanController._drain`
  has no other way to know the producer died, so leaving it without a `Finished` would hang the
  UI in "scanning" state forever.
- **`cancel()` is SIGINT-then-SIGTERM, not SIGKILL.** `scanner_cli.py` already turns SIGINT into
  a cooperative-cancel `Finished(cancelled=True)` (see WP2's manifest); SIGTERM after a 3 s
  grace period is the fallback for a wedged or already-exited-mid-signal-handling child, not the
  normal path. `pause()`/`resume()` are SIGSTOP/SIGCONT, which is also how the cancellation test
  gets a deterministic "mid-scan" cancellation despite the scanner being fast enough to finish a
  test-sized tree in well under a millisecond: SIGSTOP freezes the child before it can make
  progress, `cancel()`'s SIGINT is queued (a stopped process only reacts to SIGCONT/SIGKILL), and
  `resume()`'s SIGCONT lets it discover the pending SIGINT essentially immediately.
- **`helper_path()`/`$LINDRIVESPACE_SCAN_HELPER`** (finds the *helper script*, used by
  `PrivilegedScan`) and **`$LINDRIVESPACE_SCANNER_CLI`** (finds `scanner_cli.py`, read *inside
  the helper script itself*) are two independent env-var seams, not one — tests set whichever
  one is relevant to what they're faking (a fake helper binary vs. a real helper pointed at the
  checkout's `scanner_cli.py`).

## Testing notes
- `tests/services/test_privilege.py` never invokes real `pkexec`; every `PrivilegedScan` in
  tests uses `use_pkexec=False` with `python=sys.executable`, so it runs
  `[sys.executable, helper_path, --json, ..., path]` directly. The 126/127 exit-code-mapping
  tests use a tiny throwaway `python3 -c`-equivalent script file (`sys.exit(126)` /
  `sys.exit(127)`) pointed to by `$LINDRIVESPACE_SCAN_HELPER`, standing in for what a dismissed/
  denied `pkexec` invocation would look like from `PrivilegedScan`'s perspective (stdout closes
  with no NDJSON at all, nonzero exit).
- The mid-scan cancellation test builds a 4000-file tree (40 dirs x 100 files) specifically so a
  natural finish is slow enough, in principle, for the pause/cancel/resume race described above
  to matter if the SIGSTOP timing ever slips — in practice `producer.pause()` lands before the
  freshly-`execv`'d interpreter even finishes importing `argparse`/`lindrivespace.core.*` under
  `-I`, so it is not actually a tight race in this test's own timing budget.
- The root-totals-match assertion compares the `PrivilegedScan` root `DirDone` against a plain
  in-process `Scanner().scan(...)` call on the same tree with the same `ScanOptions()`, matched
  by `id` (both start numbering at 1) rather than by re-deriving totals independently, since
  WP2's `test_scanner.py` already owns the independent-walker oracle for the algorithm itself —
  this test is about the pkexec/subprocess/NDJSON plumbing being lossless, not about
  re-verifying scan correctness.
- The policy XML test uses `xml.etree.ElementTree` only (no `xmllint` in this environment, per
  the work order); it checks the action id, description/message strings, `<defaults>` triple,
  and both `org.freedesktop.policykit.exec.*` annotations.

## Manual pkexec check (optional, not automated)
`pkexec` is present on `PATH` in this sandbox (`/usr/bin/pkexec`), and
`data/bin/lindrivespace-scan-helper` is executable and resolves the checkout `scanner_cli.py`.
I did not run `pkexec data/bin/lindrivespace-scan-helper --json /root` interactively: doing so
would either block on a password prompt with no way to safely dismiss it non-interactively in
this session, or (with no polkit agent / no `DISPLAY` reliably available here) fail in a way
that says nothing useful about the real desktop path. Left for a manual check by whoever has a
real Mint session; everything it depends on (helper permissions, arg validation, policy XML
shape) is covered by the automated tests above.

## Contract concerns for the orchestrator
None — no changes needed to `core/{fsnode,events,options}.py` or `services/scan_controller.py`.
`PrivilegedScan` satisfies `scan_controller.Producer` as-is (structural typing, no import of
`scan_controller` needed from `services/privilege.py`, keeping the two services modules
decoupled). `data/bin/` and `data/polkit/` did not exist before this work package; both created
fresh, no conflicts with other data-file work.

## Verification
```
.venv/bin/ruff format src tests && .venv/bin/ruff check src tests    # clean
.venv/bin/mypy --strict src/lindrivespace/core                        # Success: no issues found in 12 source files
.venv/bin/python -m pytest -q tests/core tests/services               # 141 passed (35 new: 19 event_codec + 16 privilege)
```
`tests/core/test_purity.py` still passes — `event_codec.py` is discovered automatically via
`pkgutil.iter_modules` and imports cleanly with `gi`/`cairo`/`lindrivespace.ui`/
`lindrivespace.models` blocked.
