import { createTheme } from '@mui/material/styles';
import type { Shadows } from '@mui/material/styles';

/**
 * Dinamic Inventory v3 — product theme (Sprint 2.1).
 * Source: Re diseño 3.3 §5–7 (enterprise tone, neutral surfaces, semantic colors, MUI typography, medium density).
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
      // Neutral “passive” UI — Re diseño 3.3 §6.3 (gris / estado pasivo). Not accent pink.
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
      // Informational / sistema — same family as action blue (§6.2–6.3).
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
    fontWeightBold: 600,
    h4: { fontWeight: 600, letterSpacing: '-0.02em' },
    h5: { fontWeight: 600, letterSpacing: '-0.015em' },
    h6: { fontWeight: 600, letterSpacing: '-0.01em' },
    subtitle1: { fontWeight: 600 },
    subtitle2: { fontWeight: 600 },
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
        root: {
          borderRadius: 8,
          paddingLeft: '1rem',
          paddingRight: '1rem',
        },
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
        text: {
          '&:focus-visible': {
            outline: '2px solid',
            outlineColor: 'primary.main',
            outlineOffset: 2,
          },
        },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: {
          '&:focus-visible': {
            outline: '2px solid',
            outlineColor: 'primary.main',
            outlineOffset: 2,
          },
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
        },
        rounded: {
          borderRadius: 8,
        },
        elevation1: {
          boxShadow: shadows[1],
        },
        elevation2: {
          boxShadow: shadows[2],
        },
        elevation3: {
          boxShadow: shadows[3],
        },
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
        paper: {
          borderRight: '1px solid',
          borderColor: 'divider',
          boxShadow: 'none',
        },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          marginBottom: 2,
          '&.Mui-selected': {
            backgroundColor: 'action.selected',
            '&:hover': {
              backgroundColor: 'action.selected',
            },
          },
        },
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
        root: {
          borderRadius: 8,
        },
      },
    },
    MuiBreadcrumbs: {
      styleOverrides: {
        separator: {
          color: 'text.secondary',
        },
      },
    },
    MuiLink: {
      defaultProps: {
        underline: 'hover',
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: {
          borderRadius: 8,
        },
        standardSuccess: {
          backgroundColor: 'rgba(46, 125, 50, 0.08)',
        },
        standardWarning: {
          backgroundColor: 'rgba(237, 108, 2, 0.08)',
        },
        standardError: {
          backgroundColor: 'rgba(198, 40, 40, 0.08)',
        },
        standardInfo: {
          backgroundColor: 'rgba(2, 119, 189, 0.08)',
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        head: {
          fontWeight: 600,
          color: 'text.secondary',
          backgroundColor: 'rgba(0, 0, 0, 0.02)',
        },
      },
    },
  },
});

export default theme;
