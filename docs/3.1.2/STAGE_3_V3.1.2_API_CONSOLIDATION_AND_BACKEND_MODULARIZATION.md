STAGE_3_V3.1.2_API_CONSOLIDATION_AND_BACKEND_MODULARIZATION.md
1. Summary

This stage reorients the v3.1.2 plan toward the real architectural objective of the project:

consolidate the active API surface on v3

migrate or replace any still-needed v1 behavior

modularize the current v3_inventories.py router properly

remove src/api/routes/jobs.py

remove src/api/routes/entities.py

Stage 2 established that those two v1 route modules still had consumers, so they could not be safely deleted.
Therefore, Stage 3 is the controlled migration stage that removes those dependencies first, and only then retires the legacy modules.

This stage is not primarily about DB renaming.
It is about API consolidation, backend modularization and legacy route retirement.

2. Main objective

Move the remaining relevant API behavior from the legacy v1 route surface into the v3 API surface and reorganize the backend routing structure so that:

v3_inventories.py is no longer a monolithic router file

v3 becomes the only supported HTTP API surface for the inventory workflow

legacy route modules jobs.py and entities.py are no longer needed

frontend and tests stop depending on v1 route modules

3. End-state expected after this stage

At the end of this stage, the desired state is:

src/api/routes/v3_inventories.py no longer exists as a large monolithic file, or becomes a thin composition layer only

v3 inventory routes are split into clear modules

src/api/routes/jobs.py is removed

src/api/routes/entities.py is removed

frontend clients no longer consume v1 entities endpoints

backend tests no longer require v1 routes

the active API contract is fully expressed through /api/v3/inventories/...

4. Out of scope

This stage should not:

perform broad database renaming

remove legacy DB tables unless they become fully unreachable and explicitly approved

redesign the product UX

introduce unrelated business features

perform a broad backend cleanup outside the routing/API consolidation objective

5. Architectural intent

The key architectural rule for this stage is:

All actively supported inventory workflow API behavior must live in v3, under a modular backend route structure.

That means the v1 route surface should stop being the place where:

entities are listed

evidence is fetched

reviews are submitted

audits are consulted

legacy job state is exposed as an active product surface

If some of those concepts are still needed, they must be:

recreated in v3

mapped to existing v3 domain concepts

consumed by frontend and tests through v3

Only after that can the legacy route modules disappear.

6. Stage breakdown
Phase 1 — Define the target v3 API surface
Objective

Design the final v3 route surface that will replace the remaining useful v1 behavior.

Tasks

inspect current v3 routes in v3_inventories.py

inspect current v1 routes in jobs.py and entities.py

determine which v1 behaviors are still truly needed

map each retained behavior to a v3 route design

explicitly decide what will:

migrate to v3

be dropped

be replaced by existing v3 endpoints

define the final route contract for the supported product flow

Required output

A route migration map:

Legacy route	Current consumer	Decision	Target v3 route / replacement
Done criteria

There is a clear target API surface before implementation begins.

Phase 2 — Design the modular router structure
Objective

Break the current v3 route implementation into coherent modules.

Intent

v3_inventories.py should stop being the single large file that owns all v3 routing behavior.

Tasks

Define a target modular structure, for example:

src/api/routes/v3/inventories.py

src/api/routes/v3/inventory_assets.py

src/api/routes/v3/inventory_positions.py

src/api/routes/v3/inventory_reviews.py

src/api/routes/v3/inventory_jobs.py

src/api/routes/v3/router.py

Or another equivalent structure that is cleaner and consistent.

The exact split should be based on domain responsibilities, not arbitrary line count.

Responsibilities to separate

Potential route concerns to isolate:

inventory creation / listing / detail

asset upload and asset retrieval

job/process status

positions

evidence / previews

reviews

reports / exports if applicable

Done criteria

A target backend router structure is defined and justified.

Phase 3 — Implement v1 → v3 behavior migration
Objective

Move or recreate the remaining required v1 behaviors inside the v3 surface.

High-priority migration targets

Based on Stage 2 findings, the first likely target is:

GET /api/v1/inventory/jobs/{job_id}/entities

because it still has a confirmed frontend consumer.

Other v1 routes that may need migration or replacement depending on test/product value:

GET .../entities/{entity_uid}/evidence

POST .../entities/{entity_uid}/review

GET .../entities/{entity_uid}/audit

The legacy job endpoints should be evaluated carefully:

if they are only test-driven legacy surface, they may be retired after tests migrate

if they are still needed operationally, their supported equivalent should exist in v3

Tasks

implement the necessary v3 endpoints or adapt existing ones

make sure response shapes are coherent with current v3 models

avoid blindly copying v1 contracts if v3 already has a better domain model

keep response naming/domain consistent with positions/reviews/evidence concepts

Done criteria

All still-needed v1 behaviors have a v3 replacement or explicit removal decision.

Phase 4 — Migrate frontend consumers
Objective

Stop the frontend from consuming v1 route modules.

Tasks

replace getJobEntities usage with v3 clients

update API client modules

update query keys if needed

update hooks/pages/components consuming legacy responses

align frontend types with the final v3 contract

remove frontend references to /api/v1/inventory/jobs/...

Done criteria

The frontend no longer depends on entities.py or jobs.py.

Phase 5 — Migrate and update tests
Objective

Remove backend test dependency on v1 route modules.

Tasks

identify tests that hit v1 endpoints

decide whether each test should:

migrate to v3 endpoint assertions

be removed because it only validates retired legacy behavior

be rewritten around the new modular router structure

update integration/e2e expectations

make the test suite validate the new v3-supported API surface

Done criteria

Tests no longer require jobs.py or entities.py to exist.

Phase 6 — Remove legacy route modules
Objective

Delete the v1 route modules once they have no remaining supported consumers.

Target removals

src/api/routes/jobs.py

src/api/routes/entities.py

Preconditions

Before deletion, confirm:

no frontend consumer remains

no active backend test depends on them

no route registration still references them

no documented supported product flow depends on them

Tasks

remove router registration

delete files

remove dead imports

remove dead schemas/helpers if they become unreachable

remove dead route-specific response models if no longer used

validate app boot and OpenAPI registration

Done criteria

Both legacy route modules are removed cleanly.

Phase 7 — Finalize modular v3 routing structure
Objective

Ensure the v3 routing layer is clean after migration.

Tasks

make v3_inventories.py either:

fully removed in favor of smaller modules, or

reduced to a tiny composition layer only

ensure route modules are grouped by responsibility

validate imports and prefixes

document the new routing structure

ensure no monolithic router remains

Done criteria

The routing layer is modular and maintainable.

7. Recommended target structure

A suggested target could look like this:

src/api/routes/
  v3/
    __init__.py
    router.py
    inventories.py
    assets.py
    jobs.py
    positions.py
    reviews.py
    evidence.py
    reports.py

Or, if you prefer more explicit naming:

src/api/routes/
  v3/
    __init__.py
    router.py
    inventory_root.py
    inventory_assets.py
    inventory_jobs.py
    inventory_positions.py
    inventory_reviews.py
    inventory_evidence.py

The important thing is not the exact filenames, but that:

responsibilities are separated

the route surface is coherent

v1 modules disappear

8. Risks
Risk 1 — Migrating v1 contracts too literally

If v1 responses are copied as-is into v3, the result may preserve legacy design instead of consolidating the domain.

Mitigation: map concepts to v3 domain language, not just path-by-path copying.

Risk 2 — Breaking frontend while moving entities flow

The frontend still has at least one known v1 dependency.

Mitigation: migrate client + types + query keys in the same change set.

Risk 3 — Tests preserve legacy forever

If tests are not updated, they will block retirement of old modules indefinitely.

Mitigation: explicitly migrate or retire tests tied only to deprecated surface.

Risk 4 — Half-migrated router architecture

If new v3 modules are introduced but old monolithic routing remains as source of truth, the system becomes more confusing.

Mitigation: define the final router ownership clearly before implementation.

9. Acceptance criteria

This stage is complete only if:

the target v3 surface replacing relevant v1 behavior is defined

frontend no longer consumes v1 entities/jobs routes

tests no longer require jobs.py or entities.py

jobs.py is removed

entities.py is removed

v3_inventories.py is modularized correctly

route registration works through the new modular structure

backend boots and main flows remain operational

10. Recommended deliverables

At the end of this stage, the project should contain:

code changes implementing the consolidation

a migration report:

STAGE_3_V3.1.2_API_CONSOLIDATION_REPORT.md

an optional route map:

V3_ROUTE_SURFACE_FINAL.md

11. Recommendation on plan order after this stage

Once this stage is complete, the plan should continue as:

Stage 4 — DB Normalization

Stage 5 — Backend Optimization

Stage 6 — Job Cancellation

Stage 7 — Frontend Reorganization / Cleanup

Stage 8 — Validation and Closure

Because by then the supported API surface will already be properly consolidated.