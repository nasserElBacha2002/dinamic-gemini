/**
 * Client-scoped positioning labels — list / search / detail (no inventory/aisle).
 * Signing and QR generation stay on the backend.
 */

import { useCallback, useEffect, useState } from 'react';
import { FlatList, Text, View } from 'react-native';

import {
  ClientPositionLabelService,
  type ClientPositionLabelDto,
} from '../api/clientPositionLabelsApi';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import { ErrorText, Input, SmallButton, messageOf, styles } from '../ui';

export interface ClientPositionLabelsScreenProps {
  services: AppServices;
  clientId: string;
  clientName?: string;
  onBack: () => void;
}

export function ClientPositionLabelsScreen({
  services,
  clientId,
  clientName = '',
  onBack,
}: ClientPositionLabelsScreenProps): JSX.Element {
  const [items, setItems] = useState<ClientPositionLabelDto[]>([]);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<ClientPositionLabelDto | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const labelService = useCallback(
    () => new ClientPositionLabelService(services.api),
    [services.api],
  );

  const reload = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await labelService().list(clientId, {
        ...(search.trim() ? { search: search.trim() } : {}),
        page: 1,
        pageSize: 100,
      });
      setItems(res.items);
    } catch (e) {
      setError(messageOf(e));
      setItems([]);
    } finally {
      setBusy(false);
    }
  }, [clientId, labelService, search]);

  useEffect(() => {
    void reload();
  }, [reload]);

  if (selected) {
    return (
      <View>
        <SmallButton label="← Lista" onPress={() => setSelected(null)} />
        <Text style={styles.h2}>Detalle de etiqueta</Text>
        <Text style={styles.row}>Nombre: {selected.name}</Text>
        <Text style={styles.muted}>
          Descripción: {selected.description?.trim() ? selected.description : '—'}
        </Text>
        <Text style={styles.muted}>ID: {selected.public_identifier}</Text>
        <Text style={styles.muted}>Estado: {selected.status}</Text>
        <Text style={styles.muted}>
          Creada: {new Date(selected.created_at).toLocaleString('es-AR')}
        </Text>
        <Text style={[styles.muted, { marginTop: 8 }]}>
          La firma y el QR se generan en el servidor. Descarga desde la web del cliente si
          necesitás PDF/PNG.
        </Text>
      </View>
    );
  }

  return (
    <View style={{ flex: 1 }}>
      <SmallButton label="← Pasillos" onPress={onBack} />
      <Text style={styles.h2}>Etiquetas de posicionamiento</Text>
      <Text style={styles.muted}>
        {clientName ? `Cliente: ${clientName}` : `Cliente ${clientId}`}
      </Text>
      <Text style={styles.muted}>
        Independientes del inventario. Se reutilizan en todos los inventarios del cliente.
      </Text>
      <Input
        value={search}
        onChangeText={setSearch}
        placeholder="Buscar por nombre o ID"
      />
      <View style={styles.nav}>
        <SmallButton
          label={busy ? 'Cargando…' : 'Actualizar'}
          disabled={busy}
          onPress={() => void reload()}
        />
      </View>
      {error ? <ErrorText text={error} /> : null}
      <FlatList
        data={items}
        keyExtractor={(item) => item.id}
        ListEmptyComponent={
          !busy ? (
            <Text style={styles.muted}>Este cliente todavía no tiene etiquetas de posicionamiento.</Text>
          ) : null
        }
        renderItem={({ item }) => (
          <View style={[styles.pickerItem, { marginTop: 6 }]}>
            <Text style={styles.row}>{item.name}</Text>
            <Text style={styles.muted}>
              {item.status} · {item.public_identifier}
            </Text>
            <SmallButton label="Ver detalle" onPress={() => setSelected(item)} />
          </View>
        )}
      />
    </View>
  );
}
