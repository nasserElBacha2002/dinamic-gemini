/**
 * Result mappers — API → visible Result model (v3.1.1 Epic 1).
 */

export {
  mapPositionSummaryToResultSummary,
  mapPositionDetailToResultDetail,
  mapEvidenceToResultEvidence,
  mapReviewActionToHistoryItem,
  mapTraceabilityToVisible,
  mapPositionStatusToReviewStatus,
  mapResultEvidenceViewResponse,
} from './positionToResult';
export { getSummaryString, getSummaryNumber } from './detectedSummary';
