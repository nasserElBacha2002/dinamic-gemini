import { alpha, createTheme } from '@mui/material/styles';
import type { Shadows } from '@mui/material/styles';

/**
 * Dinamic Inventory v3 — product theme (Sprint 2.1).
 * Source: Re diseño 3.3 §5–7 (enterprise tone, neutral surfaces, semantic colors, MUI typography, medium density).
 *
 * **Palette roles**
 * - `primary`: action / links / focus / active nav (§6.2–6.3).
 * - `secondary`: **not** a marketing accent — reserved for neutral “support” chrome (outlined secondary actions,
 *   passive controls). Semantic “grey / neutral state” in the redesign maps here and to `text.secondary` / greys;
 *   do not use `secondary` for brand accent or success (§6.3–6.4).
 * - `success` | `warning` | `error` | `info`: semantic statuses (§6.3).
 *
 * **Shape**
 * - `theme.shape.borderRadius` (8px) is the default corner radius for buttons, inputs, paper, list rows, alerts,
 *   and shell-adjacent surfaces unless a component documents an exception (§6.1 soft edges).
 */

const baseShadows = createTheme().shadows;
const shadows: Shadows = [...baseShadows] as unknown as Shadows;
shadows[1] = '0px 1px 2px rgba(15, 23, 42, 0.06), 0px 1px 3px rgba(15, 23, 42, 0.04)';
shadows[2] = '0px 2px 4px rgba(15, 23, 42, 0.06), 0px 2px 8px rgba(15, 23, 42, 0.04)';
shadows[3] = '0px 4px 8px rgba(15, 23, 42, 0.06), 0px 2px 4px rgba(15, 23, 42, 0.04)';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1565c0',
      light: '#42a5f5',
      dark: '#0d47a1',
      contrastText: '#ffffff',
    },
    secondary: {
      main: '#5f6368',
      light: '#80868b',
      dark: '#3c4043',
      contrastText: '#ffffff',
    },
    success: {
      main: '#2e7d32',
      light: '#4caf50',
      dark: '#1b5e20',
    },
    warning: {
      main: '#ed6c02',
      light: '#ff9800',
      dark: '#e65100',
    },
    error: {
      main: '#c62828',
      light: '#ef5350',
      dark: '#b71c1c',
    },
    info: {
      main: '#0277bd',
      light: '#039be5',
      dark: '#01579b',
    },
    background: {
      default: '#f4f6f8',
      paper: '#ffffff',
    },
    text: {
      primary: '#1c1c1e',
      secondary: '#5c5c66',
      disabled: 'rgba(0, 0, 0, 0.38)',
    },
    divider: 'rgba(0, 0, 0, 0.08)',
    action: {
      active: 'rgba(0, 0, 0, 0.56)',
      hover: 'rgba(0, 0, 0, 0.04)',
      selected: 'rgba(21, 101, 192, 0.08)',
      selectedOpacity: 0.08,
      focus: 'rgba(21, 101, 192, 0.12)',
      focusOpacity: 0.12,
      disabled: 'rgba(0, 0, 0, 0.26)',
      disabledBackground: 'rgba(0, 0, 0, 0.12)',
    },
  },
  shape: {
    borderRadius: 8,
  },
  shadows,
  typography: {
    fontFamily: '"Roboto", "Helvetica Neue", "Arial", sans-serif',
    fontWeightRegular: 400,
    fontWeightMedium: 500,
    /** Roboto is loaded at 400 / 500 / 700 only — use 700 for heading-level emphasis (no synthetic 600). */
    fontWeightBold: 700,
    h4: { fontWeight: 700, letterSpacing: '-0.02em' },
    h5: { fontWeight: 700, letterSpacing: '-0.015em' },
    h6: { fontWeight: 700, letterSpacing: '-0.01em' },
    subtitle1: { fontWeight: 500 },
    subtitle2: { fontWeight: 500 },
    body1: { lineHeight: 1.5 },
    body2: { lineHeight: 1.43 },
    caption: { lineHeight: 1.33 },
    button: {
      textTransform: 'none',
      fontWeight: 500,
      letterSpacing: '0.02em',
    },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          WebkitFontSmoothing: 'antialiased',
          MozOsxFontSmoothing: 'grayscale',
        },
      },
    },
    MuiButton: {
      defaultProps: {
        disableElevation: true,
      },
      styleOverrides: {
        root: ({ theme }) => ({
          borderRadius: theme.shape.borderRadius,
          paddingLeft: theme.spacing(2),
          paddingRight: theme.spacing(2),
        }),
        containedPrimary: {
          '&:hover': {
            boxShadow: 'none',
          },
        },
        outlined: {
          borderWidth: 1,
          '&:hover': {
            borderWidth: 1,
          },
        },
        text: ({ theme }) => ({
          '&:focus-visible': {
            outline: `2px solid ${theme.palette.primary.main}`,
            outlineOffset: 2,
          },
        }),
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: ({ theme }) => ({
          '&:focus-visible': {
            outline: `2px solid ${theme.palette.primary.main}`,
            outlineOffset: 2,
          },
        }),
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
        },
        rounded: ({ theme }) => ({
          borderRadius: theme.shape.borderRadius,
        }),
        elevation1: ({ theme }) => ({
          boxShadow: theme.shadows[1],
        }),
        elevation2: ({ theme }) => ({
          boxShadow: theme.shadows[2],
        }),
        elevation3: ({ theme }) => ({
          boxShadow: theme.shadows[3],
        }),
      },
    },
    MuiAppBar: {
      defaultProps: {
        elevation: 0,
        color: 'inherit',
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: ({ theme }) => ({
          borderRight: `1px solid ${theme.palette.divider}`,
          boxShadow: 'none',
        }),
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: ({ theme }) => ({
          borderRadius: theme.shape.borderRadius,
          marginBottom: theme.spacing(0.25),
          '&.Mui-selected': {
            backgroundColor: theme.palette.action.selected,
            '&:hover': {
              backgroundColor: theme.palette.action.selected,
            },
          },
        }),
      },
    },
    MuiTextField: {
      defaultProps: {
        variant: 'outlined',
        size: 'medium',
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: ({ theme }) => ({
          borderRadius: theme.shape.borderRadius,
        }),
      },
    },
    MuiBreadcrumbs: {
      styleOverrides: {
        separator: ({ theme }) => ({
          color: theme.palette.text.secondary,
        }),
      },
    },
    MuiLink: {
      defaultProps: {
        underline: 'hover',
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: ({ theme }) => ({
          borderRadius: theme.shape.borderRadius,
        }),
        standardSuccess: ({ theme }) => ({
          backgroundColor: alpha(theme.palette.success.main, 0.08),
        }),
        standardWarning: ({ theme }) => ({
          backgroundColor: alpha(theme.palette.warning.main, 0.08),
        }),
        standardError: ({ theme }) => ({
          backgroundColor: alpha(theme.palette.error.main, 0.08),
        }),
        standardInfo: ({ theme }) => ({
          backgroundColor: alpha(theme.palette.info.main, 0.08),
        }),
      },
    },
    MuiTableCell: {
      styleOverrides: {
        head: ({ theme }) => ({
          fontWeight: theme.typography.fontWeightBold,
          color: theme.palette.text.secondary,
          backgroundColor: theme.palette.action.hover,
        }),
      },
    },
    MuiMenu: {
      styleOverrides: {
        paper: ({ theme }) => ({
          borderRadius: theme.shape.borderRadius,
          border: `1px solid ${theme.palette.divider}`,
          boxShadow: theme.shadows[2],
        }),
      },
    },
  },
});

// Sprint 2.3–2.4: StatusBadge, FilterToolbar, DataTable — `DataTable` uses `size="small"` + `MuiTableCell` head overrides above.

export default theme;
