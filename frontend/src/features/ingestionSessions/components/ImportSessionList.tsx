import OpenInNewOutlinedIcon from '@mui/icons-material/OpenInNewOutlined';
import { Button, Link } from '@mui/material';
import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { DataTable, type DataTableColumn, type DataTableSortDirection, EmptyState } from '../../../components/ui';
import type { CaptureSessionResponse } from '../../../types/captureSession';
import { formatDate } from '../../../utils/formatDate';
import { pathToIngestionSessionDetail } from '../../../constants/appRoutes';

interface ImportSessionListProps {
  sessions: CaptureSessionResponse[];
  loading: boolean;
  onOpen: (session: CaptureSessionResponse) => void;
  sortDir: DataTableSortDirection;
  setSortDir: (dir: DataTableSortDirection) => void;
}

export default function ImportSessionList({
  sessions,
  loading,
  onOpen,
  sortDir,
  setSortDir,
}: ImportSessionListProps) {
  const navigate = useNavigate();
  const sortedRows = useMemo(() => {
    const copy = [...sessions];
    copy.sort((a, b) => {
      const t1 = new Date(a.created_at).getTime();
      const t2 = new Date(b.created_at).getTime();
      return sortDir === 'asc' ? t1 - t2 : t2 - t1;
    });
    return copy;
  }, [sessions, sortDir]);

  const columns = useMemo<DataTableColumn<CaptureSessionResponse>[]>(
    () => [
      {
        id: 'id',
        label: 'Session ID',
        sortable: false,
        cell: (session) => (
          <Link
            component="button"
            type="button"
            underline="hover"
            color="text.primary"
            onClick={() =>
              navigate(pathToIngestionSessionDetail(session.id, session.inventory_id, session.aisle_id))
            }
          >
            {session.id}
          </Link>
        ),
      },
      { id: 'aisle_id', label: 'Aisle ID', sortable: false, cell: (session) => session.aisle_id },
      { id: 'status', label: 'Status', sortable: false, cell: (session) => session.status },
      { id: 'created_at', label: 'Created', sortable: true, cell: (session) => formatDate(session.created_at) },
      {
        id: 'open',
        label: 'Actions',
        sortable: false,
        cell: (session) => (
          <Button size="small" variant="outlined" startIcon={<OpenInNewOutlinedIcon />} onClick={() => onOpen(session)}>
            Open
          </Button>
        ),
      },
    ],
    [navigate, onOpen]
  );

  if (!loading && sortedRows.length === 0) {
    return <EmptyState title="No import sessions yet" message="Create a new import session to begin ingestion." />;
  }

  return (
    <DataTable<CaptureSessionResponse>
      rows={sortedRows}
      rowKey={(row) => row.id}
      columns={columns}
      loading={loading}
      sort={{
        sortBy: 'created_at',
        sortDir,
        onSortChange: (_sortBy, dir) => setSortDir(dir),
      }}
    />
  );
}
