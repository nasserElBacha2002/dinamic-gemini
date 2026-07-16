import OpenInNewOutlinedIcon from '@mui/icons-material/OpenInNewOutlined';
import { Button, Link } from '@mui/material';
import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  TableSection,
  sortDataTableRows,
  type DataTableColumn,
} from '../../../components/ui';
import { useTableState } from '../../../hooks';
import type { CaptureSessionResponse } from '../../../types/captureSession';
import { formatDate } from '../../../utils/formatDate';
import { pathToIngestionSessionDetail } from '../../../constants/appRoutes';

interface ImportSessionListProps {
  title?: string;
  sessions: CaptureSessionResponse[];
  loading: boolean;
  onOpen: (session: CaptureSessionResponse) => void;
}

export default function ImportSessionList({
  title,
  sessions,
  loading,
  onOpen,
}: ImportSessionListProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { sortBy, sortDir, setSort } = useTableState({
    initialSortBy: 'created_at',
    initialSortDir: 'desc',
  });

  const columns = useMemo<DataTableColumn<CaptureSessionResponse>[]>(
    () => [
      {
        id: 'id',
        label: t('ingestion_sessions.list.column_session_id'),
        sortable: false,
        cell: (session) => (
          <Link
            component="button"
            type="button"
            underline="hover"
            color="text.primary"
            onClick={() =>
              navigate(pathToIngestionSessionDetail(session.id, session.inventory_id))
            }
          >
            {session.id}
          </Link>
        ),
      },
      { id: 'aisle_id', label: t('ingestion_sessions.list.column_aisle_id'), sortable: false, cell: (session) => session.aisle_id },
      { id: 'status', label: t('ingestion_sessions.list.column_status'), sortable: false, cell: (session) => session.status },
      {
        id: 'created_at',
        label: t('ingestion_sessions.list.column_created'),
        sortable: true,
        sortType: 'date',
        sortAccessor: (session) => session.created_at,
        cell: (session) => formatDate(session.created_at),
      },
      {
        id: 'open',
        label: t('ingestion_sessions.list.column_actions'),
        sortable: false,
        cell: (session) => (
          <Button size="small" variant="outlined" startIcon={<OpenInNewOutlinedIcon />} onClick={() => onOpen(session)}>
            {t('ingestion_sessions.actions.open')}
          </Button>
        ),
      },
    ],
    [navigate, onOpen, t]
  );

  /** TableDataMode: client-bulk — bounded session list for the selected inventory/aisle filters. */
  const sortedRows = useMemo(
    () => sortDataTableRows(sessions, columns, sortBy, sortDir),
    [sessions, columns, sortBy, sortDir]
  );

  return (
    <TableSection<CaptureSessionResponse>
      testId="import-session-list-section"
      title={title}
      table={{
        rows: sortedRows,
        rowKey: (row) => row.id,
        columns,
        loading,
        onRowClick: onOpen,
        mobile: {
          mode: 'card',
          title: (session) => session.id,
          subtitle: (session) => session.aisle_id,
          ariaLabel: (session) => session.id,
          fields: [
            {
              id: 'status',
              label: t('ingestion_sessions.list.column_status'),
              value: (session) => session.status,
            },
            {
              id: 'created_at',
              label: t('ingestion_sessions.list.column_created'),
              value: (session) => formatDate(session.created_at),
            },
          ],
          primaryAction: (session) => (
            <Button
              size="small"
              variant="outlined"
              startIcon={<OpenInNewOutlinedIcon />}
              onClick={() => onOpen(session)}
            >
              {t('ingestion_sessions.actions.open')}
            </Button>
          ),
        },
        emptyState: {
          title: t('ingestion_sessions.empty.title'),
          message: t('ingestion_sessions.empty.message'),
        },
        sort: {
          sortBy,
          sortDir,
          onSortChange: setSort,
        },
      }}
    />
  );
}
