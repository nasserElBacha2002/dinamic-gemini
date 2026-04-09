/**
 * Shared list/table defaults — align with backend `page_size` caps (e.g. inventories route le=200).
 *
 * **DEFAULT_LIST_PAGE_SIZE** is for **interactive paginated** list screens (`DataTable` + user-controlled page size).
 * Other hooks may use larger `page_size` on purpose (e.g. inventory detail aisle grid fetching one chunk,
 * results overview loading a full aisle slice for client-side filters) — that is intentional until those views
 * move to server pagination.
 */

export const DEFAULT_LIST_PAGE_SIZE = 25;

/** Debounce for search strings that trigger server list queries (inventories, review queue SKU, etc.). */
export const TABLE_SERVER_SEARCH_DEBOUNCE_MS = 300;

export const TABLE_PAGE_SIZE_OPTIONS = [10, 25, 50, 100, 200] as const;

/** i18n key — used when `DataTable` shows its built-in empty state. */
export const DATATABLE_DEFAULT_EMPTY_MESSAGE_KEY = 'table.empty_default' as const;
