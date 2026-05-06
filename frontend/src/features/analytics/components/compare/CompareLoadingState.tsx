import { Box, Skeleton, Typography } from '@mui/material';

type CompareLoadingStateProps = {
  message?: string;
  sx?: object;
  testId?: string;
  skeletonHeights?: number[];
};

export default function CompareLoadingState({ message, sx, testId, skeletonHeights }: CompareLoadingStateProps) {
  if (skeletonHeights && skeletonHeights.length > 0) {
    return (
      <Box sx={{ display: 'grid', gap: 2, ...sx }} data-testid={testId}>
        {skeletonHeights.map((height, index) => (
          <Skeleton key={`${height}-${index}`} variant="rounded" height={height} />
        ))}
      </Box>
    );
  }
  return (
    <Typography sx={sx} data-testid={testId}>
      {message}
    </Typography>
  );
}
