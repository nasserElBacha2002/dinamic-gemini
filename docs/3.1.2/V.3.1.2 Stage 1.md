# **STAGE\_1\_V3.1.2\_TECHNICAL\_AUDIT.md**

## **1\. Summary**

This stage defines the **technical audit** for Dinamic Inventory v3.1.2.

Its purpose is to create a precise and actionable picture of the current state of the system before starting cleanup, renaming, reorganization and optimization work.

This stage does **not** implement structural changes yet.  
Its goal is to reduce risk and ensure that later refactors are based on evidence instead of assumptions.

---

## **2\. Main objective**

Identify, classify and document:

* active vs legacy backend code  
* active vs obsolete database tables  
* active vs legacy frontend modules  
* duplicated code paths  
* current backend → frontend contract usage  
* response inefficiencies  
* structural issues in backend and frontend directories  
* current job lifecycle limitations, especially around cancellation

---

## **3\. Expected outputs of the audit**

At the end of this stage, the team should have:

1. A validated inventory of active backend routes and modules  
2. A list of backend artifacts that can likely be removed  
3. A validated inventory of active and obsolete DB tables  
4. A proposed mapping from current `v3_*` tables to final domain names  
5. A frontend inventory showing active and legacy screens/components/types/clients  
6. A contract map of backend responses vs actual frontend usage  
7. A duplication report for backend and frontend  
8. A structural reorganization proposal for backend and frontend  
9. A technical note about how job cancellation should integrate with the existing lifecycle  
10. A prioritized implementation backlog for Stages 2–9

---

## **4\. Out of scope**

This stage should **not**:

* delete code  
* rename tables  
* move folders  
* change DTOs  
* optimize queries  
* implement cancellation  
* modify business behavior

Only audit, classify, document and recommend.

---

## **5\. Workstreams inside Stage 1**

The audit will be divided into 7 workstreams:

1. Backend route and module audit  
2. Database schema audit  
3. Frontend structure audit  
4. Backend ↔ frontend contract audit  
5. Duplication audit  
6. Directory structure audit  
7. Job lifecycle and cancellation audit

---

# **6\. Operational breakdown**

---

# **Workstream 1 — Backend route and module audit**

## **Objective**

Understand exactly which backend routes, handlers, services, repositories and DTOs are active, deprecated, duplicated or unused.

## **Tasks**

### **1.1 Inventory all backend routes**

* List every registered route.  
* Group them by domain/module.  
* Mark HTTP method, path and response type.  
* Identify whether each route is:  
  * active  
  * deprecated  
  * legacy  
  * unclear

### **1.2 Trace route consumers**

* Determine which frontend screens/hooks/clients call each route.  
* Detect routes with no known consumer.  
* Detect internal backend-only routes or utility flows.

### **1.3 Audit handlers/controllers**

* For each active route, identify the entry handler/controller.  
* Detect handlers no longer referenced by any active route.  
* Mark handlers with overlapping responsibilities.

### **1.4 Audit services/use cases**

* Trace each active handler to its service/use-case layer.  
* Detect services that are:  
  * active  
  * partially active  
  * duplicated in responsibility  
  * unused

### **1.5 Audit repositories/adapters**

* Identify repositories and adapters used by the active backend.  
* Detect storage/data-access layers no longer used.  
* Mark any legacy compatibility adapters.

### **1.6 Audit DTOs/schemas/mappers**

* List request/response schemas.  
* Detect DTOs no longer referenced.  
* Identify multiple DTOs representing almost the same concept.  
* Mark mapping utilities that can later be consolidated or removed.

## **Deliverables**

* backend route inventory  
* handler/service/repository dependency map  
* list of likely removable backend artifacts  
* unclear artifacts list requiring manual confirmation

## **Done criteria**

* every route is classified  
* every active route has a known consumer or justification  
* unused or suspicious backend modules are documented

---

# **Workstream 2 — Database schema audit**

## **Objective**

Identify which tables belong to the active architecture, which are obsolete, and which should be renamed.

## **Tasks**

### **2.1 Inventory all tables**

* List all current DB tables.  
* Group them by business/domain responsibility.  
* Mark current naming pattern.

### **2.2 Classify tables**

For each table, determine whether it is:

* actively used  
* legacy but still present  
* transitional  
* unclear

### **2.3 Trace data usage from backend**

* Map repositories/queries/models to actual tables.  
* Detect tables with no active access path.  
* Detect tables referenced only by legacy modules.

### **2.4 Identify version-based naming**

* Find all tables using `v3`, version prefixes or transitional technical names.  
* Propose domain-based replacement names.

### **2.5 Review schema consistency**

* Review foreign keys, constraints and index naming.  
* Detect naming inconsistencies.  
* Detect conceptual duplication across tables.

### **2.6 Flag migration risks**

* Identify tables with sensitive rename/delete impact.  
* Mark tables requiring migration sequencing or data preservation care.

## **Deliverables**

* DB inventory and classification report  
* list of obsolete tables  
* list of `v3_*` or equivalent technical names  
* draft target naming proposal  
* migration risk notes

## **Done criteria**

* every active table is mapped to current code usage  
* likely obsolete tables are identified  
* all version-based names are documented

---

# **Workstream 3 — Frontend structure audit**

## **Objective**

Identify which frontend modules are active, which are legacy, and where structural problems or redundancies exist.

## **Tasks**

### **3.1 Inventory top-level frontend structure**

* List pages, features, components, hooks, services, types and stores.  
* Group by folder/module.

### **3.2 Identify active product flows**

* Determine which screens and flows are currently used in the product.  
* Mark screens/components that appear obsolete, transitional or disconnected.

### **3.3 Audit API clients and service layers**

* List current frontend API clients.  
* Detect duplicated clients or inconsistent endpoint access patterns.  
* Detect clients still pointing to old backend structures.

### **3.4 Audit types and models**

* List major frontend DTOs/types/interfaces.  
* Detect repeated or overlapping type definitions.  
* Identify outdated types tied to removed or legacy routes.

### **3.5 Audit hooks and shared components**

* Identify hooks with overlapping behavior.  
* Detect components that appear duplicated or too similar.  
* Mark components that are shared vs feature-specific.

## **Deliverables**

* frontend inventory report  
* active vs legacy frontend map  
* candidate list for frontend cleanup  
* candidate list for future folder reorganization

## **Done criteria**

* major frontend areas are classified  
* probable legacy UI/client/type artifacts are documented  
* structural pain points are identified

---

# **Workstream 4 — Backend ↔ frontend contract audit**

## **Objective**

Compare what the backend sends with what the frontend actually consumes.

## **Tasks**

### **4.1 Inventory API responses**

* List key endpoints used by the frontend.  
* Capture their current response shapes.  
* Separate summary endpoints from detail endpoints where applicable.

### **4.2 Trace frontend field usage**

* For each key response, identify which fields are actually consumed in the frontend.  
* Detect fields received but never used.  
* Detect nested objects only partially consumed.

### **4.3 Detect redundant payload design**

* Identify duplicated fields across the same response.  
* Identify repeated data represented in multiple nested objects.  
* Detect over-fetching patterns.

### **4.4 Identify contract ambiguity**

* Detect response fields with confusing names.  
* Detect multiple endpoints returning the same concept with different shapes.  
* Detect opportunities for clearer summary/detail separation.

### **4.5 Flag performance candidates**

* Identify endpoints where payload size or nested serialization seems excessive.  
* Flag routes to review in Stage 5\.

## **Deliverables**

* contract map backend → frontend  
* payload usage matrix  
* unused field list  
* response optimization candidate list

## **Done criteria**

* key frontend-consumed endpoints are mapped  
* actual field usage is known  
* payload inefficiencies are documented

---

# **Workstream 5 — Duplication audit**

## **Objective**

Identify meaningful duplication in backend and frontend before refactoring.

## **Tasks**

### **5.1 Backend duplication audit**

Review duplication in:

* validation logic  
* mapping logic  
* response assembly  
* repository/query access  
* job status handling  
* error handling  
* utility functions

### **5.2 Frontend duplication audit**

Review duplication in:

* components  
* hooks  
* transforms/selectors  
* table/detail views  
* loading/error handling  
* repeated API consumption logic  
* repeated type definitions

### **5.3 Classify duplication**

For each duplicated case, classify as:

* safe to consolidate  
* requires design decision  
* acceptable duplication  
* unclear

### **5.4 Estimate impact**

* high impact / easy win  
* high impact / risky  
* low impact / easy  
* low impact / not worth in v3.1.2

## **Deliverables**

* duplication report  
* prioritized duplication backlog  
* recommendation list for later consolidation

## **Done criteria**

* duplicated areas are documented with enough detail to act later  
* priority level is assigned

---

# **Workstream 6 — Directory structure audit**

## **Objective**

Identify how current folder organization differs from the desired architectural model.

## **Tasks**

### **6.1 Audit backend structure**

* Review current tree.  
* Detect mixed responsibilities.  
* Detect temporary/transitional folders.  
* Detect modules that should live elsewhere.

### **6.2 Audit frontend structure**

* Review current tree.  
* Detect poor separation between shared and feature-specific code.  
* Detect inconsistent module grouping.  
* Detect folders reflecting old implementation history.

### **6.3 Propose target structures**

* Draft desired backend structure.  
* Draft desired frontend structure.  
* Keep proposals realistic and incremental.

### **6.4 Flag reorg risks**

* Identify high-risk moves.  
* Identify modules with many import dependencies.  
* Note where reorg should be delayed until backend stabilization.

## **Deliverables**

* backend structure audit note  
* frontend structure audit note  
* proposed target tree for both layers  
* risk notes for future reorganization

## **Done criteria**

* current structural problems are documented  
* target reorganization direction is clear enough to plan later stages

---

# **Workstream 7 — Job lifecycle and cancellation audit**

## **Objective**

Understand the current lifecycle of jobs and define where cancellation can be integrated safely.

## **Tasks**

### **7.1 Document current job lifecycle**

* Identify all current job states.  
* Trace how state transitions occur.  
* Identify where state is persisted.  
* Identify which layer controls job status.

### **7.2 Identify long-running stages**

* Map the main execution pipeline.  
* Identify stages likely to block for too long.  
* Detect places where cancellation checks could be inserted later.

### **7.3 Review timeout behavior**

* Check whether any timeout policy exists today.  
* Detect implicit timeout assumptions.  
* Identify missing safeguards.

### **7.4 Review current frontend visibility**

* Determine what the frontend currently knows about job state.  
* Identify what extra fields/statuses would be needed later.

### **7.5 Draft cancellation strategy recommendation**

* Propose cooperative cancellation approach.  
* Suggest likely new states:  
  * `cancel_requested`  
  * `canceled`  
  * `timed_out`  
* Suggest safe checkpoint model.

## **Deliverables**

* current lifecycle document  
* cancellation integration note  
* timeout gap analysis  
* recommended future state model

## **Done criteria**

* current job lifecycle is clearly documented  
* cancellation integration points are identified  
* the next stage can implement cancellation with low ambiguity

---

# **7\. Audit artifacts to produce**

At the end of Stage 1, the following files/documents should exist:

1. `AUDIT_BACKEND_V3.1.2.md`  
2. `AUDIT_DATABASE_V3.1.2.md`  
3. `AUDIT_FRONTEND_V3.1.2.md`  
4. `AUDIT_API_CONTRACTS_V3.1.2.md`  
5. `AUDIT_DUPLICATION_V3.1.2.md`  
6. `AUDIT_STRUCTURE_V3.1.2.md`  
7. `AUDIT_JOB_LIFECYCLE_V3.1.2.md`  
8. `STAGE_1_FINDINGS_SUMMARY_V3.1.2.md`

---

# **8\. Prioritization model for findings**

Every finding in Stage 1 should be classified with:

## **Severity**

* High  
* Medium  
* Low

## **Type**

* Legacy removal  
* Rename  
* Reorganization  
* Duplication  
* API contract improvement  
* Performance  
* Job lifecycle  
* Unclear/manual review needed

## **Actionability**

* Immediate for next stage  
* Requires technical decision  
* Informational only

---

# **9\. Final summary document structure**

The final summary of Stage 1 should contain:

## **A. Executive summary**

* what was found  
* major technical debt areas  
* biggest risks  
* biggest easy wins

## **B. Backend findings**

* routes  
* modules  
* DTOs  
* repositories

## **C. Database findings**

* active tables  
* obsolete tables  
* rename candidates

## **D. Frontend findings**

* active areas  
* legacy areas  
* structural issues

## **E. Contract findings**

* duplicated fields  
* unused fields  
* over-fetching  
* unclear DTO shapes

## **F. Duplication findings**

* backend duplication  
* frontend duplication  
* priority ranking

## **G. Structure findings**

* backend reorg proposal  
* frontend reorg proposal

## **H. Job lifecycle findings**

* current states  
* cancellation gaps  
* timeout gaps

## **I. Recommended execution order for Stages 2–9**

---

# **10\. Stage 1 acceptance criteria**

Stage 1 is complete when:

* active and legacy backend routes are classified  
* active and obsolete DB tables are classified  
* active and legacy frontend areas are classified  
* key API responses are mapped to real frontend usage  
* major duplication areas are documented  
* backend and frontend structural problems are documented  
* current job lifecycle and cancellation gaps are documented  
* a prioritized backlog exists for the next stages

---

# **11\. Recommended execution strategy**

This audit should be executed in the following order:

1. backend route/module audit  
2. database schema audit  
3. frontend structure audit  
4. backend/frontend contract audit  
5. duplication audit  
6. structure audit  
7. job lifecycle audit  
8. final summary and prioritization

This order reduces ambiguity because:

* backend and DB establish the technical truth  
* frontend and contracts are interpreted against that truth  
* duplication and reorganization are easier to assess once the active surface is known

---

# **12\. Suggested next artifact after Stage 1**

Once this stage is complete, the next document to generate should be:

**`STAGE_2_V3.1.2_BACKEND_LEGACY_CLEANUP_PLAN.md`**

built only from validated findings, not assumptions.

---

