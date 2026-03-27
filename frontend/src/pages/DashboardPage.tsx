import { useMemo, useState } from 'react';
import { Box, Button, Grid, Link, Typography } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import type { Inventory, InventoryListItem } from '../api/types';
import { ApiError } from '../api/types';
import { getApiErrorMessage } from '../utils/apiErrors';
import { formatDate } from '../utils/formatDate';
import { formatInventoryStatusLabel, inventoryStatusToBadgeSemantic } from '../utils/inventoryRowStatus';
import {
  DataTable,
  EmptyState,
  ErrorAlert,
  KpiCard,
  SectionCard,
  StatusBadge,
  type DataTableColumn,
} from '../components/ui';
import { PageHeader } from '../components/shell';
import CreateInventoryDialog from '../components/CreateInventoryDialog';
import { useInventoriesList, useCreateInventory } from '../hooks';

/**
 * Dashboard — Sprint 3.1 (Re diseño 3.3 §9.2).
 *
 * **Contract note:** KPI row + attention/activity blocks require a dashboard-summary backend contract.
 * Until that ships, this page renders the correct **structure** and wires only the Recent Inventories table
 * to the existing inventories list endpoint (no fake business logic in the UI).
 */
export default function DashboardPage() {
  const navigate = useNavigate();
  const [createOpen, setCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const createMutation = useCreateInventory();

  const recentInvQuery = useInventoriesList({
    page: 1,
    page_size: 10,
    sort_by: 'last_activity_at',
    sort_dir: 'desc',
  });

  const recentInventories: InventoryListItem[] = recentInvQuery.data?.items ?? [];
  const recentErrorMessage =
    recentInvQuery.isError && recentInvQuery.error
      ? recentInvQuery.error instanceof ApiError
        ? getApiErrorMessage(recentInvQuery.error, 'Failed to load recent inventories')
        : String(recentInvQuery.error)
      : null;

  const handleCreateSuccess = (_created: Inventory) => {
    setCreateOpen(false);
    setCreateError(null);
    // Always refresh so the Recent inventories table is not stale after creation.
    recentInvQuery.refetch();
  };

  const recentColumns = useMemo<DataTableColumn<InventoryListItem>[]>(
    () => [
      {
        id: 'name',
        label: 'Inventory name',
        cell: (inv) => (
          <Link
            component="button"
            type="button"
            underline="hover"
            color="text.primary"
            onClick={() => navigate(`/inventories/${inv.id}`)}
            sx={{ fontWeight: 600, textAlign: 'left' }}
          >
            {inv.name}
          </Link>
        ),
      },
      {
        id: 'status',
        label: 'Status',
        cell: (inv) => (
          <StatusBadge
            label={formatInventoryStatusLabel(String(inv.status))}
            semantic={inventoryStatusToBadgeSemantic(String(inv.status))}
          />
        ),
      },
      { id: 'aisles_count', label: 'Aisles', align: 'right', cell: (inv) => inv.aisles_count ?? '—' },
      {
        id: 'pending_review_count',
        label: 'Pending review',
        align: 'right',
        cell: (inv) => inv.pending_review_count ?? '—',
      },
      {
        id: 'last_activity_at',
        label: 'Last activity',
        cell: (inv) => formatDate(inv.last_activity_at ?? undefined),
      },
    ],
    [navigate]
  );

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle="Operational overview"
        actions={
          <Button
            variant="contained"
            onClick={() => {
              setCreateError(null);
              setCreateOpen(true);
            }}
          >
            Create inventory
          </Button>
        }
      />

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} sm={6} md={4} lg={2} sx={{ display: 'flex' }}>
          <KpiCard label="Active inventories" value="—" description="Pending dashboard summary contract" />
        </Grid>
        <Grid item xs={12} sm={6} md={4} lg={2} sx={{ display: 'flex' }}>
          <KpiCard label="Pending review" value="—" description="Pending dashboard summary contract" />
        </Grid>
        <Grid item xs={12} sm={6} md={4} lg={2} sx={{ display: 'flex' }}>
          <KpiCard label="Processed aisles" value="—" description="Pending dashboard summary contract" />
        </Grid>
        <Grid item xs={12} sm={6} md={4} lg={2} sx={{ display: 'flex' }}>
          <KpiCard label="Failed jobs" value="—" description="Pending dashboard summary contract" />
        </Grid>
        <Grid item xs={12} sm={6} md={4} lg={2} sx={{ display: 'flex' }}>
          <KpiCard label="Manual corrections" value="—" description="Pending dashboard summary contract" />
        </Grid>
        <Grid item xs={12} sm={6} md={4} lg={2} sx={{ display: 'flex' }}>
          <KpiCard label="Auto-acceptance rate" value="—" description="Pending dashboard summary contract" />
        </Grid>
      </Grid>

      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2, mb: 2 }}>
        <SectionCard title="Requires attention" subtitle="Inventories with errors, failed aisles, and critical results.">
          <EmptyState message="Dashboard attention feed is not wired yet. Backend summary contract needed." />
        </SectionCard>
        <SectionCard title="Recent activity" subtitle="Recent inventory creation, processing, and review actions.">
          <EmptyState message="Recent activity feed is not wired yet. Backend summary contract needed." />
        </SectionCard>
      </Box>

      {recentErrorMessage ? (
        <ErrorAlert message={recentErrorMessage} onRetry={() => recentInvQuery.refetch()} />
      ) : (
        <SectionCard title="Recent inventories">
          <DataTable<InventoryListItem>
            rows={recentInventories}
            rowKey={(inv) => inv.id}
            columns={recentColumns}
            loading={recentInvQuery.isLoading}
            emptyState={{ message: 'No inventories yet.' }}
          />
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
            Showing the 10 most recently active inventories.
          </Typography>
        </SectionCard>
      )}

      {createError ? (
        <ErrorAlert
          message={createError}
          onRetry={() => {
            setCreateError(null);
            recentInvQuery.refetch();
          }}
          onClose={() => setCreateError(null)}
        />
      ) : null}

      <CreateInventoryDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSuccess={handleCreateSuccess}
        onError={setCreateError}
        createInventoryFn={createMutation.mutateAsync}
      />
    </>
  );
}
