import re
from pathlib import Path

from freezer.config import load_config

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"


def read(name: str) -> str:
    return (DEPLOY / name).read_text(encoding="utf-8")


def test_install_script_fills_every_placeholder():
    install = read("install.sh")
    for name in ["Caddyfile.template", "cert.html", "systemd/freezer-notify.timer"]:
        for placeholder in set(re.findall(r"__[A-Z_]+__", read(name))):
            assert f"s|{placeholder}|" in install, (name, placeholder)


def test_install_script_is_a_unix_bash_script():
    raw = (DEPLOY / "install.sh").read_bytes()
    assert raw.startswith(b"#!/usr/bin/env bash\n")
    assert b"\r\n" not in raw


def test_env_example_is_a_valid_config():
    env = {}
    for line in read("freezer.env.example").splitlines():
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            env[key] = value
    cfg = load_config(env)
    assert cfg.port == 8765
    assert cfg.db_path == "/var/lib/freezer/freezer.db"
    assert cfg.backup_keep == 14


def test_units_run_as_freezer_with_env_file():
    for unit in ["freezer.service", "freezer-notify.service", "freezer-backup.service"]:
        text = read(f"systemd/{unit}")
        assert "User=freezer" in text
        assert "EnvironmentFile=/etc/freezer/freezer.env" in text
        assert "WorkingDirectory=/opt/freezer" in text
    service = read("systemd/freezer.service")
    assert "--host 127.0.0.1" in service
    assert "--port ${FREEZER_PORT}" in service


def test_caddy_serves_only_the_root_certificate():
    caddyfile = read("Caddyfile.template")
    assert caddyfile.startswith("# freezer")
    assert "rewrite * /root.crt" in caddyfile
    assert "tls internal" in caddyfile
    assert "reverse_proxy 127.0.0.1:__APP_PORT__" in caddyfile
