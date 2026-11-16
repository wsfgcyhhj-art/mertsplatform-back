export interface PaginationMeta {
  total: number;
  page: number;
  limit: number;
  totalPages: number;
}

export interface PaginatedResult<T> {
  items: T[];
  meta: PaginationMeta;
  isPaginatedRequested: boolean;
}

export function applyListQuery<T extends Record<string, any>>(
  rawItems: T[],
  query: Record<string, any>,
  searchKeys: Array<keyof T | string> = []
): PaginatedResult<T> {
  let filtered = [...rawItems];

  const searchRaw = query.search ?? query.q;
  if (typeof searchRaw === 'string' && searchRaw.trim() && searchKeys.length > 0) {
    const needle = searchRaw.trim().toLowerCase();
    filtered = filtered.filter((item) =>
      searchKeys.some((key) => {
        const val = item[key as keyof T];
        return val !== null && val !== undefined && String(val).toLowerCase().includes(needle);
      })
    );
  }

  const sortByRaw = query.sortBy ?? query.sort_by;
  const orderRaw = String(query.order ?? 'asc').toLowerCase() === 'desc' ? 'desc' : 'asc';

  if (typeof sortByRaw === 'string' && sortByRaw.trim()) {
    const sortKey = sortByRaw.trim();
    filtered.sort((a, b) => {
      const va = a[sortKey];
      const vb = b[sortKey];
      if (va === vb) return 0;
      if (va === null || va === undefined) return 1;
      if (vb === null || vb === undefined) return -1;
      if (typeof va === 'number' && typeof vb === 'number') {
        return orderRaw === 'desc' ? vb - va : va - vb;
      }
      return orderRaw === 'desc'
        ? String(vb).localeCompare(String(va), 'ru', { numeric: true })
        : String(va).localeCompare(String(vb), 'ru', { numeric: true });
    });
  }

  const total = filtered.length;
  const hasPageParam = query.page !== undefined || query.limit !== undefined || query.paginated === 'true' || query.paginated === '1';

  const parsedPage = Math.max(1, parseInt(String(query.page ?? '1'), 10) || 1);
  const parsedLimit =
    query.limit !== undefined
      ? Math.min(200, Math.max(1, parseInt(String(query.limit), 10) || 20))
      : hasPageParam
      ? 20
      : Math.max(1, total);

  const totalPages = Math.max(1, Math.ceil(total / parsedLimit));
  const items = hasPageParam
    ? filtered.slice((parsedPage - 1) * parsedLimit, parsedPage * parsedLimit)
    : filtered;

  return {
    items,
    meta: {
      total,
      page: parsedPage,
      limit: parsedLimit,
      totalPages,
    },
    isPaginatedRequested: hasPageParam,
  };
}
