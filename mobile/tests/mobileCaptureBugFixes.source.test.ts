/**
 * Source-level regressions for mobile capture bug fixes (export / layout / login).
 */

import * as fs from 'fs';
import * as path from 'path';

const root = path.join(__dirname, '..');

function read(rel: string): string {
  return fs.readFileSync(path.join(root, rel), 'utf8');
}

describe('mobile capture bug-fix source contracts', () => {
  it('App saves locally for ZIP export; local_completed opens in review', () => {
    const app = read('App.tsx');
    expect(app).toMatch(/finishReviewForExport/);
    expect(app).toMatch(/completeLocalSession/);
    expect(app).toMatch(/mobileServerUpload/);
    expect(app).not.toMatch(
      /work\.kind === 'local_completed' \? 'uploads' : 'review'/,
    );
    expect(app).toMatch(/work\.kind === 'capture_review' \|\| work\.kind === 'local_completed'/);
    expect(app).toMatch(/forceNewCapture/);
    expect(app).toMatch(/forceClear:\s*true/);
    expect(app).toMatch(/contentPaddingBottom=\{footerHeight\}/);
    expect(app).toMatch(/onLayout/);
  });

  it('ReviewScreen keeps ZIP enabled except while exporting', () => {
    const review = read('src/screens/ReviewScreen.tsx');
    expect(review).toMatch(/canExportSession/);
    expect(review).toMatch(/runLocalCsvExport/);
    expect(review).toMatch(/isLocalCompleted/);
    expect(review).toMatch(/Exportar ZIP/);
    expect(review).toMatch(/Guardar captura/);
    expect(review).not.toMatch(/Subir fotos y resultados/);
    expect(review).not.toMatch(/Continuar carga al servidor/);
    expect(review).toMatch(/disabled=\{exportBusy \|\| !sessionId \|\| !services\.localCsvExport\}/);
    expect(review).not.toMatch(/disabled=\{!exportGate\.ok/);
  });

  it('LocalActivityScreen offers Exportar ZIP for any session with CSV export', () => {
    const activity = read('src/screens/LocalActivityScreen.tsx');
    expect(activity).toMatch(/Exportar ZIP/);
    expect(activity).toMatch(/runLocalCsvExport/);
    expect(activity).toMatch(/csvExport && services\.localCsvExport/);
    expect(activity).not.toMatch(/exportableKind &&/);
  });

  it('CaptureService exposes startNewSession / forceNew and does not delete on prepare', () => {
    const svc = read('src/features/capture/captureService.ts');
    expect(svc).toMatch(/startNewSession/);
    expect(svc).toMatch(/forceNew/);
    expect(svc).toMatch(/prepareNewCapture\([\s\S]*forceClear/);
    expect(svc).not.toMatch(/DELETE FROM capture_sessions/);
  });

  it('Shell uses SafeAreaView and keyboard-aware scroll options', () => {
    const ui = read('src/ui/primitives.tsx');
    expect(ui).toMatch(/SafeAreaView/);
    expect(ui).toMatch(/useSafeAreaInsets/);
    expect(ui).toMatch(/KeyboardAvoidingView/);
    expect(ui).toMatch(/PasswordInput/);
    expect(ui).toMatch(/scroll\??:/);
  });

  it('LoginScreen toggles password visibility with a11y labels', () => {
    const login = read('src/screens/LoginScreen.tsx');
    expect(login).toMatch(/passwordVisible/);
    expect(login).toMatch(/PasswordInput/);
    expect(login).toMatch(/scroll/);
    expect(login).toMatch(/keyboardAware/);
    const primitives = read('src/ui/primitives.tsx');
    expect(primitives).toMatch(/Ocultar contraseña/);
    expect(primitives).toMatch(/Mostrar contraseña/);
    expect(primitives).toMatch(/secureTextEntry=\{!visible\}/);
  });

  it('index wraps App with SafeAreaProvider', () => {
    const index = read('index.ts');
    expect(index).toMatch(/SafeAreaProvider/);
  });
});
