"""Production mTLS entry point for the Evidence Mesh Leader AIP service."""

from __future__ import annotations

import os
from pathlib import Path
import ssl

from acps_sdk.aip.aip_peer_cert import AipPeerCertH11Protocol
import uvicorn

from .runtime_config import env_flag, required_env


def _required_file(name: str) -> Path:
    path = Path(required_env(name)).expanduser()
    if not path.is_file():
        raise ValueError(f"{name} does not point to a readable file: {path}")
    return path


def _tls_context_factory(
    _config: uvicorn.Config,
    default_factory,
) -> ssl.SSLContext:
    context = default_factory()
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    return context


def main() -> None:
    if not env_flag("AIP_IDENTITY_BINDING_ENABLED", default=False):
        raise ValueError(
            "serve_leader requires AIP_IDENTITY_BINDING_ENABLED=true; "
            "use ordinary uvicorn only for the public demo listener"
        )

    required_env("LEADER_AIC")
    ca_file = _required_file("AIP_SERVER_CA_FILE")
    cert_file = _required_file("AIP_SERVER_CERT_FILE")
    key_file = _required_file("AIP_SERVER_KEY_FILE")
    host = os.getenv("AIP_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("AIP_SERVER_PORT", "8440"))

    uvicorn.run(
        "evidence_mesh.leader_app:app",
        host=host,
        port=port,
        http=AipPeerCertH11Protocol,
        ssl_ca_certs=str(ca_file),
        ssl_certfile=str(cert_file),
        ssl_keyfile=str(key_file),
        ssl_cert_reqs=ssl.CERT_REQUIRED,
        ssl_context_factory=_tls_context_factory,
    )


if __name__ == "__main__":
    main()
