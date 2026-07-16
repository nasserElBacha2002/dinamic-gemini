import { compareCursor, cursorFromMarker, EMPTY_CURSOR, type CompositeCursor } from '../../core/compositeCursor';
import { createLogger, type Logger } from '../../core/logging';
import { detectNewPhotos } from '../../core/photoDetection';
import { createScanCoordinator, type ScanCoordinator } from '../../core/scanCoordinator';
import type { CaptureMarker } from '../../domain/entities/captureMarker';
import type { GalleryImage } from '../../domain/entities/galleryImage';
import type { CapturePhotoStatus } from '../../domain/enums/photoStatus';
import { CaptureRepository } from '../../database/repositories/captureRepository';
import type { CapturePhotoRow, CaptureSessionRow } from '../../database/schema/captureSchema';
import { cursorFromSession, imageFromPhotoRow } from '../../database/schema/captureSchema';
import type { ForegroundService } from '../../native/foregroundService';
import type { PermissionState } from '../../native/mediaStore';
import { queryMostRecentPhoto, queryNewPhotosSince, subscribeToGalleryChanges } from '../../native/mediaStore';
import { probeStability } from '../../native/stabilityProber';
import type { ScanMetrics } from '../../core/incrementalScan';
import { emptyScanMetrics } from '../../core/incrementalScan';

export interface StartCaptureInput {
  readonly inventoryId: string;
  readonly inventoryName: string;
  readonly aisleId: string;
  readonly aisleName: string;
  readonly permission: PermissionState;
}

export interface CaptureSnapshot {
  readonly session: CaptureSessionRow | null;
  readonly photos: CapturePhotoRow[];
  readonly scanCursor: CompositeCursor;
  readonly lastValidCursor: CompositeCursor;
  readonly metrics: ScanMetrics;
  readonly scanInProgress: boolean;
  readonly pendingScan: boolean;
  readonly fgsActive: boolean;
}

type Listener = (snapshot: CaptureSnapshot) => void;

export class CaptureService {
  private session: CaptureSessionRow | null = null;
  private photos: CapturePhotoRow[] = [];
  private scanCursor: CompositeCursor = EMPTY_CURSOR;
  private lastValidCursor: CompositeCursor = EMPTY_CURSOR;
  private inspectedIds = new Set<string>();
  private coordinator: ScanCoordinator;
  private subscription: { remove: () => void } | null = null;
  private listeners = new Set<Listener>();
  private metrics: ScanMetrics = emptyScanMetrics();
  private fgsActive = false;
  private cancelled = false;

  constructor(
    private readonly repo: CaptureRepository,
    private readonly foregroundService: ForegroundService,
    private readonly logger: Logger = createLogger(),
  ) {
    this.coordinator = createScanCoordinator(() => this.runScanOnce());
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    listener(this.snapshot());
    return () => this.listeners.delete(listener);
  }

  async restoreLatestOpen(): Promise<CaptureSessionRow | null> {
    const [session] = await this.repo.listOpenSessions();
    if (!session) {
      this.emit();
      return null;
    }
    await this.loadSession(session.id, false);
    this.logger.info('recovery', { sessionId: session.id, status: session.status });
    return session;
  }

  async loadSession(sessionId: string, startListener: boolean): Promise<void> {
    const session = await this.repo.getSession(sessionId);
    if (!session) {
      throw new Error('No se encontró la sesión local.');
    }
    this.session = session;
    this.photos = await this.repo.listPhotos(session.id);
    this.scanCursor = cursorFromSession(session, 'scan');
    this.lastValidCursor = cursorFromSession(session, 'lastValid');
    this.inspectedIds = await this.repo.inspectedAssetIds(session.id);
    this.cancelled = session.status !== 'active';
    if (startListener && session.status === 'active') {
      await this.startForeground();
      this.attachListener();
    }
    this.emit();
  }

  async start(input: StartCaptureInput): Promise<void> {
    if (!input.permission.granted) {
      throw new Error('Se requieren permisos de fotografías.');
    }
    const existing = await this.repo.findOpenSessionForAisle(input.inventoryId, input.aisleId);
    if (existing && existing.status !== 'completed' && existing.status !== 'cancelled') {
      await this.loadSession(existing.id, existing.status === 'active');
      return;
    }
    const recent = await queryMostRecentPhoto();
    const marker: CaptureMarker = {
      assetId: recent?.assetId ?? null,
      mediaStoreNumericId: recent?.mediaStoreNumericId ?? null,
      dateAdded: recent?.dateAdded ?? null,
      dateModified: recent?.dateModified ?? null,
      displayName: recent?.displayName ?? null,
      size: recent?.size ?? null,
      bucketId: recent?.bucketId ?? null,
      inventoryId: input.inventoryId,
      aisleId: input.aisleId,
    };
    const session = await this.repo.createSession({
      id: createId(),
      inventoryId: input.inventoryId,
      inventoryName: input.inventoryName,
      aisleId: input.aisleId,
      aisleName: input.aisleName,
      marker,
    });
    this.session = session;
    this.photos = [];
    this.scanCursor = cursorFromMarker(marker);
    this.lastValidCursor = this.scanCursor;
    this.inspectedIds = new Set(recent?.assetId ? [recent.assetId] : []);
    this.cancelled = false;
    await this.startForeground();
    this.attachListener();
    this.logger.info('session_start', { sessionId: session.id, inventoryId: input.inventoryId, aisleId: input.aisleId });
    this.emit();
  }

  async pause(): Promise<void> {
    if (!this.session) return;
    this.detachListener();
    await this.repo.updateSessionStatus(this.session.id, 'paused');
    await this.foregroundService.update(this.notificationContent('Pausada'));
    await this.loadSession(this.session.id, false);
  }

  async resume(): Promise<void> {
    if (!this.session) return;
    await this.repo.updateSessionStatus(this.session.id, 'active');
    await this.loadSession(this.session.id, true);
    void this.requestScan();
  }

  async finish(): Promise<void> {
    if (!this.session) return;
    await this.repo.updateSessionStatus(this.session.id, 'finishing');
    await this.requestScan();
    this.detachListener();
    this.cancelled = true;
    await this.stopForeground();
    await this.repo.updateSessionStatus(this.session.id, 'review');
    await this.loadSession(this.session.id, false);
    this.logger.info('session_finish', { sessionId: this.session.id });
  }

  async completeReview(): Promise<void> {
    if (!this.session) return;
    if (this.photos.some((p) => p.status === 'waiting_stability')) {
      throw new Error('Todavía hay fotografías validándose.');
    }
    if (this.photos.some((p) => p.status === 'unstable' || p.status === 'undecodable')) {
      throw new Error('Resolvé o excluí los errores antes de confirmar.');
    }
    await this.repo.updateSessionStatus(this.session.id, 'completed', true);
    await this.loadSession(this.session.id, false);
  }

  async cancel(): Promise<void> {
    if (!this.session) return;
    this.detachListener();
    this.cancelled = true;
    await this.stopForeground();
    await this.repo.updateSessionStatus(this.session.id, 'cancelled', true);
    await this.loadSession(this.session.id, false);
  }

  async exclude(assetId: string): Promise<void> {
    if (!this.session) return;
    await this.repo.updatePhotoStatus(this.session.id, assetId, 'excluded');
    await this.reloadPhotos();
  }

  async reincorporate(assetId: string): Promise<void> {
    if (!this.session) return;
    const row = this.photos.find((p) => p.asset_id === assetId);
    if (!row) return;
    await this.repo.updatePhotoStatus(this.session.id, assetId, 'waiting_stability');
    await this.reloadPhotos();
    void this.validateImage(imageFromPhotoRow(row));
  }

  async retryErrors(): Promise<void> {
    for (const row of this.photos) {
      if (row.status === 'unstable' || row.status === 'undecodable') {
        await this.repo.updatePhotoStatus(row.capture_session_id, row.asset_id, 'waiting_stability');
        void this.validateImage(imageFromPhotoRow(row));
      }
    }
    await this.reloadPhotos();
  }

  requestScan(): Promise<void> {
    return this.coordinator.request();
  }

  private async runScanOnce(): Promise<void> {
    if (!this.session || this.session.status !== 'active') {
      return;
    }
    const { images, metrics } = await queryNewPhotosSince({ scanCursor: this.scanCursor });
    this.metrics = metrics;
    const result = detectNewPhotos({
      candidates: images,
      scanCursor: this.scanCursor,
      inspectedIds: this.inspectedIds,
    });
    result.inspectedIds.forEach((id) => this.inspectedIds.add(id));
    this.scanCursor = result.nextScanCursor;
    await this.repo.updateScanCursor(this.session.id, this.scanCursor);
    for (const rejected of result.rejected) {
      this.logger.info('photo_ignored', { assetId: rejected.assetId, reason: rejected.reason });
    }
    for (const image of result.admitted) {
      await this.repo.upsertPhoto(this.session.id, image, 'detected');
      await this.repo.upsertPhoto(this.session.id, image, 'waiting_stability');
      void this.validateImage(image);
    }
    await this.reloadPhotos();
  }

  private async validateImage(image: GalleryImage): Promise<void> {
    if (!this.session || this.cancelled) return;
    const outcome = await probeStability(image.uri);
    if (!this.session || this.cancelled) return;
    if (outcome.ok) {
      await this.repo.updatePhotoStatus(this.session.id, image.assetId, 'stable');
      const cursor = { dateAdded: image.dateAdded, assetId: image.assetId };
      if (compareCursor(cursor, this.lastValidCursor) > 0) {
        this.lastValidCursor = cursor;
        await this.repo.updateLastValidCursor(this.session.id, cursor);
      }
      this.logger.info('photo_detected', { assetId: image.assetId, status: 'stable' });
    } else {
      const status: CapturePhotoStatus = outcome.reason === 'undecodable' ? 'undecodable' : 'unstable';
      await this.repo.updatePhotoStatus(this.session.id, image.assetId, status, outcome.reason);
      this.logger.warn('file_unstable', { assetId: image.assetId, reason: outcome.reason });
    }
    await this.reloadPhotos();
    await this.updateForeground();
  }

  private async reloadPhotos(): Promise<void> {
    if (!this.session) return;
    this.photos = await this.repo.listPhotos(this.session.id);
    this.emit();
  }

  private attachListener(): void {
    this.detachListener();
    this.subscription = subscribeToGalleryChanges(() => {
      void this.requestScan();
    });
  }

  private detachListener(): void {
    this.subscription?.remove();
    this.subscription = null;
  }

  private async startForeground(): Promise<void> {
    if (!this.foregroundService.isAvailable) {
      return;
    }
    await this.foregroundService.start(this.notificationContent('Activa'));
    this.fgsActive = true;
  }

  private async updateForeground(): Promise<void> {
    if (!this.foregroundService.isAvailable || !this.fgsActive) return;
    await this.foregroundService.update(this.notificationContent('Activa'));
  }

  private async stopForeground(): Promise<void> {
    if (!this.foregroundService.isAvailable) return;
    await this.foregroundService.stop();
    this.fgsActive = false;
  }

  private notificationContent(_state: string) {
    const session = this.session;
    return {
      inventoryName: session?.inventory_name ?? 'Inventario',
      aisleName: session?.aisle_name ?? 'Pasillo',
      detected: this.photos.length,
      stable: this.photos.filter((p) => p.status === 'stable').length,
      pending: this.photos.filter((p) => p.status === 'waiting_stability' || p.status === 'detected').length,
    };
  }

  private snapshot(): CaptureSnapshot {
    return {
      session: this.session,
      photos: this.photos,
      scanCursor: this.scanCursor,
      lastValidCursor: this.lastValidCursor,
      metrics: this.metrics,
      scanInProgress: this.coordinator.isInProgress,
      pendingScan: this.coordinator.hasPending,
      fgsActive: this.fgsActive,
    };
  }

  private emit(): void {
    const snap = this.snapshot();
    this.listeners.forEach((listener) => listener(snap));
  }
}

function createId(): string {
  return `cap_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

