import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  type AppliedState,
  parseAppliedState,
  sameSelection,
} from '../adapters/compareManyRunsViewModel';
import { MAX_COMPARE_JOBS, MIN_COMPARE_JOBS } from '../constants/compareManyRuns';

export type CompareManyRunsWorkspaceMode = 'route' | 'embedded';

export interface CompareManyAppliedStateOptions {
  mode: CompareManyRunsWorkspaceMode;
  initialAisleId?: string;
  initialJobIds?: string[];
  initialBaselineJobId?: string;
}

function emptyApplied(initial?: Partial<AppliedState>): AppliedState {
  return {
    aisleId: initial?.aisleId ?? '',
    jobIds: initial?.jobIds ?? [],
    baseline: initial?.baseline ?? '',
  };
}

function appliedToSearchParams(state: AppliedState): URLSearchParams {
  const p = new URLSearchParams();
  if (state.aisleId) p.set('aisleId', state.aisleId);
  if (state.jobIds.length) p.set('jobIds', state.jobIds.join(','));
  if (state.baseline) p.set('baseline', state.baseline);
  return p;
}

export function useCompareManyAppliedState({
  mode,
  initialAisleId,
  initialJobIds,
  initialBaselineJobId,
}: CompareManyAppliedStateOptions) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [embeddedApplied, setEmbeddedApplied] = useState<AppliedState>(() =>
    emptyApplied({
      aisleId: initialAisleId,
      jobIds: initialJobIds,
      baseline: initialBaselineJobId,
    })
  );

  const embeddedSeedKey = `${initialAisleId ?? ''}|${(initialJobIds ?? []).join(',')}|${initialBaselineJobId ?? ''}`;
  const lastEmbeddedSeedRef = useRef(embeddedSeedKey);

  useEffect(() => {
    if (mode !== 'embedded') return;
    if (lastEmbeddedSeedRef.current === embeddedSeedKey) return;
    lastEmbeddedSeedRef.current = embeddedSeedKey;
    setEmbeddedApplied(
      emptyApplied({
        aisleId: initialAisleId,
        jobIds: initialJobIds,
        baseline: initialBaselineJobId,
      })
    );
  }, [mode, embeddedSeedKey, initialAisleId, initialJobIds, initialBaselineJobId]);

  const applied = useMemo(
    () => (mode === 'route' ? parseAppliedState(searchParams) : embeddedApplied),
    [mode, searchParams, embeddedApplied]
  );

  const commitApplied = useCallback(
    (next: AppliedState) => {
      if (mode === 'route') {
        setSearchParams(appliedToSearchParams(next), { replace: false });
        return;
      }
      setEmbeddedApplied(next);
    },
    [mode, setSearchParams]
  );

  const [draftOverride, setDraftOverride] = useState<{
    sourceKey: string;
    aisleId: string;
    jobIds: string[];
    baseline: string;
  } | null>(null);

  const draftSourceKey = `${applied.aisleId}|${applied.jobIds.join(',')}|${applied.baseline}`;
  const draftAisleId =
    draftOverride?.sourceKey === draftSourceKey ? draftOverride.aisleId : applied.aisleId;
  const draftJobIds =
    draftOverride?.sourceKey === draftSourceKey ? draftOverride.jobIds : applied.jobIds;
  const draftBaseline =
    draftOverride?.sourceKey === draftSourceKey ? draftOverride.baseline : applied.baseline;

  const correctionNoticeRef = useRef<string | null>(null);
  const [showBaselineAdjustedNotice, setShowBaselineAdjustedNotice] = useState(false);

  useEffect(() => {
    if (mode !== 'route') return;
    if (!applied.aisleId) return;
    if (applied.jobIds.length < MIN_COMPARE_JOBS || applied.jobIds.length > MAX_COMPARE_JOBS) return;
    if (new Set(applied.jobIds).size !== applied.jobIds.length) return;
    if (!applied.jobIds.length) return;
    if (applied.baseline && applied.jobIds.includes(applied.baseline)) return;
    const nextBaseline = applied.jobIds[0];
    if (!nextBaseline) return;
    const baselineInUrl = searchParams.get('baseline')?.trim() ?? '';
    if (baselineInUrl === nextBaseline) return;

    const correctionKey = `${applied.aisleId}|${applied.jobIds.join(',')}|${nextBaseline}`;
    setSearchParams((prev) => {
      const p = new URLSearchParams(prev);
      p.set('baseline', nextBaseline);
      return p;
    }, { replace: true });

    if (correctionNoticeRef.current !== correctionKey) {
      correctionNoticeRef.current = correctionKey;
      setShowBaselineAdjustedNotice(true);
    }
  }, [mode, applied.aisleId, applied.baseline, applied.jobIds, searchParams, setSearchParams]);

  const applyDraft = useCallback(
    (draft: { aisleId: string; jobIds: string[]; baseline: string }, draftError: string | null) => {
      if (draftError) return;
      const safeBaseline = draft.jobIds.includes(draft.baseline) ? draft.baseline : (draft.jobIds[0] ?? '');
      if (!safeBaseline) return;
      if (safeBaseline !== draft.baseline) {
        setShowBaselineAdjustedNotice(true);
      }
      commitApplied({
        aisleId: draft.aisleId,
        jobIds: draft.jobIds,
        baseline: safeBaseline,
      });
    },
    [commitApplied]
  );

  const dirty =
    draftAisleId !== applied.aisleId ||
    draftBaseline !== applied.baseline ||
    !sameSelection(draftJobIds, applied.jobIds);

  return {
    applied,
    draftAisleId,
    draftJobIds,
    draftBaseline,
    draftSourceKey,
    dirty,
    showBaselineAdjustedNotice,
    setShowBaselineAdjustedNotice,
    setDraftOverride,
    applyDraft,
  };
}
