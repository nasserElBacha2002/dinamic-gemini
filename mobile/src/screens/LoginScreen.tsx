import { useState } from 'react';

import type { AuthSession } from '../features/auth/authService';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import { Button, ErrorText, Input, Shell, messageOf } from '../ui';

export interface LoginScreenProps {
  services: AppServices;
  onLoggedIn: (session: AuthSession) => void;
}

export function LoginScreen({ services, onLoggedIn }: LoginScreenProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Shell title="Iniciar sesión">
      {error ? <ErrorText text={error} /> : null}
      <Input placeholder="Usuario" value={username} onChangeText={setUsername} />
      <Input placeholder="Contraseña" value={password} onChangeText={setPassword} secureTextEntry />
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
