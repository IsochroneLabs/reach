# Team & Course-Management Decisions

Companion to `architecture_proposal.md` (technical decisions D1-D21) and `features.md` (features and roadmap). This file holds everything that is about the team, the course requirements and the supervisors rather than about the system itself.

Course context: DS500 Data Science Project, WT 2026/27. Evaluation is **individual**: the brief says each member's contribution to the project and to the presentations is considered. Two presentations (interim and final), a 3-minute video, a 3-sentence summary, code access, database access for supervisors, and a hosted interface are required.

**How to use this file:** discuss each item as a team, write the decision and date into the log (Section 9), and revise the recommendation if the team disagrees. Items marked **[ASK]** need an answer from the supervisors (Section 7).

---

## 1. Decisions Overview

| # | Decision | Options | Recommendation | Owner | Settled by |
| --- | --- | --- | --- | --- | --- |
| T1 | **Contribution tracking** (do we keep a contributions table?) | None, rely on git history; a maintained contributions table; table plus GitHub conventions | Table plus conventions. Git history alone is a weak signal (commit counts, pair work, refactors), and grading is individual, so make each person's work visible on purpose. See Section 2. | Whole team | 4 Nov |
| T2 | **Roles and ownership split** | Everyone does everything; owners per component | One owner and one reviewer per component. Every person owns at least one technically substantial, demonstrable piece, and no component has only one person who understands it. See Section 3. | Whole team | 4 Nov |
| T3 | **Presentation allocation** (interim 25 Nov, final 29 Jan) | Ad hoc; planned split | Every member presents a part that matches their owned component, so contributions are visible in the room as well as in the repo. Rehearse with Q&A. See Section 4. | Whole team | 18 Nov (interim), 8 Jan (final) |
| T4 | **Complexity and novelty argument** (grading criterion 1) | Leave implicit; write it down once and reuse | Write a one-paragraph claim, checked by every member, and reuse it in README, slides and video. See Section 5. | Doc owner | 18 Nov |
| T5 | **Motivation and literature outline** | Minimal; structured | Short structured outline (problem, relevance, key references, gap, our contribution). The brief gives literature low weight, so keep it brief but present. See Section 6. | Doc owner | 18 Nov |
| T6 | **Calendar and internal deadlines** | Only course dates; plus internal buffers | Add internal deadlines at least three days before every course deadline. See Section 8. | Whole team | 4 Nov |
| T7 | **Supervisor questions** **[ASK]** | Decide alone; ask first | Ask early, in one message, before the decisions that depend on the answers are frozen. See Section 7. | One person sends | Before 4 Nov |
| T8 | **Communication, meetings and decision log** | Ad hoc; fixed cadence | One chat channel, one weekly meeting with notes, and a decision log (Section 9) kept in the repository so decisions and their reasons survive. | Whole team | 4 Nov |
| T9 | **Video and 3-sentence summary** | Last-minute; planned | Assign an owner now, draft the summary when Core scope is frozen, storyboard the video by early January, record after the deployed app is stable. Target audience is a non-technical manager. | Video owner | Plan 18 Nov, record by 17 Jan |
| T10 | **Risk register and fallbacks** | None; short register | Short register reviewed weekly (Section 10). | Whole team | 4 Nov |

---

## 2. Contributions Table (T1)

**Why:** the brief evaluates individuals. A table that is maintained from the start avoids reconstructing contributions at the end, and gives the supervisors a clear overview.

**Proposed rules**

- Every component has one **owner** and one **reviewer**. Owners write the main part; reviewers read it, run it and approve pull requests.
- Every pull request has an author and at least one reviewer who is not the author.
- Pair work is declared in the commit message (`Co-authored-by:`) so it counts for both people.
- Issues are assigned to a person. Work done outside git (analysis, meetings with supervisors, data checks, writing) is added to the table by hand.
- The table is reviewed in the weekly meeting and corrected by whoever disagrees with it.
- Commit counts and lines of code are **not** used as the measure; the table describes who built and understands what.

**Template** (`CONTRIBUTIONS.md` in the repository)

| Component | Owner | Reviewer | Main deliverables | Status | Notes |
| --- | --- | --- | --- | --- | --- |
| Data ingestion and validation | | | OSM/GTFS/Zensus download, checks, report | | |
| Routing and accessibility counting | | | G1 test, counting method, batch baseline | | |
| Scoring and spatial statistics | | | Scoring spec, deficit index, Moran's I / hot spots | | |
| Recommender and validation experiments | | | Greedy solver, exact comparison, back-test, sensitivity | | |
| API and database | | | Schema, endpoints, job queue | | |
| Frontend and visualization | | | Maps, scorecards, recommender views | | |
| Deployment and automation | | | bwCloud, Compose, scheduled refresh, D20 test | | |
| Documentation | | | README, scoring spec, data dictionary, architecture | | |
| Presentation, video, summary | | | Slides, video, 3-sentence summary | | |

---

## 3. Roles and Ownership (T2)

With 2-4 people, several components go to one person. Check these rules when assigning:

1. Every person owns something that can be shown and explained alone in the final presentation (for example: the counting pipeline, the recommender, the web app).
2. The reviewer role cross-trains: the reviewer must be able to explain the component in the Q&A.
3. Hard, risky parts (routing/terrain test G1, recommender) are not owned by the same person.
4. Documentation is shared: each owner writes the README section for their component; one person integrates and checks it.
5. If a member leaves or is unavailable, the reviewer takes over. Write down who that is.

**Open question for the team:** team size and strengths. Fill in names against the template above and note where one person carries more than one component.

---

## 4. Presentations (T3)

| Presentation | Date | Required content (from the brief) | Our plan |
| --- | --- | --- | --- |
| Interim | 25 Nov 2026, 14:00-18:00, SR209 | The plan and first steps | Problem and relevance, literature gap, chosen region and decisions made (D-table), G1 result, first ingestion and baseline map, plan for the rest |
| Final | 29 Jan 2027, 9:00-14:00, SR209 | Completed project, central structure of the code, architecture, how users interact, discussion with questions | Motivation, architecture walk-through, live demo, validation results, limits, lessons learned |

Allocation table to fill in:

| Part | Speaker | Backup |
| --- | --- | --- |
| Motivation, relevance, literature | | |
| Method and scoring | | |
| Architecture and automation | | |
| Demo | | |
| Validation and results | | |
| Limits and next steps | | |

Note that the course requires attendance at all sessions. Slides for the final presentation are due 28 Jan, 20:00, after the code submission on 22 Jan.

---

## 5. Complexity & Novelty Claim (T4)

The brief grades "how complex are the components" and "how novel are the problem and the solution". Draft claim for the team to challenge and edit:

- **Complexity:** an automated, multi-source pipeline (street graph, scheduled public transport timetables, population grid), network-based accessibility measurement for several disaggregated service categories, a documented scoring specification, and a location-optimization component with a defined objective and an exact-solver comparison.
- **Novelty:** the paper (Mouratidis, 2026) provides a measurement and spatial-analysis methodology applied manually to Copenhagen. We add full automation, application to a German region with German open data, and a prescriptive layer that recommends where new facilities help most, validated by back-testing and sensitivity analysis.
- **What we do not claim:** a new theory of accessibility, or planning-ready recommendations (zoning, parcels, capacity are out of scope).

**Team task:** replace anything above that the final implementation does not support, and add the technical difficulties we actually solved.

---

## 6. Motivation & Literature Outline (T5)

Structure for slides and README:

1. **Problem:** car dependence and uneven access to everyday services; the 15-minute city as a planning idea.
2. **Relevance:** planners need to know where access is lacking and where an added facility would help most.
3. **Key literature** (from the reference list of Mouratidis, 2026; check each entry before citing):
   - Moreno et al. (2021), introducing the 15-minute city
   - Mouratidis (2024), seven pitfalls of the 15-minute city
   - Mouratidis (2026), the GIS methodology we build on
   - Logan et al. (2022) and Staricco (2022) on x-minute accessibility with disaggregated facilities
   - Willberg et al. (2023) on individual and temporal variation in walking accessibility
   - Calafiore et al. (2022) and Knap et al. (2023) on spatial analysis and equity
4. **Gap:** existing work mostly measures; automation and prescriptive placement are rare.
5. **Our contribution and its limits:** see Section 5.

---

## 7. Questions for the Supervisors [ASK] (T7)

Send as one message; the answers affect technical decisions in `architecture_proposal.md`.

1. Is Topic 9 confirmed for our team, and who is our supervisor?
2. **Modes (D18):** is a walking-only Core acceptable, given that the topic text says "walk or bicycle ride"?
3. **Analysis method (D19):** is optimization plus spatial statistics (Moran's I, hot spots) an adequate "traditional statistics or machine learning" component, or do you expect a statistical or ML model?
4. **Scale:** is one well-validated region sufficient, or is a larger coverage expected?
5. **Hosting (D13):** which bwCloud flavors and quota are available to us, and how do graders access the hosted app and the database?
6. **Individual evaluation (T1):** what evidence of individual contribution do you want (contributions table, git history, presentation parts)?
7. **Compute:** may we use bwUniCluster for optional large runs?
8. **Validation data (D5):** are there authoritative facility data you suggest for checking OSM completeness?
9. **Interim presentation:** how long is it, and what level of results do you expect on 25 Nov?
10. **Video and summary:** any format requirements beyond the brief?

---

## 8. Calendar (T6)

| Date | Event | Source |
| --- | --- | --- |
| Wed 4 Nov 2026, 9:00-13:00 | Workshop "Presentation Skills", SR331 (mandatory) | Course schedule |
| Before 4 Nov | Send supervisor questions; first team meeting; decision round 1 | Internal |
| Wed 25 Nov 2026, 14:00-18:00 | Interim presentation, SR209 (mandatory) | Course schedule |
| 22 Nov | Interim slides ready, rehearsal done | Internal |
| Fri 22 Jan 2027, 23:59 | Submission: code access, hosted interface, video, summary (all except slides) | Course schedule |
| 19 Jan | Internal freeze: everything deployed and tested, D20 reproducibility run done | Internal |
| Thu 28 Jan 2027, 20:00 | Submission of final slides | Course schedule |
| Fri 29 Jan 2027, 9:00-14:00 | Final presentation, SR209 (mandatory) | Course schedule |

Times may change depending on the number of participants, according to the brief; check the course page regularly.

---

## 9. Decision Log

Record every decision from this file and from `architecture_proposal.md` here, so the reasons survive.

| Date | ID | Decision | Reason | Decided by | Revisit if |
| --- | --- | --- | --- | --- | --- |
| | | | | | |

---

## 10. Risk Register (T10)

| Risk | Early signal | Fallback |
| --- | --- | --- |
| Terrain handling does not change walking time (G1) | G1 test shows identical catchments | Time-based slope function on our own graph, or drop terrain mode and keep it as a documented limitation |
| OSM data too incomplete for a category (GPs especially) | Low recall against the authoritative list | Report the gap openly; drop or mark the category as low-confidence; use official data for that category |
| Zensus grid lacks age data at 100 m | D7 check fails | Total-population demand only |
| bwCloud VM too small for the routing engine and database | Out-of-memory during deployment test | Pre-compute results, serve static tiles, reduce live isochrones |
| Counting at scale takes too long | Batch run exceeds a day on one region | Facility-side counting, smaller region, use the cluster |
| Team member unavailable | Missed deadlines, silence | Reviewer takes over (T2); cut stretch items first |
| Scope grows | Core not done by feature freeze | Cut list in `features.md`, Section 8 |
| README is incomplete when a non-author runs it (D20) | Test fails | Fix README, rerun, repeat before submission |
