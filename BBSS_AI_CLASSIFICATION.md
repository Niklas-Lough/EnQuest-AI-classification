# EnQuest BBSS AI Classification — Hazard & Human Factors

## Overview

Every EnQuest BBSS observation card (Safe and Unsafe) is now automatically classified on two independent dimensions using an Azure AI Foundry Agent:

- **Hazard Category** — the energy source referenced in the observation text, based on the IOGP Energy Wheel plus four extensions (15 labels: Gravity, Motion, Mechanical, Electrical, Pressure, Temperature, Chemical, Biological, Radiation, Sound, Safety Systems, Environment, Major Accident Hazard, Other Hazard, N/A).
- **Human Factors Category** — the human or organisational factor evidenced in the text (11 labels: Organisational Systems & Culture, Procedures & Documentation, Leadership & Supervision, Communication & Handover, Training/Competence & Experience, Planning/Workload & Time Pressure, Equipment/Tools & Workplace Design, Fatigue & Fitness for Duty, Human Error, Risk-Taking & Compliance Behaviour, N/A).

This is a broader, AI-assigned taxonomy sitting alongside the existing manually-selected "Type of Hazard" (9 Life-Saving Rules) field — it does not replace or overwrite it, and applies to every card regardless of what the reporter picked on that field.

The two new fields, `AI_Hazard_Category` and `AI_Human_Factors_Category`, live directly on `dbo.FormData_Master`.

## How It Works

**Taxonomy as data, not code.** `taxonomy.json` holds every label's definition, keyword triggers, disambiguation guidance, and the precedence rules that resolve overlapping cases (e.g. "Major Accident Hazard overrides everything," "stated cause beats described act" for Human Error vs. Risk-Taking Behaviour). It can be retuned without a code deploy.

**Classification via Azure AI Foundry Agent.** An Agent (`EnQuestObservationClassifier`), configured in the Foundry portal, receives the concatenated `Hazard_Description + Action_Taken` text for one card and returns a label and confidence (High/Medium/Low) for each dimension. The full taxonomy prompt lives in the Agent's portal-configured Instructions field — this project's Agent type doesn't accept per-call instruction overrides, so the portal is the single source of truth for classification behaviour. `agent_setup.py` prints the current instructions (generated from the taxonomy file) for pasting in whenever the taxonomy changes.

**Confidence-driven retry.** If either dimension comes back Low confidence, the whole card is re-classified up to two extra times. A card is never left unclassified over confidence alone — the best result is always persisted. Any dimension still Low after the retry budget is exhausted is written to a lightweight review log (`dbo.AI_Classification_Review_Log`) rather than cluttering the main schema, so it can be triaged by a human during the pilot without needing to touch every row.

**Idempotent, resumable execution.** One shared function, `classify_observations()`, backs both entry points:
- `backfill.py` — on-demand run for the historical dataset, with `--force` (reclassify everything) and `--concurrency` (tune parallel Agent calls) options.
- `main.py` — the daily scheduled webjob, which by default only processes cards where both AI fields are still `NULL`.

Re-running either is always safe: already-classified cards are skipped unless `--force` is used.

## Data You Now Have

For (eventually) every historical and new BBSS card:
- A consistent, structured Hazard label — independent of whether the reporter picked an LSR category, marked it Not Applicable, or left it blank.
- A consistent, structured Human Factors label — capturing *why* an unsafe condition or behaviour occurred, not just *what* was observed.
- A confidence signal per dimension, with unresolved Low-confidence cases already flagged in a dedicated review table.

This is a level of structure the raw free-text `Hazard_Description`/`Action_Taken` fields never had — every card is now queryable by hazard type and human factor, not just by the fields a reporter happened to fill in.

## Ways to Analyse This Data

- **Hazard Wheel distribution** — volume of cards per Hazard label, sliced by Facility, Company, Department, or time period. Surfaces which energy sources dominate observations at each site.
- **Human Factors Pareto** — which human/organisational factors show up most often, and whether that shifts by shift pattern, contractor, or work area.
- **Cross-tabulation** — Hazard × Human Factors together (e.g. "Gravity hazards driven by Planning/Workload & Time Pressure" vs. "driven by Equipment/Tools & Workplace Design") to identify the *combination* that's actually driving risk, not just the hazard alone.
- **Trend over time** — rolling weekly/monthly counts per label to catch emerging patterns before they become incidents, and to measure whether interventions (toolbox talks, procedure updates) actually move the numbers.
- **Correlation with existing fields** — Risk_Level, Safe/Unsafe, Card_Type, Company_Name — e.g. do High-risk cards cluster around specific Hazard or Human Factors labels; do certain companies/contractors show a distinct profile.
- **LSR field coverage check** — compare the AI Hazard label against the existing manually-selected "Type of Hazard" field to spot systemic gaps in that separate, already-in-progress workstream (without altering that field).
- **Review log as a quality signal** — tracking review-log volume over time is itself a useful metric: a rising Low-confidence rate on a particular label pair is a signal the taxonomy or prompt needs retuning, not just that individual cards need review.

## Potential Future Uses

**Dashboard.** The two new fields, joined with existing metadata already on `FormData_Master` (Facility, Facility_Area, Company_Name, Risk_Level, Submission_Date), are dashboard-ready as-is — no further data engineering needed. A Power BI (or similar) dashboard could offer: an Energy Wheel heatmap by facility, a Human Factors Pareto with drill-down to source cards, trend lines per label, and a review-queue view surfacing Low-confidence cards for human triage.

**Agentic email nudges.** Because classification already runs as a daily scheduled job, a natural extension is a second lightweight step after each run that compares the day's/week's distribution against a rolling baseline and proactively emails relevant HSE leads when something moves — e.g. a spike in a specific Hazard/Human Factors combination at a facility, or a Company/contractor trending toward Risk-Taking & Compliance Behaviour more than their historical norm. This could reuse the same Foundry Agent Service infrastructure (a summarisation/insight-generation agent reading the day's classified cards) rather than hand-written threshold rules, so the nudge includes a plain-English explanation, not just a number.

**Safety-critical alerting.** Distinct from routine trend nudges: any card classified Major Accident Hazard could trigger a near-real-time notification to safety leadership, independent of the daily batch cadence, given the severity that label represents.

**Coaching/training recommendations.** Human Factors trends at a facility or company level could feed a recommendation loop — e.g. a facility trending high on Fatigue & Fitness for Duty gets a suggested toolbox talk topic, rather than someone having to notice the pattern manually.

**Review-log-driven taxonomy improvement.** The review log isn't just a triage queue — corrections made there during the pilot are the natural feedback source for retuning `taxonomy.json`'s keyword libraries and precedence rules over time.

## Recommended Next Steps

1. Complete the full historical backfill, then let the daily webjob run for a few weeks to build up a trend baseline.
2. Review the confidence-retry and review-log volumes from that period to judge whether the taxonomy needs retuning before building anything on top of the data.
3. Scope the dashboard first (lowest effort, immediate value, no new infrastructure) before the agentic nudge/alerting ideas, which need their own design pass (recipients, thresholds, tone of the email, false-positive tolerance).
