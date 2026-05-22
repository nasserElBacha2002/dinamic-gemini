# Dialog Usage Guide

Shared dialog shells live under `frontend/src/components/ui/`. Prefer these primitives over raw MUI `Dialog` unless the layout is genuinely special (see below).

## When to use BaseDialog

Use for simple operational dialogs:

- create/edit forms
- selection dialogs
- read-only detail dialogs with standard layout
- simple action dialogs with custom content

Compose `actions` as `ReactNode` (typically MUI `Button` children). Use `contentDividers` for long forms that previously used `DialogContent` with `dividers`. Use `disableClose` while async work must not be interrupted; pair with disabling primary actions from the parent.

## When to use ConfirmDialog

Use for confirmations:

- delete
- invalidate
- recompute
- promote
- irreversible or warning actions

`ConfirmDialog` composes `BaseDialog` with a fixed cancel + confirm row and supports `loading` / `disableClose` for in-flight mutations.

## When to use WizardModal

Use for multi-step flows:

- create inventory wizard
- flows that need progress/stepper UI

Do not nest `WizardModal` inside `BaseDialog`.

## When to use ImagePreviewDialog

Use for image/media previews where the main content is an image and the richer `ImageViewer` toolbar (zoom, fullscreen) is desired.

For minimal “full width image + close” previews that must stay visually identical to a legacy simple `img` layout, `BaseDialog` with the same children is acceptable.

## When to use Drawer + DrawerHeader

Use for persistent side panels or larger management surfaces—especially right-anchored drawers that need a sticky title row and close control.

## When raw MUI Dialog is allowed

Raw MUI `Dialog` is allowed only when:

- the layout is genuinely special (e.g. custom chrome, non-standard padding)
- fullscreen media is required (`ImageViewer` fullscreen mode)
- migration would make the code less clear or risk scroll/focus behavior
- the dialog is intentionally outside the shared design system

`WizardModal`, `ImagePreviewDialog`, and `ImageViewer` intentionally wrap MUI `Dialog` directly.

## Standard action order

- Secondary/cancel action on the left.
- Primary/confirm action on the right.
- Destructive actions must use `error` styling (`ConfirmDialog`: `confirmColor="error"`).
- Warning actions must use `warning` styling where the action is reversible but risky.

## Close behavior

- Use `disableClose` during async operations when closing would interrupt or corrupt a mutation.
- Use `showCloseButton` for longer read-only/detail dialogs when a header close control helps discovery; it respects `disableClose` (the icon button is disabled when close is disabled).
- Preserve keyboard/backdrop behavior intentionally: `BaseDialog` passes `onClose={undefined}` to MUI `Dialog` when `disableClose` is true.

## i18n rules

- Do not hardcode English UI strings.
- Prefer shared keys:
  - `common.cancel`
  - `common.close`
  - `common.confirm`
  - `common.delete`
  - `common.save`
  - `common.loading` (and feature-specific keys like `common.starting` where appropriate)
- Feature-specific titles/descriptions should stay in feature namespaces.

## Error/loading rules

- Prefer shared error display patterns (`BaseDialog` `error` prop for a simple alert region; `ConfirmDialog` `errorMessage` for confirm failures).
- Disable submit buttons during pending mutations.
- Preserve field-level validation errors inside forms (do not move validation copy out of the form).

## Declarative `actionItems` API (Phase 4)

**Decision: DEFERRED.**

`actions?: ReactNode` remains the supported extension point: dialog footers vary (single close, cancel+submit, extra tertiary actions, custom spacing). A declarative `actionItems[]` API would duplicate MUI `Button` props and still need escape hatches for non-standard layouts.

**Re-evaluate** if multiple new dialogs repeat the same cancel + contained primary pattern with no custom JSX; until then, keep using `actions` or `ConfirmDialog`.
