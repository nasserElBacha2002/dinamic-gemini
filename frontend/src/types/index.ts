/**
 * Cross-cutting type modules (planning target taxonomies, status alignment, screen contracts,
 * and capture-session API contract mirrors used by feature code.
 * Note: `captureSession.ts` is a feature-level export location for UI ergonomics,
 * but its shapes intentionally mirror backend API DTOs.
 */

export * from './screenTargets';
export * from './statusAlignment';
export * from './screenContracts';
export * from './captureSession';
