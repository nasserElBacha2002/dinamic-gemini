import { Alert } from '@mui/material';

type CompareErrorStateProps = {
  message: string;
  sx?: object;
};

export default function CompareErrorState({ message, sx }: CompareErrorStateProps) {
  return (
    <Alert severity="error" sx={sx}>
      {message}
    </Alert>
  );
}
