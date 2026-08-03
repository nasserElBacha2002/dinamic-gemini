/** Lightweight product analytics for positioning UI (no secrets / no full payloads). */

export function trackPositioningEvent(
  name:
    | 'physical_locations_opened'
    | 'physical_location_created'
    | 'position_label_generation_requested'
    | 'position_label_preview_opened'
    | 'position_label_download_requested'
    | 'position_label_reprint_requested'
    | 'position_label_replace_requested'
    | 'position_label_invalidated'
    | 'position_label_batch_requested',
  props?: Record<string, string | number | boolean | null | undefined>
): void {
  if (typeof window === 'undefined') return;
  try {
    const detail = { name, props: props ?? {}, at: new Date().toISOString() };
    window.dispatchEvent(new CustomEvent('dinamic:analytics', { detail }));
    if (import.meta.env.DEV) {
      // eslint-disable-next-line no-console
      console.debug('[positioning]', detail);
    }
  } catch {
    /* ignore analytics failures */
  }
}
