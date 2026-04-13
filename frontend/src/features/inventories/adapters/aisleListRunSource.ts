import type { Aisle } from '../../../api/types';

/**
 * Single attach point for the backend’s “latest run” field on aisle list DTOs.
 * Adapters read the run record here so UI-facing types stay free of `latest_job` naming.
 */
export function getLatestRunFromAisleListItem(aisle: Aisle): NonNullable<Aisle['latest_job']> | null {
  return aisle.latest_job ?? null;
}
