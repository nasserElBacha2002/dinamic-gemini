/**
 * Wall-clock benchmark run duration (matches backend `format_execution_duration_human`).
 */

export function formatExecutionDurationHuman(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return '';
  }
  if (seconds < 60) {
    let text = seconds.toFixed(1);
    text = text.replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '');
    return `${text}s`;
  }
  const total = Math.round(seconds);
  const minutes = Math.floor(total / 60);
  const sec = total % 60;
  if (sec === 0) {
    return `${minutes}m`;
  }
  return `${minutes}m ${String(sec).padStart(2, '0')}s`;
}

export function wallClockSecondsFromJobTimestamps(
  startedAt?: string | null,
  finishedAt?: string | null
): number | null {
  if (!startedAt?.trim() || !finishedAt?.trim()) {
    return null;
  }
  const a = Date.parse(startedAt);
  const b = Date.parse(finishedAt);
  if (!Number.isFinite(a) || !Number.isFinite(b)) {
    return null;
  }
  const secs = (b - a) / 1000;
  if (secs < 0) {
    return null;
  }
  return secs;
}

export function formatSignedDurationHuman(seconds: number): string {
  const abs = Math.abs(seconds);
  const body = formatExecutionDurationHuman(abs);
  if (seconds > 0) {
    return `+${body}`;
  }
  if (seconds < 0) {
    return `-${body}`;
  }
  return body;
}
