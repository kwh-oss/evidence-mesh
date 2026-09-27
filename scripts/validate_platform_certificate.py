"""Validate an ACPs leaf certificate without exposing private material."""

from __future__ import annotations

import argparse
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--aic", required=True)
    parser.add_argument("--usage", choices=("clientAuth", "serverAuth"), required=True)
    parser.add_argument("--dns")
    parser.add_argument("--cert", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--trust", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    certificates = x509.load_pem_x509_certificates(args.cert.read_bytes())
    if not certificates:
        raise SystemExit("certificate chain is empty")
    leaf = certificates[0]
    private_key = load_pem_private_key(args.key.read_bytes(), password=None)

    common_names = leaf.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if len(common_names) != 1 or common_names[0].value != args.aic:
        raise SystemExit("certificate CN does not match the expected AIC")

    san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    uri_names = set(san.get_values_for_type(x509.UniformResourceIdentifier))
    if f"acps://{args.aic}" not in uri_names:
        raise SystemExit("certificate URI SAN does not contain the expected AIC")
    if args.dns:
        dns_names = set(san.get_values_for_type(x509.DNSName))
        if args.dns not in dns_names:
            raise SystemExit("certificate DNS SAN does not contain the expected host")

    eku = leaf.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    expected_eku = (
        ExtendedKeyUsageOID.CLIENT_AUTH
        if args.usage == "clientAuth"
        else ExtendedKeyUsageOID.SERVER_AUTH
    )
    if expected_eku not in eku:
        raise SystemExit("certificate EKU does not match the expected usage")

    cert_public = leaf.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key_public = private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    if cert_public != key_public:
        raise SystemExit("certificate and private key do not match")

    trust_certificates = x509.load_pem_x509_certificates(args.trust.read_bytes())
    if not trust_certificates:
        raise SystemExit("trust bundle is empty")

    print(f"CERT_OK {args.name}")


if __name__ == "__main__":
    main()
