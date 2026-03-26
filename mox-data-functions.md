# Mox Data Function Documentation

This document tracks validated feature flows in Mox Data.

## Missing Game Winners

### Purpose

Allows a logged-in user to review unresolved game outcomes and manually set winners (`P1` or `P2`) using recent end-of-game actions.

---

### End-to-End Flow (Validated)

1. User clicks **Missing Game Winners** from the sidebar.
2. Frontend initializes `GameWinnerManager` and calls:
   - `GET /api/game-winner/next`
3. Backend returns the next actionable unresolved game for that user (if one exists), including:
   - game/match context
   - last 15 game actions (from `GameActions`)
4. Frontend populates the Game Winner modal:
   - Match/Game + date
   - formatted end-game actions
   - player-labeled winner buttons
5. User chooses:
   - `Player 1`
   - `Player 2`
   - `Skip`
6. Frontend submits:
   - `POST /api/game-winner/update`
7. Backend updates `Game` + `Match` (+ `Draft` rollups when applicable), removes processed `GameActions` for that game, then returns next actionable game (if any).
8. Frontend immediately advances to the next game in modal, or closes when complete.

---

### Actionable Game Eligibility (Current Logic)

A game is considered actionable for **Missing Game Winners** when all are true:

- `Game.uid == current_user.uid`
- `Game.p1 == current_user.username` (hero-perspective row to avoid mirrored duplicates)
- winner is unresolved:
  - `game_winner IS NULL`, or
  - trimmed `game_winner == ''`, or
  - `game_winner NOT IN ('P1', 'P2')`
- matching `GameActions` row exists for same `(uid, match_id, game_num)`
- valid `Match` join exists for same `(uid, match_id, p1)`

This same actionable definition is used for sidebar enablement (`missing_winners_enabled`), preventing menu-state drift.

---

### Modal Payload / Display Behavior

Backend response includes:

- current game context (`match_id`, `game_num`, `p1`, `p2`, etc.)
- `date` from `Match.date`
- `game_actions`: last 15 actions from `GameActions.game_actions`

Formatting:

- backend and frontend both support marker replacement:
  - `@[ ... @]` -> `<strong> ... </strong>`

---

### Update Behavior

Endpoint: `POST /api/game-winner/update`

Input:

- `match_id`
- `game_num`
- `winner` (`P1`, `P2`, or `skip`)

Winner resolution:

- Resolved from authoritative DB hero-perspective row:
  - `Game(uid=current_user.uid, match_id, game_num, p1=current_user.username)`
- Avoids trusting client-provided player names.

Database updates when winner is not `skip`:

1. Update all mirrored `Game` rows for `(uid, match_id, game_num)` where winner is unresolved.
2. Count whether at least one game row actually changed (`changed_games > 0`).
3. Only if `changed_games > 0`:
   - increment corresponding `Match.p1_wins` / `Match.p2_wins`
   - recompute `Match.match_winner` (`P1` / `P2` / `NA`)
   - recompute draft rollup via `update_draft_win_loss(...)`
4. Delete `GameActions` for this game `(uid, match_id, game_num)` to prevent reprocessing.
5. Commit transaction.

This protects against accidental score inflation from repeated submissions.

---

### Next-Game Progression

Both initial and follow-up selection use deterministic ordering:

1. `Match.date` (ascending)
2. `Match.match_id` (ascending)
3. `Game.game_num` (ascending)

This ensures stable sequencing when multiple matches share the same timestamp.

---

### Security Boundary

Primary protection is:

- `@login_required`
- user-scoped DB filters (`uid`, hero perspective constraints)

The flow no longer relies on `X-Requested-By` header checks for these two endpoints.

---

### Related Components

- Backend:
  - `modules/views.py`
    - `api_game_winner_next`
    - `api_game_winner_update`
    - sidebar status helpers (`compute_sidebar_status_for_user`, actionable missing-winner count)
- Frontend:
  - `templates/base.html` (modal + menu hook)
  - `static/base.js` (`GameWinnerManager`, modal lifecycle, API calls)

## Associated Draft IDs

### Purpose

Allows a logged-in user to associate unresolved limited `Match` records to the correct `Draft` by reviewing cards played in the match and selecting from candidate draft IDs.

---

### End-to-End Flow (Validated)

1. User clicks **Associated Draft IDs** from the sidebar.
2. Frontend initializes `DraftIdManager` and calls:
   - `GET /api/draft-id/next`
3. Backend returns the next actionable limited match for that user (if one exists), including:
   - match context
   - played card lists (`lands`, `spells`)
   - candidate draft IDs (`possible_draft_ids`)
4. Frontend populates the Draft ID modal:
   - Match + date
   - Lands/Spells lists
   - Draft ID dropdown (default = first candidate)
5. User chooses:
   - **Apply** (assign selected draft ID), or
   - **Skip**
6. Frontend submits:
   - `POST /api/draft-id/update`
7. Backend applies changes (for Apply), recalculates draft match stats, and returns next actionable match (if any).
8. Frontend advances to next match in modal, or closes when complete.

---

### Actionable Match Eligibility (Current Logic)

A match is considered actionable for **Associated Draft IDs** when all are true:

- `Match.uid == current_user.uid`
- `Match.p1 == current_user.username` (hero-perspective row to avoid mirrored duplicates)
- unresolved draft association:
  - `draft_id IS NULL`, or
  - trimmed `draft_id == ''`, or
  - `draft_id == 'NA'`
- limited format:
  - `Match.format IN ('Cube', 'Booster Draft')`

Candidate draft IDs are generated from prior drafts (`Draft.date < Match.date`) using card overlap against draft picks.

This same actionable definition is used for sidebar enablement (`draft_ids_enabled`) via `count_actionable_draft_id_matches(...)`, preventing menu-state drift.

---

### Candidate Draft ID Generation

For each actionable match:

1. Pull hero card activity from `Play`:
   - lands (`action='Land Drop'`)
   - spells (`action='Casts'`)
2. Normalize via multiface mapping (`modo.clean_card_set`).
3. Compare played cards against each prior draft's pick pool (`Pick` rows).
4. Compute overlap percentage tiers:
   - 100% bucket
   - >=80% bucket
   - fallback/all bucket
5. Return prioritized candidates in `possible_draft_ids`.

---

### Update Behavior

Endpoint: `POST /api/draft-id/update`

Input:

- `match_id`
- `draft_id` (nullable when skipping)
- `skip` (boolean)

Apply path (`skip=false`, `draft_id` provided):

1. Update all mirrored `Match` rows for `(uid, match_id)` with selected `draft_id`.
2. Recompute associated `Draft.match_wins` / `Draft.match_losses` using hero-perspective matches:
   - `Match.uid == current_user.uid`
   - `Match.draft_id == selected_draft_id`
   - `Match.p1 == current_user.username`
3. Commit transaction.

Skip path:

- No DB draft assignment is written for the match.

After either path, backend returns next actionable match in sequence (if any).

---

### Next-Match Progression

Selection and progression use deterministic ordering:

1. `Match.date` (ascending)
2. `Match.match_id` (ascending)

This avoids unstable traversal and prevents skipping same-timestamp candidates.

---

### Security Boundary

Primary protection is:

- `@login_required`
- user-scoped DB filters (`uid`, hero perspective constraints)

These Draft ID endpoints no longer rely on `X-Requested-By` header checks as a security gate.

---

### Related Components

- Backend:
  - `modules/views.py`
    - `api_draft_id_next`
    - `api_draft_id_update`
    - sidebar status helpers (`compute_sidebar_status_for_user`, actionable draft-id count)
    - reusable unresolved predicate (`unresolved_draft_id_filter`)
- Frontend:
  - `templates/base.html` (modal + menu hook)
  - `static/base.js` (`DraftIdManager`, modal lifecycle, API calls)

## Best Guess Deck Names

### Purpose

Allows a logged-in user to auto-populate `Match.p1_subarch` / `Match.p2_subarch` based on match scope and replacement strategy.

The feature supports:

- match scope: `Limited Only`, `Constructed Only`, or `All Matches`
- replacement strategy: `Overwrite All` or `Replace NA Only`

---

### End-to-End Flow (Validated)

1. User clicks **Best Guess Deck Names** from sidebar.
2. Frontend opens modal and requires both dropdowns to be explicitly selected (`Choose an option` defaults).
3. Apply button remains disabled until:
   - `BG_Match_Set` is selected
   - `BG_Replace` is selected
4. Form posts to:
   - `POST /best_guess`
5. Backend runs scoped update logic (limited / constructed, overwrite mode).
6. Backend commits changes and flashes summary of revised constructed/limited match counts.
7. User is redirected back to current page (`request.referrer`), with fallback to matches table page 1.

---

### Inputs and Validation

Modal fields submit:

- `BG_Match_Set`:
  - `All Matches`
  - `Limited Only`
  - `Constructed Only`
- `BG_Replace`:
  - `Overwrite All`
  - `Replace NA` (displayed as `Replace NA Only` in UI)

Safety behavior:

- Both fields default to empty on modal open.
- Apply is disabled until both fields are set.

---

### Limited Match Logic

Scope filter:

- `Match.format IN options['Limited Formats']`

Subarchetype derivation:

- pulls cards from `Play` where action in `['Land Drop', 'Casts']` for each side
- passes card list to `modo.get_limited_subarch(...)`
- color identity is inferred from basic lands:
  - `Plains`, `Island`, `Swamp`, `Mountain`, `Forest`
  - mapped to `W/U/B/R/G` signature

Archetype behavior hardening:

- `p1_arch` / `p2_arch` are now set to `Limited` only when archetype is unresolved
  (null/blank/`NA`/`Unknown`), not unconditionally.

---

### Constructed Match Logic

Scope filter:

- `Match.format IN options['Constructed Formats']`

Subarchetype derivation:

- pulls cards from `Play` where action in `['Land Drop', 'Casts']` for each side
- computes `yyyy_mm` from match date
- compares played-card set against sampled decklists from `AllDeck` cache via `modo.closest_list(...)`
- writes closest deck name to subarchetype

`closest_list` behavior:

- compares against current month and previous two month deck pools
- returns best deck name if similarity > 20%
- otherwise returns `Unknown`

---

### Replacement Strategies

`Overwrite All`:

- updates targeted scope regardless of current subarchetype values.

`Replace NA Only`:

- updates only unresolved subarchetype values.
- unresolved now includes:
  - `NULL`
  - blank/whitespace
  - `NA`
  - `Unknown`

---

### Database Effects

Table:

- `Match`

Updated columns:

- always target: `p1_subarch`, `p2_subarch` (based on scope and strategy)
- limited-only conditional fallback:
  - `p1_arch`, `p2_arch` set to `Limited` only if unresolved

Transaction behavior:

- single commit at end of route
- rollback on commit failure

---

### Related Components

- Backend:
  - `modules/views.py`
    - `best_guess`
  - `modules/modo.py`
    - `get_limited_subarch`
    - `closest_list`
- Frontend:
  - `templates/base.html`
    - Best Guess modal form + dropdown handlers + apply-state gating

## Import GameLogs

### Purpose

Allows a logged-in user to upload a `.zip` containing MTGO `GameLog` (`.dat`) and/or `DraftLog` (`.txt`) files, parse them through `modo.py`, and load parsed data into core gameplay tables.

---

### End-to-End Flow (Validated)

1. User clicks **Import GameLogs** from the sidebar.
2. Frontend opens Import modal and submits multipart form:
   - `POST /load`
3. Backend route validates upload:
   - file exists
   - filename ends with `.zip`
   - payload is a valid zip archive (`zipfile.is_zipfile`)
4. Backend enqueues Celery task:
   - `process_logs.delay(...)`
5. Task extracts/classifies zip members and archives accepted files per user (local/S3).
6. Task parses accepted files with `modo.py`:
   - `GameLog` -> `modo.get_all_data(...)` + `modo.invert_join(...)`
   - `DraftLog` -> `modo.parse_draft_log(...)`
7. Task writes parsed data into DB tables (`Match`, `Game`, `Play`, `GameActions`, `Draft`, `Pick`) with insert/update behavior.
8. Task logs run metadata to `TaskHistory`, emails load report, and rebuilds derived `CardsPlayed`.

---

### Accepted File Detection

Files are accepted only when `get_logtype_from_filename(...)` returns:

- `GameLog`:
  - filename contains `Match_GameLog_`
  - filename ends with `.dat`
  - minimum filename length check passes
- `DraftLog`:
  - filename passes strict dash/dot shape heuristic
  - `.txt` extension
  - year/id segment format checks pass

All other files are skipped.

---

### Archival + Timestamp Policy

Before parsing, accepted files are archived to user storage (local folder or S3) with preserved timestamp metadata.

Current policy keeps the archived file with the **oldest** timestamp for a given filename:

- if incoming file timestamp is newer-or-equal to archived timestamp -> incoming file is skipped
- if incoming file timestamp is older -> archived file is replaced

This prioritizes timestamp integrity for match-time inference when copied files may have artificially newer modification times.

---

### Parse and Load Behavior

`GameLog` parse output is loaded into:

- `Match`
- `Game`
- `Play`
- `GameActions` (last 15 actions per game)

`DraftLog` parse output is loaded into:

- `Draft`
- `Pick`

For existing rows, import uses mixed update strategy:

- system refresh fields are updated from parsed data (for example match rolls/date and game turn details)
- user-revisable `Match` fields are updated only when:
  - existing DB value is unresolved (`NULL`, blank, `NA`, `Unknown`)
  - parsed value is resolved

This prevents common full-fileset imports from clobbering manual revisions.

---

### GameActions Refresh Behavior

For each parsed game action block:

- if `GameActions(uid, match_id, game_num)` exists, it is now updated with latest parsed last-15 actions
- otherwise, a new row is inserted

This prevents stale action snapshots on repeated imports.

---

### Error Handling and Task Outcome

- Parse-level file errors are counted and skipped per file (load continues).
- Unexpected task-level failures are logged and re-raised so Celery marks the task as failed (instead of silently returning success).
- `/load` rejects invalid file types/archives before task submission.

---

### Related Components

- Backend:
  - `modules/views.py`
    - `load`
    - `process_logs`
    - `get_logtype_from_filename`
    - `build_cards_played_db`
  - `modules/modo.py`
    - `get_all_data`
    - `invert_join`
    - `parse_draft_log`
- Frontend:
  - `templates/base.html`
    - Import modal + form submission hooks

## Re-Process Archived Files

### Purpose

Allows a logged-in user to re-parse their already archived `GameLog` (`.dat`) and `DraftLog` (`.txt`) files when parsing logic changes, then refresh database records from the re-parsed output.

This flow preserves user-revised `Match` fields (same intent as Import), while intentionally allowing `Game.game_winner` to be overwritten from parser output.

---

### End-to-End Flow (Validated)

1. User clicks **Re-Process Archived Files** from the sidebar.
2. Frontend opens Reprocess modal and submits:
   - `POST /reprocess`
3. Backend route enqueues Celery task:
   - `reprocess_logs.delay(...)`
4. Task enumerates the user’s archived files (local upload directory or S3 prefix).
5. Task filters accepted files using `get_logtype_from_filename(...)`:
   - `GameLog` or `DraftLog` only
6. Task reads each file and parses with `modo.py`:
   - `GameLog` -> `modo.get_all_data(...)` + `modo.invert_join(...)`
   - `DraftLog` -> `modo.parse_draft_log(...)`
7. Task updates/inserts database rows for Matches/Games/Plays/GameActions and Drafts/Picks.
8. Task recomputes draft win/loss rollups after all file writes, rebuilds `CardsPlayed`, writes `TaskHistory`, and sends load report email.

---

### File Source + Selection

Reprocess does not take a new upload; it uses files already archived from previous imports:

- local mode:
  - `local-dev/data/uploads/<uid>/`
- S3 mode:
  - `${S3_PREFIX}<uid>/`

Only valid log filenames are processed. `.meta` sidecar files are skipped in local mode.

---

### Parse + Load Behavior

`GameLog` path refreshes:

- `Match`
- `Game`
- `Play`
- `GameActions`

`DraftLog` path refreshes:

- `Draft`
- `Pick`

For existing `Match` rows, reprocess intentionally preserves user-revisable columns:

- preserved: `draft_id`, `p1_arch`, `p1_subarch`, `p2_arch`, `p2_subarch`, `format`, `limited_format`, `match_type`
- refreshed from parser: roll data, win counts, match winner, date, processing timestamp, and child game/play/action rows

`Game.game_winner` is overwritten during reprocess by design.

---

### Removed/Ignore Handling

Files/matches marked in `Removed` are skipped.

DraftLog removed-check now uses the parsed authoritative `draft_id` (with filename fallback if needed), avoiding older filename-shape mismatches.

---

### Draft Win/Loss Recompute (Order Safety)

Draft match W/L recompute is deferred until after all files are processed:

1. collect affected `draft_id` values while processing files
2. after all DB updates, recompute via `update_draft_wins(...)` for each collected ID

This avoids order-dependent partial recomputes when DraftLogs and GameLogs are processed in different sequences.

---

### Error Handling and Task Outcome

- per-file parse errors are counted and skipped (processing continues)
- unexpected task-level exceptions are re-raised so Celery marks task failure
- task history stores error details in `error_code` when failures occur

---

### Related Components

- Backend:
  - `modules/views.py`
    - `reprocess`
    - `reprocess_logs`
    - `get_logtype_from_filename`
    - `update_draft_wins`
    - `build_cards_played_db`
  - `modules/modo.py`
    - `get_all_data`
    - `invert_join`
    - `parse_draft_log`
- Frontend:
  - `templates/base.html`
    - Reprocess modal + form submission

## Load Revisions

### Purpose

Allows a logged-in user to import MTGO-Tracker desktop save data (`ALL_DATA` pickle) and apply user-revision fields onto existing `Match` rows.

This is a targeted update flow (revisions only), not a full parser reload.

---

### End-to-End Flow (Validated)

1. User clicks **Load Revisions** from the sidebar.
2. Frontend opens modal and submits multipart form:
   - `POST /load_revisions_from_app`
   - expected filename: `ALL_DATA`
3. Backend route reads uploaded bytes and performs safe deserialization:
   - `safe_pickle_loads(...)` via restricted unpickler
4. Backend validates payload shape:
   - `normalize_and_validate_revisions_all_data(...)`
5. Backend expands perspective data:
   - `modo.invert_join(all_data)` (adds mirrored match/game rows)
6. Backend validates shape again post-inversion, then enqueues Celery task:
   - `process_revisions_from_app.delay(...)`
7. Task validates shape again (defense-in-depth), prefetches existing DB keys, applies revision updates to existing `Match` rows, and commits in batches.
8. Task writes `TaskHistory`, emails load report, and returns.

---

### Input + Security Validation

Route-level protections:

- `@login_required`
- filename gate (`ALL_DATA`)
- safe pickle loader (`RestrictedUnpickler`) that allows only basic builtins
- schema/shape validation before enqueue

Task-level protections:

- re-validates `all_data` shape before any positional indexing

This prevents unsafe object deserialization and avoids crashes from malformed row shapes.

---

### Expected ALL_DATA Contract

The loader expects:

- `all_data[0]`: list of match rows (each row list/tuple, min length 17)
- `all_data[1]`: list of game rows (each row list/tuple, min length 12)
- `all_data[2]`: list of play rows (list/tuple rows accepted)
- `all_data[3]`: dict of game actions

Both top-level tuple/list payloads are accepted (tuple normalized to list).

---

### Update Behavior (Current)

`process_revisions_from_app` updates existing `Match` rows only (no inserts):

- key lookup:
  - `(uid, match_id, p1)`
- writes:
  - `draft_id` (only if referenced draft exists for user)
  - `p1_arch`, `p1_subarch`
  - `p2_arch`, `p2_subarch`
  - `format`, `limited_format`, `match_type`
  - `proc_dt`

Intentionally not updated in this flow:

- `Game.game_winner`
- `Match.p1_wins`, `Match.p2_wins`, `Match.match_winner`
- draft win/loss recompute (`update_draft_wins`)

This keeps Load Revisions aligned with revision intent rather than gameplay result recomputation.

---

### Performance + Commit Behavior

To reduce DB load and improve resilience:

- prefetches all candidate matches once into in-memory map keyed by `(match_id, p1)`
- prefetches all candidate draft IDs once into set
- avoids repeated per-row `first()` queries
- commits in batches (`commit_every = 250`) instead of one giant final commit

Batch commits reduce blast radius of late-run failures to only the current uncommitted batch.

---

### Error Handling and Task Outcome

- malformed/unsafe upload data is rejected in route with user-facing flash error
- task-level exceptions still re-raise so Celery marks task failure
- post-commit `build_cards_played_db(...)` failures are logged as warnings and do not flip an already-persisted revision run to failed
- `TaskHistory` write failure is now explicitly logged (no bare `except`)
  - email still sends with fallback task id `N/A` if history row cannot be written

---

### Frontend Validation Notes

Load Revisions modal submit activation is filename-based (`ALL_DATA`) and no longer depends on a required help-text DOM node:

- `validateLoadRevisionsFiles()` now safely handles missing optional help-text element
- button enable/disable works even when help text is not rendered

---

### Related Components

- Backend:
  - `modules/views.py`
    - `load_revisions_from_app`
    - `process_revisions_from_app`
    - `RestrictedUnpickler`
    - `safe_pickle_loads`
    - `normalize_and_validate_revisions_all_data`
  - `modules/modo.py`
    - `invert_join`
- Frontend:
  - `templates/base.html`
    - Load Revisions modal + client-side file gate

## Revise Row(s)

### Purpose

Allows a logged-in user to revise selected `Match` table fields from the `/table/matches/...` page.

The feature supports:

- single-row revise:
  - shows current match values
  - shows cards played summary (lands/spells per side)
  - writes revisions to DB for mirrored match rows
- multi-row revise:
  - applies one selected field change across multiple selected matches

---

### End-to-End Flow (Validated)

1. User navigates to the Matches table and selects one or more rows.
2. **Single selection**:
   - frontend requests:
     - `GET /api/match/<match_id>/details`
   - backend returns hero-perspective match row plus optional `CardsPlayed` payload.
   - frontend populates Revise modal (players, lands/spells, editable fields).
3. **Multi selection**:
   - frontend opens Revise Multiple modal with field-group selector.
4. User clicks **Apply**:
   - single -> `POST /api/match/revise`
   - multi -> `POST /api/match/revise-multi`
5. Backend applies user-scoped updates, commits transaction, and returns success/error JSON.
6. Frontend closes modal, shows flash message, and reloads table data for the current page.

---

### Single-Row Revise Behavior

#### Data shown in modal

From `Match`:

- `match_id`, `date`
- `p1`, `p2`
- `p1_arch`, `p1_subarch`
- `p2_arch`, `p2_subarch`
- `format`, `limited_format`, `match_type`

From `CardsPlayed` (if available):

- `lands1`, `plays1`
- `lands2`, `plays2`
- `casting_player1`, `casting_player2` (used for side alignment)

#### Editable fields

- `P1 Archetype`
- `P1 Subarchetype`
- `P2 Archetype`
- `P2 Subarchetype`
- `Format`
- `Limited Format`
- `Match Type`

#### Write semantics

Backend updates all rows matching:

- `Match.uid == current_user.uid`
- `Match.match_id == requested_match_id`

Mirrored rows are handled by mapping P1/P2 deck fields based on whether row perspective is hero (`match.p1 == current_user.username`) or mirrored opponent perspective.

---

### Multi-Row Revise Behavior

User selects a target group in modal:

- `P1 Deck`
- `P2 Deck`
- `Format`
- `Match Type`

Payload includes selected `match_ids` and one value set for chosen group.

Backend updates all matching rows:

- `Match.uid == current_user.uid`
- `Match.match_id IN match_ids`

Special format behavior:

- when revised `format` is in limited formats:
  - force `p1_arch = 'Limited'`
  - force `p2_arch = 'Limited'`
- when revised `format` is not limited:
  - if archetype currently `Limited`, reset to `NA`

`Limited Format` input is only enabled in modal when selected Format is a limited format; otherwise it is disabled and normalized to `NA`.

---

### Security Boundary

Primary protections:

- `@login_required`
- strict user-scoped queries (`uid=current_user.uid`)

Revise endpoints no longer rely on `X-Requested-By` header checks as a security boundary.

---

### Notes from Validation

- Current UX intentionally favors responsiveness for single-row revise open.
- A rare race can occur if user selects a row and immediately opens revise before details fetch completes; this was accepted as a tradeoff.

---

### Related Components

- Backend:
  - `modules/views.py`
    - `api_match_details`
    - `api_match_revise`
    - `api_match_revise_multi`
- Frontend:
  - `templates/tables.html`
    - single and multi revise modal structure
  - `static/tables.js`
    - row selection
    - details fetch + modal population
    - single/multi apply submission

## Remove Row(s)

### Purpose

Allows a logged-in user to remove selected matches from the database, with optional ignore behavior for future parsing.

The feature supports:

- `Remove`:
  - deletes selected match and associated records
  - does **not** add match to ignore list
  - match can be re-added by future Import/Re-Process from archived files
- `Remove & Ignore`:
  - deletes selected match and associated records
  - adds `match_id` to `Removed` list so future Import/Re-Process skips it

---

### End-to-End Flow (Validated)

1. User selects one or more rows in Matches table and clicks **Remove Row(s)**.
2. Frontend opens Remove modal with two actions:
   - `Remove`
   - `Remove & Ignore`
3. Frontend submits:
   - `POST /api/match/remove`
   - payload: `match_ids`, `remove_type`
4. Backend validates payload and processes each `match_id` (user-scoped).
5. Backend deletes records across all associated tables.
6. If `remove_type == 'Ignore'`, backend inserts `Removed` row(s) for future skip logic.
7. Backend commits, recomputes affected draft W/L rollups, and returns counts.
8. Frontend closes modal, shows success/error flash, and reloads table data.

---

### Deletion Scope

For each selected `match_id`, backend now deletes user-scoped rows from:

- `Match`
- `Game`
- `Play`
- `GameActions`
- `CardsPlayed`

This ensures no orphaned gameplay summary/action rows remain after removal.

---

### Ignore Behavior and Future Parsing

If `Remove & Ignore` is used:

- backend inserts into `Removed` with:
  - `uid`
  - `match_id`
  - original match date
  - `reason='Ignored'`

Future parsing behavior:

- Import/Re-Process checks `Removed` by `(uid, match_id)`
- matching logs are skipped (`gamelogs_skipped_removed` / related counters)

If plain `Remove` is used:

- no `Removed` row is inserted
- future Import/Re-Process can re-add the match from archived raw logs

---

### Draft Win/Loss Consistency

During deletion, backend collects affected resolved `draft_id` values from removed match rows.

After successful deletion commit, backend recomputes draft match stats via `update_draft_wins(...)` for each affected draft, preventing stale draft W/L totals.

---

### Security Boundary

Primary protections:

- `@login_required`
- strict user-scoped operations (`uid=current_user.uid`)

`/api/match/remove` no longer relies on `X-Requested-By` header checks as a security boundary.

---

### Related Components

- Backend:
  - `modules/views.py`
    - `api_match_remove`
    - `update_draft_wins`
  - `modules/models.py`
    - `Removed`
    - `Match`, `Game`, `Play`, `GameActions`, `CardsPlayed`
- Frontend:
  - `templates/tables.html`
    - Remove modal action buttons (`Remove`, `Remove & Ignore`)
  - `static/tables.js`
    - `submitRemoval(removeType)` API submission + table refresh

## Unignore Match

### Purpose

Allows a logged-in user to remove a `match_id` from the `Removed` table so it is no longer skipped by future parsing operations.

This effectively reverses **Remove & Ignore** behavior for selected ignored entries.

---

### End-to-End Flow (Validated)

1. User opens **Ignored Matches** page (`/ignored`).
2. Frontend renders rows from `Removed` table for the current user.
3. User selects one ignored row and clicks **Unignore Match**.
4. Frontend opens confirmation modal showing selected `match_id`.
5. User confirms; frontend submits:
   - `POST /api/ignored/remove`
   - payload: `match_ids: [selected_match_id]`
6. Backend deletes matching `Removed` record(s) scoped by user.
7. Backend commits and returns success/error JSON.
8. Frontend reloads page:
   - ignored table refreshes
   - if no ignored records remain, `/ignored` route redirects to home
   - sidebar status refresh on load reflects updated ignored count

---

### Backend Behavior

Route:

- `POST /api/ignored/remove`

Validation:

- request JSON required
- `match_ids` required/non-empty

Delete scope:

- `Removed.uid == current_user.uid`
- `Removed.match_id IN match_ids`

Transaction:

- single commit after deletes
- rollback + error response on failure

---

### Effect on Future Import/Re-Process

Import and Re-Process skip checks are based on:

- `Removed.query.filter_by(uid=uid, match_id=...)`

After unignore removes that row:

- skip condition no longer matches
- the match becomes eligible again for future Import GameLogs / Re-Process Archived Files

---

### Security Boundary

Primary protections:

- `@login_required`
- user-scoped delete filter (`uid=current_user.uid`)

---

### Related Components

- Backend:
  - `modules/views.py`
    - `ignored`
    - `api_ignored_remove`
  - `modules/models.py`
    - `Removed`
- Frontend:
  - `templates/tables.html`
    - Ignored table selection + Unignore confirmation modal
  - inline JS in `templates/tables.html`
    - `initializeIgnoredTable`
    - `unignoreMatch()`

## Register

### Purpose

Allows a new user to create an account, store account details in `Player`, and verify email ownership before normal login access.

Core outcomes:

- new `Player` record created with unique `uid`
- duplicate email prevented
- password confirmation validated
- confirmation email sent with signed token link
- account flagged confirmed after token link is opened

---

### End-to-End Flow (Validated)

1. User opens `GET /register`.
2. Frontend renders registration form (`email`, `password`, `confirm password`, `MTGO username`).
3. User submits form to:
   - `POST /email`
4. Backend validates:
   - all fields present
   - password and confirm password match
   - minimum password length (>= 6)
   - email not already registered
5. Backend creates `Player` row and commits.
6. Backend generates signed confirmation token and sends confirmation email with:
   - `GET /confirm_email/<token>`
7. User clicks confirmation link.
8. Backend validates token, marks account confirmed, logs user in, and redirects to profile.

---

### Registration Write Behavior

On successful registration, backend inserts into `Player`:

- `email` (unique)
- `pwd` (hashed via `generate_password_hash`)
- `username` (MTGO username field)
- `created_on` (timestamp)
- `is_admin=False`
- `is_confirmed=False`
- `confirmed_on=None`

`uid` is auto-generated as unique primary key.

---

### Confirmation Email and Token

Token generation:

- `URLSafeTimedSerializer.dumps(email, salt=EMAIL_CONFIRMATION_SALT)`

Confirmation route:

- `GET /confirm_email/<token>`

Token validation:

- `loads(..., max_age=3600)` (1 hour expiry)

On valid token:

- set `user.is_confirmed = True`
- set `user.confirmed_on = now`
- commit
- login user and redirect to `/profile`

On invalid/expired token:

- flash error and redirect home

---

### Resend Confirmation Behavior

Route:

- `POST /send_confirmation_email`

Current behavior:

- requires email only
- verifies account exists and is not already confirmed
- sends new confirmation email with signed token link
- returns user to login view with status flash

If account is already confirmed:

- does not resend
- shows informative message

---

### Login Gate on Unconfirmed Accounts

`POST /login` enforces confirmation:

- valid credentials + `is_confirmed == False` -> login blocked
- user is prompted to resend confirmation email

This ensures only confirmed accounts can enter authenticated app flows.

---

### Error Handling Notes

- Registration commit failures return user-facing error and do not continue.
- Email-send failures are caught and surfaced with user guidance.
- Resend email failures are caught and surfaced with retry guidance.

---

### Related Components

- Backend:
  - `modules/views.py`
    - `register`
    - `email` (registration submit)
    - `send_confirmation_email`
    - `confirm_email`
    - `login`
  - `modules/models.py`
    - `Player`
- Frontend:
  - `templates/register.html`
    - registration form + client-side match/length validation UX
  - `templates/login.html`
    - resend confirmation entry point for unconfirmed users

## Reset Password

### Purpose

Allows a user to request a password reset email and set a new password via a time-limited tokenized reset link.

Core outcomes:

- reset email link is sent to the user
- link opens `/reset_email/<token>` reset form
- password update is accepted only with a valid reset token
- new password is hashed and stored in `Player`

---

### End-to-End Flow (Validated)

1. User opens login page and clicks **Reset Password**.
2. Frontend reset modal collects email and submits:
   - `POST /reset_pwd`
3. Backend validates request and (if account exists) sends reset email containing:
   - `GET /reset_email/<token>`
4. User opens reset link.
5. Backend validates token (`RESET_PASSWORD_SALT`, 1-hour max age) and renders reset form.
6. Reset form posts:
   - `POST /change_pwd`
   - includes hidden `reset_token`
7. Backend re-validates reset token, resolves user email from token, validates new password inputs, updates password hash, logs user in, and redirects to profile.

---

### Reset Request Behavior (`POST /reset_pwd`)

Input:

- `reset_email`

Behavior:

- missing email -> error flash
- if account exists:
  - generate signed reset token
  - send reset email with tokenized link
- if account does not exist:
  - no specific existence disclosure

Response hardening:

- returns generic success message:
  - "If an account exists for that email, a reset link has been sent..."
- avoids account enumeration via response content
- email send is exception-handled and logged

---

### Token Validation (`GET /reset_email/<token>`)

Token checks:

- signed by serializer
- salt: `RESET_PASSWORD_SALT`
- expiry: `max_age=3600` (1 hour)

On valid token:

- load user by token email
- render `resetpwd.html` with:
  - hidden email value (display/support)
  - hidden `reset_token` (authoritative for update)

On invalid/expired token:

- flash error and redirect to index

---

### Password Update (`POST /change_pwd`)

Security model (token-bound):

- requires `reset_token`
- verifies token server-side before any password change
- derives target email from verified token (does not trust posted email as authority)

Validation:

- both password fields present
- password and confirmation match
- minimum length >= 6 (backend enforced)

Write:

- `Player.pwd = generate_password_hash(new_pwd)`
- commit transaction
- login user and redirect to `/profile`

---

### Error Handling Notes

- reset email send failures are caught/logged
- invalid/expired/missing token blocks password change
- reset form re-render now preserves correct email context on validation failures

---

### Related Components

- Backend:
  - `modules/views.py`
    - `reset_pwd`
    - `reset_email`
    - `change_pwd`
- Frontend:
  - `templates/login.html`
    - reset modal + hidden reset form submit
  - `templates/resetpwd.html`
    - new password form + hidden `reset_token`

## Edit Profile

### Purpose

Allows an authenticated user to view and update profile attributes from `/profile`.

Displayed profile values:

- `Player.email` (read-only)
- `Player.username` (editable)
- `Player.profile_image` filename (rendered as image preview)

Editable fields:

- `Player.username`
- `Player.profile_image`

The UI supports edit/cancel/save interactions without full-page reload on successful save.

Intentional behavior:

- changing username changes which hero-perspective data rows are shown throughout the app (queries keyed by `p1 == current_user.username`)
- this is expected and intentionally not auto-migrated

---

### End-to-End Flow (Validated)

1. User opens `GET /profile`.
2. Backend loads profile page with:
   - current user details
   - available profile images from `static/images/profile`
   - selected image fallback to default when stored filename is missing/invalid
3. User clicks **Edit Profile**.
4. Frontend switches to edit mode, exposing:
   - username input
   - profile image dropdown
   - email remains display-only
5. User clicks **Save Changes**.
6. Frontend compares current values to original state:
   - if unchanged -> exits edit mode with no API call
   - if changed -> submits JSON to `POST /edit_profile`
7. Backend validates/sanitizes payload:
   - username length policy `3-20` chars (for changed usernames)
   - profile image constrained to server-side filesystem allowlist
8. Backend updates `Player`, commits transaction, and returns JSON response.
9. Frontend applies returned values to display + preview and exits edit mode.

---

### Backend Validation + Write Behavior

Route:

- `POST /edit_profile`

Validation behavior:

- reads JSON payload keys:
  - `ProfileUsernameInputText`
  - `ProfileImageInputValue`
- trims username input server-side
- username policy:
  - if username changed, length must be `3-20`
  - invalid -> `400` JSON error: `Username must be 3-20 characters long.`
- rebuilds allowlist of profile images from filesystem
- enforces profile image selection to allowlist; invalid values fall back to default image

No-op detection:

- if requested username and image are unchanged from current values:
  - returns success with `updated: false`
  - skips DB write

Write behavior:

- updates `Player.username` and/or `Player.profile_image`
- commits on success
- rolls back, logs commit error, and returns error JSON on DB failure

---

### Frontend UX Behavior

Implemented in `static/profile.js`:

- stores original profile state on entering edit mode
- **Cancel** restores original values and exits edit mode
- live image preview updates when dropdown selection changes
- **Save** updates view with backend-confirmed values
- when backend returns validation/error JSON (including HTTP 400), UI now surfaces specific server message instead of always showing a generic failure

Performance behavior:

- avoids unnecessary API/database call when user made no changes
- does not force page reload after successful update

---

### Security Boundary

Primary protections:

- `@login_required`
- update is scoped to `Player.uid == current_user.uid`
- profile image value constrained to server-side allowlist
- username policy enforced server-side (`3-20`) independent of frontend checks

---

### Related Components

- Backend:
  - `modules/views.py`
    - `profile`
    - `edit_profile`
  - `modules/models.py`
    - `Player`
- Frontend:
  - `templates/profile.html`
    - profile edit controls and form elements
  - `static/profile.js`
    - edit mode, state management, submit/cancel logic

## Export to CSV

### Purpose

Allows a logged-in user to request an asynchronous data export from `/profile`, generate CSV files for user-owned datasets, and receive a time-limited download link by email.

Export scope includes:

- `Match` (hero-perspective rows)
- `Game` (hero-perspective rows)
- `Play`
- `Pick`
- `Draft`

---

### End-to-End Flow (Validated)

1. User clicks **Export to CSV** on `/profile`.
2. Frontend calls:
   - `POST /api/export/request`
3. Backend validates request guardrails:
   - no active export job for this user
   - cooldown has elapsed since last request
4. Backend creates `ExportJob(status='queued')` and dispatches Celery task:
   - `generate_export_csv.delay(...)`
5. Worker transitions job to `running`, queries table data, and writes CSV artifacts.
6. Worker stores artifacts to configured backend:
   - S3 (`/{uid}/export/...`) when S3 is enabled
   - local filesystem (`local-dev/data/exports/{uid}/...`) in local development
7. Worker creates ZIP bundle of generated CSVs, updates `ExportJob` to `completed`, and sets `expires_at` (TTL).
8. Worker emails user a signed download link (`/export/download/<token>`).
9. User downloads from email link before expiry.

---

### Request Eligibility and Cooldown

Route:

- `POST /api/export/request`

Request is accepted only when:

- user is authenticated (`@login_required`)
- no existing export job for that user is in `queued` or `running`
- cooldown window has elapsed

Cooldown behavior:

- `EXPORT_COOLDOWN_SECONDS` env value is enforced per user
- default is `24 * 60 * 60` (24 hours) when env is unset

---

### Data Selection Rules

Export queries are user-scoped:

- `Match`: `uid == current_user.uid` and `p1 == current_user.username`
- `Game`: `uid == current_user.uid` and `p1 == current_user.username`
- `Play`: `uid == current_user.uid`
- `Pick`: `uid == current_user.uid`
- `Draft`: `uid == current_user.uid`

For exported CSV content:

- internal `uid` column is dropped before write
- large tables are written in chunks to reduce peak memory pressure

---

### Delivery and Download Link Security

Email delivery:

- on successful completion, worker sends an email to the requesting user
- email contains signed token URL: `/export/download/<token>`

Token and link controls:

- token signed with `URLSafeTimedSerializer`
- dedicated salt: `EXPORT_DOWNLOAD_SALT`
- token max age aligned to export TTL (+ small buffer)
- token payload binds to both:
  - `uid`
  - `export_id`

Download validation (`GET /export/download/<token>`):

- token must be valid and unexpired
- job must exist and belong to token user
- job must be `completed`
- `expires_at` must be in the future
- `zip_key` must be present and artifact must exist

On failure, endpoint returns explicit error responses (`400`, `410`, or `500` as applicable).

---

### TTL and Cleanup Behavior

TTL:

- `EXPORT_TTL_SECONDS = 3600` (1 hour per export)

Runtime cleanup:

- expired completed exports are deleted when export-status/download flows execute
- job is marked `expired` and `cleaned_at` is recorded

Startup cleanup:

- app startup runs `cleanup_export_artifacts_on_startup()`
- deletes any previously tracked export artifacts (S3/local)
- clears persisted artifact keys on `ExportJob`
- marks stale completed jobs as `expired`
- marks stale queued/running jobs as `failed`

This ensures export artifacts do not persist across app restarts.

---

### Frontend Status Messaging

`/profile` status is driven by `GET /api/export/latest-status`:

- `queued/running` -> export in progress messaging
- `completed + non-expired` -> "Check email for download link."
- cooldown active without completed export -> cooldown remaining message
- failed/expired/no-history -> corresponding state message

---

### Related Components

- Backend:
  - `modules/views.py`
    - `api_export_request`
    - `api_export_latest_status`
    - `export_download_token`
    - `generate_export_csv` (Celery task)
    - `_cleanup_expired_exports`
    - `cleanup_export_artifacts_on_startup`
  - `modules/models.py`
    - `ExportJob`
  - `app.py`
    - startup invocation of export artifact cleanup
- Frontend:
  - `templates/profile.html`
    - Export request UI and status text container
  - `static/profile.js`
    - request action + status polling/render logic

---

### Operational Notes

Key environment/config values for export behavior:

- `EXPORT_COOLDOWN_SECONDS`
  - per-user minimum interval between export requests
  - default: `86400` (24 hours)
- `EXPORT_DOWNLOAD_SALT`
  - salt used when signing export download tokens
  - should be a long, random, private secret
- `URL_SAFETIMEDSERIALIZER`
  - serializer secret key used for signed tokens in multiple app flows
  - must be stable across app/worker processes
- `APP_BASE_URL`
  - public base URL used to build absolute download links in export emails
  - examples:
    - production: `https://mox-data.com`
    - local testing with exposed host: `http://localhost:8000`
- `S3_BUCKET_NAME`
  - when set, export artifacts are stored in S3
  - when unset, local filesystem export storage is used
- `S3_PREFIX` (optional)
  - prefix prepended to S3 object keys
  - normalized with trailing `/` when present
- `AWS_REGION` (S3 mode)
  - region used by S3 client initialization

Operational recommendations:

- Keep `EXPORT_DOWNLOAD_SALT` and `URL_SAFETIMEDSERIALIZER` out of source control.
- Ensure Flask app and Celery worker share the same env values.
- Set `APP_BASE_URL` explicitly in production to avoid malformed email links.
- If you rotate signing secrets, existing emailed links become invalid.
- Startup cleanup removes prior export artifacts; users should request a fresh export after restarts.

## Analytics Dashboards (`/dashboards`)

### Purpose

Provides interactive analytics views for the logged-in user across four dashboard types:

- Match Performance
- Card Analysis
- Opponent Analysis
- Game Statistics

Users generate dashboards from the menu, apply filters, and render KPI cards, charts, and tables from user-scoped match/game/play data.

---

### End-to-End Flow (Validated)

1. User opens `GET /dashboards`.
2. Backend route `dashboards()` renders `templates/dashboards.html` (`@login_required`).
3. Frontend initializes on `DOMContentLoaded`:
   - loads filter dropdown options via `GET /filter_options`
   - applies dashboard-type filter UI behavior
   - generates the default dashboard
4. User selects dashboard type + filters and clicks **Generate Dashboard**.
5. Frontend calls `POST /api/dashboard/generate` with:
   - `dashboard_type`
   - `filters`
6. Backend:
   - validates request payload
   - normalizes numeric filters (`opponentThreshold`, `heroMulls`, `oppMulls`)
   - applies user-scoped base query + dashboard filters
   - dispatches to the matching generator function
7. Backend returns dashboard payload (`metrics`, `charts`, `tables`, optional `table_grids`).
8. Frontend renders cards/tables/charts and updates loading/error states.

---

### Routes and API Endpoints

- Page route:
  - `GET /dashboards` -> template render
- Filter options:
  - `GET /filter_options`
- Cascading filter refresh:
  - `POST /api/dashboard/filtered-options`
- Dashboard generation:
  - `POST /api/dashboard/generate`

All are authenticated with `@login_required`.

---

### Dashboard Types and Generators

Backend dispatch (`api_dashboard_generate`) maps to:

- `match-performance` -> `generate_match_performance_dashboard(...)`
- `card-analysis` -> `generate_card_analysis_dashboard(...)`
- `opponent-analysis` -> `generate_opponent_analysis_dashboard(...)`
- `game-data` -> `generate_game_data_dashboard(...)`

Shared filtering helpers:

- `apply_dashboard_filters(...)` (match query)
- `apply_dashboard_filters_to_play_query(...)`
- `apply_dashboard_filters_to_game_query(...)`

---

### Filter Behavior and Validation

Common filters:

- `card`, `opponent`, `format`, `deck`, `oppDeck`
- `startDate`, `endDate`
- dashboard-specific:
  - `perspective` (card analysis)
  - `opponentThreshold` (opponent analysis)
  - `heroMulls`, `oppMulls` (game statistics)
  - `chartCasting` (game chart perspective toggle)

Validation hardening:

- numeric filter parsing is centralized in `api_dashboard_generate`
- invalid numeric values now return clean `400` errors (not `500`)
- invalid payload shape also returns clean `400`

---

### Data Scope and Security Boundary

Core constraints:

- all dashboard queries are scoped to the current user:
  - `uid == current_user.uid`
  - hero perspective for match rows (`Match.p1 == current_user.username`)
- no custom header is used as a security boundary

This prevents cross-user data leakage and keeps dashboard stats tied to the authenticated account.

---

### Rendering Contract

Frontend (`templates/dashboards.html`) expects:

- `metrics`: KPI card list
- `charts`: chart definitions (may be empty by design)
- `tables`: standalone tables
- `table_grids`: grouped table card layouts

Note:

- Opponent Analysis intentionally returns no chart in the normal success path (`charts: []`) based on current product UX decision.

---

### Error and Loading UX

Behavior:

- dashboard generation shows loading state and hides prior results
- errors render a visible inline error panel with retry action
- chart-casting updates now use the same visible error/reset behavior as full generation (not console-only)

---

### Hardening Changes Applied During Validation

1. **Duplicate match inflation fix (high)**
   - card filter in `apply_dashboard_filters(...)` now uses correlated `EXISTS` instead of join-expansion
   - avoids duplicate match rows when a card appears multiple times in a match
2. **Security boundary cleanup**
   - removed reliance on `X-Requested-By` checks for dashboard/filter APIs
3. **Numeric parsing hardening**
   - invalid `opponentThreshold` / `heroMulls` / `oppMulls` now return `400`
4. **`/filter_options` response-shape consistency**
   - endpoint now consistently returns JSON via `jsonify(...)`
5. **Chart-casting error UX consistency**
   - failures now show the same user-visible error panel and reset loading state
6. **Residual HTML injection surface reduction**
   - dashboard table text from DB/user content is escaped before HTML embedding via `sanitize_dashboard_text(...)`

---

### Related Components

- Backend:
  - `modules/views.py`
    - `dashboards`
    - `filter_options`
    - `api_dashboard_filtered_options`
    - `api_dashboard_generate`
    - `apply_dashboard_filters*`
    - `generate_match_performance_dashboard`
    - `generate_card_analysis_dashboard`
    - `generate_opponent_analysis_dashboard`
    - `generate_game_data_dashboard`
- Frontend:
  - `templates/dashboards.html`
    - dashboard controls, fetch calls, rendering, loading/error states
  - `static/dashboards.css`
    - dashboard visual styling

## Table Pages (`/table`) — Matches and Drafts Display

### Purpose

Displays paginated database records for:

- `Matches` (`/table/matches/<page>`)
- `Drafts` (`/table/drafts/<page>`)

This section covers display/load flow only (data retrieval, pagination, rendering).  
`Revise Row(s)` / `Remove Row(s)` are intentionally excluded because those flows are documented separately.

---

### End-to-End Flow (Validated)

1. User opens a table page:
   - `GET /table/matches/<page_num>` or
   - `GET /table/drafts/<page_num>`
2. Backend route `table(table_name, page_num)` renders `templates/tables.html`.
3. Frontend initializes `TableManager` (`static/tables.js`) using hidden `#tname` and page context.
4. For top-level Matches/Drafts pages, frontend now forces API-driven rendering:
   - `GET /api/table/<table_name>/<page_num>`
5. Backend route `api_table_data(...)` returns paginated JSON payload:
   - `data`, `total_count`, `total_pages`, `page_num`, `has_previous`, `has_next`
6. Frontend renders rows into the table body, updates pagination controls, and applies selection/drill interactions.
7. User clicks `Previous`/`Next`; frontend calls same API for the new page and re-renders.

---

### Routes and API Endpoints

Page routes:

- `GET /table/<table_name>/<page_num>` -> `table(...)`

API route:

- `GET /api/table/<table_name>/<int:page_num>` -> `api_table_data(...)`

Both are protected by `@login_required`.

---

### Query Scope and Ordering

`Matches`:

- scope:
  - `Match.uid == current_user.uid`
  - `Match.p1 == current_user.username` (hero-perspective row)
- ordering:
  - `Match.date DESC`

`Drafts`:

- scope:
  - `Draft.uid == current_user.uid`
- ordering:
  - `Draft.date DESC`

---

### Pagination Behavior

Pagination constants:

- `page_size = 20`

API payload includes:

- `page_num`
- `total_pages`
- `total_count`
- `has_previous`
- `has_next`

Empty-table hardening:

- `api_table_data(...)` now clamps `total_pages` to at least `1`
- this prevents `/api/table/<table>/1` from returning `400` when dataset is empty
- empty page now returns valid response with `data: []`

---

### Rendering Path and Formatting

Primary renderer:

- `static/tables.js`:
  - `loadTableData(...)`
  - `renderTable()`
  - `getColumnsForTable(...)`

Matches format display:

- uses JS formatter `formatDisplayForMatch(...)` to conditionally render:
  - `{format} - {limited_format}` when applicable

Draft format display:

- JS renderer now uses:
  - `row.draft_format ?? row.format ?? 'NA'`
- this fixes API-rendered Draft rows that previously referenced `row.format` only.

---

### Loading / Empty / Error States

Loading:

- `showProcessingModal('Loading table data...')` during API fetch

Success:

- rows rendered into `.modern-table tbody`
- pagination updated from API response

Empty:

- table body shows `No data available` row when API returns empty `data`

Error:

- fetch failures surface `Failed to load table data`

---

### Security Boundary

Primary protections:

- `@login_required` on page + API endpoints
- user-scoped database filters (`uid`, plus hero perspective for Matches)

No cross-user rows are returned in these table views.

---

### Hardening Changes Applied During Validation

1. **Draft format mismatch fix**
   - corrected JS Draft column mapping from `row.format` to `row.draft_format` fallback chain
2. **Empty dataset pagination fix**
   - API now returns valid page-1 response for empty tables
3. **Dual render-path divergence reduction**
   - top-level Matches/Drafts pages now force API-driven rendering to keep display logic consistent with one path

---

### Related Components

- Backend:
  - `modules/views.py`
    - `table`
    - `api_table_data`
- Frontend:
  - `templates/tables.html`
    - table shell, headers, pagination controls
  - `static/tables.js`
    - `TableManager`
    - `loadTableData`
    - `renderTable`
    - `getColumnsForTable`
    - `formatDisplayForMatch`

## User Login (`/login`)

### Purpose

Authenticates an existing user account and establishes an application session, with optional persistent login via a **Remember me** choice.

Related login-page capabilities include:

- resend confirmation email for unconfirmed accounts
- reset password initiation

---

### End-to-End Flow (Validated)

1. User opens `GET /login`.
2. Backend route `login()` checks auth state:
   - if already authenticated -> redirect to `/profile`
   - otherwise render `templates/login.html`
3. User submits login form (`POST /login`) with:
   - `login_email`
   - `login_pwd`
   - optional `remember_me`
4. Backend validates request fields.
5. Backend looks up user by email (`Player` table).
6. Backend verifies password hash (`check_password_hash`).
7. Backend checks confirmation status:
   - unconfirmed -> block login and render page with resend-confirmation UI
8. On valid credentials + confirmed account:
   - `login_user(user, remember=remember_me)`
   - redirect to `/profile`

---

### Validation and Decision Flow

`POST /login` server-side checks:

1. missing email/password -> error flash + re-render
2. invalid credentials -> generic error flash + re-render
3. valid credentials but `is_confirmed == False` -> confirmation-required error + `not_confirmed=True`
4. valid + confirmed -> login success + redirect

Re-render behavior:

- email is preserved for convenience
- password field is intentionally left blank
- remember-me checkbox state is preserved

---

### Session Behavior

Login persistence is now user-controlled:

- if **Remember me** checked:
  - persistent login cookie is issued (`remember=True`)
- if unchecked:
  - standard non-persistent session cookie is used (`remember=False`)

Current application config does not override session lifetime values in code for non-remember sessions.

---

### Login Page Adjacent Flows

From `templates/login.html`:

- **Send Confirmation Email**
  - posts to `POST /send_confirmation_email`
  - now requires only email client-side (no password requirement)
- **Reset Password**
  - modal posts to `POST /reset_pwd`
  - always returns generic success message to avoid account enumeration

These flows are adjacent to login UX but distinct from credential authentication itself.

---

### Security Boundary

Primary protections:

- password hashes verified server-side (`check_password_hash`)
- authenticated session established through Flask-Login (`login_user`)
- user restoration via SQLAlchemy session lookup in user loader (`db.session.get(Player, uid)`)

Enumeration hardening applied to login auth path:

- unknown-email and wrong-password cases now use the same generic credential error message.

---

### Hardening Changes Applied During Validation

1. **Account enumeration reduction in login path**
   - login now returns a unified invalid-credentials message for unknown email and wrong password
2. **Password repopulation removed**
   - login form no longer re-renders the submitted password value
3. **Resend confirmation UX updated**
   - frontend resend-confirmation action no longer requires password input
4. **Remember-me policy made explicit**
   - added checkbox and switched login call to `remember=remember_me`
5. **Legacy SQLAlchemy user-loader warning resolved**
   - replaced `Player.query.get(...)` with `db.session.get(Player, ...)`

---

### Related Components

- Backend:
  - `modules/views.py`
    - `login`
    - `send_confirmation_email`
    - `reset_pwd`
  - `app.py`
    - Flask-Login setup
    - `user_loader` (`db.session.get`)
  - `modules/models.py`
    - `Player` (`email`, `pwd`, `is_confirmed`)
- Frontend:
  - `templates/login.html`
    - login form
    - remember-me checkbox
    - resend-confirmation and reset-password triggers

## Load Report Email

### Purpose

Builds and emails a post-run summary report to the user after background load/reprocess tasks complete, using record-count values captured during task execution.

The report provides a quick operational summary of:

- new records loaded
- updated/replaced records
- skipped files/records (where applicable)
- task completion timestamp

---

### Triggering Flows (Validated)

Load report email generation is used after:

- `process_logs`
- `process_revisions_from_app`
- `reprocess_logs`

These run as Celery tasks and construct report content within Flask app context.

---

### End-to-End Flow (Validated)

1. User action triggers one of the load/reprocess routes.
2. Route enqueues Celery task with user metadata (email, uid, username).
3. Task executes and accumulates counters in a `counts` dictionary.
4. Task captures completion timestamps (`curr_date`, `curr_time`).
5. Task writes a `TaskHistory` row:
   - `submit_date`
   - `complete_date`
   - `task_type`
   - `error_code` (when applicable)
6. Task builds HTML report (`msg.html`) from counter values.
7. Task sends report email to requesting user:
   - subject: `MTGO-DB Load Report #<task_id>`
8. Task logs email success/failure in debug logs.

---

### Routes / Task Mapping

- `POST /load` -> `process_logs`
- `POST /load_revisions_from_app` -> `process_revisions_from_app`
- `POST /reprocess` -> `reprocess_logs`

---

### Report Content and Counters

Each task has its own report table shape, but all are count-driven.

Examples of count classes:

- new records (`new_matches`, `new_games`, `new_plays`, `new_drafts`, `new_picks`)
- updated/replaced records (`updated_*`, `*_replaced`, `matches_updated`, `drafts_updated`)
- skipped categories (`*_skipped_*`)
- processed file totals (`total_gamelogs`, `total_draftlogs`)

Counter-to-report alignment hardening applied:

- `process_logs`: now increments `plays_replaced` / `picks_replaced` when duplicates are encountered in those branches

---

### Failure / Email Behavior

Failure hardening applied:

- `reprocess_logs` no longer continues to send normal success-style reports after critical failures
- it now:
  - set `error_code`
  - persist `TaskHistory`
  - raise to mark Celery task as failed
  - skip success report send when task failed

Email-send resilience hardening applied:

- load report email sending now uses `try/except` logging consistently across all active task flows
- SMTP/send failures are logged without crashing unrelated task-finalization bookkeeping

---

### Presentation / HTML Consistency

Report presentation fixes applied:

- corrected malformed heading close tags (`</h3>`)
- normalized revisions report title wording to explicitly indicate revisions flow
- corrected missing paragraph close tag in reprocess report footer

These changes reduce malformed HTML rendering risk in email clients and improve report clarity.

---

### Security and Scope

Load reports are sent to the email supplied from authenticated user-triggered flows.

Core protections:

- task submission routes are user-scoped app flows
- counters are generated from user-scoped processing operations
- `TaskHistory` rows are tied to the initiating user (`uid`, `curr_username`)

---

### Related Components

- Backend:
  - `modules/views.py`
    - `process_logs`
    - `process_revisions_from_app`
    - `reprocess_logs`
    - trigger routes: `load`, `load_revisions_from_app`, `reprocess`
  - `modules/models.py`
    - `TaskHistory`
- Frontend:
  - `templates/base.html`
    - forms/buttons that trigger load/reprocess routes
