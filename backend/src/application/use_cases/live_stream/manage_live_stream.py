"""Live stream use cases — DIN-508 Phase 3."""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.clock import Clock
from src.application.ports.live_stream_repository import LiveStreamRepository
from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.application.services.live_stream_aisle_channel_resolver import (
    LiveStreamAisleChannelResolver,
    ResolvedLiveChannel,
)
from src.application.services.live_stream_credential_crypto import (
    derive_channel_password,
    derive_public_grant_password,
    hash_live_stream_secret,
    hash_public_token,
    mint_public_token,
    mint_public_view_username,
    mint_readable_stream_username,
)
from src.application.services.live_stream_mediamtx_control import LiveStreamMediaMtxControl
from src.application.services.live_stream_status_service import (
    LiveStreamStatusService,
    LiveStreamStatusSnapshot,
)
from src.domain.live_stream.entities import LiveChannelCredentials, LiveViewGrant


@dataclass(frozen=True)
class PreparedLiveChannelResult:
    channel: ResolvedLiveChannel
    rtmp_publish_url: str
    publish_username: str
    publish_password: str
    read_username: str
    read_password: str
    hls_playlist_url: str
    status: LiveStreamStatusSnapshot


@dataclass(frozen=True)
class PublicLivePlaybackTicket:
    presence: str
    hls_playlist_url: str
    view_username: str
    view_password: str
    expires_at: object
    publish_blocked: bool = False


@dataclass(frozen=True)
class PublicLiveGrantItem:
    grant_id: str
    expires_at: object
    revoked_at: object | None
    created_at: object


@dataclass(frozen=True)
class CreatedPublicGrantResult:
    grant_id: str
    public_url: str
    public_token: str
    expires_at: object
    view_username: str
    view_password: str


@dataclass(frozen=True)
class StopTransmissionResult:
    channel: ResolvedLiveChannel
    status: LiveStreamStatusSnapshot
    publisher_kicked: bool


class ManageLiveStreamUseCase:
    def __init__(
        self,
        *,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository | None,
        live_repo: LiveStreamRepository,
        clock: Clock,
        enabled: bool,
        server_secret: str,
        rtmp_publish_base_url: str,
        hls_public_base_url: str,
        status_service: LiveStreamStatusService,
        mediamtx_control: LiveStreamMediaMtxControl,
        public_link_base_url: str,
        public_grant_default_ttl_hours: int,
        fixed_publish_username: str = "",
        fixed_publish_password: str = "",
        fixed_read_username: str = "",
        fixed_read_password: str = "",
        mediamtx_hls_internal_url: str = "",
    ) -> None:
        self._inventory_repo = inventory_repo
        self._access = InventoryAccessPolicy(inventory_repo, aisle_repo=aisle_repo)
        self._resolver = LiveStreamAisleChannelResolver(
            aisle_repo=aisle_repo,
            inventory_repo=inventory_repo,
        )
        self._live_repo = live_repo
        self._clock = clock
        self._enabled = enabled
        self._server_secret = server_secret
        self._rtmp_base = rtmp_publish_base_url.rstrip("/")
        self._hls_base = hls_public_base_url.rstrip("/")
        self._status = status_service
        self._mtx_control = mediamtx_control
        self._public_link_base = public_link_base_url.rstrip("/")
        self._grant_ttl_hours = max(1, public_grant_default_ttl_hours)
        self._fixed_publish_user = (fixed_publish_username or "").strip()
        self._fixed_publish_password = fixed_publish_password or ""
        self._fixed_read_user = (fixed_read_username or "").strip()
        self._fixed_read_password = fixed_read_password or ""
        self._mediamtx_hls_internal = (mediamtx_hls_internal_url or "").strip().rstrip("/")

    @property
    def hls_proxy_enabled(self) -> bool:
        return bool(self._mediamtx_hls_internal)

    def _resolve_channel_credentials(
        self,
        *,
        inv_name: str,
        resolved: ResolvedLiveChannel,
    ) -> tuple[str, str, str, str]:
        if self._fixed_publish_user and self._fixed_publish_password:
            pub_user = self._fixed_publish_user
            pub_pass = self._fixed_publish_password
            read_user = self._fixed_read_user or pub_user
            read_pass = self._fixed_read_password or pub_pass
            return pub_user, pub_pass, read_user, read_pass
        publish_user = mint_readable_stream_username(
            "pub",
            inventory_name=inv_name,
            aisle_code=resolved.canonical_aisle_code,
        )
        read_user = mint_readable_stream_username(
            "view",
            inventory_name=inv_name,
            aisle_code=resolved.canonical_aisle_code,
        )
        publish_password = derive_channel_password(
            server_secret=self._server_secret,
            mediamtx_path=resolved.mediamtx_path,
            purpose="publish",
        )
        read_password = derive_channel_password(
            server_secret=self._server_secret,
            mediamtx_path=resolved.mediamtx_path,
            purpose="read",
        )
        return publish_user, publish_password, read_user, read_password

    def _require_enabled(self) -> None:
        from src.application.errors import LiveStreamDisabledError

        if not self._enabled:
            raise LiveStreamDisabledError("Live stream integration is disabled")

    def _enrich_status(
        self,
        probe: LiveStreamStatusSnapshot,
        *,
        publish_blocked: bool,
    ) -> LiveStreamStatusSnapshot:
        presence = probe.presence
        if publish_blocked and probe.presence == "live":
            presence = "ended"
        elif publish_blocked and probe.presence in ("connecting", "reconnecting"):
            presence = "ended"
        return LiveStreamStatusSnapshot(
            presence=presence,
            publisher_ready=probe.publisher_ready and not publish_blocked,
            bytes_received=probe.bytes_received,
            publish_blocked=publish_blocked,
        )

    def _channel_status(
        self, *, mediamtx_path: str, creds: LiveChannelCredentials | None
    ) -> LiveStreamStatusSnapshot:
        blocked = bool(creds is not None and creds.publish_blocked)
        probe = self._status.probe(mediamtx_path=mediamtx_path)
        return self._enrich_status(probe, publish_blocked=blocked)

    def prepare_channel(
        self,
        *,
        inventory_id: str,
        aisle_code: str,
        principal: AccessPrincipal,
    ) -> PreparedLiveChannelResult:
        self._require_enabled()
        self._access.require_inventory(inventory_id, principal)
        resolved = self._resolver.resolve(inventory_id=inventory_id, aisle_code=aisle_code)
        now = self._clock.now()
        existing = self._live_repo.get_channel_credentials(
            inventory_id=resolved.inventory_id, channel_slug=resolved.channel_slug
        )
        inventory = self._inventory_repo.get_by_id(resolved.inventory_id)
        inv_name = inventory.name if inventory is not None else ""
        publish_user, publish_password, read_user, read_password = self._resolve_channel_credentials(
            inv_name=inv_name,
            resolved=resolved,
        )
        record = LiveChannelCredentials(
            id=existing.id if existing else str(uuid4()),
            inventory_id=resolved.inventory_id,
            canonical_aisle_code=resolved.canonical_aisle_code,
            channel_slug=resolved.channel_slug,
            mediamtx_path=resolved.mediamtx_path,
            publish_username=publish_user,
            publish_password_hash=hash_live_stream_secret(publish_password),
            read_username=read_user,
            read_password_hash=hash_live_stream_secret(read_password),
            created_by_principal_id=(
                existing.created_by_principal_id if existing else principal.actor_id
            ),
            created_at=existing.created_at if existing else now,
            updated_at=now,
            publish_blocked_at=None,
            publish_blocked_by_principal_id=None,
        )
        self._live_repo.upsert_channel_credentials(record)
        status = self._channel_status(mediamtx_path=resolved.mediamtx_path, creds=record)
        return PreparedLiveChannelResult(
            channel=resolved,
            rtmp_publish_url=self._build_rtmp_url(resolved.mediamtx_path),
            publish_username=publish_user,
            publish_password=publish_password,
            read_username=read_user,
            read_password=read_password,
            hls_playlist_url=self._build_viewer_hls_playlist_url(
                inventory_id=resolved.inventory_id,
                canonical_aisle_code=resolved.canonical_aisle_code,
                mediamtx_path=resolved.mediamtx_path,
            ),
            status=status,
        )

    def get_status(
        self,
        *,
        inventory_id: str,
        aisle_code: str,
        principal: AccessPrincipal,
    ) -> tuple[ResolvedLiveChannel, LiveStreamStatusSnapshot]:
        self._require_enabled()
        self._access.require_inventory(inventory_id, principal)
        resolved = self._resolver.resolve(inventory_id=inventory_id, aisle_code=aisle_code)
        creds = self._live_repo.get_channel_credentials(
            inventory_id=resolved.inventory_id, channel_slug=resolved.channel_slug
        )
        return resolved, self._channel_status(mediamtx_path=resolved.mediamtx_path, creds=creds)

    def stop_transmission(
        self,
        *,
        inventory_id: str,
        aisle_code: str,
        principal: AccessPrincipal,
    ) -> StopTransmissionResult:
        self._require_enabled()
        self._access.require_inventory(inventory_id, principal)
        resolved = self._resolver.resolve(inventory_id=inventory_id, aisle_code=aisle_code)
        creds = self._live_repo.get_channel_credentials(
            inventory_id=resolved.inventory_id, channel_slug=resolved.channel_slug
        )
        if creds is None:
            from src.application.errors import LiveStreamNotPreparedError

            raise LiveStreamNotPreparedError("Live channel has not been prepared for this aisle")
        now = self._clock.now()
        self._live_repo.set_channel_publish_blocked(
            inventory_id=resolved.inventory_id,
            channel_slug=resolved.channel_slug,
            blocked_at=now,
            blocked_by_principal_id=principal.actor_id,
            updated_at=now,
        )
        kicked = self._mtx_control.kick_publisher(mediamtx_path=resolved.mediamtx_path)
        blocked_creds = LiveChannelCredentials(
            id=creds.id,
            inventory_id=creds.inventory_id,
            canonical_aisle_code=creds.canonical_aisle_code,
            channel_slug=creds.channel_slug,
            mediamtx_path=creds.mediamtx_path,
            publish_username=creds.publish_username,
            publish_password_hash=creds.publish_password_hash,
            read_username=creds.read_username,
            read_password_hash=creds.read_password_hash,
            created_by_principal_id=creds.created_by_principal_id,
            created_at=creds.created_at,
            updated_at=now,
            publish_blocked_at=now,
            publish_blocked_by_principal_id=principal.actor_id,
        )
        status = self._channel_status(mediamtx_path=resolved.mediamtx_path, creds=blocked_creds)
        return StopTransmissionResult(
            channel=resolved,
            status=status,
            publisher_kicked=kicked,
        )

    def get_internal_playback(
        self,
        *,
        inventory_id: str,
        aisle_code: str,
        principal: AccessPrincipal,
    ) -> tuple[ResolvedLiveChannel, str, str, str, LiveStreamStatusSnapshot]:
        self._require_enabled()
        self._access.require_inventory(inventory_id, principal)
        resolved = self._resolver.resolve(inventory_id=inventory_id, aisle_code=aisle_code)
        creds = self._live_repo.get_channel_credentials(
            inventory_id=resolved.inventory_id, channel_slug=resolved.channel_slug
        )
        if creds is None:
            from src.application.errors import LiveStreamNotPreparedError

            raise LiveStreamNotPreparedError("Live channel has not been prepared for this aisle")
        inventory = self._inventory_repo.get_by_id(resolved.inventory_id)
        inv_name = inventory.name if inventory is not None else ""
        _, _, _, read_password = self._resolve_channel_credentials(
            inv_name=inv_name,
            resolved=resolved,
        )
        status = self._channel_status(mediamtx_path=resolved.mediamtx_path, creds=creds)
        return (
            resolved,
            self._build_viewer_hls_playlist_url(
                inventory_id=resolved.inventory_id,
                canonical_aisle_code=resolved.canonical_aisle_code,
                mediamtx_path=resolved.mediamtx_path,
            ),
            creds.read_username,
            read_password,
            status,
        )

    def resolve_hls_proxy_source(
        self,
        *,
        inventory_id: str,
        aisle_code: str,
        principal: AccessPrincipal,
    ) -> tuple[ResolvedLiveChannel, str, str, str]:
        """Return channel + stored MediaMTX path + read credentials for HLS proxy."""
        self._require_enabled()
        self._access.require_inventory(inventory_id, principal)
        resolved = self._resolver.resolve(inventory_id=inventory_id, aisle_code=aisle_code)
        creds = self._live_repo.get_channel_credentials(
            inventory_id=resolved.inventory_id, channel_slug=resolved.channel_slug
        )
        if creds is None:
            from src.application.errors import LiveStreamNotPreparedError

            raise LiveStreamNotPreparedError("Live channel has not been prepared for this aisle")
        inventory = self._inventory_repo.get_by_id(resolved.inventory_id)
        inv_name = inventory.name if inventory is not None else ""
        _, _, _, read_password = self._resolve_channel_credentials(
            inv_name=inv_name,
            resolved=resolved,
        )
        playout_path = (creds.mediamtx_path or resolved.mediamtx_path).strip().lstrip("/")
        return resolved, playout_path, creds.read_username, read_password

    def resolve_public_hls_proxy_source(
        self, *, token: str
    ) -> tuple[str, str, str]:
        """Return mediamtx_path, view_username, view_password for public proxy."""
        self._require_enabled()
        grant = self._live_repo.get_view_grant_by_token_hash(hash_public_token(token))
        if grant is None:
            from src.application.errors import LiveStreamGrantNotFoundError

            raise LiveStreamGrantNotFoundError("Invalid or unknown public live link")
        now = self._clock.now()
        if grant.revoked_at is not None or grant.expires_at <= now:
            from src.application.errors import LiveStreamGrantNotFoundError

            raise LiveStreamGrantNotFoundError("Public live link is expired or revoked")
        view_password = derive_public_grant_password(
            server_secret=self._server_secret, grant_id=grant.id
        )
        return grant.mediamtx_path, grant.view_username, view_password

    def create_public_grant(
        self,
        *,
        inventory_id: str,
        aisle_code: str,
        principal: AccessPrincipal,
        ttl_hours: int | None = None,
    ) -> CreatedPublicGrantResult:
        self._require_enabled()
        self._access.require_inventory(inventory_id, principal)
        resolved = self._resolver.resolve(inventory_id=inventory_id, aisle_code=aisle_code)
        if self._live_repo.get_channel_credentials(
            inventory_id=resolved.inventory_id, channel_slug=resolved.channel_slug
        ) is None:
            from src.application.errors import LiveStreamNotPreparedError

            raise LiveStreamNotPreparedError("Prepare the channel before creating a public link")
        now = self._clock.now()
        ttl = ttl_hours if ttl_hours is not None else self._grant_ttl_hours
        expires = now + timedelta(hours=max(1, ttl))
        token = mint_public_token()
        grant_id = str(uuid4())
        view_user = mint_public_view_username(grant_id=grant_id)
        view_password = derive_public_grant_password(
            server_secret=self._server_secret, grant_id=grant_id
        )
        grant = LiveViewGrant(
            id=grant_id,
            inventory_id=resolved.inventory_id,
            channel_slug=resolved.channel_slug,
            mediamtx_path=resolved.mediamtx_path,
            token_hash=hash_public_token(token),
            view_username=view_user,
            view_password_hash=hash_live_stream_secret(view_password),
            created_by_principal_id=principal.actor_id,
            created_at=now,
            expires_at=expires,
            revoked_at=None,
        )
        self._live_repo.save_view_grant(grant)
        return CreatedPublicGrantResult(
            grant_id=grant.id,
            public_url=f"{self._public_link_base}/live/{token}",
            public_token=token,
            expires_at=expires,
            view_username=view_user,
            view_password=view_password,
        )

    def revoke_public_grant(
        self,
        *,
        inventory_id: str,
        grant_id: str,
        principal: AccessPrincipal,
    ) -> None:
        self._require_enabled()
        self._access.require_inventory(inventory_id, principal)
        if not self._live_repo.revoke_view_grant(
            grant_id, inventory_id=inventory_id, revoked_at=self._clock.now()
        ):
            from src.application.errors import LiveStreamGrantNotFoundError

            raise LiveStreamGrantNotFoundError("Public live grant not found or already revoked")

    def list_public_grants(
        self,
        *,
        inventory_id: str,
        aisle_code: str,
        principal: AccessPrincipal,
    ) -> list[PublicLiveGrantItem]:
        self._require_enabled()
        self._access.require_inventory(inventory_id, principal)
        resolved = self._resolver.resolve(inventory_id=inventory_id, aisle_code=aisle_code)
        grants = self._live_repo.list_view_grants_for_channel(
            inventory_id=resolved.inventory_id, channel_slug=resolved.channel_slug
        )
        return [
            PublicLiveGrantItem(
                grant_id=g.id,
                expires_at=g.expires_at,
                revoked_at=g.revoked_at,
                created_at=g.created_at,
            )
            for g in grants
        ]

    def resolve_public_playback(self, *, token: str) -> PublicLivePlaybackTicket:
        self._require_enabled()
        grant = self._live_repo.get_view_grant_by_token_hash(hash_public_token(token))
        if grant is None:
            from src.application.errors import LiveStreamGrantNotFoundError

            raise LiveStreamGrantNotFoundError("Invalid or unknown public live link")
        now = self._clock.now()
        if grant.revoked_at is not None or grant.expires_at <= now:
            from src.application.errors import LiveStreamGrantNotFoundError

            raise LiveStreamGrantNotFoundError("Public live link is expired or revoked")
        view_password = derive_public_grant_password(
            server_secret=self._server_secret, grant_id=grant.id
        )
        channel_creds = self._live_repo.get_channel_credentials_by_path(grant.mediamtx_path)
        status = self._channel_status(mediamtx_path=grant.mediamtx_path, creds=channel_creds)
        return PublicLivePlaybackTicket(
            presence=status.presence,
            hls_playlist_url=self._build_public_viewer_hls_playlist_url(
                token=token,
                mediamtx_path=grant.mediamtx_path,
            ),
            view_username=grant.view_username,
            view_password=view_password,
            expires_at=grant.expires_at,
            publish_blocked=status.publish_blocked,
        )

    def _build_rtmp_url(self, mediamtx_path: str) -> str:
        return f"{self._rtmp_base}/{mediamtx_path.strip().lstrip('/')}"

    def _build_direct_hls_url(self, mediamtx_path: str) -> str:
        path = mediamtx_path.strip().lstrip("/")
        return f"{self._hls_base}/{path}/index.m3u8"

    def _build_viewer_hls_playlist_url(
        self,
        *,
        inventory_id: str,
        canonical_aisle_code: str,
        mediamtx_path: str,
    ) -> str:
        if self.hls_proxy_enabled:
            inv = urllib.parse.quote(inventory_id, safe="")
            aisle = urllib.parse.quote(canonical_aisle_code, safe="")
            return (
                f"/api/v3/inventories/{inv}/live-stream/hls/"
                f"{aisle}/index.m3u8"
            )
        return self._build_direct_hls_url(mediamtx_path)

    def _build_public_viewer_hls_playlist_url(self, *, token: str, mediamtx_path: str) -> str:
        if self.hls_proxy_enabled:
            tok = urllib.parse.quote(token, safe="")
            return f"/api/public/live/{tok}/hls/index.m3u8"
        return self._build_direct_hls_url(mediamtx_path)
