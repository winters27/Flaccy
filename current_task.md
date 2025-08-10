# **Boilerplate Preface — Preserve Logic, Change Presentation Only**

> **IMPORTANT:** This project is limited strictly to changes in **toast presentation**. **Do not alter** any underlying logic for downloading music, defining albums/playlists/tracks, retrieving metadata, or displaying album art information. The backend’s output for album/playlist definitions, metadata (titles, artwork, artist names), and download behavior is **authoritative** and must be used exactly as provided. Treat these systems as a **black box** — read from them, but never modify them.

* No changes to album, playlist, or track definitions.
* No changes to metadata/artwork source or processing.
* No changes to download logic, queuing, or concurrency.
* No changes to API contracts other than adding a **read-only** progress reporting surface.
* No introduction of new network calls or third-party services.

The only permitted scope of change is **how toasts behave, update, and display** the existing data.

---

# Flaccy Toast & Progress — **Execution Expectations & Outcomes**

This document specifies **what must be true** after the work is completed. It intentionally avoids prescribing how to implement it. Treat this as a product/QA spec.

---

## 1) Scope

Upgrade notifications so **album** and **playlist** downloads use **a single, persistent toast per job** with **determinate progress** and clear lifecycle states.

---

## 2) Definitions

* **Job**: A single album or playlist download; uniquely identified by a `jobId`.
* **Toast**: The transient UI surface that communicates job status and progress.
* **Progress**: Determinate numeric progress reflecting tracks processed vs total.

---

## 3) UX Requirements (Must-Haves)

1. **One toast per job**

   * Only **one** toast is visible per album or playlist job at any time.
   * Starting a new job shows one toast for that job. No per-track toasts.

2. **Determinate progress**

   * Toast displays **`current/total`** and a **percentage**.
   * **Album:** `current` counts tracks in that album.
   * **Playlist:** `current` counts tracks in that playlist; must read **`1/N, 2/N, … N/N`** where **N** equals the playlist size at job start.

3. **Descriptive labels**

   * Title reflects the scope: “Downloading Album …” or “Downloading Playlist …”.
   * Body includes **current track title** when available: `Track current/total — <track title>`.

4. **Smooth updates**

   * Progress updates feel **stable** (no flicker, no restart to 0%).
   * Visual updates appear **no more frequently than \~5–8 per second** and **no less frequently than \~1 per second** while work is progressing.

5. **Terminal states**

   * **Success:** Toast morphs to “Download complete” with a ✅ and **auto‑dismisses** within **2–4s**.
   * **Error:** Toast switches to an error state, shows a concise message, and offers **Retry** and **Dismiss**.
   * **Cancelled (if supported):** Toast shows “Cancelled” and dismisses within **4–6s**.

6. **Multiple concurrent jobs**

   * Each job has its **own toast**; no cross‑pollination of progress or labels.
   * Up to **three** simultaneous jobs display without overlap or misrouting.

7. **No duplicate or zombie toasts**

   * Updates always target the existing toast for that `jobId`.
   * After a terminal state, the toast is removed and does **not** reappear.

---

## 4) Behavioral Requirements

1. **Playlist counting**

   * `total` for a playlist equals the number of tracks in the playlist at job start.
   * `current` increments by **1** per track processed, regardless of individual track failures (see partial failure rules).

2. **Album counting**

   * `total` equals album track count; `current` increments per track.

3. **Partial failures**

   * If some tracks fail but the job as a whole finishes, the final toast either:

     * Shows success with a small note like “Some tracks failed”, **or**
     * Shows error with a count of failures and offers **Retry failed** (implementation of retry is optional; the presence of an affordance is required if errors occurred).

4. **Idempotent visual updates**

   * The same logical progress update should never create a new toast or regress the visible count/percent.

5. **Resilience to rapid events**

   * Progress should remain monotonic and stable even if tracks complete very quickly.

6. **Accessibility**

   * Toast content must be readable by screen readers (announce title + progress updates).
   * Provide sufficient contrast and avoid purely color‑coded status indications.

---

## 5) Non‑Functional Requirements

* **Performance:** UI updates should not noticeably impact scrolling or interactivity.
* **Resource cleanup:** All resources associated with a job (timers, listeners) are released on terminal state.
* **Configurability:** Timeouts for auto‑dismiss are centralized and tunable.

---

## 6) Observability

* Log (or otherwise record) per `jobId`:

  * First visible progress event
  * Last/terminal state
  * Total duration (ms)
  * Count of failed tracks (if any)

---

## 7) Acceptance Tests (Black‑Box)

1. **Album — happy path**

   * Start an album download with N tracks.
   * Expect a single toast with title “Downloading Album …”.
   * Progress advances `1/N → N/N`, shows current track title.
   * On finish, toast shows ✅ and auto‑dismisses within 2–4s.

2. **Playlist — counting rule**

   * Start a playlist download with **N=12** tracks.
   * Expect body to display `1/12, 2/12, …, 12/12` (no extra toasts).

3. **Concurrency**

   * Start two jobs (album A with 8 tracks, playlist P with 20 tracks).
   * Each job maintains its own toast with correct labels and counts.
   * No cross‑updates or flicker.

4. **Fast tracks**

   * Simulate tracks that complete in <100ms.
   * Progress appears smooth; text/percent never flickers or resets.

5. **Error handling**

   * Force a mid‑job error.
   * Toast transitions to error state, shows message, offers **Retry**.
   * On Retry, a new job begins with a **new** `jobId` and a **new** toast; the old one does not reanimate.

6. **Partial failures**

   * Simulate 2 failed tracks in a 10‑track playlist.
   * Final state communicates partial failure (either success with note or error with count) per Behavioral Requirements.

7. **Cancellation (if supported)**

   * Cancel an in‑flight job.
   * Toast shows “Cancelled”; disappears within 4–6s; no background updates continue.

8. **Zombie/toast leaks**

   * After terminal state, verify no stray timers/listeners remain and the toast is not visible.

---

## 8) Out‑of‑Scope

* Changing providers or altering what constitutes a “track”.
* Replacing the existing toast library or UI framework.
* Building a full job queue dashboard beyond the toast surface.

---

## 9) Deliverables (Expectation‑oriented)

* The application, when run, exhibits all **UX**, **Behavioral**, and **Non‑Functional** requirements above.
* A brief doc (`docs/notifications.md`) explains:

  * The meaning of `current`, `total`, and how **playlist `N`** is determined.
  * Lifecycle states and what the user should see in each state.
  * How errors and partial failures are communicated to the user.
* Evidence (screenshots or short GIFs) showing:

  * Album: `1/N → N/N` with track titles and final ✅.
  * Playlist: **`1/N … N/N`** behavior.
  * Two concurrent jobs with independent toasts.
  * An error case showing Retry.

---

## 10) Success Criteria (Go/No‑Go)

* **GO** if every Acceptance Test passes as‑written and the Deliverables are provided.
* **NO‑GO** if any of the following occur:

  * Multiple toasts are created for a single job.
  * Playlist progress fails to show **`1/N … N/N`** using the real playlist size.
  * Visual progress regresses or flickers under fast updates.
  * Terminal states fail to auto‑dismiss or leave zombie listeners.
  * Error states lack a clear message or a Retry affordance.

---

## 11) Guardrails: Protected Logic & Domain Invariants (Do **Not** Change)

These items are **frozen**. The work only alters how toasts **present** information, not how data is **produced**.

**Domain semantics**

* The meaning of **album**, **playlist**, and **track** is **unchanged**.
* Source providers, authentication, and fetch semantics remain as they are today.
* The rules for **which tracks belong** to an album/playlist, their **order**, and any filtering/quality selection **must not be modified**.

**Download pipeline**

* The steps that locate, fetch, decode, transcode, tag, and write files are **unchanged**.
* File names/paths, tagging rules, embedded artwork handling, and output directory logic are **unchanged**.
* Any concurrency/queuing/backoff behavior that determines *when* a track is processed is **unchanged**.

**Metadata & artwork**

* The **current source of album art and track metadata** is authoritative; do not replace or transform it beyond what’s already emitted.
* Toasts may **display** existing fields (album name, artist, track title, artwork thumbnail if available), but they **must not compute new metadata** or rewrite existing values.

**APIs & contracts**

* Existing public/IPC/HTTP contracts (request/response shapes) remain unchanged **except** for adding a **read-only progress surface**.
* No renaming of fields, changing types, or removing fields that callers depend on.

**Security & privacy**

* Do not add new network calls, third-party telemetry, or additional permissions.

> Bottom line: treat the downloader and metadata pipeline as a **black box**. You may **read** progress/metadata from it, and you may **visualize** that in toasts, but you may not **alter** how that data is produced.

---

## 12) Contract Tests to Prevent Logic Drift

Implementers must ensure the following checks pass before merging. These tests are **black‑box** and exist to catch accidental behavior changes.

1. **API Shape Snapshot**

   * Capture the current request/response schema for starting a download job and for any progress payloads.
   * Assert that **no fields are removed or renamed** and that the types of existing fields are unchanged.

2. **Metadata Fidelity**

   * Given a known album/playlist fixture, verify the **exact same album/artist/track titles and artwork hashes** appear in the toast as those produced by the existing pipeline (string equality and image hash match).

3. **Ordering Guarantee**

   * For a playlist fixture, assert that the order of tracks shown in the toast body matches the order produced by the existing downloader (index equality across the whole list).

4. **Output Parity**

   * Before/After comparison of the written files (paths, tags, embedded art) shows **no differences** beyond timestamps.

5. **Throughput Invariance**

   * Average time to complete a fixed playlist (smoke test) does not regress by more than **5%** due solely to UI updates.

6. **Provider Parity**

   * Run one album and one playlist per provider currently supported; assert identical counts and labels vs. baseline logs.

7. **No Side‑Effects in UI Layer**

   * Disable toasts and re‑run the suite; downloader behavior and outputs remain identical, proving UI is read‑only.

**Failure policy:** Any failure in these tests is a **NO‑GO** until resolved; fixes must retain the guardrails in Section 11.
