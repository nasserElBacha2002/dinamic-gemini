import { Link as RouterLink } from 'react-router-dom';
import { Box, Link, Typography } from '@mui/material';
import { PageLayout } from '../components/ui';

export interface ScreenPlaceholderPageProps {
  title: string;
  description?: string;
}

/** Reserved route shell for v3.3 screens not yet implemented (dashboard, review queue, metrics). */
export default function ScreenPlaceholderPage({ title, description }: ScreenPlaceholderPageProps) {
  return (
    <PageLayout maxWidth={720}>
      <Typography variant="h5" component="h1" gutterBottom>
        {title}
      </Typography>
      {description ? (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {description}
        </Typography>
      ) : null}
      <Box>
        <Link component={RouterLink} to="/" underline="hover">
          Back to inventories
        </Link>
      </Box>
    </PageLayout>
  );
}
