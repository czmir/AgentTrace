from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_vite_proxies_api_to_real_backend():
    text = (ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    assert "/api" in text
    assert "8765" in text


def test_nginx_proxies_api_to_api_service():
    text = (ROOT / "deploy" / "nginx.conf").read_text(encoding="utf-8")
    assert "location /api/" in text
    assert "proxy_pass http://api:8765" in text


def test_frontend_fetch_is_same_origin_api():
    text = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")
    assert "/api/traces" in text
    assert "http://mock" not in text.lower()
