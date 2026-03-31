# ScanQA Project — Conversation Handoff Document

## How to use this document

Paste this entire document into a new Claude conversation. It contains all the context, decisions, and the current spec needed to continue development planning for the ScanQA project. After pasting, you can pick up from any of the suggested next steps at the bottom.

---

## 1. Project summary

We are developing a 3D scan-based dimensional QA inspection system called **ScanQA**. It's a receiving inspection tool that compares 3D scans of incoming parts against CAD models to assess dimensional compliance. The system is designed to be a fast first-pass screen — not a CMM replacement. It auto-dispositions features it has proven capability to measure, and explicitly escalates everything else to manual gauging or CMM.

## 2. Key decisions made

### Hardware
- **Primary dev/production machine:** Mac Mini M4 Pro — 12-core CPU, 16-core GPU, 64GB unified RAM, 500GB+ SSD. Already owned.
- **Phase 0–1 scanner:** Creality Ferret SE — already owned. Consumer-grade, 0.1mm accuracy class. Explicitly classified as a **feasibility and Class B (review-only) scanner only**. Not approved for Class A auto-disposition in production.
- **Phase 2+ scanner:** To be determined based on Phase 0 accuracy data. Likely a Revopoint MINI 2 (~$800) or Einscan SP class (~$2K–$5K). The Phase 0 kill test produces the data to justify this purchase.
- **Budget:** ~$1K available now (already covered by the Ferret SE and Mac Mini being owned). Boss needs data to justify further spend — Phase 0 deliverables are designed to provide that data.

### Platform
- **macOS only for Phase 0–2.** Windows port deferred to Phase 3+. The Mac Mini runs all the needed open-source tools natively on Apple Silicon.
- **Scanner software:** Creality Scan (runs on macOS) exports PLY/OBJ files. The ScanQA application imports these files — it is scanner-agnostic by design.

### Target parts
- Mix of sizes, centered on shoebox-to-microwave range
- **Machined aluminum and steel** (CNC) — need scan spray for reflective surfaces
- **Injection molded plastic** (ABS, PC, Nylon) — cooperative surfaces, scan well
- **3D printed** (FDM and SLA) — FDM has layer line noise, SLA scans cleanly
- **10–50 SKUs** total
- **Low throughput** — a few parts per shift, receiving inspection

### Accuracy
- ±0.005" (±0.13mm) is the realistic working target for scan-derived measurements with multi-scan averaging on a mid-range scanner
- ±0.001" is not achievable with scanning — those features stay on calipers/CMM
- The Ferret SE will realistically achieve ±0.008–0.015" — useful for screening but not for tight-tolerance auto-disposition
- The system is designed around the principle that **the scanner determines the ceiling, not the software**

### Architecture philosophy
The spec went through two rounds of adversarial review that fundamentally reshaped the product from a "generic scan-to-CAD dimensional inspector" into a **"risk-limited, feature-gated, scan-assisted receiving inspection system."** Key principles:

1. **Feature eligibility classes (A/B/C):** Every feature on every part is classified. Class A = auto-disposition allowed (proven capable). Class B = review-only (measured but human decides). Class C = manual measurement only (scanner can't reliably observe it).
2. **No auto-disposition without MSA:** A formal Measurement System Analysis (Gage R&R) must prove the system is capable before any feature can be Class A. Two tiers: Screening MSA (Class B) and Release MSA (Class A, 10 parts, 3 operators, AIAG methodology).
3. **Conservative decision rules:** Pass only if measured value ± expanded uncertainty is fully inside tolerance (with guard band). Ambiguous results escalate — never auto-pass.
4. **Recipe locking:** Each part has a locked inspection recipe binding part revision + scanner + fixture + datum scheme + validated capabilities. Recipe mismatch blocks auto-disposition.
5. **NIST GUM uncertainty model:** Eight named uncertainty components, combined per GUM methodology. Coverage deficiency is a gate/inflation factor, not an RSS term.

### Tech stack
- Python 3.11+, PySide6 (Qt 6) for UI, VTK/PyVista for 3D rendering
- Open3D for point cloud processing and ICP alignment
- trimesh + scipy for primitive fitting
- cadquery / OCP (OpenCascade) for STEP import
- SQLite for data storage
- Jinja2 + weasyprint for PDF reports

### Development phases
- **Phase 0 (Weeks 1–3):** Feasibility kill test with Ferret SE. Can we align scans to CAD and extract useful measurements? Kill criteria defined.
- **Phase 1 (Months 1–2 post Phase 0):** Vertical slice — 3 parts, feature eligibility, decision engine, basic UI.
- **Phase 2 (Months 3–4):** Guarded production pilot — recipe locking, MSA workflow, 10+ parts, operator training.
- **Phase 3 (Months 5–8):** Broaden — datum-constrained alignment, GD&T, scanner upgrade, Windows port.

### Team
- In-house SW/controls engineers available for development
- QA technicians will be end users (wizard-driven UX, minimal training)
- Engineers handle part onboarding and recipe creation

## 3. Adversarial review feedback incorporated

The spec went through two rounds of expert review. Here's what each round changed:

### Review 1 — Major restructuring
- Added feature eligibility model (A/B/C classes) — the single most important addition
- Added formal decision rules with uncertainty and guard bands
- Added datum/fixture-first alignment (replaced generic best-fit default)
- Added MSA / Gage R&R acceptance plan
- Added false accept / false reject targets
- Added recipe locking by revision, scanner, and process
- Replaced global confidence score with local per-feature confidence
- Added reason-coded rescan/manual escalation
- Added Phase 0 kill test before any real development
- Cut: generic symmetry-aware alignment, rich trend dashboards, Windows support in early phases, surface reconstruction as default measurement path (direct primitive fitting is safer and more traceable)

### Review 2 — Precision redline (v2.1)
- Added hardware positioning statement (Ferret SE = feasibility/Class B only)
- Split MSA into two tiers (Screening for Class B, Release for Class A with AIAG 10-part study)
- Tightened GRR thresholds (<10% critical Class A, <20% noncritical, <30% Class B)
- Fixed alignment contradiction: added datum observability requirement (scan-visible fiducials, fixture geometry, or identifiable datum features required for fixture-assisted alignment)
- Rewrote uncertainty model per NIST GUM: 8 named components, proper RSS combination, coverage as gate/inflation not RSS term
- Added formal guard band policy section (3 methods: simple percentage, uncertainty-based per ASME B89.7.3.1, shared risk)
- Made local confidence thresholds recipe-derived from MSA data instead of global constants
- Added ReceivingContext entity (supplier, PO, lot, serial, sample plan)
- Expanded disposition taxonomy from 3 states to 7 (pass_scan_only, pass_after_manual, fail_by_scan, fail_after_manual, hold_for_review, accepted_under_deviation, incomplete)
- Added manual gauge provenance (gauge asset ID, cal due date)
- Added full uncertainty component breakdown in MeasurementEvidence
- Added operating model (30-min scanner warm-up, shift-start calibration, validity windows)
- Added blind holdout validation method for false accept rate
- Fixed constrained vs. unconstrained alignment gate (replaced with perturbation sensitivity test that works without the constrained algorithm)

### Review 3 — Adversarial redline (v2.2)
- **Section 4:** Split Class A column into critical and noncritical. Added ndc ≥ 5 (number of distinct categories) as a hard gate for Class A and Class B, per AIAG MSA 4th Edition guidance.
- **Section 7.1:** Fixed physically impossible preprocessing order. Moved CAD-proximity filtering to after Stage 1 coarse alignment (new Section 7.1.1). Replaced pre-alignment CAD filter with fixture/background ROI clip that does not depend on CAD alignment.
- **Section 7.2 / 8.1:** Resolved alignment failure policy contradiction. Introduced explicit two-band model: hard-block band (alignment rejected, no measurement) and soft-degrade band (measurement proceeds, all features capped at Class B review-only). Removed aggressive global defaults (0.05mm RMSE, 0.01mm stability convergence) — all alignment thresholds are now recipe-derived from MSA.
- **Section 2.2 / Phase 2:** Replaced false-accept pilot claim with statistically honest language. Phase 2 holdout is an early warning screen (goal: zero false accepts), not proof of <0.5%. Added rolling window minimum of 200 audited features for correlation checks. Added cumulative validation milestone at 500+ audited out-of-spec features.
- **Principle 0:** Added explicit statement that Ferret SE recipes are expected to be predominantly Class B. Removed consumer-hardware global micrometer-scale defaults throughout.
- **Section 7.5:** Replaced naive u_fit = RMSE/√n_inliers with effective sample size model (empirical correction factor for Class A, spatial decimation fallback for Class B). Made f_cov either empirically calibrated per recipe (Class A) or a conservative demotion rule (Class B).
- **Section 12:** Added EnvironmentSnapshot entity capturing ambient temperature, humidity, part temperature, warm-up elapsed time, CTE source, and ΔT. Enriched MSAStudy reference instrument fields with asset ID, calibration dates, certified uncertainty, and calibration authority. Added environment_snapshot_id FK to Inspection.
- **Phase 0:** Replaced "any feature type" kill test with requirement to test top 3 supplier-risk feature families. Coarse envelope dimensions do not count. Engineer must document target features and tolerance bands before scanning begins.

### Review 4 — Policy/schema seam closure (v2.3)
- **Sections 7.7 / 8.2:** Resolved local-confidence failure inconsistency. Added explicit precedence rule: Section 8.2 demotion (Class A → Class B) is evaluated first; Section 7.7 escalation (to RESCAN/MANUAL) only fires for features that fail all Class B gates. Added `REVIEW_ONLY_CONFIDENCE_DEMOTED` reason code. Documented which failing metrics route to RESCAN vs MANUAL.
- **Reason codes:** Fixed `FAIL_MARGINAL` semantic contradiction. Renamed the overlapping-uncertainty reject case to `MARGINAL_OUTSIDE` (routed to manual verification). `FAIL_MARGINAL` now means "clear reject with small margin" (value ± U entirely outside tolerance but deviation < 2×U). Added `MARGINAL_OUTSIDE` to reason code table and decision rules.
- **Section 12 — MeasurementFeature:** Added `criticality` field (critical/noncritical), `guard_band_method` field (simple_percentage/uncertainty_based/shared_risk), per-feature `guard_band_percent`, and `shared_risk_approval` text field. Moved guard band from recipe-level to per-feature with recipe-level default. This closes the gap between the policy (critical vs noncritical Class A, per-feature guard band method selection) and the data model.
- **Section 12 — ReceivingContext:** Added lot disposition fields (`lot_disposition`, `lot_disposition_by`, `lot_disposition_at`, `lot_disposition_notes`) and explicit lot disposition rules mapping per-part inspection outcomes to lot accept/reject/hold decisions. Documented sampling plan enforcement and noted that automated Z1.4 switching rules are deferred to Phase 3+.
- **Phase 1:** Added explicit hardware constraint: no production Class A on Ferret SE unless Release MSA proves it for the specific feature/part/fixture combination. Phase 1's primary value is pipeline validation, not Class A auto-disposition.

### Review 5 — Batch mode integration (v2.4)
- **Section 3:** Added same-part fixed-slot batch mode as Phase 2 in-scope. Mixed-part plates explicitly out of scope until Phase 3.
- **Section 5:** Added Step 2a — Batch plate layout definition (slot poses, spacing, fiducials, occlusion masks, slot equivalence groups). Added rule that batch recipes require separate MSA from single-part recipes.
- **Section 6:** Added Section 6.4 — Batch plate scanning mode with loading instructions, slot occupancy entry, scan path guidance, and shadow zone spacing rule.
- **Section 7:** Added Section 7.1.2 — Batch plate processing (plate localization → slot occupancy detection → slot ROI crop → slot contamination check → per-slot pipeline fan-out). Clustering is backup logic, not source of truth.
- **Section 8:** Added Section 8.0 — Plate-level confidence and Section 8.0.1 — Slot-level confidence as new confidence tiers above the existing global/local/decision model.
- **Section 9:** Added batch inspection wizard and batch results page (plate map, per-slot cards, batch summary banner, per-slot drill-down).
- **Section 10:** Added batch report structure (batch cover page + child per-slot reports).
- **Section 12:** Added BatchPlateLayout, BatchInspection, BatchSlot entities. Added slot_id FK to Inspection. Added slot_assignment_confidence, cluster_count, and cross_slot_contamination to MeasurementEvidence.
- **Section 13:** Added batch-mode performance targets (effective per-part cycle time, per-plate rescan rate, slot assignment error rate, contaminated-slot rate, unaffected-slot salvage rate).
- **Section 14:** Phase 1 adds plate design and slot-aware recipe schema (no batch execution). Phase 2 adds 2-up to 4-up same-part batch execution. Phase 3 adds mixed-part plates.

### Review 6 — Batch seam closure (v2.4.1)
- **Section 7.1.2 (B6):** Fixed per-slot pipeline sequencing bug. Call chain is now explicit: alignment (7.2) first, then post-alignment cleanup (7.1.1), then fusion through decision. Slot transform (plate pose + slot offset) is used as Stage 1 initial guess.
- **Section 8.0:** Split plate-level outcomes into fatal-redo (PLATE_LOCALIZATION_FAILED, PLATE_POSE_POOR, PLATE_COVERAGE_INSUFFICIENT) and pause/resolve (SLOT_OCCUPANCY_MISMATCH). "Entire batch must be redone" now only applies to fatal-redo events.
- **Reason codes / Section 8.0.1 / BatchSlot.slot_status:** Normalized batch failure codes to one canonical set of 8 codes used consistently across pipeline, reason code table, confidence model, DB schema, and reporting. Added PLATE_POSE_POOR, PLATE_COVERAGE_INSUFFICIENT, SLOT_ASSIGNMENT_UNCERTAIN, SLOT_MULTI_CLUSTER.
- **Section 8.0.1 / Section 15:** Contamination verification now caps all features at Class B review-only. Class A auto-disposition requires a clean rescan with no contamination flag. Hard no-go criteria updated to match.
- **Section 9.2.8:** "Reject entire batch" now requires free-text justification, engineer e-signoff if any slots were individually passing, and confirmation dialog. Added `fail_by_batch_override` to disposition taxonomy. Per-slot disposition is the default workflow.
- **Section 8.2:** Replaced misleading "silent from the operator's perspective" with "no extra operator action required." Reason code is visible in results/reports but does not generate an action item.

### Review 7 — Final naming/report cleanup (v2.4.2)
- **Section 10.1:** Added `fail_by_batch_override` to the report's overall disposition list so the report taxonomy exactly matches the persisted disposition taxonomy in Section 12.
- **Section 12 (BatchSlot):** Clarified that `slot_status` is a normalized state enum distinct from the canonical `SLOT_*` reason codes. Added explicit mapping table between the two. The reason_code field on child Inspection/InspectionResult records carries the full canonical code; slot_status is the persisted summary state on BatchSlot.

## 4. Open questions not yet resolved

These were raised in the reviews and not yet answered:

1. **What tolerance range do you actually need to auto-disposition?** Is ±0.003" really in scope, or is the business value mostly at ±0.010" and above? (This determines whether the Ferret SE is viable for any Class A features or if a scanner upgrade is required before Phase 1.)
2. **Are your critical features mostly external and visible?** Or do you need bores, hidden geometry, and datum-dependent true position? (The more internal/hidden features matter, the less a scanner helps.)
3. **Can you require a simple fixture and controlled scan path?** Or must it remain fully handheld and operator-variable? (Fixture-assisted scanning dramatically improves repeatability.)
4. **Is the goal to reduce manual measurement time, reduce CMM load, or catch supplier escapes earlier?** These lead to different product optimizations.
5. **What false-accept rate is acceptable for auto-pass?** The spec says 0.5% but this should be validated with QA leadership.

## 5. Suggested next steps

Any of these are good starting points for the next conversation:

- **Write the Phase 0 kill-test protocol** — a standalone document an engineer could execute this week with the Ferret SE and 3 test parts
- **Write skeleton Python code for the Phase 0 pipeline** — PLY import → STEP import → ICP alignment → measurement extraction → accuracy comparison
- **Design the Phase 1 UI wireframes** — the inspection wizard, results screen, and part onboarding flow
- **Deep-dive the alignment pipeline implementation** — practical code architecture for the three-stage alignment
- **Deep-dive the uncertainty model implementation** — how to actually compute each of the 8 uncertainty components in Python
- **Develop the MSA study workflow** — what the engineer does step-by-step to validate a part for Class A

---

## 6. Current spec (v2.4.2)

Below is the complete, current specification with all review feedback incorporated.

---

# ScanQA — Product Specification v2.4.2

**Document status:** Approved for Phase 0 protocol development and Phase 1 implementation planning
**Target platform:** macOS (Apple Silicon). Windows port deferred to Phase 3+.
**Target hardware:** Mac Mini M4 Pro (64GB), Creality Ferret SE (Phase 0–1), upgraded scanner TBD (Phase 2+)
**Prepared:** March 2026
**Review rounds:** 6 (v2.1 → v2.4.2)

---

## 1. Product definition

### 1.1 What this is

A risk-limited, feature-gated, scan-assisted receiving inspection tool. It uses 3D scan data to assess a curated set of scan-eligible dimensional features against CAD nominal geometry, with explicit uncertainty handling and conservative decision rules.

The tool is optimized to minimize false accepts. When confidence is insufficient, it does not guess — it escalates to rescan, manual gauging, or CMM.

### 1.2 What this is not

This is not a universal dimensional metrology system. It is not a CMM replacement. It does not attempt to measure every feature on a drawing. It does not auto-disposition any feature that has not been formally validated as scan-capable for the specific part, scanner, fixture, and workflow in use.

### 1.3 Core product principles

**Principle 0 — The scanner determines the ceiling, not the software.**
This system cannot measure better than the scanner hardware allows. The Creality Ferret SE (0.1mm accuracy class, consumer-grade) is approved for feasibility testing and Class B (review-only) exploration only. Production Class A auto-disposition requires demonstrated measurement capability at ≤20% of feature tolerance on target features, which will likely require a scanner upgrade to mid-range or better hardware (e.g., Revopoint MINI 2 or Einscan SP class). Phase 0 exists specifically to quantify this gap. **Ferret SE recipes are expected to be predominantly Class B** unless the Release MSA proves otherwise for specific features on specific parts. Creality's own guidance recommends a 30-minute preheat before high-precision use, and their stated accuracy ceiling is 0.1mm — no global alignment or convergence defaults should assume better performance than this.

**Principle 1 — No measurement without validated capability.**
A feature cannot be auto-dispositioned unless a measurement system analysis (MSA) has proven the system capable of measuring that feature type, on that part, with that scanner and fixture, at the required tolerance. No recipe, no auto-disposition.

**Principle 2 — Minimize false accepts, not false rejects.**
A false accept (passing a bad part) is far more costly than a false reject (flagging a good part for manual review). Every decision rule is biased toward caution. Ambiguous results are escalated, never auto-passed.

**Principle 3 — Feature-level confidence, not global confidence.**
A scan can have excellent global alignment and still be untrustworthy for a specific feature due to occlusion, noise, reflectivity, tangency, or weak observation. Confidence is assessed per feature, per decision.

**Principle 4 — The scanner is a screen, not a sentence.**
The system's job is to quickly clear obviously-good parts and flag obviously-bad ones. Parts in the ambiguous middle get routed to higher-fidelity instruments. The value is in speed and coverage, not in replacing precision metrology.

---

## 2. Success criteria

The product succeeds only if all of the following are true in production use:

| Metric | Target | Rationale |
|---|---|---|
| Median inspection cycle time (supported parts) | < 6 minutes | Faster than full manual inspection. Includes scan, process, review. Excludes scanner warm-up (see 2.1). |
| False accept rate (auto-passed features) | < 0.5% | Core safety metric. Validated against blind holdout set (see 2.2). |
| Auto-pass rate (supported parts, all features) | > 75% | If too many features escalate, the tool isn't saving labor. |
| Manual review rate | < 25% | Acceptable operational burden. |
| Per-feature Gage R&R — critical Class A | < 10% of tolerance | AIAG guidance: <10% is clearly acceptable. Required for critical-to-function features. |
| Per-feature Gage R&R — noncritical Class A | < 20% of tolerance | Acceptable with guard band and written engineering approval. |
| Per-feature Gage R&R — Class B | < 30% of tolerance | Review-only use; no auto-disposition. |
| Operator trust | Qualitative | Operators understand and accept escalation decisions because reasons are explicit. |
| Time to onboard a new part (screening MSA) | < 4 hours | Class B provisional release. |
| Time to onboard a new part (release MSA) | < 16 hours | Class A release. Includes 10-part study across multiple sessions. |

### 2.1 Operating model

Structured light scanners require thermal stabilization before producing accurate data. The operational model is:

- **Shift start:** Power on scanner. Begin 30-minute warm-up period. During warm-up, technician performs other receiving tasks (paperwork, unpacking, visual checks).
- **Calibration validation:** After warm-up, scan reference artifact. If validation passes, scanner is cleared for the shift (configurable validity window, default 8 hours).
- **Mid-shift revalidation:** Required after any of: scanner power cycle, scanner drop or physical disturbance, ambient temperature change > 5°C, or validity window expiration.
- **Cycle time target (< 6 minutes)** applies to individual part inspections after warm-up and calibration are complete. It does not include warm-up time.

### 2.2 False accept validation method

The < 0.5% false accept target is validated incrementally:

1. **Blind holdout set (Phase 2 pilot — early warning screen).** During Phase 2 pilot, assemble a set of parts with known in-spec and out-of-spec features (confirmed by CMM or calibrated instruments). The system inspects these parts without the operator knowing which are which. False accept rate = (out-of-spec features auto-passed) / (total out-of-spec features inspected). **Note:** The Phase 2 holdout is sized for early warning, not statistical proof. With a pilot holdout of ~20–40 known out-of-spec features, zero observed false accepts yields a 95% upper confidence bound of approximately 7–15% — not 0.5%. The pilot goal is zero false accepts in the holdout. Formal demonstration of <0.5% requires a substantially larger audited out-of-spec population, which is established through ongoing correlation checks over months of production use.
2. **Ongoing correlation checks (production — cumulative validation).** During production use, a defined percentage of auto-passed inspections (default 5%) are randomly selected for confirmatory CMM or manual measurement. Correlation results are tracked and trended. If the running false accept rate exceeds 0.5% over any rolling window of at least 200 audited features (not 50 — a 50-feature window is too small to estimate a rare escape rate reliably), the system is placed in Class B (review-only) mode pending investigation. The 200-feature minimum ensures that a single false accept does not breach the threshold by chance but also does not go undetected.
3. **Cumulative validation report.** Once the correlation program has accumulated ≥ 500 audited out-of-spec features with zero or near-zero false accepts, the system's false accept rate can be reported with meaningful statistical confidence. Until then, all false-accept-rate claims carry a caveat noting the upper confidence bound at the current sample size.

---

## 3. Scope

### 3.1 In scope for v1 auto-disposition (Class A eligible)

These feature types may be validated for auto-pass/fail after MSA proves capability:

- Overall envelope dimensions (length, width, height) referenced to a fixture datum
- Hole diameters for exposed, scan-visible cylindrical features above a validated minimum size (typically > 0.200" / 5mm for the Ferret SE; lower with a better scanner)
- Hole-to-hole and hole-to-datum distances where both features are locally well-observed
- Large planar face flatness as a screen (deviation from best-fit plane, not formal ASME Y14.5 minimum zone)

### 3.2 In scope for v1 review-only (Class B)

Measured and displayed, but cannot auto-disposition:

- Surface profile deviation heatmap (color-mapped scan-to-CAD deviation)
- Dimensions derived from best-fit alignment (shown with explicit "review-only" flag)
- Features with marginal coverage or confidence

### 3.3 Out of scope for v1 (Class C — manual only)

- True position (requires validated datum-constrained alignment)
- Threads, knurls, and surface texture features
- Small chamfers, edge breaks, and fillet radii
- Deep blind holes and internal geometry
- Sharp edge quality assessment
- Concentricity, runout, cylindricity
- Tight-tolerance bores below validated capability threshold
- Any feature requiring full DRF compliance unless datum-constrained setup is validated
- Any feature on a part without a completed MSA study

### 3.4 In scope for Phase 2 — Batch mode (same-part, fixed-slot plate)

Batch mode allows scanning up to 4 identical parts on a single fixture plate in one scan session, with each occupied slot processed as an independent child inspection through the existing per-part pipeline.

- Same-part batching: all slots on a plate must use the same part number, revision, and recipe
- Fixed-slot plates: 2-up to 4-up, with deterministic slot positions defined during plate onboarding
- Poka-yoke nests or visible fiducials for slot identification — no reliance on clustering as the primary identity mechanism
- Independent per-slot measurement, confidence, uncertainty, decision, and disposition
- Batch-level summary with per-slot drill-down in UI and reports
- Batch recipes require their own MSA (separate from single-part recipes for the same part)

### 3.5 Out of scope until Phase 3 — Mixed-part plates

- Plates with different part numbers in different slots
- Dense layouts exceeding 4-up
- Automatic slot identification without fixture geometry or fiducials
- Plates where slot-to-slot spacing is insufficient to avoid shadow zones on Class A/B features

### 3.6 Material-specific scope notes

| Material | Surface prep required | Scan quality expectation | Notes |
|---|---|---|---|
| Machined aluminum | Scan spray mandatory | Moderate — reflections cause gaps without spray | Wipe oil residue before spraying. |
| Machined steel | Scan spray recommended | Good — less reflective than aluminum | Dark oxides scan well, bright finishes need spray. |
| Injection molded plastic | None | Good — cooperative surfaces | Watch for warpage on thin walls, flash at parting lines. |
| FDM 3D printed | None | Moderate — layer lines add surface noise | Looser outlier thresholds. Layer lines are real geometry. |
| SLA/resin 3D printed | None | Good — smooth surfaces | Treat like injection molded. |

---

## 4. Feature eligibility model

This is the most important system in the product. Every measurable feature on every part is classified during onboarding:

### 4.1 Feature classes

**Class A — Auto-disposition eligible.**
The system may pass or fail this feature without human review. Requirements: MSA study completed, Gage R&R < 10% (critical) or < 20% (noncritical with guard band and approval) of tolerance, bias characterized, minimum coverage threshold defined, decision rule validated, recipe locked.

**Class B — Review-only.**
The system measures and displays this feature with uncertainty bounds, but it cannot contribute to an auto-pass or auto-fail verdict. A human must review Class B results. Typical reasons for Class B: insufficient MSA data, marginal Gage R&R, feature type not yet validated, alignment-sensitive measurement.

**Class C — Manual measurement only.**
The scanner cannot reliably observe this feature. The system may display a visual guide ("measure this feature with pin gauge") but produces no numeric result. Typical reasons for Class C: hidden geometry, threads, small chamfers, deep bores, scanner resolution insufficient.

### 4.2 Class assignment rules

During part onboarding, each candidate feature is evaluated against these criteria:

| Criterion | Class A critical | Class A noncritical | Class B minimum | Below all → Class C |
|---|---|---|---|---|
| Gage R&R (% of tolerance) | < 10% | < 20% (with guard band and written engineering approval) | < 30% | ≥ 30% |
| Number of distinct categories (ndc) | ≥ 5 | ≥ 5 | ≥ 5 | < 5 |
| Feature coverage in MSA scans | > 80% of feature area | > 80% of feature area | > 50% of feature area | < 50% |
| Inter-scan repeatability (2σ) | < 25% of tolerance | < 25% of tolerance | < 50% of tolerance | ≥ 50% |
| Sensitivity to alignment perturbation | < 15% of tolerance for ±0.2° rotation | < 15% of tolerance for ±0.2° rotation | < 30% of tolerance | ≥ 30% |
| Feature minimum dimension | > validated scanner threshold | > validated scanner threshold | > 50% of threshold | Below 50% |

**Number of distinct categories (ndc)** is computed from the MSA study as ndc = 1.41 × (σ_parts / σ_GRR). Per AIAG MSA 4th Edition, ndc ≥ 5 indicates the measurement system can distinguish enough categories within the tolerance band to be useful. A feature with ndc < 5 cannot be Class A or Class B regardless of GRR percentage, because the system cannot reliably distinguish between parts even if variation appears low.

A feature that meets Class A on all criteria is Class A. A feature that fails any single Class A criterion but meets all Class B criteria is Class B. A feature that fails any Class B criterion is Class C.

### 4.3 Class promotion and demotion

Classes may change when:
- A better scanner is introduced (may promote B → A)
- MSA study is completed for a previously unstudied feature (may promote C → B → A)
- Scanner firmware or software version changes (all classes reset to "unvalidated" until re-confirmed)
- Part revision changes geometry near a measured feature (affected feature resets)
- Field data reveals false accepts attributable to a feature (immediate demotion to B or C pending investigation)

---

## 5. Part onboarding workflow

A part number cannot enter production inspection use until this workflow is complete. This is an engineer-facing process, not a technician task.

### Step 1 — CAD and drawing import

Import STEP file and associated drawing (PDF or MBD). Render 3D preview. Record part number, revision, material type, and drawing callout summary.

### Step 2 — Fixture and orientation strategy

Define how the part will be physically held during scanning:
- Fixture type (flat plate, V-block, custom fixture, 3D printed nest)
- Part orientation (which datum face is down / against fixture)
- Number of orientations required (single setup vs. flip)
- Fixture drawing or photo stored with recipe

The fixture determines which features are scannable and which datums are accessible. This decision drives everything downstream.

### Step 2a — Batch plate layout (Phase 2, if applicable)

If the part will be inspected in batch mode, define the fixture plate layout in addition to the single-part fixture:

- **Plate definition:** Physical plate dimensions, material, and identifier.
- **Slot count and arrangement:** 2-up to 4-up. Each slot has a unique ID (e.g., Slot_A, Slot_B, Slot_C, Slot_D).
- **Slot poses:** Rigid transform from plate origin to each slot origin (translation + rotation in plate coordinates). These are the ground-truth slot positions — the system uses them for partitioning, not clustering.
- **Minimum inter-slot spacing:** Measured edge-to-edge between nearest part features. Must be sufficient to avoid shadow zones on Class A/B features for the target scanner class. Minimum spacing is validated during batch MSA.
- **Slot nest / poka-yoke design:** Each slot must physically constrain the part in a known orientation. Loose placement in open slots is not acceptable for batch mode.
- **Fiducials or fixture geometry for plate localization:** At least 3 non-collinear reference features on the plate (engraved targets, dowel pins, corner geometry) that the system can detect in the scan to solve the plate pose. These are distinct from per-part datum features.
- **Expected occlusion masks per slot:** Which regions of each slot are expected to be occluded by neighboring parts, plate edges, or fixture geometry. These masks adjust per-slot coverage requirements.
- **Slot equivalence groups:** If the plate is symmetric (e.g., 2×2 grid with identical nests), define which slots are geometrically equivalent. Equivalent slots may share a single MSA validation. Non-equivalent slots (e.g., edge vs center with different viewing geometry) require independent MSA.
- **Allowed part numbers:** In Phase 2, all slots must use the same part number. Record this constraint in the plate layout.

**Batch MSA requirement:** A batch recipe is a separate validated workflow from the single-part recipe for the same part. The single-part MSA does not transfer to batch mode because the fixture, coverage patterns, viewing geometry, and noise characteristics all change. Batch mode requires:
- Screening MSA (Tier 1) for Class B batch release: 3–5 parts per slot position, 2 operators, 3 sessions each.
- Release MSA (Tier 2) for Class A batch release: 10 parts per slot position (or per equivalence group), 3 operators, AIAG methodology. Slot equivalence must be statistically justified — if slot-to-slot variation exceeds 20% of within-slot variation, the slots are not equivalent and require independent MSA.

### Step 3 — Datum scheme definition

Define the inspection datum reference frame:
- Primary datum (typically largest planar face, often fixture-contact face)
- Secondary datum (if applicable — perpendicular face or hole axis)
- Tertiary datum (if applicable)

In v1, alignment is fixture/datum-assisted for coarse pose, with feature-based refinement. Full datum-constrained ICP is a Phase 2 capability. The datum scheme is recorded now so it can be enforced later.

### Step 4 — Feature identification and classification

For each feature the engineer wants to inspect:
1. Select the feature in the 3D CAD view (click a face, edge, or hole)
2. Define the measurement type (diameter, distance, flatness, envelope)
3. Enter nominal value and tolerance from the drawing
4. System pre-classifies as A/B/C based on feature type, size, and scanner capability model
5. Engineer confirms or overrides (with justification logged)

Features that are not scan-visible in the defined fixture orientation are automatically classified as Class C.

### Step 5 — MSA capability study

The MSA has two tiers. A part must complete the screening study for Class B release, and the full release study for Class A release. You cannot skip to Class A.

**Tier 1 — Screening MSA (Class B provisional release)**

| Parameter | Requirement |
|---|---|
| Parts | 3–5, ideally spanning tolerance range |
| Operators | 2 minimum |
| Scan sessions per operator per part | 3 |
| Reference instrument | Calibrated calipers, pin gauges, or CMM |
| Gage R&R threshold | < 30% of tolerance for Class B |

This study validates that the system produces consistent, meaningful measurements — sufficient for review-only use where a human makes the final call. It answers: "Can we measure this feature repeatably enough to be useful?"

**Tier 2 — Release MSA (Class A auto-disposition)**

| Parameter | Requirement |
|---|---|
| Parts | 10 minimum, spanning the tolerance range (include parts near upper and lower spec limits) |
| Operators | 3 minimum |
| Repeats per operator per part | 2–3 (randomized order, operator blind to prior results) |
| Reference instrument | CMM or calibrated instrument with uncertainty < 10% of feature tolerance |
| Gage R&R threshold — critical features | < 10% of tolerance |
| Gage R&R threshold — noncritical features | < 20% of tolerance, with guard band and written engineering approval |
| Additional requirement | Bias must be statistically characterized and stable across the study. Alignment sensitivity test must be included. |

This study follows AIAG MSA 4th Edition crossed Gage R&R methodology. It answers: "Can we trust this system to auto-pass and auto-fail parts without human review?" The 10-part requirement is not negotiable for Class A — with fewer parts, the study cannot reliably separate part variation from measurement system variation.

**For both tiers, compute per feature:**
- Bias: mean scan measurement minus reference measurement (caliper, CMM, or pin gauge)
- Repeatability: within-operator, within-session variation (2σ)
- Reproducibility: between-operator variation (2σ)
- Gage R&R: combined repeatability and reproducibility as % of tolerance
- Number of distinct categories (ndc): 1.41 × (σ_parts / σ_GRR). Must be ≥ 5 for Class A and Class B.
- Alignment sensitivity: variation in measured value when alignment is perturbed by ±0.2° and ±0.2mm
- Fit correction factor (c_fit): ratio of observed measurement variation to naive u_fit across the study. Stored in FeatureCapability for production use in the uncertainty model (Section 7.5).

Record all results. Apply classification rules from Section 4.2. Any feature that does not achieve Class A is downgraded to B or C. The engineer cannot override a failed MSA to force Class A — this is a hard gate.

### Step 6 — Recipe creation and locking

Create an inspection recipe that binds together:

| Recipe field | Description |
|---|---|
| Part number and revision | Exact drawing revision this recipe applies to. |
| CAD file hash (SHA-256) | Detects unauthorized CAD changes. |
| Scanner model and firmware | Recipe is invalid if scanner changes. |
| Software version | ScanQA version at recipe creation. |
| Fixture ID | Physical fixture used during MSA. |
| Fixture notes | Setup instructions and photo reference. |
| Scan preset | Scanner resolution, exposure, and distance settings. |
| Surface prep requirements | "Scan spray required" / "Wipe with IPA" / "No prep needed." |
| Required scan count | Minimum number of passes (typically 3). |
| Datum scheme | Primary, secondary, tertiary datums. |
| Datum observability method | Fiducials, fixture geometry, datum features, or marker board. |
| Feature list with classes | Each feature, its class, and its validated parameters. |
| MSA study reference | Link to capability study data. |
| Approval signature | Engineer name and date. |

The recipe is version-controlled. Any change to part revision, scanner, fixture, or software triggers a recipe review. The system refuses to auto-disposition if the active recipe does not match the current configuration.

---

## 6. Scanning strategy

### 6.1 Preferred scanning method

V1 defaults to a guided, semi-structured scanning approach — not fully freehand:

- Part is placed in its designated fixture on a stable surface
- Lighting is controlled (consistent ambient, no direct sunlight)
- Scanner is on a fixed stand or hand-guided along a prescribed path defined during onboarding
- Surface prep is completed per recipe requirements before scanning begins
- Technician follows on-screen guidance for scan path and coverage

This trades flexibility for repeatability. A consistent scan path produces consistent data, which makes confidence estimates meaningful. Fully freehand scanning introduces too much operator variability for reliable auto-disposition.

### 6.2 Multi-scan capture

The system captures N scans per the recipe (default N=3). Between each pass, the technician adjusts the scanner angle slightly per on-screen guidance. This ensures each scan samples slightly different surface points and noise patterns.

Quality gates enforced per scan:
- Minimum point count (configurable per recipe, default 500K)
- Minimum estimated coverage of Class A and B features
- Maximum noise metric (mean distance to k-nearest neighbors)
- If any gate fails, the system prompts the technician with a specific corrective instruction before accepting the scan

### 6.3 Turntable integration (optional)

A motorized turntable ($30–$50) improves multi-angle coverage consistency. If present, the system drives the turntable to prescribed angles between scans, removing operator positioning variability.

### 6.4 Batch plate scanning mode (Phase 2)

When using a batch plate, the scanning workflow changes from single-part to plate-level:

**Plate loading:**
1. Place fixture plate on stable surface in consistent position.
2. Load parts into slot nests per plate layout. Parts must be fully seated in poka-yoke nests.
3. Apply surface prep to all parts per recipe requirements.
4. In the batch inspection wizard, select batch recipe. Enter or scan slot/serial mapping: which serial number (or receiving sample ID) is in which slot. Mark any empty slots as unoccupied.

**Scan path:**
- The scan path covers the full plate, not individual parts. Recipe defines a plate-level scan path that ensures all slot positions receive adequate coverage.
- N scan passes per the batch recipe (default N=3), with angle variation between passes as in single-part mode.
- Quality gates are evaluated at the plate level first (total point count, plate fiducial visibility), then per-slot after partitioning.

**Shadow zone rule:** Plate slot spacing must be sufficient that no Class A or Class B feature on any part is occluded by an adjacent part from the primary scan angles defined in the recipe. The batch MSA validates this empirically. If a slot arrangement causes systematic coverage deficits on specific features, those features must be demoted or the plate redesigned.

**Turntable note:** Turntable integration is more valuable for batch plates than for single parts, because a plate scan from a single angle is more likely to produce slot-dependent occlusion. If a turntable is not used, the batch recipe must define a multi-angle scan path that compensates.

---

## 7. Processing pipeline

### 7.1 Per-scan preprocessing

For each imported scan (PLY/OBJ file from scanner software):

1. **Validate:** Check point count, bounding box plausibility, noise metric.
2. **Statistical outlier removal:** Remove isolated noise points. Parameters tuned by scanner profile (see 7.8).
3. **Fixture/background ROI clip:** Remove points outside a coarse region of interest defined by the expected part bounding box in fixture coordinates (with generous margin, e.g., 2× part envelope). This eliminates obvious background, table surface, and distant fixture points without requiring CAD alignment. The ROI is defined during recipe creation relative to the fixture origin.
4. **Normal estimation:** Compute surface normals for ICP alignment.
5. **Downsample:** Voxel grid downsample for alignment computation. Full-resolution cloud retained for measurement.

### 7.1.1 Post-alignment cleanup

After Stage 1 coarse pose alignment (Section 7.2) places the scan in the CAD coordinate frame:

6. **CAD-proximity filter:** Remove points farther than the CAD proximity limit from the nearest CAD surface. This eliminates residual fixture, turntable, and background points that survived the ROI clip. This step requires at least a coarse alignment to be meaningful — applying it to a raw scan in scanner coordinates is undefined.

### 7.1.2 Batch plate processing (Phase 2)

When processing a batch plate scan, the following steps execute between per-scan preprocessing (7.1) and per-part alignment (7.2). The mental model is **"plate-localize, slot-partition, then run the existing per-part pipeline per slot"** — not "segment the cloud into blobs and figure out what they are."

**Step B1 — Plate localization.**
Detect plate fiducials or fixture geometry (dowel pins, corner features, engraved targets) in the preprocessed point cloud. Solve the rigid transform from scanner coordinates to plate coordinates. This is analogous to single-part coarse pose (Stage 1 in Section 7.2) but targets the plate, not an individual part.

If plate fiducials cannot be detected: the batch scan is rejected. There is no fallback to unconstrained plate localization — plate pose is the foundation for all slot assignments, and an uncertain plate pose would propagate errors to every slot.

**Step B2 — Transform to plate coordinates.**
Apply the plate pose transform to the full point cloud. All subsequent slot operations occur in plate coordinates.

**Step B3 — Slot occupancy detection.**
For each slot defined in the BatchPlateLayout, extract points within the slot's predefined ROI (from Step 2a onboarding). Compare point count and coverage within each ROI against a minimum occupancy threshold (recipe-defined). Slots below the threshold are marked as empty and skipped. Slots above the threshold are marked as occupied.

Cross-check against the operator's declared slot/serial mapping from the batch wizard. If the system detects an occupied slot the operator marked empty, or vice versa, the batch is paused and the operator is prompted to confirm. This catches loading errors before measurement.

**Step B4 — Slot ROI crop.**
For each occupied slot, crop the plate-coordinate point cloud to the slot's ROI. Each cropped cloud becomes the input to an independent per-part pipeline run.

**Step B5 — Slot contamination and merge check.**
Within each cropped slot cloud, run DBSCAN clustering (Open3D `cluster_dbscan`) as a **sanity check only** — not as the primary slot identity mechanism. The expected result is a single dominant cluster corresponding to the part. Flag the slot if:
- Zero clusters (slot appears empty despite passing occupancy threshold — possible debris)
- Multiple significant clusters (possible cross-slot contamination, scan spray bridging, or part misplacement)
- Dominant cluster centroid is offset from the expected part centroid by more than a recipe-defined tolerance

Flagged slots are routed to their respective reason code (SLOT_CONTAMINATED, SLOT_MULTI_CLUSTER, or SLOT_ASSIGNMENT_UNCERTAIN) — the operator is prompted to verify the slot before measurement proceeds. Unflagged slots proceed directly to Step B6.

**Step B6 — Per-slot pipeline fan-out.**
For each clean, occupied slot, run the standard per-part pipeline in this order:

1. **Alignment (7.2):** Three-stage alignment using the slot's cropped cloud against the part CAD. Stage 1 coarse pose uses the known slot transform as the initial guess (the plate pose + slot offset gives a strong prior). Stages 2–3 refine as normal.
2. **Post-alignment cleanup (7.1.1):** CAD-proximity filter on the now-aligned slot cloud. This step depends on coarse pose and therefore must follow alignment, not precede it.
3. **Fusion (7.3):** Multi-scan voxel consensus and averaging within the slot.
4. **Measurement (7.4):** Local primitive fitting per feature.
5. **Uncertainty (7.5):** GUM model with all 8 components.
6. **Confidence (8.1, 8.2):** Per-slot global scan confidence, then per-feature local confidence.
7. **Guard band (7.6) and decision (7.7):** Bias correction, guard band application, and verdict.

Each slot produces its own child Inspection record, InspectionResults, and MeasurementEvidence. The slot's cropped cloud is the input — the per-part pipeline does not see the full plate cloud.

**Isolation principle:** A failure in one slot (rescan needed, contamination, alignment failure) does not automatically invalidate other slots. Each slot is independently evaluated. If Slot B fails alignment but Slots A, C, and D are clean, the system produces valid inspections for A, C, and D and routes Slot B to rescan or manual. The batch summary reports the per-slot outcomes.

### 7.2 Alignment

Three-stage alignment, progressing from coarse to fine:

**Stage 1 — Fixture/datum-assisted coarse pose.**
The recipe defines the expected part orientation in the fixture, but fixture knowledge alone is insufficient — a handheld scan's coordinate system is determined by the scanner, not the fixture. To bridge this gap, the system requires at least one of the following datum observability methods:

- **Scan-visible fiducial markers** on the fixture (adhesive targets or engraved features at known positions)
- **Known fixture geometry** visible in the scan (e.g., V-block edges, fixture plate surface) that the system can detect and use to compute the fixture-to-scan transform
- **Identifiable datum features** on the part itself (e.g., a large flat datum face, a datum hole) that can be automatically detected and matched to the CAD datum scheme
- **Marker board or external reference frame** with known geometry visible in at least one scan pass

The system detects the chosen reference features in the scan point cloud and computes the rigid transform from scan coordinates to CAD/fixture coordinates. If the reference features cannot be detected (occluded, insufficient points, ambiguous match), coarse alignment falls back to PCA + bounding box with axis-flip testing, and the alignment is flagged as "unconstrained." Unconstrained alignment limits all features to Class B maximum for that inspection.

During part onboarding (Step 2), the engineer selects and validates the datum observability method. The recipe records which method is required and what reference features the system should look for.

**Stage 2 — Feature-based refinement.**
Extract geometric primitives (planes, cylinders) from both scan and CAD near datum features. Compute rigid transform from matched datum features. This narrows alignment from ~5° to ~0.5°.

**Stage 3 — Fine alignment (point-to-plane ICP).**
Constrained to the datum reference frame where possible:
- Primary datum plane constrains one translation and two rotations
- Secondary datum constrains one rotation and one translation
- Tertiary datum fully constrains the remaining DOF

In v1, if datum-constrained ICP is not yet implemented, use unconstrained point-to-plane ICP but record this in the inspection evidence. The alignment sensitivity test (perturbing alignment by ±0.2° and ±0.2mm and measuring the resulting change in each feature value) serves as the proxy gate: any feature whose measured value changes by more than 15% of its tolerance under perturbation is not Class A eligible, regardless of alignment method. This is a necessary but not sufficient condition — when datum-constrained alignment is implemented in Phase 3, features must be re-validated under the constrained method before retaining Class A status.

**ICP parameters:**

| Parameter | Default | Notes |
|---|---|---|
| Max correspondence distance | 2.0mm (pass 1), 0.5mm (pass 2) | Two-pass: coarse then fine. |
| Max iterations | 50 per pass | Typically converges in 15–30. |
| Convergence threshold (RMSE delta) | 1e-7 | |
| Downsample voxel for ICP | 0.3mm | Full-res retained for measurement. |

**Alignment validation (two-band failure policy):**

Alignment outcomes are split into a **hard-block band** (measurement is not produced) and a **soft-degrade band** (measurement proceeds but all features are capped at Class B review-only).

*Hard-block band — alignment is rejected, no measurement:*
- Fitness score (inlier fraction) below hard-block threshold (default 0.70)
- RMSE above hard-block threshold (default 0.15mm)
- Alignment mode is "unconstrained" AND fitness is below 0.80

When alignment is hard-blocked, the system displays the misaligned overlay and prompts the technician to rescan or check part orientation. No feature measurements are produced.

*Soft-degrade band — measurement proceeds as review-only:*
- Fitness score is between hard-block threshold and recipe threshold (default 0.85)
- RMSE is between recipe threshold and hard-block threshold
- Alignment stability test fails: re-running ICP from a perturbed starting pose (±0.3° and ±0.3mm) does not converge within recipe-defined tolerance

When alignment is in the soft-degrade band, all features are demoted to Class B (review-only) for this inspection. The reason code REVIEW_ONLY_ALIGNMENT_DEGRADED is applied.

*Pass band — full measurement with recipe-defined classes:*
- Fitness score above recipe threshold (default 0.85)
- RMSE below recipe threshold (recipe-derived from MSA, no global default — see note below)
- Alignment stability passes

**Note on alignment thresholds:** RMSE and stability convergence thresholds are recipe-derived from the Release MSA study, not global defaults. Consumer-class scanners (Ferret SE) are expected to produce higher RMSE values than mid-range or industrial scanners. Setting a global 0.05mm RMSE default would inappropriately reject valid alignments from consumer hardware. During recipe creation, the MSA study establishes the actual achievable RMSE for each part/scanner/fixture combination, and the recipe threshold is set at MSA_mean_RMSE × 1.5.

### 7.3 Multi-scan fusion

After all N scans are independently aligned:

1. **Merge** all full-resolution aligned point clouds.
2. **Voxel consensus filtering.** Divide merged cloud into fine voxels (size per scanner profile). Discard voxels with points from fewer than ceil(N/2) scans. This removes transient noise visible in only one pass.
3. **Per-voxel averaging.** For surviving voxels, compute centroid of all contributing points. Noise reduction factor ≈ √N.

The fused cloud is used for measurement. No global surface reconstruction is performed — measurements are extracted by local primitive fitting directly on point subsets (see 7.4). This avoids introducing reconstruction artifacts into measurements.

### 7.4 Measurement extraction

For each configured feature, the system:

1. **Selects local points.** Extract all fused-cloud points within a search region around the CAD feature location. Search region size defined during onboarding (default: feature bounding box + 2mm margin).
2. **Fits a geometric primitive.** Method depends on feature type:
   - Hole diameter: RANSAC cylinder fit (through holes) or circle fit on a cross-section (blind holes)
   - Distance: Fit primitives at both endpoints, compute distance between fitted centers/centroids
   - Envelope dimensions: Oriented bounding box of the full fused cloud in the aligned frame
   - Flatness: Least-squares plane fit, report peak-to-valley residual
3. **Computes measurement value and fit quality.** Record the fitted dimension, fit residual (RMSE of points to fitted primitive), and number of inlier points.
4. **Computes per-feature confidence evidence.** See Section 8.
5. **Computes measurement uncertainty.** See Section 7.5.

### 7.5 Uncertainty model

Measurement uncertainty follows NIST GUM (Guide to the Expression of Uncertainty in Measurement) methodology. Each uncertainty component is expressed as a standard uncertainty in the same dimensional unit (inches or mm) before combination.

**Combined standard uncertainty:**

```
u_c² = u_fit² + u_repeat² + u_reprod² + u_align² + u_cal² + u_ref² + u_temp² + u_bias_est²
```

| Component | Symbol | Source | Evaluation method |
|---|---|---|---|
| Fit uncertainty | u_fit | RMSE of geometric primitive fit to local scan points | Type A: direct from fit residuals, divided by √n_eff (effective sample size — see note below) |
| Repeatability | u_repeat | Within-operator, within-session variation | Type A: from MSA study (stored in FeatureCapability) |
| Reproducibility | u_reprod | Between-operator variation | Type A: from MSA study |
| Alignment uncertainty | u_align | Sensitivity of measured value to alignment perturbation | Type A: half-range of measurement variation across ±0.2°/±0.2mm perturbation set |
| Calibration uncertainty | u_cal | Scanner accuracy from most recent calibration validation | Type B: derived from calibration artifact error history |
| Reference instrument uncertainty | u_ref | Uncertainty of the caliper/CMM used to establish bias | Type B: from instrument calibration certificate |
| Thermal uncertainty | u_temp | Dimensional change due to temperature deviation from 20°C | Type B: estimated from CTE × part size × ΔT |
| Bias estimation uncertainty | u_bias_est | Uncertainty in the bias correction itself (is the stored bias still accurate?) | Type A: standard error of the mean bias from MSA study |

**Expanded uncertainty:**

```
U = k × u_c
```

where k = 2 (95% confidence interval) is the default coverage factor.

**Note on effective sample size for u_fit:** The naive formula `u_fit = RMSE / √n_inliers` assumes inlier points behave as independent observations. In fused point clouds this is rarely true — neighboring points are spatially correlated (they share scan overlap, projection geometry, and noise patterns), which makes the naive u_fit look much smaller than it really is. The system uses an **effective sample size** (n_eff) instead of the raw inlier count:

- **Option A — Empirical model (preferred for Class A).** During the Release MSA study, the system computes u_fit for each feature using the naive formula and compares it to the observed measurement variation. The ratio establishes an empirical correction factor `c_fit` per feature per recipe, stored in FeatureCapability. In production, `u_fit = c_fit × (RMSE / √n_inliers)` where c_fit ≥ 1. This is the only method approved for Class A features.
- **Option B — Spatial decimation (fallback for Class B).** Subsample the inlier set to one point per spatial correlation length (estimated as 2× voxel size). Use the subsampled count as n_eff. This is a conservative heuristic and acceptable for Class B review-only features.

The coverage inflation factor `f_cov` is similarly either empirically calibrated per recipe (Class A) or applied as a conservative demotion rule (Class B). The formula `f_cov = required_coverage / actual_coverage` is a Class B default; Class A recipes must validate or override this factor during the Release MSA.

**Coverage deficiency handling:**

Local scan coverage is not an uncertainty component — it is a gate and an inflation factor:

- If local feature coverage > recipe-defined minimum (typically 80% for Class A): no adjustment
- If local feature coverage is between 50% and the minimum: apply a coverage inflation factor `f_cov = (required_coverage / actual_coverage)`, so `U_adj = f_cov × U`. Feature is demoted to Class B for this inspection.
- If local feature coverage < 50%: feature is blocked from measurement (RESCAN_NEEDED or MANUAL_GAUGE_REQUIRED)

**Note on per-inspection vs. per-recipe components:** Components u_repeat, u_reprod, u_ref, and u_bias_est are established during the MSA study and stored in the recipe. They do not change per inspection. Components u_fit, u_align, u_cal, and u_temp are computed fresh for each inspection from the actual scan data and current conditions. The combined uncertainty therefore reflects both the system's inherent capability and the quality of this specific scan.

### 7.6 Guard band policy

Guard banding is the intentional narrowing of acceptance limits to account for measurement uncertainty, ensuring that parts accepted by the system are truly in-spec with high confidence. This is not optional for Class A features — it is a core element of the false-accept-minimization strategy.

**Guard band methods (engineer selects during recipe creation):**

| Method | Rule | When to use |
|---|---|---|
| Simple percentage | Narrow tolerance by G% on each side (default G = 10%) | General-purpose, easy to explain to operators |
| Uncertainty-based (ASME B89.7.3.1) | Accept only if measured value + U < upper limit AND measured value − U > lower limit | Rigorous, adapts to each inspection's actual uncertainty |
| Shared risk (no guard band) | Accept if measured value is inside tolerance, ignore uncertainty | Only for noncritical features with written engineering approval |

The default for Class A critical features is the uncertainty-based method. The decision engine applies the guard band rule specified in the recipe for each feature.

### 7.7 Decision engine

For each feature, the system evaluates:

| Input | Source |
|---|---|
| Measured value | Primitive fit (7.4) |
| Bias correction | MSA study (stored in recipe) |
| Expanded uncertainty (U) | Computed per Section 7.5 uncertainty model |
| Coverage-adjusted uncertainty (U_adj) | U × coverage inflation factor if applicable |
| Feature class | Recipe (Section 4) |
| Local confidence evidence | Section 8 |

**Bias-corrected value** = measured value − stored bias

**Decision rules:**

| Condition | Verdict |
|---|---|
| Feature is Class C | NOT_SCAN_ELIGIBLE — skip to manual instruction |
| Feature is Class B | REVIEW_ONLY — display value and uncertainty, no auto-verdict |
| Calibration expired or recipe mismatch | BLOCKED — no measurement produced |
| Local confidence fails all Class B gates (Section 8.2 precedence rule) | RESCAN_NEEDED or MANUAL_GAUGE_REQUIRED (see Section 8.2 escalation logic for which applies) |
| Feature passes guard band rule (Section 7.6) for its recipe-specified method | PASS |
| Feature fails — value ± U_adj entirely outside tolerance, large margin | FAIL_FULL_CONFIDENCE |
| Feature fails — value ± U_adj entirely outside tolerance, small margin (deviation < 2×U beyond limit) | FAIL_MARGINAL — auto-reject but flagged for trend analysis |
| Value outside tolerance but uncertainty overlaps the tolerance limit | MARGINAL_OUTSIDE — routed to manual verification (cannot auto-reject) |
| Value inside tolerance but uncertainty extends past limit | MARGINAL_INSIDE — routed to manual verification (cannot auto-pass) |

### 7.8 Scanner profiles

Processing parameters are tuned per scanner class. The profile is selected during recipe creation and locked.

**Part-type base thresholds:**

| Part type | SOR std_ratio | Voxel consensus threshold | CAD proximity limit | Notes |
|---|---|---|---|---|
| Machined metal | 2.0σ | ceil(N/2) | 1.5mm | Tight — clean surfaces expected. |
| Injection molded | 2.0σ | ceil(N/2) | 1.5mm | Watch for flash at parting lines. |
| FDM 3D printed | 2.5σ | ceil(N/2) | 2.0mm | Layer lines are real geometry. |
| SLA 3D printed | 2.0σ | ceil(N/2) | 1.5mm | Smooth, treat like injection molded. |

**Scanner-class adjustments** (applied on top of base thresholds):

| Scanner class | SOR adjustment | CAD proximity adjustment | Fusion voxel size | Min feature size for Class A |
|---|---|---|---|---|
| Industrial (GOM, Creaform) | Base values | Base values | 0.1mm | Per MSA |
| Mid-range (Einscan, Revopoint MINI 2) | Base values | Base values | 0.15mm | Per MSA |
| Consumer (Creality Ferret SE, Revopoint POP) | +0.5σ | +1.0mm | 0.25mm | ≥ 0.200" (5mm) typical |
| Phone LiDAR / photogrammetry | +1.0σ | +3.0mm | 0.5mm | Envelope checks only |

---

## 8. Confidence model

Confidence is assessed at up to five levels, depending on inspection mode. In single-part mode, levels 8.0 and 8.0.1 are skipped. In batch mode, all five levels are evaluated in order: plate → slot → global (per-slot) → local (per-feature) → decision. These are not collapsed into a single score — each level has its own gates.

### 8.0 Plate-level confidence (batch mode only)

Assessed once per batch scan, before slot partitioning. Plate-level outcomes fall into two categories: **fatal-redo** (the batch scan is rejected and must be redone) and **pause/resolve** (the batch is paused for operator action and may proceed after resolution).

**Fatal-redo — batch scan must be redone:**

| Check | Gate | Failure action |
|---|---|---|
| Plate fiducial detection | All required plate fiducials / fixture geometry features detected | PLATE_LOCALIZATION_FAILED — batch scan rejected. No fallback. |
| Plate pose quality | Plate localization RMSE below recipe threshold | PLATE_POSE_POOR — batch scan rejected. Prompt rescan of plate. |
| Plate coverage | Scan covers all declared-occupied slot ROIs with minimum point density | PLATE_COVERAGE_INSUFFICIENT — batch scan rejected. Prompt rescan with guidance on underscanned plate regions. |

If any fatal-redo check fails, no slot-level or per-part processing occurs. The entire batch scan must be redone.

**Pause/resolve — batch paused for operator action, then proceeds:**

| Check | Gate | Failure action |
|---|---|---|
| Slot occupancy agreement | System-detected occupancy matches operator-declared slot mapping | SLOT_OCCUPANCY_MISMATCH — batch paused. Operator confirms or corrects the slot/serial mapping. Once confirmed, processing resumes with the corrected mapping. No rescan required. |

Pause/resolve events do not require a new scan — they require the operator to verify or correct input data. Once resolved, the batch proceeds to slot partitioning.

### 8.0.1 Slot-level confidence (batch mode only)

Assessed per occupied slot, after plate localization and slot partitioning (Section 7.1.2 Steps B3–B5).

| Check | Gate | Failure action |
|---|---|---|
| Slot assignment certainty | Slot ROI contains a single dominant point cluster with centroid within recipe tolerance of expected part center | SLOT_ASSIGNMENT_UNCERTAIN — slot paused for operator verification. Other slots unaffected. |
| Cross-slot contamination | No significant point clusters in the slot ROI that originate from an adjacent slot or inter-slot fixture region | SLOT_CONTAMINATED — slot flagged. Operator may verify visually and either rescan the slot or accept with all features capped at Class B (review-only) for this inspection. Contamination verification **does not** restore Class A auto-disposition — only a clean rescan with no contamination flag can produce Class A results for a previously contaminated slot. |
| Cluster purity | DBSCAN cluster count within slot ROI = 1 (dominant part) + expected fixture points only | SLOT_MULTI_CLUSTER — possible debris, overspray bridging, or misplaced part. Route to operator. |
| Slot-level point density | Total point count in slot ROI exceeds per-slot minimum (may differ from single-part minimum due to occlusion masks) | SLOT_SPARSE — rescan needed for this slot region. Other slots unaffected. |

Slots that pass all slot-level gates proceed to the per-slot pipeline (Section 7.1.2 Step B6), where the existing per-part confidence model (Sections 8.1, 8.2, 8.3) applies independently within each slot. Slots that fail are isolated — they do not affect the disposition of other slots on the same plate.

### 8.1 Global scan confidence

Assessed once per inspection, before feature measurement begins.

| Check | Gate | Failure action |
|---|---|---|
| Calibration status | Validation artifact scanned within N hours (configurable, default 8) | CALIBRATION_EXPIRED — block all auto-disposition |
| Recipe match | Scanner model, firmware, software version, fixture match recipe | RECIPE_MISMATCH — block all auto-disposition |
| Gross coverage | Scan covers all recipe-defined required regions (datum surfaces + Class A/B feature zones). Expected occlusion zones defined during onboarding are excluded from coverage check. | Prompt rescan with specific missing-region guidance |
| Alignment fitness | > recipe threshold (default 0.85) for Class A; > hard-block threshold (default 0.70) for any measurement | Below hard-block → alignment rejected, no measurement. Between thresholds → soft-degrade, all features review-only (Section 7.2) |
| Alignment RMSE | < recipe threshold (recipe-derived from MSA) for Class A; < hard-block threshold (default 0.15mm) for any measurement | Same two-band policy as fitness |
| Alignment stability | Perturbed re-runs converge within recipe-derived tolerance | Stability failure → soft-degrade band, all features demoted to review-only |

### 8.2 Local feature confidence

Assessed per feature, after alignment and fusion. Each check produces a metric stored in the measurement evidence record.

| Metric | Description | Class A gate | Class B gate |
|---|---|---|---|
| Local point density | Points per mm² within feature search region | Recipe-derived from MSA (typical: > 5 pts/mm²) | > 50% of Class A threshold |
| Local coverage fraction | % of feature CAD surface area with scan points within 0.5mm | Recipe-defined per feature (typical: > 80%) | > 50% |
| Incidence angle quality | Median angle between scan normals and CAD surface normal at feature | < 60° | < 75° |
| Fit residual (RMSE) | Quality of primitive fit to local points | Recipe-derived from MSA (must be ≤ MSA residual × 1.5) | ≤ MSA residual × 2.5 |
| Inter-scan repeatability | Std dev of measurement across N individual scans (before fusion) | < 25% of tolerance | < 50% of tolerance |
| Boundary proximity | Distance from feature centroid to nearest scan edge/gap | > 3mm | > 1mm |
| Alignment sensitivity | Change in measured value when alignment is perturbed ±0.2° and ±0.2mm | < 15% of tolerance | < 30% of tolerance |

All Class A thresholds are established during the Release MSA study and stored in the FeatureCapability record. They are not global defaults — they are specific to the part, feature, scanner, and fixture combination validated in the MSA. The values shown in the "typical" notes are starting points for the MSA, not acceptance criteria.

A Class A feature that fails any Class A local gate but passes the corresponding Class B gate is temporarily demoted to Class B (review-only) for this inspection. The feature is measured, displayed with uncertainty, and flagged REVIEW_ONLY_CONFIDENCE_DEMOTED — but no extra operator action is required (no rescan prompt, no manual gauge prompt). The reason code is visible in the results screen and report, but the demotion does not generate an action item. It simply removes the feature from the auto-disposition pool and routes it to the review-only section.

A Class B feature (whether originally Class B or demoted from A) that fails any Class B local gate is escalated to RESCAN_NEEDED or MANUAL_GAUGE_REQUIRED depending on whether rescan can plausibly improve the failing metric:
- Coverage, density, boundary proximity, or incidence angle failures → RESCAN_NEEDED (a better scan path may fix these)
- Fit residual or inter-scan repeatability failures after a rescan has already been attempted → MANUAL_GAUGE_REQUIRED (the scanner cannot resolve this feature on this part)
- Alignment sensitivity failure → MANUAL_GAUGE_REQUIRED (this is a geometric limitation, not a scan-quality issue)

**Precedence rule:** Section 8.2 demotion is evaluated first. If a feature survives demotion (i.e., it is still Class B or better), Section 7.7 decision rules are applied to the demoted class. Section 7.7 never sees a feature that has already been escalated to RESCAN or MANUAL by Section 8.2. This means the decision engine's local-confidence gate check (Section 7.7 row 4) only fires for features that failed all Class B local gates — it does not fire for features that merely dropped from A to B.

### 8.3 Decision confidence

After the measured value and uncertainty are computed, the decision engine applies the rules in Section 7.7. The decision itself carries a reason code that is displayed to the technician and logged:

| Reason code | Meaning |
|---|---|
| PASS_FULL_CONFIDENCE | Value ± U fully inside tolerance. All gates passed. |
| PASS_WITH_GUARD_BAND | Value ± U inside narrowed tolerance with guard band. |
| FAIL_FULL_CONFIDENCE | Value ± U fully outside tolerance — clear reject. |
| FAIL_MARGINAL | Value outside tolerance and uncertainty band does not reach back inside tolerance — reject with high confidence. Distinct from FAIL_FULL_CONFIDENCE only in that the margin is small (deviation < 2×U beyond limit). Logged for trend analysis. |
| MARGINAL_OUTSIDE | Value outside tolerance but uncertainty overlaps the tolerance limit — cannot confirm reject with confidence. Routed to manual verification. |
| MARGINAL_INSIDE | Value inside tolerance but uncertainty extends past limit. |
| RESCAN_LOW_COVERAGE | Feature coverage below threshold, rescan may help. |
| RESCAN_HIGH_NOISE | Fit residual or repeatability poor, rescan may help. |
| MANUAL_ALIGNMENT_SENSITIVE | Measurement varies with alignment — scanner cannot resolve. |
| MANUAL_FEATURE_TOO_SMALL | Feature below scanner-validated minimum. |
| MANUAL_NOT_SCAN_ELIGIBLE | Feature class C. |
| BLOCKED_CALIBRATION | Calibration expired. |
| BLOCKED_RECIPE_MISMATCH | Configuration does not match locked recipe. |
| REVIEW_ONLY_BEST_FIT | Measurement derived from unconstrained alignment — display only. |
| REVIEW_ONLY_ALIGNMENT_DEGRADED | Alignment passed hard-block but is in the soft-degrade band (fitness, RMSE, or stability between thresholds) — all features demoted to review-only for this inspection. |
| REVIEW_ONLY_CONFIDENCE_DEMOTED | Class A feature failed one or more Class A local confidence gates but passed Class B gates — demoted to review-only for this inspection per Section 8.2 precedence rule. |
| PLATE_LOCALIZATION_FAILED | Batch mode: plate fiducials not detected. Fatal-redo — entire batch scan rejected. |
| PLATE_POSE_POOR | Batch mode: plate localization RMSE above recipe threshold. Fatal-redo — entire batch scan rejected. |
| PLATE_COVERAGE_INSUFFICIENT | Batch mode: one or more occupied slot ROIs below minimum point density at plate level. Fatal-redo — rescan plate. |
| SLOT_OCCUPANCY_MISMATCH | Batch mode: system-detected slot occupancy disagrees with operator declaration. Pause/resolve — operator confirms or corrects mapping, then processing resumes. |
| SLOT_ASSIGNMENT_UNCERTAIN | Batch mode: dominant cluster centroid offset from expected part center beyond tolerance. Slot paused for operator verification. |
| SLOT_CONTAMINATED | Batch mode: cross-slot contamination detected in slot ROI. Slot paused — see contamination handling rule (Section 8.0.1). |
| SLOT_MULTI_CLUSTER | Batch mode: multiple significant clusters in slot ROI (debris, overspray bridging, or misplaced part). Slot paused for operator verification. |
| SLOT_SPARSE | Batch mode: insufficient point density in slot ROI after partitioning. Rescan needed for this slot region. |

---

## 9. UX design

### 9.1 Design principles

- **Decision-first, not visualization-first.** The top of every result screen shows what passed, what failed, what needs action, and why. The 3D deviation heatmap is a supporting detail, not the headline.
- **Wizard-driven for technicians.** The inspection flow is linear. The technician cannot get lost.
- **Explicit escalation.** Every non-pass result includes a specific recommended action, not a generic warning.
- **No hidden state.** Calibration status, recipe match status, and scan quality are always visible.

### 9.2 Application screens

#### 9.2.1 Home / part library

Searchable grid of configured part numbers. Each card shows: CAD thumbnail, part number, revision, recipe status (valid / expired / not configured), last inspection date and result. Two actions: "Start inspection" (available only for parts with valid recipes) and "Configure part" (engineer mode).

A persistent status bar at the top shows: scanner connection status, calibration status (valid / expiring soon / expired), and current operator ID.

#### 9.2.2 Part onboarding (engineer-facing)

The full onboarding workflow from Section 5, presented as a multi-step form. Saves progress between sessions. Cannot be completed without a successful MSA study.

#### 9.2.3 Inspection wizard (technician-facing)

**Step 1 — Select part.**
Choose from library. Shows prep instructions, fixture setup photo, and any notes from the engineer. If calibration is expired, the system blocks this step and prompts for a validation scan.

**Step 2 — Scan.**
Displays a live or imported point cloud preview. Shows scan count progress ("Scan 2 of 3"). Quality gates are enforced per scan with specific corrective prompts:
- "Scan too sparse — move scanner more slowly across the part"
- "Hole B area has low coverage — angle scanner toward the bore entrance"
- "High noise on left side — check for ambient light interference or scan spray coverage"

If a scan fails quality gates, it is rejected and the technician is prompted to redo that scan, not move to the next step.

**Step 3 — Processing.**
Automatic. Progress bar with stages: preprocessing → alignment → fusion → measurement → decision. Target: < 45 seconds for 3-scan pipeline. The technician waits.

**Step 4 — Results.**

The results screen is organized by decision priority, not by feature number:

**Top section — Verdict banner.**
Full-width banner showing overall disposition: PASS (all Class A features passed), FAIL (any Class A feature failed), or ACTION REQUIRED (features need manual verification).

**Section A — Requires action (if any).**
Features that need manual measurement, rescan, or review. Each row shows:

| Feature | Value | Tolerance | Status | Reason | Action |
|---|---|---|---|---|---|
| Hole B diameter | 0.252" ± 0.004" | 0.250" ± 0.003" | MANUAL_GAUGE_REQUIRED | Coverage 42%, below 80% threshold | Measure with pin gauge |
| Top face flatness | 0.006" ± 0.003" | 0.005" max | MARGINAL_INSIDE | Value in-spec but uncertainty exceeds limit | Verify with indicator |

**Section B — Failed (if any).**
Features that definitively failed:

| Feature | Value | Tolerance | Status | Deviation |
|---|---|---|---|---|
| Overall length | 4.528" ± 0.002" | 4.500" ± 0.010" | FAIL_FULL_CONFIDENCE | +0.028" |

**Section C — Passed.**
Features that auto-passed. Collapsed by default (expandable). Each row shows value, tolerance, deviation, and confidence level.

**Section D — Review-only (Class B).**
Features measured but not eligible for auto-disposition. Displayed with clear "REVIEW ONLY — NOT FOR DISPOSITION" labeling.

**Section E — Not measured (Class C).**
List of features that require manual gauging with the recommended instrument and method.

**3D viewport (lower section).**
Deviation color map overlay on the aligned scan. Blue = under nominal, green = within tolerance, red = over nominal. Clicking a row in the feature table highlights that feature in the viewport. Clicking a point in the viewport shows its local deviation value.

**Step 5 — Disposition.**
Technician selects overall action:
- "Accept" — available only if no Class A features failed and all action items are resolved
- "Reject" — available anytime
- "Hold for review" — logs the inspection and flags for engineering review
- "Complete manual measurements" — opens a form to enter hand-gauge results for Class C and escalated features

All disposition actions require the technician to confirm. Results are logged with timestamp, operator, scan data reference, recipe version, and all measurement evidence.

#### 9.2.4 Manual measurement entry

When features are escalated to manual gauging, this screen shows:
- The feature name and location (highlighted in 3D view)
- The nominal value and tolerance
- The recommended measurement instrument and method
- An input field for the technician to enter the measured value
- Input field for gauge asset ID and calibration due date
- Auto-computed pass/fail based on entered value

This keeps all inspection data (scan-derived and manual) in one record.

#### 9.2.5 Calibration validation

Accessed from the status bar or at shift start. The technician scans a reference artifact (gauge block, 1-2-3 block, or calibration sphere). The system compares scan-derived dimensions to certified values and reports current scanner accuracy. If accuracy is within limits, calibration is marked valid for the configured duration.

#### 9.2.6 History and trends (Phase 2)

Inspection history per part number. Table view with filtering. Trend charts showing measurement drift over time per feature. The database schema supports this from v1 — the UI is deferred.

#### 9.2.7 Batch inspection wizard (Phase 2)

The batch wizard replaces the single-part inspection wizard when the operator selects a batch recipe.

**Step 1 — Select batch recipe.**
Choose from batch-configured recipes in the part library. Shows plate layout diagram, slot count, prep instructions, and plate setup photo.

**Step 2 — Slot/serial mapping.**
Interactive plate map showing all slot positions. For each occupied slot, the operator enters or scans the part serial number or receiving sample ID. Empty slots are marked as unoccupied. The system validates that all entered serials match the expected part number for this batch recipe.

**Step 3 — Scan.**
Same as single-part scan (Section 9.2.3 Step 2) but with plate-level scan path guidance. Quality gates are evaluated at the plate level (point count, fiducial visibility) during capture. Per-slot quality is evaluated after partitioning.

**Step 4 — Processing.**
Progress display shows: plate localization → slot partitioning → then per-slot progress bars (Slot A: aligning… Slot B: measuring… etc.). Slots process in parallel where hardware allows. A failed slot shows its failure reason immediately without blocking other slots.

**Step 5 — Results.**
See Section 9.2.8.

#### 9.2.8 Batch results page (Phase 2)

The batch results page is structured as a plate summary with per-slot drill-down, not a flat list of all features across all slots.

**Top section — Batch summary banner.**
Shows overall batch outcome: ALL PASSED (all occupied slots passed), MIXED (some passed, some need action), ALL FAILED, or INCOMPLETE. Counts: X of Y slots passed, Z need action.

**Middle section — Plate map.**
Visual plate layout showing each slot as a card with color-coded status (green = pass, red = fail, yellow = action required, gray = empty). Each card shows: slot ID, serial number, slot disposition, and count of features by status. Clicking a slot card drills down to the per-slot detail view.

**Per-slot detail view.**
Identical to the single-part results screen (Section 9.2.3 Step 4): verdict banner, action-required features, failed features, passed features, review-only features, manual features, and 3D viewport — all scoped to that slot's data. A breadcrumb or back button returns to the plate map.

**Bottom section — Batch actions.**
- "Accept all passed" — available only if all occupied slots are individually acceptable
- "Disposition per slot" — opens per-slot accept/reject/hold actions individually. **This is the default and preferred workflow.** It preserves the isolation principle and the >95% unaffected-slot salvage target.
- "Rescan plate" — if plate-level or multiple slot-level failures suggest a full rescan is more efficient than slot-by-slot recovery
- "Reject entire batch" — rejects all slots regardless of individual outcome. This is a **lot-level administrative action**, not a routine operator button. It requires: (a) free-text justification, (b) engineer e-signoff if any slots had individually passing dispositions, and (c) a confirmation dialog warning that passing slots will be overridden. Use case: lot-level rejection based on external information (supplier notification, receiving hold, etc.), not individual part failure. The system logs the override with audit trail.

Each slot's disposition is recorded independently in its child Inspection record. The batch summary disposition is derived from the child dispositions, not set independently — except when "Reject entire batch" is used, in which case the override is recorded as a lot-level action and all child dispositions are set to `fail_by_batch_override` with the engineer's justification.

### 9.3 Keyboard shortcuts

| Action | Shortcut |
|---|---|
| Start new inspection | Cmd + N |
| Import scan file | Cmd + I |
| Toggle deviation overlay | D |
| Toggle measurement callouts | M |
| Orbit 3D view | Click + drag |
| Zoom | Scroll wheel |
| Pan | Shift + click + drag |
| Next wizard step | Enter or → |
| Previous wizard step | ← or Esc |
| Export report | Cmd + E |

---

## 10. Reporting

### 10.1 Inspection report contents

1. **Header:** Part number, revision, serial/lot number, date, operator, scanner asset ID, recipe version, calibration status at time of inspection.
2. **Receiving context (if applicable):** Supplier, PO, lot number, sample plan reference.
3. **Overall disposition:** Using the full disposition taxonomy (pass_scan_only, pass_after_manual, fail_by_scan, fail_after_manual, hold_for_review, accepted_under_deviation, incomplete, fail_by_batch_override).
4. **Feature results by class and status:** Organized as in the results screen (action required → failed → passed → review-only → manual).
5. **Per-feature evidence:** For each measured feature: value, bias correction applied, expanded uncertainty, all local confidence metrics, all uncertainty components, reason code.
6. **Deviation color map:** Rendered images from 2–3 standard viewing angles.
7. **Alignment quality:** Fitness, RMSE, stability check result, alignment mode (datum-observed / fixture-geometry / unconstrained), alignment band (pass / soft-degrade / hard-block).
8. **Environment snapshot:** Ambient temperature, part temperature (if recorded), humidity, warm-up elapsed time, CTE material and value used for u_temp calculation.
9. **Manual measurement results:** If any Class C or escalated features were measured by hand, including gauge ID and cal status.
10. **Operator notes:** Free-text field.

### 10.2 Report formats

- On-screen: interactive HTML in the results panel
- Export: PDF (for filing and email), CSV (for SPC/ERP import)
- All raw data (point clouds, alignment transforms, measurement evidence) archived to configurable directory with SQLite cross-reference

### 10.3 Batch report structure (Phase 2)

Batch inspections produce a two-level report: one batch cover page plus one child report per occupied slot.

**Batch cover page:**
1. **Header:** Batch ID, plate layout ID, part number, revision, batch recipe version, date, operator, scanner asset ID.
2. **Receiving context:** Supplier, PO, lot number, sample plan reference (shared across all slots in the batch).
3. **Plate summary:** Slot map diagram with per-slot disposition color coding. Counts: slots occupied, passed, failed, action required, empty.
4. **Slot summary table:** One row per occupied slot showing slot ID, serial number, disposition, feature pass/fail counts, and any flags (contamination, confidence demotion).
5. **Batch disposition:** Derived from child slot dispositions. Not independently editable.
6. **Environment snapshot:** Shared across the batch (one plate scan = one environment).

**Child per-slot reports:**
Each occupied slot produces a full inspection report per Section 10.1, identical in structure to a single-part report. The child report includes:
- Slot ID and position on plate
- Serial number assigned to this slot
- Reference to parent batch ID
- All per-feature results, evidence, deviation maps, and disposition for this slot only

Child reports are independently archivable. An auditor can pull a single slot's report without needing the full batch context, or can pull the batch cover page for an overview.

---

## 11. Technology stack

| Component | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | Cross-platform ecosystem, team familiarity, scientific computing. |
| UI framework | PySide6 (Qt 6) | Native macOS look and feel, hardware-accelerated 3D viewport. |
| 3D rendering | VTK via PyVista | Point cloud and mesh rendering, deviation overlay, measurement callouts. |
| Point cloud processing | Open3D | ICP alignment, normal estimation, downsampling, outlier removal. ARM64 native. |
| Mesh and primitive fitting | trimesh, scipy | RANSAC fits, least-squares plane/cylinder/circle fitting. |
| CAD import | cadquery / OCP (OpenCascade) | STEP import, B-rep to mesh conversion, feature topology access. |
| Numerical core | numpy, scipy | Deviation math, statistical analysis, uncertainty propagation. |
| Report generation | Jinja2 + weasyprint | HTML-templated PDF reports. |
| Data storage | SQLite | Part library, recipes, inspection history, measurement evidence. Zero-config. |
| Scanner interface | File-based PLY/OBJ import | Scanner-agnostic. Creality Scan (Ferret SE) and Revo Scan 5 both export PLY. |
| Configuration | YAML | Scanner profiles, default thresholds, paths. |

### 11.1 Module structure

```
scanqa/
├── core/
│   ├── alignment.py         # Three-stage alignment pipeline
│   ├── deviation.py          # Point-to-surface deviation computation
│   ├── measurement.py        # Local primitive fitting and dimension extraction
│   ├── fusion.py             # Multi-scan merge, voxel consensus, averaging
│   ├── outlier.py            # SOR, CAD-proximity, consensus filtering
│   ├── confidence.py         # Per-feature local confidence evaluation
│   ├── decision.py           # Decision engine with uncertainty and guard bands
│   └── uncertainty.py        # Uncertainty propagation and expanded uncertainty
├── cad/
│   ├── importer.py           # STEP file loading via OpenCascade
│   ├── feature_extract.py    # Hole detection, face classification, datum extraction
│   └── feature_region.py     # Search region definition for measurement extraction
├── scanner/
│   ├── import_ply.py         # Point cloud file ingestion and validation
│   ├── preprocessing.py      # Downsample, normal estimation, noise filtering
│   ├── profiles.py           # Scanner-specific parameter profiles
│   └── calibration.py        # Validation artifact scanning and accuracy tracking
├── recipe/
│   ├── manager.py            # Recipe creation, locking, version control
│   ├── msa.py                # Measurement system analysis study execution
│   └── eligibility.py        # Feature class assignment and gate evaluation
├── ui/
│   ├── main_window.py        # Application shell with status bar
│   ├── scan_viewport.py      # 3D viewer with deviation overlay
│   ├── part_library.py       # Part grid and search
│   ├── inspection_wizard.py  # 5-step technician workflow
│   ├── results_panel.py      # Decision-first results display
│   ├── manual_entry.py       # Manual measurement input form
│   ├── onboarding_wizard.py  # Engineer part setup workflow
│   ├── calibration_view.py   # Validation artifact routine
│   └── report_viewer.py      # PDF preview and export
├── batch/                     # Phase 2 batch mode
│   ├── plate_layout.py        # Plate definition, slot poses, fiducial config
│   ├── plate_localization.py  # Fiducial detection and plate pose solve
│   ├── slot_partition.py      # Slot ROI crop and occupancy detection
│   ├── contamination.py       # DBSCAN sanity check and cross-slot contamination
│   └── batch_manager.py       # Per-slot pipeline fan-out and batch summary
├── reports/
│   ├── templates/            # Jinja2 HTML report templates
│   └── generator.py          # PDF report assembly
├── data/
│   └── scanqa.db             # SQLite database
└── config/
    ├── settings.yaml         # Global settings
    └── scanner_profiles/     # Per-scanner YAML profiles
```

---

## 12. Data model

### 12.1 Core entities

**Part**

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key. |
| part_number | string | Company part number. |
| revision | string | Drawing revision. |
| description | string | Human-readable name. |
| cad_file_path | string | Path to STEP file. |
| cad_hash | string | SHA-256 of STEP file. |
| material_type | enum | machined_metal, injection_molded, fdm_printed, sla_printed. |
| created_at | timestamp | |
| updated_at | timestamp | |

**InspectionRecipe**

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key. |
| part_id | UUID | FK to Part. |
| revision | string | Recipe revision (increments on any change). |
| scanner_model | string | Validated scanner model. |
| scanner_firmware | string | Validated firmware version. |
| software_version | string | ScanQA version at recipe creation. |
| fixture_id | string | Physical fixture identifier. |
| fixture_notes | text | Setup instructions and photo reference. |
| datum_observability_method | enum | fiducials, fixture_geometry, datum_features, marker_board. |
| scan_preset | JSON | Scanner resolution, exposure, distance settings. |
| surface_prep | text | Required prep procedure. |
| required_scan_count | integer | Minimum scan passes. |
| datum_scheme | JSON | Primary/secondary/tertiary datum definitions. |
| alignment_mode | enum | datum_constrained, fixture_assisted, unconstrained. |
| default_guard_band_method | enum | simple_percentage, uncertainty_based, shared_risk. Recipe-level default; can be overridden per feature in MeasurementFeature. |
| default_guard_band_percent | float | Default G% for simple_percentage method (default 10%). Per-feature override in MeasurementFeature takes precedence. |
| msa_study_id | UUID | FK to the MSA study that validated this recipe. |
| approved_by | string | Engineer name. |
| approved_at | timestamp | |
| status | enum | draft, active, superseded, revoked. |
| created_at | timestamp | |

**MeasurementFeature**

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key. |
| recipe_id | UUID | FK to InspectionRecipe. |
| name | string | Feature label ("Hole A diameter"). |
| type | enum | diameter, distance, bbox_length, bbox_width, bbox_height, flatness. |
| nominal | float | Nominal dimension (inches). |
| tolerance_plus | float | Upper tolerance. |
| tolerance_minus | float | Lower tolerance (negative). |
| cad_feature_ref | JSON | CAD geometry reference (face IDs, search region). |
| sort_order | integer | Display order in report. |
| eligibility_class | enum | A, B, C. |
| criticality | enum | critical, noncritical. Critical features use <10% GRR threshold for Class A; noncritical use <20% with guard band and written approval. |
| guard_band_method | enum | simple_percentage, uncertainty_based, shared_risk. Per Section 7.6. Determines how acceptance limits are narrowed for this feature. |
| guard_band_percent | float | For simple_percentage method: G% narrowing on each side. Ignored for other methods. |
| shared_risk_approval | text | Required when guard_band_method = shared_risk. Engineer name, date, and justification for accepting shared risk on this noncritical feature. Null for other methods. |
| class_justification | text | Why this class was assigned. |

**FeatureCapability**

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key. |
| feature_id | UUID | FK to MeasurementFeature. |
| msa_study_id | UUID | FK to MSAStudy. |
| bias | float | Mean measurement error vs reference. |
| repeatability_2sigma | float | Within-operator variation. |
| reproducibility_2sigma | float | Between-operator variation. |
| gage_rr_percent | float | GRR as % of tolerance. |
| ndc | integer | Number of distinct categories (1.41 × σ_parts / σ_GRR). Must be ≥ 5 for Class A and Class B. |
| fit_correction_factor | float | Empirical c_fit for u_fit calculation. Derived from MSA by comparing naive u_fit to observed measurement variation. |
| alignment_sensitivity | float | Value change per ±0.2° perturbation. |
| min_coverage_required | float | Minimum local coverage for valid measurement. |
| min_density_required | float | Minimum local point density. |
| validated_min_feature_size | float | Smallest feature validated for this class. |
| max_uncertainty_for_autopass | float | Maximum expanded uncertainty for Class A pass. |
| max_fit_residual | float | Maximum acceptable fit RMSE (recipe-derived from MSA). |
| slot_group | string | Batch mode only: slot equivalence group this capability was validated for (e.g., "center_slots", "edge_slots"). Null for single-part capabilities. Allows equivalent slots to share one MSA validation. |

**MSAStudy**

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key. |
| recipe_id | UUID | FK to InspectionRecipe. |
| tier | enum | screening, release. |
| operators | JSON | List of operator IDs. |
| part_serials | JSON | List of part serial numbers used. |
| sessions_per_operator | integer | Number of scan sessions per operator. |
| reference_instrument | string | Instrument type: "CMM" / "Caliper" / "Pin gauge set". |
| reference_instrument_asset_id | string | Physical asset tag or serial number of the reference instrument. |
| reference_instrument_cal_date | date | Most recent calibration date of the reference instrument. |
| reference_instrument_cal_due | date | Next calibration due date. Study is invalid if reference instrument calibration was expired at time of study. |
| reference_instrument_uncertainty | float | Certified uncertainty of reference instrument (from calibration certificate). |
| reference_instrument_cert_authority | string | Calibration lab or authority (e.g., "NIST-traceable lab XYZ"). |
| completed_at | timestamp | |
| raw_data_path | string | Path to archived study data. |

**ReceivingContext**

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key. |
| supplier_id | string | Supplier code or name. |
| purchase_order | string | PO number. |
| lot_number | string | Supplier lot or batch number. |
| serial_number | string | Individual part serial (if applicable). |
| inspection_level | enum | normal, tightened, reduced (per sampling plan). |
| sample_plan | string | Reference to applicable sampling plan (e.g., "AQL 1.0, Level II"). |
| quantity_received | integer | Total parts in shipment. |
| quantity_to_inspect | integer | Sample size per plan. |
| lot_disposition | enum | pending, lot_accept, lot_reject, lot_hold, lot_accepted_under_deviation. See lot disposition rules below. |
| lot_disposition_by | string | Engineer or system that set lot disposition. |
| lot_disposition_at | timestamp | When lot disposition was set. |
| lot_disposition_notes | text | Justification, especially for lot_hold or lot_accepted_under_deviation. |
| created_at | timestamp | |

**Lot disposition rules:**

After all sampled parts in a receiving context have been inspected, the system evaluates lot-level acceptance. This is the bridge between per-part inspection results and the actual receiving decision.

| Condition | Lot disposition | Action |
|---|---|---|
| All sampled parts dispositioned pass_scan_only or pass_after_manual | lot_accept | Lot is accepted. No further action. |
| Any sampled part dispositioned fail_by_scan or fail_after_manual, and reject count exceeds the sampling plan's reject number (per AQL table) | lot_reject | Lot is rejected. System generates lot rejection report referencing all failed inspections. |
| Any sampled part dispositioned fail, but reject count is at or below the sampling plan's accept number | lot_accept | Lot is accepted per sampling plan. Failed parts are individually segregated per standard practice. |
| Any sampled part dispositioned hold_for_review or incomplete | lot_hold | Lot cannot be dispositioned until all holds are resolved. System blocks lot acceptance. |
| Lot rejected but engineering concession granted | lot_accepted_under_deviation | Requires e-signoff with deviation number. All inspection records are linked. |

**Sampling plan enforcement:** The system tracks how many of the `quantity_to_inspect` parts have been inspected and prevents lot disposition until the sample is complete. If `inspection_level` is `tightened`, the system applies the tightened accept/reject numbers from the referenced sampling plan. Switching between normal/tightened/reduced inspection levels is an engineer action logged with justification.

**Note:** The system does not implement the full ANSI/ASQ Z1.4 switching rules (e.g., automatic tightening after 2-of-5 lot rejects). In v1, inspection level switching is manual. Automated switching rules are a Phase 3+ capability. The system does track the data needed for switching decisions (consecutive lot accept/reject history per supplier × part number).

**Inspection**

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key. |
| part_id | UUID | FK to Part. |
| recipe_id | UUID | FK to InspectionRecipe. |
| receiving_context_id | UUID | FK to ReceivingContext (nullable for standalone inspections). |
| recipe_revision | string | Snapshot of recipe version used. |
| operator | string | Technician ID. |
| scanner_asset_id | string | Physical scanner asset tag / serial number. |
| fixture_asset_id | string | Physical fixture asset tag. |
| scan_count | integer | Number of scans captured. |
| alignment_fitness | float | |
| alignment_rmse | float | |
| alignment_stable | boolean | Perturbation stability check result. |
| alignment_mode_actual | enum | datum_observed, fixture_geometry, datum_features, unconstrained. |
| calibration_run_id | UUID | FK to most recent CalibrationRun. |
| environment_snapshot_id | UUID | FK to EnvironmentSnapshot. Required for all inspections. |
| batch_inspection_id | UUID | FK to BatchInspection (nullable — null for single-part inspections). |
| batch_slot_id | UUID | FK to BatchSlot (nullable — null for single-part inspections). |
| disposition | enum | See disposition taxonomy below. |
| notes | text | Operator notes. |
| report_pdf_path | string | |
| created_at | timestamp | |

**Disposition taxonomy:**

| Value | Meaning |
|---|---|
| pass_scan_only | All Class A features passed by scan. No manual measurements were required or performed. |
| pass_after_manual | Class A scan features passed. Escalated and Class C features verified by manual measurement — all passed. |
| fail_by_scan | One or more Class A features failed by scan with full confidence. |
| fail_after_manual | Scan results were marginal or escalated; manual measurement confirmed failure. |
| hold_for_review | Inspection complete but results require engineering review before disposition. |
| accepted_under_deviation | Part does not meet drawing spec but accepted via engineering concession / deviation approval. Requires e-signoff. |
| incomplete | Inspection started but not finished (scan quality issues, operator stopped, etc.). |
| fail_by_batch_override | Batch mode only: slot was individually acceptable but overridden by a lot-level "Reject entire batch" action. Requires engineer e-signoff and justification. |

The distinction between `pass_scan_only` and `pass_after_manual` is critical for traceability. It tells an auditor whether the pass was fully automated or required human measurement in the loop.

**InspectionResult**

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key. |
| inspection_id | UUID | FK to Inspection. |
| feature_id | UUID | FK to MeasurementFeature. |
| raw_value | float | Measured value before bias correction. |
| corrected_value | float | Measured value after bias correction. |
| expanded_uncertainty | float | U_adj (k=2, coverage-adjusted). |
| deviation | float | Corrected value minus nominal. |
| status | enum | pass, fail_full, fail_marginal, marginal_outside, marginal_inside, rescan_needed, manual_required, review_only, blocked. |
| reason_code | string | From decision engine (Section 8.3). |
| recommended_action | text | Specific next step for non-pass results. |
| measurement_source | enum | scan, manual. |
| manual_gauge_id | string | If manual: asset ID of gauge/instrument used (nullable). |
| manual_gauge_cal_due | date | If manual: calibration due date of gauge (nullable). |

**MeasurementEvidence**

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key. |
| result_id | UUID | FK to InspectionResult. |
| local_coverage | float | Feature coverage fraction. |
| local_density | float | Points per mm². |
| incidence_angle_median | float | Median scan angle at feature. |
| fit_residual | float | RMSE of primitive fit. |
| inter_scan_stddev | float | Std dev of measurement across individual scans. |
| alignment_sensitivity | float | Value change under alignment perturbation. |
| boundary_proximity | float | Distance to nearest scan edge. |
| inlier_count | integer | Number of points used in fit. |
| effective_sample_size | integer | n_eff used for u_fit (spatial decimation or empirical model). |
| fit_correction_factor | float | c_fit from MSA empirical model (1.0 if using spatial decimation fallback). |
| u_fit | float | Standard uncertainty: fit component (RMSE / √n_eff × c_fit). |
| u_repeat | float | Standard uncertainty: repeatability (from recipe). |
| u_reprod | float | Standard uncertainty: reproducibility (from recipe). |
| u_align | float | Standard uncertainty: alignment sensitivity. |
| u_cal | float | Standard uncertainty: calibration. |
| u_ref | float | Standard uncertainty: reference instrument (from recipe). |
| u_temp | float | Standard uncertainty: thermal. |
| u_bias_est | float | Standard uncertainty: bias estimation. |
| u_combined | float | Combined standard uncertainty (u_c). |
| coverage_inflation_factor | float | f_cov applied (1.0 if no inflation). |
| expanded_uncertainty | float | U_adj = k × u_c × f_cov. |
| slot_assignment_confidence | float | Batch mode only: confidence score for slot assignment (0–1). Null for single-part inspections. |
| cluster_count | integer | Batch mode only: number of DBSCAN clusters found in slot ROI. Expected = 1 for clean slot. Null for single-part. |
| cross_slot_contamination | float | Batch mode only: fraction of points in slot ROI attributed to adjacent slot or inter-slot fixture. 0.0 = clean. Null for single-part. |

**CalibrationRun**

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key. |
| scanner_model | string | |
| scanner_asset_id | string | Physical asset tag. |
| artifact_id | string | Reference artifact identifier. |
| artifact_certified_value | float | Known dimension of artifact. |
| artifact_cert_uncertainty | float | Certification uncertainty. |
| measured_value | float | Scan-derived dimension. |
| error | float | Measured minus certified. |
| pass_fail | boolean | Error within acceptance limit. |
| operator | string | |
| environment_temp_c | float | Ambient temperature at time of calibration. |
| environment_notes | text | Lighting, vibration, etc. |
| created_at | timestamp | |

**EnvironmentSnapshot**

Captures the environmental conditions at the time of an inspection or calibration run. This record justifies the u_temp uncertainty component and supports auditability of thermal compensation.

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key. |
| inspection_id | UUID | FK to Inspection (nullable — may be linked to CalibrationRun instead). |
| calibration_run_id | UUID | FK to CalibrationRun (nullable). |
| ambient_temp_c | float | Measured ambient temperature in °C at time of inspection/calibration. |
| part_temp_c | float | Measured or estimated part temperature in °C (nullable — recorded if part was recently machined, stored cold, etc.). |
| humidity_percent | float | Relative humidity % (nullable — recorded if available). |
| warmup_elapsed_minutes | float | Time elapsed since scanner power-on. Must be ≥ 30 for valid inspections per operating model (Section 2.1). |
| cte_material | string | Material used for CTE calculation (e.g., "6061-T6 aluminum", "ABS"). |
| cte_value | float | Coefficient of thermal expansion used in u_temp calculation (µm/m/°C). |
| cte_source | string | Source of CTE value (e.g., "MatWeb 6061-T6", "recipe default"). |
| delta_t_from_20c | float | Computed |ambient_temp_c − 20°C|, the ΔT used in u_temp. |
| recorded_by | string | Operator or sensor ID that recorded the environment data. |
| created_at | timestamp | |

### 12.2 Batch mode entities (Phase 2)

**BatchPlateLayout**

Defines a reusable fixture plate configuration for batch inspection.

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key. |
| name | string | Plate identifier (e.g., "4-up aluminum bracket plate"). |
| plate_dimensions | JSON | Physical plate width, length, thickness in mm. |
| plate_material | string | Plate material (for CTE if relevant). |
| slot_count | integer | Number of defined slots (2–4 for Phase 2). |
| allowed_part_id | UUID | FK to Part. Phase 2: all slots must use this part. Phase 3: nullable for mixed-part plates. |
| fiducial_definitions | JSON | Array of fiducial/fixture geometry features for plate localization: type, position in plate coordinates, expected size. Minimum 3 non-collinear. |
| slot_definitions | JSON | Array of slot records, each containing: slot_id, pose (6DOF transform from plate origin), ROI bounds in plate coordinates, expected part centroid, occlusion mask, and slot_equivalence_group. |
| min_inter_slot_spacing_mm | float | Minimum edge-to-edge spacing between nearest part features across slots. |
| plate_photo_path | string | Reference photo of plate with parts loaded. |
| created_by | string | Engineer name. |
| created_at | timestamp | |
| status | enum | draft, active, retired. |

**BatchInspection**

Parent record for a batch scan session. Links to child Inspection records per slot.

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key. |
| plate_layout_id | UUID | FK to BatchPlateLayout. |
| recipe_id | UUID | FK to InspectionRecipe (batch recipe). |
| receiving_context_id | UUID | FK to ReceivingContext (nullable). Shared across all slots in this batch. |
| operator | string | Technician ID. |
| scanner_asset_id | string | Physical scanner asset tag. |
| scan_count | integer | Number of plate-level scan passes captured. |
| plate_localization_rmse | float | RMSE of plate fiducial/geometry fit. |
| plate_localization_method | enum | fiducials, fixture_geometry. |
| slots_occupied | integer | Number of slots with parts loaded. |
| slots_passed | integer | Number of child inspections with pass disposition. |
| slots_failed | integer | Number of child inspections with fail disposition. |
| slots_action_required | integer | Number of child inspections needing manual action or review. |
| batch_disposition | enum | all_passed, mixed, all_failed, incomplete. Derived from child dispositions. |
| environment_snapshot_id | UUID | FK to EnvironmentSnapshot. Shared across the batch. |
| calibration_run_id | UUID | FK to CalibrationRun. |
| notes | text | Operator notes for the batch. |
| report_pdf_path | string | Batch cover page report path. |
| created_at | timestamp | |

**BatchSlot**

Links a physical slot position on a plate to its child inspection in a batch scan.

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key. |
| batch_inspection_id | UUID | FK to BatchInspection. |
| slot_id_on_plate | string | Slot identifier from BatchPlateLayout (e.g., "Slot_A"). |
| slot_pose | JSON | Rigid transform used for this slot (from plate layout, may include runtime refinement). |
| serial_number | string | Part serial or sample ID loaded in this slot. |
| occupied | boolean | True if part was loaded, false if slot left empty. |
| inspection_id | UUID | FK to child Inspection record (nullable — null if slot is empty). |
| slot_assignment_confidence | float | Confidence that the correct point subset was assigned to this slot (0–1). |
| cluster_count | integer | DBSCAN cluster count in slot ROI. |
| cross_slot_contamination | float | Fraction of points attributed to adjacent slots. |
| slot_status | enum | clean, assignment_uncertain, contamination_flagged, multi_cluster, occupancy_mismatch, sparse, empty. This is a **normalized state enum**, not a direct copy of the reason code strings. The mapping is: clean = no issue; assignment_uncertain ↔ SLOT_ASSIGNMENT_UNCERTAIN; contamination_flagged ↔ SLOT_CONTAMINATED; multi_cluster ↔ SLOT_MULTI_CLUSTER; occupancy_mismatch ↔ SLOT_OCCUPANCY_MISMATCH; sparse ↔ SLOT_SPARSE; empty = slot unoccupied. The reason_code field on the child Inspection or InspectionResult records carries the full canonical SLOT_* code; slot_status is the persisted summary state on the BatchSlot record. |
| created_at | timestamp | |

---

## 13. Performance targets

### 13.1 Operational targets

| Metric | Target | Notes |
|---|---|---|
| Setup-to-decision time per part | < 6 minutes | Excludes scanner warm-up (shift-start cost, not per-part cost). |
| Scanner warm-up and calibration (shift start) | < 35 minutes | 30-min thermal stabilization + validation scan. One-time per shift. |
| Processing time (3-scan pipeline) | < 45 seconds | Import through decision engine on Mac Mini M4 Pro. |
| Scans per accepted part (average) | ≤ 3.5 | Occasional rescans expected; more than 4 average indicates a workflow problem. |
| Auto-pass rate (Class A features) | > 75% | Below this, labor savings are marginal. |
| Escalation rate (rescan + manual) | < 25% | |
| Time to onboard new part (Screening MSA, Class B) | < 4 hours | Fixture setup, feature definition, 3-part study. |
| Time to onboard new part (Release MSA, Class A) | < 16 hours | Full 10-part study, may span multiple sessions/days. |
| Recipe maintenance per revision | < 2 hours | Re-validate affected features only. May require partial MSA re-run. |

### 13.2 Compute targets (Mac Mini M4 Pro)

| Operation | Target | Notes |
|---|---|---|
| PLY import (2M points) | < 2 seconds | SSD-bound. |
| Preprocessing (SOR + downsample) | < 3 seconds | |
| Three-stage alignment | < 8 seconds | ICP is bottleneck. |
| Multi-scan fusion | < 5 seconds | Voxel consensus + averaging. |
| Measurement extraction (10 features) | < 3 seconds | Per-feature RANSAC fits. |
| Confidence evaluation (10 features) | < 2 seconds | Local metric computation. |
| Uncertainty computation (10 features) | < 1 second | GUM model, 8 components. |
| Decision engine | < 1 second | |
| Application cold start | < 5 seconds | |
| Peak memory usage | < 8 GB | |

### 13.3 Batch mode targets (Phase 2)

| Metric | Target | Notes |
|---|---|---|
| Effective per-part cycle time (4-up plate) | < 3 minutes | Compared to < 6 minutes single-part. Savings from shared scan + plate localization. Not a committed production number until batch MSA validates achievable throughput. |
| Plate localization time | < 5 seconds | Fiducial detection + pose solve. |
| Slot partitioning + contamination check | < 3 seconds per slot | DBSCAN + ROI crop + sanity checks. |
| Full 4-up plate processing time (3-scan, 5 features/part) | < 120 seconds | Plate localization + 4× per-slot pipeline. Slots process in parallel where possible. |
| Per-plate rescan rate | < 15% | Fraction of batch scans requiring a full plate rescan (not per-slot recovery). |
| Slot assignment error rate | < 0.1% | Wrong serial mapped to wrong slot. Caught by occupancy cross-check. |
| Contaminated-slot rate | < 5% | Slots flagged for cross-slot contamination or multi-cluster. |
| Unaffected-slot salvage rate | > 95% | When one slot fails, other slots on the same plate still produce valid inspections. |
| Batch-mode auto-pass rate (Class A features) | > 70% | May be lower than single-part due to slot-dependent coverage. |
| Batch-mode escalation rate | < 30% | Slightly higher than single-part is acceptable given batch throughput gains. |

---

## 14. Development phases

### Phase 0 — Feasibility kill test (Weeks 1–3)

**Goal:** Determine whether the Creality Ferret SE + Mac Mini can repeatedly measure target feature types on real parts at useful tolerance levels. This phase answers the question: "Is there a product here, or is the hardware too noisy?"

**Hardware:** Creality Ferret SE (existing), Mac Mini M4 Pro (existing). Zero spend.

**Activities:**
- Select 3 test parts (1 machined aluminum, 1 injection molded, 1 FDM printed). Must have STEP files.
- Measure 3–5 features per part with calipers/CMM — these are ground truth.
- Scan each part 5 times, repositioning between scans. Export PLY files.
- Build minimal Python CLI: load PLY → load STEP → align (ICP) → extract measurements.
- Compare scan-derived measurements to ground truth. Compute bias, repeatability, and per-feature accuracy.
- Identify which features are scan-measurable and at what tolerance threshold.
- Test scanner warm-up behavior: scan reference artifact cold, then at 10, 20, 30 minutes. Quantify drift.

**Deliverable:** A one-page accuracy characterization report:
- Per-feature bias and repeatability table
- Identified scan-eligible features vs. manual-only features
- Minimum tolerance the system can meaningfully resolve per feature type
- Scanner warm-up curve (accuracy vs. time since power-on)
- Go/no-go recommendation for Phase 1
- If go: recommended scanner upgrade path and expected accuracy improvement

**Kill criteria:** If the Ferret SE cannot achieve ±0.015" repeatability on at least 2 of the top 3 supplier-risk feature families identified below, or if alignment fails on more than 30% of scan attempts, the hardware is insufficient and the project pauses until a scanner upgrade is funded.

**Required test feature families (select top 3 from actual receiving inspection pain points):**
The 3 test parts must be chosen so that the kill test covers at least 3 of the following feature families that represent real incoming quality risk — not envelope dimensions or other features that are easy to scan but irrelevant to supplier escapes:
- Exposed hole diameters (the most common supplier-risk feature for machined parts)
- Hole-to-datum or hole-to-hole distances
- Critical envelope dimensions with tolerances ≤ ±0.010"
- Planar flatness on functional surfaces

A coarse envelope dimension that any scanner can measure does not count toward the kill test. The engineer must document, before scanning begins, which features on each test part represent actual supplier-risk dimensions and what their tolerance bands are. The kill test is evaluated only against those features.

### Phase 1 — Vertical slice (Months 1–2, post Phase 0 go)

**Goal:** End-to-end inspection pipeline on 3 parts with feature eligibility, decision engine, and basic UI.

**Hardware constraint:** Phase 1 runs on the Ferret SE. No feature may be promoted to production Class A on Ferret SE hardware unless a Release MSA (Tier 2, 10-part study) proves it meets all Class A gates for the specific feature, part, and fixture combination. This is expected to be rare — the Ferret SE's 0.1mm accuracy class means most features will remain Class B (review-only). Phase 1's primary value is proving the pipeline works end-to-end on real parts, not achieving Class A auto-disposition.

- Fixture/datum-assisted coarse alignment + ICP
- Multi-scan fusion with voxel consensus
- Local primitive fitting for 3–5 feature types
- Feature eligibility classification (A/B/C) based on Phase 0 accuracy data
- Decision engine with uncertainty (full GUM model) and reason codes
- Simple GUI: part selection → scan import → processing → decision-first results screen
- SQLite storage for recipes and inspection history
- Calibration validation routine with gauge block
- **Batch plate design (schema only, no execution):** Design and fabricate the standard 4-up fixture plate for the top 1–2 high-volume part numbers. Implement BatchPlateLayout, BatchSlot, and slot-aware recipe schema in the database. No batch scanning or processing software in Phase 1 — the plate is designed and built so it is ready for Phase 2 batch integration.

**Success criteria:**
- False accept rate: 0% in controlled testing (all known-bad features correctly flagged)
- Pipeline completes in < 60 seconds
- Results screen clearly communicates pass/fail/action-required with reasons
- Screening MSA (Tier 1) completed for all Class B features on 3 test parts

### Phase 2 — Guarded production pilot (Months 3–4)

**Goal:** Daily use on real receiving inspections with full recipe system.

- Recipe locking and version control
- Full onboarding wizard with two-tier MSA study workflow
- Release MSA (Tier 2) completed for Class A candidate features
- Guided rescan prompts (feature-specific corrective instructions)
- Manual measurement entry screen with gauge provenance
- Receiving context entry (supplier, PO, lot)
- PDF report generation with full disposition taxonomy
- 10+ part numbers configured and validated
- Operator training documentation
- Blind holdout validation set assembled and tested
- **Batch mode (same-part, 2-up to 4-up):** Batch plate scanning, plate localization, slot partitioning, per-slot pipeline fan-out, batch inspection wizard, batch results page, and batch report generation per Sections 6.4, 7.1.2, 8.0, 8.0.1, 9.2.7, 9.2.8, 10.3, and 12.2. Batch recipes require separate Screening MSA. Class A in batch requires separate Release MSA with per-slot or per-equivalence-group validation.

**Success criteria:**
- Median inspection cycle time < 6 minutes (excluding warm-up)
- Auto-pass rate > 75% for configured parts
- False accept rate: zero false accepts in Phase 2 blind holdout (early warning screen). Formal demonstration of < 0.5% deferred to cumulative production correlation program per Section 2.2. Minimum holdout: 20 known in-spec and 20 known out-of-spec features; larger holdout preferred.
- Ongoing correlation check program established (5% random re-measurement, rolling window ≥ 200 audited features)
- QA technician can operate independently after 30-minute training
- **Batch mode:** Effective per-part cycle time < 3 minutes on 4-up plate. Unaffected-slot salvage rate > 95%. Slot assignment error rate < 0.1%. Batch Screening MSA completed for at least one high-volume part.

### Phase 3 — Broaden and harden (Months 5–8)

Expand only after real field data confirms Phase 2 targets:
- Datum-constrained ICP alignment
- True position, parallelism, profile measurements (Class A eligible after MSA)
- Inspection history trends and SPC charts
- Scanner upgrade integration (swap Ferret SE for higher-accuracy unit)
- Windows port
- ERP/CSV export integration
- **Mixed-part batch plates:** Different part numbers in different slots. Requires per-slot recipe binding, mixed-part plate layout schema extension, and per-slot MSA independent of slot equivalence. Denser layouts (>4-up) and automatic slot auto-identification without fiducials are also Phase 3 scope.

### Stretch goals (Phase 4+)

- Direct scanner SDK integration
- Visual defect detection (texture analysis)
- Automated tolerance import from MBD STEP files
- Multi-site cloud sync

---

## 15. Hard no-go criteria

The system must refuse auto-disposition when any of the following are true:

- Calibration validation has expired
- Part revision does not match active recipe revision
- Scanner model or firmware does not match recipe
- Software version does not match recipe (unless explicitly re-validated)
- Feature eligibility class is not A
- Local feature coverage is below recipe-defined threshold
- Alignment sensitivity exceeds recipe-defined threshold
- Alignment is in the hard-block band (fitness or RMSE below hard-block thresholds per Section 7.2)
- Expanded uncertainty exceeds recipe-defined maximum for auto-pass
- Measured value falls within the guard band ambiguity region
- Scanner or fixture does not match recipe configuration
- Operator attempts to override a MANUAL_REQUIRED verdict without engineer e-signoff

**Additional batch-mode hard gates:**
- Plate localization failed (fiducials not detected or plate pose RMSE above threshold)
- Slot occupancy does not match operator-declared mapping (until operator confirms)
- Slot contamination flagged and not operator-verified (blocks all processing), or contamination flagged and operator-verified (caps all features at Class B review-only — Class A auto-disposition requires a clean rescan)
- Batch recipe does not have its own completed MSA (single-part MSA does not transfer)
- Slot uses a non-equivalent position that was not independently validated in the batch MSA

These are hard gates, not warnings. The system does not provide an "override and accept anyway" button accessible to the technician.

---

## 16. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Ferret SE accuracy insufficient for any useful feature class | Medium | High | Phase 0 kill test answers this before any software investment. |
| MSA study reveals no features qualify as Class A | Medium | High | Relax to Class B (review-only) use case, which still saves time. Upgrade scanner. |
| Onboarding time too high for small part count ROI | Medium | Medium | Template recipes for similar part families. Streamline MSA for low-risk features. |
| Operators bypass manual measurement steps | Medium | High | Hard gate: inspection cannot be dispositioned until all manual entries are complete. |
| Reflective aluminum causes persistent scan gaps on critical features | High | Medium | Scan spray mandatory per recipe. Coverage gates catch gaps. |
| ICP alignment converges to wrong local minimum | Medium | High | Fixture-assisted coarse pose eliminates most failure modes. Stability check catches the rest. |
| FDM layer lines bias diameter measurements | Medium | Medium | Material-specific outlier thresholds. Documented in feature capability as bias. |
| Part revision changes invalidate existing recipes | Low | Medium | CAD hash check detects changes. Recipe auto-expires on hash mismatch. |
| Over-reliance on system leads to reduced manual inspection skills | Low | Medium | Class C features ensure technicians maintain manual gauging competency. |
| Scanner thermal drift causes mid-shift accuracy degradation | Medium | Medium | 30-min warm-up protocol. Revalidation after disturbance. Validity window. |
| Batch plate slot-dependent coverage degrades edge slot features | Medium | Medium | Per-slot or per-equivalence-group MSA. Occlusion masks defined during plate onboarding. Shadow zone spacing rule. |
| Cross-slot scan spray bridging creates contamination artifacts | Medium | Low | DBSCAN contamination check per slot. Minimum inter-slot spacing. Operator guidance on spray technique. |
| Batch throughput gains do not materialize due to high per-slot rescan rate | Low | Medium | Phase 2 batch MSA validates achievable throughput before committing to batch workflow. Single-part mode remains available as fallback. |
| Single-part MSA incorrectly assumed to transfer to batch mode | Low | High | Hard gate: batch recipes require separate MSA. No inheritance from single-part validation. |

---

## 17. Glossary

| Term | Definition |
|---|---|
| MSA | Measurement System Analysis — formal study of a measurement system's bias, repeatability, and reproducibility. |
| Gage R&R | Gage Repeatability and Reproducibility — a specific MSA method quantifying measurement variation as a percentage of tolerance. |
| GRR | Combined gage repeatability and reproducibility metric. |
| ICP | Iterative Closest Point — algorithm for aligning two point clouds by minimizing correspondence distances. |
| RMSE | Root Mean Squared Error — average distance between aligned correspondences. |
| SOR | Statistical Outlier Removal — filter that removes points with anomalous neighbor distances. |
| RANSAC | Random Sample Consensus — robust model fitting method that identifies inliers in noisy data. |
| DRF | Datum Reference Frame — coordinate system established by the part's datum features per ASME Y14.5. |
| PLY | Polygon File Format — file format for 3D point cloud and mesh data. |
| MBD | Model-Based Definition — CAD models with embedded tolerancing that replace 2D drawings. |
| Guard band | Intentional narrowing of acceptance limits to account for measurement uncertainty. Per ASME B89.7.3.1. |
| Expanded uncertainty | U = k × u_c. The interval around a measured value within which the true value is expected to lie with a stated confidence (k=2 → 95%). |
| Combined standard uncertainty | u_c = RSS of all individual standard uncertainty components. Per NIST GUM methodology. |
| Coverage inflation factor | f_cov ≥ 1, applied to expanded uncertainty when local scan coverage is below the recipe-defined minimum but above the blocking threshold. |
| Feature class | Eligibility classification (A/B/C) that determines whether a feature can be auto-dispositioned, shown for review, or requires manual measurement. |
| Recipe | A locked configuration binding part revision, scanner, fixture, datum scheme, and validated feature capabilities into a single inspection definition. |
| GUM | Guide to the Expression of Uncertainty in Measurement — the international standard (JCGM 100:2008) for evaluating and expressing measurement uncertainty. Basis for the uncertainty model in this spec. |
| AQL | Acceptable Quality Level — the maximum defect rate considered acceptable in a sampling plan. |
| Batch plate | A fixture plate with multiple poka-yoke nests (slots) for scanning multiple identical parts in a single scan session. |
| Slot | A defined position on a batch plate where one part is loaded. Each slot has a known pose in plate coordinates and produces an independent child inspection. |
| Slot equivalence group | A set of slots on a batch plate that are geometrically equivalent (same viewing geometry, same expected coverage). Equivalent slots may share a single MSA validation. |
| Plate localization | The process of detecting plate fiducials or fixture geometry in a scan and solving the rigid transform from scanner coordinates to plate coordinates. |
| DBSCAN | Density-Based Spatial Clustering of Applications with Noise — clustering algorithm used in batch mode as a sanity check for slot contamination, not as the primary slot identity mechanism. |
| ndc | Number of distinct categories — a metric from MSA (1.41 × σ_parts / σ_GRR) indicating how many categories the measurement system can reliably distinguish. Must be ≥ 5 for Class A and Class B. |
