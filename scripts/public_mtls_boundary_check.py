"""Verify public ACPs mTLS listeners and their no-certificate rejection."""

from __future__ import annotations

import argparse
import ssl
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SECRET_ROOT = ROOT / "deploy" / "secrets" / "leader"
DEFAULT_HOST = "api.linsixuan.cn"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--secret-root", type=Path, default=DEFAULT_SECRET_ROOT)
    parser.add_argument("--host", default=DEFAULT_HOST)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    secret_root = args.secret_root.resolve()
    authenticated = ssl.create_default_context(
        cafile=str(secret_root / "trust-bundle.pem")
    )
    authenticated.minimum_version = ssl.TLSVersion.TLSv1_3
    authenticated.load_cert_chain(
        certfile=str(secret_root / "client-cert.pem"),
        keyfile=str(secret_root / "client-key.pem"),
    )
    unauthenticated = ssl.create_default_context(
        cafile=str(secret_root / "trust-bundle.pem")
    )
    unauthenticated.minimum_version = ssl.TLSVersion.TLSv1_3

    for port in (8440, 8441, 8442, 8443):
        url = f"https://{args.host}:{port}/health"
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

    with urlopen(f"https://{args.host}/health", timeout=15) as response:
        if response.status != 200:
            raise RuntimeError(f"unexpected public HTTPS status: {response.status}")
    print("PUBLIC_443_OK")


if __name__ == "__main__":
    main()
