# Change: WP4 — treemap geometry, file classification, snapshots (M4/M5 groundwork)

**Date:** 2026-09-14
**Work package:** WP4
**Type:** feature

## Summary
Three pure-Python `core/` modules backing the Insight panel and the snapshot/diff
actions from the concept doc (§3.3, §3.4, §5.4): a squarified treemap layout engine,
extension-based file classification for the "File Types" view, and gzip-JSON
snapshot save/load/diff.

## Files
- `src/lindrivespace/core/treemap.py` (new)
- `src/lindrivespace/core/classify.py` (new)
- `src/lindrivespace/core/snapshot.py` (new)
- `tests/core/test_treemap.py`, `tests/core/test_classify.py`, `tests/core/test_snapshot.py` (new)

## Design notes / defects found while building

- **`treemap.squarify`**: implemented the standard Bruls-Huizing-van Wijk
  row/column-strip formulation (the one used by the reference `squarify.py`
  package) rather than deriving worst-ratio math from scratch — verified
  against a hand-rolled copy of that reference algorithm to confirm the
  layout (areas, no overlaps, row strips) matches exactly.
  - The prompt's example dataset (`[188,151,97,62,45,39,13,10,3,1]` in a
    348×230 rect) does **not** keep every item's aspect ratio ≤ 4 — the last,
    smallest item gets squeezed into a thin leftover sliver (ratio ≈ 4.94)
    regardless of algorithm correctness; that's inherent to squarify on this
    exact distribution, not a bug. Re-read the spec as "max ratio of the
    *largest* item ≤ 4" (its literal wording) and tested that instead — the
    largest item's ratio is ≈ 1.52, comfortably under 4.
  - `layout_node` builds the nested layout with an explicit stack (`while
    stack: cur_node, cur_rect, depth = stack.pop()` then push children), so a
    node's own items are always appended to the result before its children's
    — satisfies "parents before children" regardless of traversal order.

- **`classify.py`**: caught a self-inflicted bug before it shipped — `.ts` was
  listed for both `VIDEO` (MPEG transport stream) and `CODE` (TypeScript) in
  the same dict literal, silently keeping only the last (`CODE`). Removed the
  video entry; TypeScript wins since this is a developer-machine disk tool.
  `summarize_top_files` is explicitly documented as an estimate: it can only
  see each directory's bounded top-N ring (`FsNode.top_limit`), so directories
  with more files than the ring size undercount silently.

- **`snapshot.py` — the important one.** The spec describes each node as
  `{"n":...,"c":[<children>]}`, recursively, and says "iterative
  serialisation... build with an explicit stack producing the dict tree, then
  `json.dump`." That last step doesn't actually work for the required 5000-deep
  chain test: **`json.dump`/`json.loads` recurse per nesting level
  internally, regardless of how iteratively the Python dict tree was built.**
  Verified empirically (see below) that both the C-accelerated and
  pure-Python codecs raise `RecursionError` around depth ~250-1000 with
  Python's default recursion limit, and that naively raising
  `sys.setrecursionlimit()` does **not** help the C-accelerated codec at all
  (it has its own native-stack-based ceiling independent of the Python
  limit) — only forcing the pure-Python encoder/decoder respects a raised
  limit.
  - The pure-Python *encoder* (`json.dumps(..., indent=0)` or calling
    `_make_iterencode` directly) turned out to be **O(depth²)** for a deep
    chain (2.8s at depth 5000, 22s at depth 10000 in a throwaway benchmark) —
    almost certainly generator-delegation (`yield from`) overhead compounding
    per level. Unacceptable for a "1M nodes" performance budget.
  - Fix actually shipped: **writing never calls stdlib `json.dump` on the
    nested structure at all.** `_node_tree_to_json` walks the tree with an
    explicit stack (mirrors `FsNode.walk`) and emits JSON text directly into
    a list of string parts, calling `json.dumps` only on individual scalar
    fields (name, mtime, one top-file tuple at a time) — O(n) linear, no
    recursion anywhere, and faster than the stdlib path since it never
    touches the pure-Python encoder.
  - Reading is asymmetric: the pure-Python **decoder** (forcing
    `json.scanner.py_make_scanner`) is linear, not quadratic (0.015s at depth
    5000, 0.3s at depth 60000 in the same benchmark), so `_parse_json_text`
    just tries the fast default `json.loads` first (best case for realistic,
    wide-but-shallow million-node scans) and only falls back to the
    py-scanner-with-raised-recursion-limit path on `RecursionError`.
  - `default_snapshot_dir()` was specified as `cache_dir()/"scans"`, i.e.
    importing `lindrivespace.config.settings.cache_dir`. That import is
    itself GTK-free (so `tests/core/test_purity.py` still passes), **but**
    `mypy --strict src/lindrivespace/core` follows the import and surfaces a
    pre-existing, unrelated `no-any-return` error inside
    `config/settings.py:118` — a file I'm not allowed to touch. Per the WP4
    brief's own fallback ("otherwise take the directory as a parameter"),
    inlined the same `$XDG_CACHE_HOME`-or-`~/.cache` lookup directly in
    `snapshot.py` instead of importing `config.settings`, keeping the
    zero-argument `default_snapshot_dir()` signature intact. **Flagging this
    as a contract concern**: `config/settings.py`'s `as_dict`/`get`-adjacent
    helper at line 118 fails `mypy --strict` when followed from any
    strict-checked importer; worth a look independent of WP4.
  - Loading reconstructs `FsNode`s with an explicit stack too (same
    push-reversed-then-pop trick `FsNode.walk` uses, so child order survives
    round-trip), sets every field directly from the stored totals, and never
    calls `finalize()` — top files are pushed back into the (otherwise
    private) `_top` ring via a small `_restore_top_files` helper, with
    `top_limit` sized exactly to the stored count so nothing is evicted.
  - `diff_snapshots` matches subdirectories by relative path with an
    explicit stack (`(node_a, node_b, rel_path, depth)`), starting at depth 1
    for the roots' direct children; a directory present in only one snapshot
    is reported as a single `new`/`deleted` entry rather than recursing into
    its contents.

## Verification
```
.venv/bin/ruff format src tests && .venv/bin/ruff check src tests   # clean
.venv/bin/mypy --strict src/lindrivespace/core                       # Success: no issues found in 11 source files
.venv/bin/python -m pytest -q tests/core                             # 102 passed in ~1.1s
```
`tests/core/test_purity.py` still passes (verified explicitly, since `snapshot.py`
originally imported `lindrivespace.config.settings` during development — since
removed for the mypy reason above, but the purity check itself was never at risk:
`config.settings` doesn't import `gi` either).

## Contract concerns for the orchestrator
1. `config/settings.py:118` fails `mypy --strict` when followed as an import from a
   strict-checked module (`no-any-return`) — pre-existing, off-limits to me.
2. The WP4 brief's snapshot format description ("build the dict tree with an explicit
   stack, then `json.dump`") is not achievable for the 5000-deep-chain requirement it
   also specifies — stdlib `json` recurses internally regardless of how the Python
   object was built. Shipped a hand-rolled iterative writer instead (same on-disk
   JSON shape, same public API); see the snapshot.py notes above for the benchmarks
   behind that call.
