import { useEffect, useRef } from 'react';
import Hls from 'hls.js';

export interface HlsLivePlayerProps {
  playlistUrl: string;
  username: string;
  password: string;
  onPresenceChange?: (presence: string) => void;
}

function buildAuthedPlaylistUrl(playlistUrl: string, username: string, password: string): string {
  try {
    const url = new URL(playlistUrl, window.location.href);
    url.username = encodeURIComponent(username);
    url.password = encodeURIComponent(password);
    return url.href;
  } catch {
    return playlistUrl;
  }
}

export default function HlsLivePlayer({
  playlistUrl,
  username,
  password,
  onPresenceChange,
}: HlsLivePlayerProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const onPresenceRef = useRef(onPresenceChange);

  useEffect(() => {
    onPresenceRef.current = onPresenceChange;
  }, [onPresenceChange]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !playlistUrl) return undefined;

    const authHeader = `Basic ${btoa(`${username}:${password}`)}`;
    let hls: Hls | null = null;
    let cancelled = false;
  let fatalRecoveryTimer: ReturnType<typeof setTimeout> | null = null;

    const emit = (presence: string) => {
      if (!cancelled) {
        onPresenceRef.current?.(presence);
      }
    };

    const clearRecoveryTimer = () => {
      if (fatalRecoveryTimer !== null) {
        clearTimeout(fatalRecoveryTimer);
        fatalRecoveryTimer = null;
      }
    };

    const startNative = () => {
      video.crossOrigin = 'anonymous';
      video.src = buildAuthedPlaylistUrl(playlistUrl, username, password);
      emit('connecting');
      const onPlaying = () => emit('live');
      const onWaiting = () => emit('reconnecting');
      const onEnded = () => emit('ended');
      const onError = () => emit('no_stream');
      video.addEventListener('playing', onPlaying);
      video.addEventListener('waiting', onWaiting);
      video.addEventListener('ended', onEnded);
      video.addEventListener('error', onError);
      void video.play().catch(() => emit('no_stream'));
      return () => {
        video.removeEventListener('playing', onPlaying);
        video.removeEventListener('waiting', onWaiting);
        video.removeEventListener('ended', onEnded);
        video.removeEventListener('error', onError);
      };
    };

    let detachNative: (() => void) | undefined;

    if (Hls.isSupported()) {
      hls = new Hls({
        enableWorker: true,
        lowLatencyMode: true,
        xhrSetup: (xhr) => {
          xhr.setRequestHeader('Authorization', authHeader);
        },
      });

      const recoverOrFail = (data: { type: string; response?: { code?: number } }) => {
        if (cancelled || !hls) return;
        const httpStatus = data.response?.code;
        if (httpStatus === 401 || httpStatus === 403) {
          emit('service_unavailable');
          return;
        }
        if (httpStatus === 404) {
          emit('no_stream');
          return;
        }
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
          emit('reconnecting');
          clearRecoveryTimer();
          fatalRecoveryTimer = setTimeout(() => {
            if (cancelled || !hls) return;
            hls?.startLoad();
          }, 1500);
          return;
        }
        emit('ended');
      };

      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        emit('live');
        void video.play().catch(() => emit('no_stream'));
      });
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (cancelled || !data.fatal) return;
        recoverOrFail(data);
      });
      // Use a clean playlist URL; auth is sent via xhrSetup (MediaMTX HLS + nginx).
      // Embedding user:pass in the URL breaks segment resolution in some browsers.
      hls.loadSource(playlistUrl);
      hls.attachMedia(video);
      emit('connecting');
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      detachNative = startNative();
    } else {
      emit('service_unavailable');
    }

    return () => {
      cancelled = true;
      clearRecoveryTimer();
      detachNative?.();
      if (hls) {
        hls.destroy();
        hls = null;
      }
      video.pause();
      video.removeAttribute('src');
      video.load();
    };
  }, [playlistUrl, username, password]);

  return (
    <video
      ref={videoRef}
      controls
      playsInline
      muted
      style={{ width: '100%', maxHeight: '70vh', backgroundColor: '#000' }}
    />
  );
}