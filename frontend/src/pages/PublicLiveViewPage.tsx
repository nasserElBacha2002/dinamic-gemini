import { useEffect, useState } from 'react';
import { Box, CircularProgress, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import {
  getPublicLivePlayback,
  inferLiveStreamAuthMode,
  resolveLiveStreamPlaylistUrl,
  type LiveStreamPresence,
} from '../api/liveStreamApi';
import { ErrorAlert } from '../components/ui';
import HlsLivePlayer from '../features/liveStream/HlsLivePlayer';

export default function PublicLiveViewPage() {
  const { t } = useTranslation();
  const { token } = useParams<{ token: string }>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [presence, setPresence] = useState<LiveStreamPresence>('connecting');
  const [publishBlocked, setPublishBlocked] = useState(false);
  const [playback, setPlayback] = useState<{
    url: string;
    authMode: ReturnType<typeof inferLiveStreamAuthMode>;
  } | null>(null);

  useEffect(() => {
    if (!token) {
      setError(t('live_stream.public_invalid'));
      setLoading(false);
      return;
    }
    let cancelled = false;
    void getPublicLivePlayback(token)
      .then((res) => {
        if (cancelled) return;
        setPlayback({
          url: resolveLiveStreamPlaylistUrl(res.hls_playlist_url),
          authMode: inferLiveStreamAuthMode(res.hls_playlist_url),
        });
        setPresence(res.presence);
        setPublishBlocked(res.publish_blocked);
      })
      .catch(() => {
        if (cancelled) return;
        setError(t('live_stream.public_invalid'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, t]);

  if (loading) {
    return (
      <Box minHeight="100vh" display="flex" alignItems="center" justifyContent="center">
        <CircularProgress />
      </Box>
    );
  }

  if (error || !playback) {
    return (
      <Box minHeight="100vh" display="flex" alignItems="center" justifyContent="center" p={2}>
        <ErrorAlert message={error ?? t('live_stream.public_invalid')} />
      </Box>
    );
  }

  return (
    <Box minHeight="100vh" p={2} display="flex" flexDirection="column" gap={2}>
      <Typography variant="h6" component="h1">
        {t('live_stream.public_page_title')}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {t('live_stream.status_label')}: {t(`live_stream.presence_${presence}`)}
        {publishBlocked ? ` — ${t('live_stream.publish_blocked_hint')}` : ''}
      </Typography>
      <HlsLivePlayer playlistUrl={playback.url} authMode={playback.authMode} />
    </Box>
  );
}