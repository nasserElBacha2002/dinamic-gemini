from src.application.services.live_stream_hls_proxy import rewrite_hls_playlist


def test_rewrite_hls_playlist_relative_segments():
    body = "#EXTM3U\n#EXT-X-VERSION:3\nseg0001.ts\nseg0002.ts\n"
    out = rewrite_hls_playlist(
        body,
        proxy_entry_prefix="/api/v3/inventories/inv/live-stream/hls/A01",
        channel_resource_prefix="live/foo/01",
    )
    assert "seg0001.ts" in out
    assert out.strip().endswith("seg0002.ts")
    assert "/api/v3/" not in out


def test_rewrite_hls_playlist_skips_comments():
    body = "#EXTINF:1,\nsegment.ts\n"
    out = rewrite_hls_playlist(
        body,
        proxy_entry_prefix="/api/public/live/tok/hls",
        channel_resource_prefix="live/x/y",
    )
    assert "#EXTINF:1," in out
    assert out.strip().endswith("segment.ts")