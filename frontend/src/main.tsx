import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider, CssBaseline } from '@mui/material';
import App from './App';
import theme from './theme';

const root = document.getElementById('root');
if (!root) throw new Error('Root element not found');

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30 * 1000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

// StrictMode is disabled to avoid duplicate TanStack Query requests in development.
// React 18 StrictMode double-mounts components; when the first observer unmounts,
// the in-flight request can be cancelled, so the remount runs the query again.
ReactDOM.createRoot(root).render(
  <React.StrictMode>
  <QueryClientProvider client={queryClient}>
    <BrowserRouter>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <App />
      </ThemeProvider>
    </BrowserRouter>
  </QueryClientProvider>
  </React.StrictMode>
);
