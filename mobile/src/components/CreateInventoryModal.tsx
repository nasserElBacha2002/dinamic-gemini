import { useEffect, useState } from 'react';
import { FlatList, Modal, Text, TouchableOpacity, View } from 'react-native';

import type { AppServices } from '../runtime/bootstrap/createAppServices';
import type { ClientDto, InventoryListItemDto } from '../services/api/types';
import { Button, ErrorText, Input, SmallButton, messageOf, styles } from '../ui';

type ClientListState =
  | { status: 'idle'; items: ClientDto[] }
  | { status: 'loading'; items: ClientDto[] }
  | { status: 'success'; items: ClientDto[] }
  | { status: 'error'; items: ClientDto[]; message: string };

export interface CreateInventoryModalProps {
  visible: boolean;
  services: AppServices;
  onClose: () => void;
  onCreated: (created: InventoryListItemDto) => void;
}

export function CreateInventoryModal({ visible, services, onClose, onCreated }: CreateInventoryModalProps) {
  const [createName, setCreateName] = useState('');
  const [createClientId, setCreateClientId] = useState('');
  const [createMode, setCreateMode] = useState<'production' | 'test'>('production');
  const [clients, setClients] = useState<ClientListState>({ status: 'idle', items: [] });
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const loadClients = () => {
    let cancelled = false;
    setClients({ status: 'loading', items: [] });
    void services.clients
      .list({ pageSize: 100 })
      .then((res) => {
        if (cancelled) return;
        setClients({ status: 'success', items: res.items });
        if (res.items[0]) setCreateClientId(res.items[0].id);
      })
      .catch((e) => {
        if (cancelled) return;
        setClients({ status: 'error', items: [], message: messageOf(e) });
      });
    return () => {
      cancelled = true;
    };
  };

  useEffect(() => {
    if (!visible) return;
    setCreateError(null);
    setCreateName('');
    setCreateClientId('');
    setCreateMode('production');
    setClients({ status: 'idle', items: [] });
    return loadClients();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, services]);

  const submitCreate = () => {
    if (createBusy) return;
    const name = createName.trim();
    if (!name) {
      setCreateError('El nombre del inventario es obligatorio.');
      return;
    }
    if (name.length > 255) {
      setCreateError('El nombre del inventario supera el máximo permitido (255).');
      return;
    }
    if (!createClientId.trim()) {
      setCreateError('Seleccioná un cliente.');
      return;
    }
    setCreateError(null);
    setCreateBusy(true);
    void services.inventories
      .create({ name, clientId: createClientId, processingMode: createMode })
      .then((created) => {
        onClose();
        onCreated(created);
      })
      .catch((e) => setCreateError(messageOf(e)))
      .finally(() => setCreateBusy(false));
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={styles.modalBackdrop}>
        <View style={styles.modalCard}>
          <Text style={styles.h2}>Crear inventario</Text>
          {createError ? <ErrorText text={createError} /> : null}
          <Input placeholder="Nombre del inventario" value={createName} onChangeText={setCreateName} />
          <Text style={styles.row}>Cliente</Text>
          {clients.status === 'loading' ? <Text style={styles.muted}>Cargando clientes…</Text> : null}
          {clients.status === 'error' ? (
            <>
              <ErrorText text={clients.message} />
              <SmallButton label="Reintentar" onPress={loadClients} />
            </>
          ) : null}
          {clients.status === 'success' && clients.items.length === 0 ? (
            <ErrorText text="No hay clientes disponibles." />
          ) : null}
          {clients.items.length > 0 ? (
            <FlatList
              data={clients.items}
              keyExtractor={(c) => c.id}
              style={styles.pickerList}
              renderItem={({ item: client }) => (
                <TouchableOpacity
                  style={[styles.pickerItem, createClientId === client.id && styles.pickerItemActive]}
                  onPress={() => setCreateClientId(client.id)}
                >
                  <Text style={styles.row}>{client.name}</Text>
                </TouchableOpacity>
              )}
            />
          ) : null}
          <View style={styles.nav}>
            <SmallButton
              label="Producción"
              onPress={() => setCreateMode('production')}
              disabled={createMode === 'production'}
            />
            <SmallButton label="Test" onPress={() => setCreateMode('test')} disabled={createMode === 'test'} />
          </View>
          <View style={styles.nav}>
            <SmallButton label="Cancelar" onPress={onClose} />
            <Button
              label={createBusy ? 'Creando…' : 'Crear'}
              disabled={createBusy || !createName.trim() || !createClientId || clients.status !== 'success'}
              onPress={submitCreate}
            />
          </View>
        </View>
      </View>
    </Modal>
  );
}
