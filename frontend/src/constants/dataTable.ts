/**
 * Shared list/table defaults — align with backend `page_size` caps (e.g. inventories route le=200).
 *
 * **DEFAULT_LIST_PAGE_SIZE** is for **interactive paginated** list screens (`DataTable` + user-controlled page size).
 * Other hooks may use larger `page_size` on purpose (e.g. inventory detail aisle grid fetching one chunk,
 * results overview loading a full aisle slice for client-side filters) — that is intentional until those views
 * move to server pagination.
 */

import { TABLE_EMPTY_DEFAULT } from './uiCopy';

export const DEFAULT_LIST_PAGE_SIZE = 25;

export const TABLE_PAGE_SIZE_OPTIONS = [10, 25, 50, 100, 200] as const;

/** Used by `DataTable` when `rows` is empty, `loading` is false, and no `emptyState` prop is passed. */
export const DATATABLE_DEFAULT_EMPTY_MESSAGE = TABLE_EMPTY_DEFAULT;
