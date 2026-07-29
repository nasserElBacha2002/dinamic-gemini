/**
 * Resolve which run the Aisle Results UI should treat as "browse selection".
 *
 * Precedence (never `jobs[0]`):
 * 1. Explicit URL `jobId` when present in the jobs list
 * 2. `operational_job_id` when present in the jobs list (display highlight only)
 * 3. `null` → omit `job_id` on the positions API so the backend resolver applies
 *    operational → legacy
 */

export type BrowseRunJobIds = {
  /** Job id to highlight / pass when the operator explicitly selected a run (URL). */
  explicitJobId: string | null;
  /** Operational job when listed (for selector chip / display). */
  operationalJobId: string | null;
  /**
   * Concrete id for UI widgets that need a selected menu value.
   * Prefer explicit URL, else operational; never first list row.
   */
  displayJobId: string | null;
  /**
   * When true, the positions list query should include `job_id` (explicit operator choice).
   * When false, omit `job_id` so ResultContextResolver owns SoT.
   */
  passExplicitJobIdToApi: boolean;
};

export function resolveBrowseRunJobIds(input: {
  jobs: ReadonlyArray<{ id: string }>;
  urlJobId: string | null | undefined;
  operationalJobId: string | null | undefined;
}): BrowseRunJobIds {
  const jobIds = new Set(input.jobs.map((j) => j.id));
  const url = (input.urlJobId ?? "").trim();
  const operational = (input.operationalJobId ?? "").trim();

  const explicitJobId = url && jobIds.has(url) ? url : null;
  const operationalListed =
    operational && jobIds.has(operational) ? operational : null;

  return {
    explicitJobId,
    operationalJobId: operationalListed,
    displayJobId: explicitJobId ?? operationalListed,
    passExplicitJobIdToApi: explicitJobId != null,
  };
}
