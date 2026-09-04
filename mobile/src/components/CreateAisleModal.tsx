import { useEffect, useState } from 'react';
import { FlatList, Modal, Text, TouchableOpacity, View } from 'react-native';

import { canUseSupplierOffline } from '../features/aisles/canUseSupplierOffline';
import { getAisleCreationRules } from '../features/aisles/aisleCreationRules';
import { userMessageForLocalAisleError } from '../features/aisles/localAisleErrors';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import type { AisleDto, ClientSupplierDto, InventoryListItemDto } from '../services/api/types';
import { Button, ErrorText, Input, SmallButton, messageOf, styles } from '../ui';

type SupplierListState =
  | { status: 'idle'; items: ClientSupplierDto[] }
  | { status: 'loading'; items: ClientSupplierDto[] }
  | { status: 'success'; items: ClientSupplierDto[] }
  | { status: 'error'; items: ClientSupplierDto[]; message: string };

export interface CreateAisleModalProps {
  visible: boolean;
  services: AppServices;
  inventory: InventoryListItemDto;
  connectivity: 'online' | 'offline' | 'unknown';
  onClose: () => void;
  onCreated: (created: AisleDto) => void;
}

export function CreateAisleModal({
  visible,
  services,
  inventory,
  connectivity,
  onClose,
  onCreated,
}: CreateAisleModalProps) {
  const rules = getAisleCreationRules(inventory);
  const offlineCreate = connectivity === 'offline';
  const [createCode, setCreateCode] = useState('');
  const [createSupplierId, setCreateSupplierId] = useState('');
  const [suppliers, setSuppliers] = useState<SupplierListState>({ status: 'idle', items: [] });
  const [supplierReady, setSupplierReady] = useState<boolean | null>(null);
  const [supplierReadyMessage, setSupplierReadyMessage] = useState<string | null>(null);
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const loadSuppliers = () => {
    if (!inventory.client_id) {
      setSuppliers({
        status: 'error',
        items: [],
        message: rules.reason,
      });
      return;
    }
    let cancelled = false;
    setSuppliers({ status: 'loading', items: [] });
    void services.clients
      .listSuppliers(inventory.client_id, { pageSize: 200 })
      .then((res) => {
        if (cancelled) return;
        setSuppliers({ status: 'success', items: res.items });
        if (res.items[0]) setCreateSupplierId(res.items[0].id);
      })
      .catch((e) => {
        if (cancelled) return;
        setSuppliers({ status: 'error', items: [], message: messageOf(e) });
      });
    return () => {
      cancelled = true;
    };
  };

  useEffect(() => {
    if (!visible) return;
    setCreateError(null);
    setCreateCode('');
    setCreateSupplierId('');
    setSupplierReady(null);
    setSupplierReadyMessage(null);
    setSuppliers({ status: 'idle', items: [] });
    if (rules.supplierRequired) {
      return loadSuppliers();
    }
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, inventory.id, inventory.client_id, services]);

  useEffect(() => {
    if (!visible || !offlineCreate || !createSupplierId || !inventory.client_id) {
      setSupplierReady(null);
      setSupplierReadyMessage(null);
      return;
    }
    let cancelled = false;
    void canUseSupplierOffline({
      inventoryId: inventory.id,
      inventoryClientId: inventory.client_id,
      clientSupplierId: createSupplierId,
      catalog: services.catalogRepo,
      recognitionRepo: services.offlineRecognition.repo,
    }).then((readiness) => {
      if (cancelled) return;
      setSupplierReady(readiness.status === 'READY_OFFLINE');
      setSupplierReadyMessage(readiness.message);
    });
    return () => {
      cancelled = true;
    };
  }, [visible, offlineCreate, createSupplierId, inventory, services]);

  const submitCreate = () => {
    if (createBusy) return;
    const code = createCode.trim();
    if (!code) {
      setCreateError('El código del pasillo es obligatorio.');
      return;
    }
    if (code.length > 64) {
      setCreateError('El código del pasillo supera el máximo permitido (64).');
      return;
    }
    if (rules.supplierRequired && !createSupplierId.trim()) {
      setCreateError(rules.reason);
      return;
    }
    if (offlineCreate && supplierReady === false) {
      setCreateError(
        supplierReadyMessage ??
          'Proveedor no está listo para trabajar offline.',
      );
      return;
    }
    setCreateError(null);
    setCreateBusy(true);
    const payload = {
      inventoryId: inventory.id,
      code,
      clientSupplierId: createSupplierId.trim() || null,
    };
    const createPromise = offlineCreate
      ? services.aisles.createLocal(payload)
      : services.aisles.create(payload);
    void createPromise
      .then((created) => {
        onClose();
        onCreated(created);
      })
      .catch((e) => {
        setCreateError(
          offlineCreate ? userMessageForLocalAisleError(e) : messageOf(e),
        );
      })
      .finally(() => setCreateBusy(false));
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={styles.modalBackdrop}>
        <View style={styles.modalCard}>
          <Text style={styles.h2}>Crear pasillo</Text>
          {offlineCreate ? (
            <Text style={styles.notif}>
              Modo sin conexión: el pasillo se guardará solo en este dispositivo.
            </Text>
          ) : null}
          {createError ? <ErrorText text={createError} /> : null}
          <Text style={styles.muted}>{rules.reason}</Text>
          <Input placeholder="Código del pasillo" value={createCode} onChangeText={setCreateCode} />
          {rules.supplierRequired ? (
            <>
              <Text style={styles.row}>Proveedor</Text>
              {suppliers.status === 'loading' ? <Text style={styles.muted}>Cargando proveedores…</Text> : null}
              {suppliers.status === 'error' ? (
                <>
                  <ErrorText text={suppliers.message} />
                  <SmallButton label="Reintentar" onPress={loadSuppliers} />
                </>
              ) : null}
              {suppliers.status === 'success' && suppliers.items.length === 0 ? (
                <ErrorText text="No hay proveedores sincronizados disponibles." />
              ) : null}
              {suppliers.items.length > 0 ? (
                <FlatList
                  data={suppliers.items}
                  keyExtractor={(s) => s.id}
                  style={styles.pickerList}
                  renderItem={({ item: supplier }) => (
                    <TouchableOpacity
                      style={[styles.pickerItem, createSupplierId === supplier.id && styles.pickerItemActive]}
                      onPress={() => setCreateSupplierId(supplier.id)}
                    >
                      <Text style={styles.row}>{supplier.name}</Text>
                    </TouchableOpacity>
                  )}
                />
              ) : null}
              {offlineCreate && supplierReady === false && supplierReadyMessage ? (
                <ErrorText text={supplierReadyMessage} />
              ) : null}
            </>
          ) : null}
          <View style={styles.nav}>
            <SmallButton label="Cancelar" onPress={onClose} />
            <Button
              label={createBusy ? 'Creando…' : 'Crear'}
              disabled={
                createBusy ||
                !createCode.trim() ||
                (rules.supplierRequired &&
                  (!createSupplierId ||
                    suppliers.status !== 'success' ||
                    suppliers.items.length === 0 ||
                    (offlineCreate && supplierReady === false)))
              }
              onPress={submitCreate}
            />
          </View>
        </View>
      </View>
    </Modal>
  );
}
