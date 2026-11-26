import { useEffect, useRef } from 'react';
import Hls from 'hls.js';
import { getStoredToken } from '../../features/auth/storage';

export type HlsLiveAuthMode = 'basic' | 'session' | 'none';

export interface HlsLivePlayerProps {
  playlistUrl: string;
  authMode?: HlsLiveAuthMode;
  username?: string;
  password?: string;
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
  authMode = 'basic',
  username = '',
  password = '',
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

    const basicAuthHeader =
      authMode === 'basic' && username
        ? `Basic ${btoa(`${username}:${password}`)}`
        : null;
    const sessionToken = authMode === 'session' ? getStoredToken() : null;
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

    const applyXhrAuth = (xhr: XMLHttpRequest) => {
      if (basicAuthHeader) {
        xhr.setRequestHeader('Authorization', basicAuthHeader);
      } else if (sessionToken) {
        xhr.setRequestHeader('Authorization', `Bearer ${sessionToken}`);
      }
    };

    const startNative = () => {
      video.crossOrigin = 'anonymous';
      if (authMode === 'basic' && username) {
        video.src = buildAuthedPlaylistUrl(playlistUrl, username, password);
      } else {
        video.src = playlistUrl;
      }
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
      video.crossOrigin = 'anonymous';
      hls = new Hls({
        enableWorker: false,
        lowLatencyMode: false,
        liveBackBufferLength: 0,
        maxBufferHole: 0.5,
        xhrSetup: (xhr) => {
          applyXhrAuth(xhr);
        },
      });

      const recoverOrFail = (data: {
        type: string;
        details?: string;
        response?: { code?: number };
      }) => {
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
        if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
          emit('reconnecting');
          hls.recoverMediaError();
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
      const sourceUrl = playlistUrl.endsWith('index.m3u8')
        ? playlistUrl.replace(/index\.m3u8$/, 'main_stream.m3u8')
        : playlistUrl;
      hls.loadSource(sourceUrl);
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
  }, [playlistUrl, authMode, username, password]);

  return (
    <video
      ref={videoRef}
      controls
      playsInline
      muted
      style={{
        width: '100%',
        maxHeight: '70vh',
        minHeight: 240,
        backgroundColor: '#000',
        objectFit: 'contain',
      }}
    />
  );
}