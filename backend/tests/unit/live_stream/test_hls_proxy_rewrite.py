from src.application.services.live_stream_hls_proxy import rewrite_hls_playlist


def test_rewrite_hls_playlist_relative_segments():
    body = "#EXTM3U\n#EXT-X-VERSION:3\nseg0001.ts\nseg0002.ts\n"
    out = rewrite_hls_playlist(
        body,
        channel_resource_prefix="live/foo/01",
    )
    assert "seg0001.ts" in out
    assert out.strip().endswith("seg0002.ts")
    assert "/api/v3/" not in out


def test_rewrite_hls_playlist_fmp4_master_variant_uris():
    body = (
        "#EXTM3U\n#EXT-X-VERSION:9\n"
        '#EXT-X-MEDIA:TYPE=AUDIO,URI="audio2_stream.m3u8"\n'
        "#EXT-X-STREAM-INF:BANDWIDTH=1\nvideo1_stream.m3u8\n"
    )
    out = rewrite_hls_playlist(
        body,
        channel_resource_prefix="live/prueba-26-11/01",
    )
    assert "video1_stream.m3u8" in out
    assert "audio2_stream.m3u8" in out


def test_rewrite_hls_playlist_skips_comments():
    body = "#EXTINF:1,\nsegment.ts\n"
    out = rewrite_hls_playlist(
        body,
        channel_resource_prefix="live/x/y",
    )
    assert "#EXTINF:1," in out
    assert out.strip().endswith("segment.ts")
