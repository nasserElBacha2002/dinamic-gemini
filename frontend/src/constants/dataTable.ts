/**
 * Shared list/table defaults — align with backend `page_size` caps (e.g. inventories route le=200).
 */

export const DEFAULT_LIST_PAGE_SIZE = 25;

export const TABLE_PAGE_SIZE_OPTIONS = [10, 25, 50, 100, 200] as const;
