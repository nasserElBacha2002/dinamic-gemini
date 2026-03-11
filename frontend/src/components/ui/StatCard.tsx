/**
 * Metric/stat card: label + value in an outlined Card.
 * Use for dashboard-style metrics (e.g. inventory metrics grid).
 */

import { Card, CardContent, Typography } from '@mui/material';

export interface StatCardProps {
  /** Short label (e.g. "Total positions", "Success rate"). */
  label: string;
  /** Value to show (number, string, or React node). */
  value: React.ReactNode;
}

export default function StatCard({ label, value }: StatCardProps) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="body2" color="text.secondary">
          {label}
        </Typography>
        <Typography variant="h6">{value}</Typography>
      </CardContent>
    </Card>
  );
}
