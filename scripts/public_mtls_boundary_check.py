"""Verify public ACPs mTLS listeners and their no-certificate rejection."""

from __future__ import annotations

import ssl
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
SECRET_ROOT = ROOT / "deploy" / "secrets" / "leader"
HOST = "api.linsixuan.cn"


def main() -> None:
    authenticated = ssl.create_default_context(
        cafile=str(SECRET_ROOT / "trust-bundle.pem")
    )
    authenticated.minimum_version = ssl.TLSVersion.TLSv1_3
    authenticated.load_cert_chain(
        certfile=str(SECRET_ROOT / "client-cert.pem"),
        keyfile=str(SECRET_ROOT / "client-key.pem"),
    )
    unauthenticated = ssl.create_default_context(
        cafile=str(SECRET_ROOT / "trust-bundle.pem")
    )
    unauthenticated.minimum_version = ssl.TLSVersion.TLSv1_3

    for port in (8440, 8441, 8442, 8443):
        url = f"https://{HOST}:{port}/health"
        with urlopen(url, context=authenticated, timeout=15) as response:
            if response.status != 200:
                raise RuntimeError(f"unexpected status on {port}: {response.status}")
        print(f"PUBLIC_MTLS_OK_{port}")

        try:
            urlopen(url, context=unauthenticated, timeout=8)
        except (ssl.SSLError, URLError, ConnectionError):
            print(f"PUBLIC_NO_CERT_REJECTED_{port}")
        else:
            raise RuntimeError(f"unauthenticated access succeeded on {port}")

    with urlopen(f"https://{HOST}/health", timeout=15) as response:
        if response.status != 200:
            raise RuntimeError(f"unexpected public HTTPS status: {response.status}")
    print("PUBLIC_443_OK")


if __name__ == "__main__":
    main()
