import { useState } from 'react';

import type { AuthSession } from '../features/auth/authService';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import { Button, ErrorText, Input, PasswordInput, Shell, messageOf } from '../ui';

export interface LoginScreenProps {
  services: AppServices;
  onLoggedIn: (session: AuthSession) => void;
}

export function LoginScreen({ services, onLoggedIn }: LoginScreenProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Shell title="Iniciar sesión" scroll keyboardAware>
      {error ? <ErrorText text={error} /> : null}
      <Input
        placeholder="Usuario"
        value={username}
        onChangeText={setUsername}
        autoCapitalize="none"
        autoCorrect={false}
        editable={!busy}
      />
      <PasswordInput
        value={password}
        onChangeText={setPassword}
        visible={passwordVisible}
        onToggleVisible={() => setPasswordVisible((v) => !v)}
        editable={!busy}
      />
      <Button
        label={busy ? 'Ingresando...' : 'Ingresar'}
        disabled={busy || !username.trim() || !password}
        onPress={() => {
          setBusy(true);
          setError(null);
          void services.auth
            .login(username.trim(), password)
            .then(onLoggedIn)
            .catch((e) => setError(messageOf(e)))
            .finally(() => setBusy(false));
        }}
      />
    </Shell>
  );
}
