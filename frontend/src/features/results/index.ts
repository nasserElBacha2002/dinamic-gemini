/**
 * v3.1.1 — Result-centric visible review model (Epic 1).
 *
 * Result is the primary visible object for the review flow. Use these types
 * and hooks when building or refactoring the results list and result detail UI.
 */

export type {
  ResultSummary,
  ResultDetail,
  ResultEvidence,
  ResultProductInfo,
  ReviewHistoryItem,
  ReviewStatus,
  TraceabilityStatus,
} from './types';

export {
  mapPositionSummaryToResultSummary,
  mapPositionDetailToResultDetail,
  mapEvidenceToResultEvidence,
  mapProductToResultProductInfo,
  mapReviewActionToHistoryItem,
  mapTraceabilityToVisible,
  mapPositionStatusToReviewStatus,
} from './mappers';

export { useResultSummaries, useResultDetail } from './hooks/useResultSummaries';

export { computeResultsKpi, filterResults } from './selectors';
export type { ResultsKpi, ResultsFilterKind } from './selectors';

export { LOW_CONFIDENCE_THRESHOLD } from './constants';
export { visibleTraceabilityToApiStatus } from './utils/traceabilityDisplay';
export { getResultNavigationContext, parseResultDetailNavigationState, getInitialFilterFromReturnState } from './utils/navigationContext';
export type { ResultDetailNavigationState, ResultNavigationContext } from './utils/navigationContext';
