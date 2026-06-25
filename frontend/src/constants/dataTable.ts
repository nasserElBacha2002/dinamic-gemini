/**
 * Shared list/table defaults — align with backend `page_size` caps (e.g. inventories route le=200).
 *
 * **DEFAULT_LIST_PAGE_SIZE** is for **interactive paginated** list screens (`DataTable` + user-controlled page size).
 * Other hooks may use larger `page_size` on purpose (e.g. inventory detail aisle grid fetching one chunk,
 * results overview loading a full aisle slice for client-side filters) — that is intentional until those views
 * move to server pagination.
 *
 * ## Table data strategies
 *
 * Pick one mode per screen; compose with `useTableState`, `TableSection`, and `DataTable`.
 *
 * 1. **`server`** — API owns pagination, sorting, and search/filtering. Parent passes query params to a list hook.
 *    Reference: `pages/InventoriesList.tsx`.
 * 2. **`client-bulk`** — API returns a bounded dataset; frontend filters, sorts, and paginates locally
 *    (`sortDataTableRows`, `rowMatchesSearchQuery`). Reference: aisle/results tables.
 * 3. **`hybrid`** — Mixed server/client behavior; avoid unless there is a clear product reason.
 *    Reference: `pages/ClientsList.tsx` (server pagination + client search on current page).
 */

/** Operational table strategy — documents intended data flow for a screen. */
export type TableDataMode = 'server' | 'client-bulk' | 'hybrid';

export const DEFAULT_LIST_PAGE_SIZE = 25;

/** Debounce for search strings that trigger server list queries (inventories, review queue SKU, etc.). */
export const TABLE_SERVER_SEARCH_DEBOUNCE_MS = 300;

export const TABLE_PAGE_SIZE_OPTIONS = [10, 25, 50, 100, 200] as const;

/** i18n key — used when `DataTable` shows its built-in empty state. */
export const DATATABLE_DEFAULT_EMPTY_MESSAGE_KEY = 'table.empty_default' as const;
