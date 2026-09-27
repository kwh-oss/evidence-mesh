"""Exercise the four-agent topology over real local TLS 1.3 + mTLS sockets.

Certificates are generated from a temporary local CA and deleted at exit. This
validates the transport and AIC-to-certificate binding code, but it is not a
substitute for Registry-issued identities, Discovery, AMP, or platform review.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import time
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import httpx


ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ROOT / "evidence" / "runs" / "2026-09-26-local-mtls-topology"
LEADER_AIC = "1.2.156.3088.1.1.1.1.1.0001"
PARTNERS = (
    ("source-verifier", "1.2.156.3088.1.1.1.1.2.0002", "evidence_mesh.source_partner:app", 8441),
    ("evidence-grader", "1.2.156.3088.1.1.1.1.3.0003", "evidence_mesh.grader_partner:app", 8442),
    ("contradiction-scout", "1.2.156.3088.1.1.1.1.4.0004", "evidence_mesh.contradiction_partner:app", 8443),
)
SAMPLE_REQUEST = {
    "schema_version": "1.0",
    "claim_id": "local-mtls-smoke-001",
    "claim_text": "材料提高抗菌率",
    "source": {
        "source_id": "doi:local-mtls-example",
        "title": "Local mTLS smoke-test source",
        "locator": "Results, paragraph 2",
    },
    "source_excerpt": "结果显示材料提高抗菌率，并在重复实验中趋势一致。",
}


def write_private_key(key: rsa.RSAPrivateKey, path: Path) -> None:
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )


def write_certificate(certificate: x509.Certificate, path: Path) -> None:
    path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))


def make_ca(directory: Path) -> tuple[rsa.RSAPrivateKey, x509.Certificate, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Evidence Mesh Local Test CA")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    ca_path = directory / "trust-bundle.pem"
    write_certificate(certificate, ca_path)
    return key, certificate, ca_path


def make_identity_certificate(
    directory: Path,
    *,
    aic: str,
    ca_key: rsa.RSAPrivateKey,
    ca_certificate: x509.Certificate,
    usage: x509.ObjectIdentifier,
    server_dns: str | None = None,
) -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    san_entries: list[x509.GeneralName] = [x509.UniformResourceIdentifier(f"acps://{aic}")]
    if server_dns:
        san_entries.append(x509.DNSName(server_dns))
    certificate = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, aic)]))
        .issuer_name(ca_certificate.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .add_extension(x509.ExtendedKeyUsage([usage]), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    cert_path = directory / f"{aic}-cert.pem"
    key_path = directory / f"{aic}-key.pem"
    write_certificate(certificate, cert_path)
    write_private_key(key, key_path)
    return cert_path, key_path


def wait_for_health(
    process: subprocess.Popen[str], client: httpx.Client, url: str, timeout: float = 20.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error = "not attempted"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"service exited early with code {process.returncode}")
        try:
            response = client.get(url)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            last_error = str(error)
            time.sleep(0.2)
    raise TimeoutError(f"health check timed out for {url}: {last_error}")


def main() -> int:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    base_environment = os.environ.copy()
    base_environment["PYTHONPATH"] = str(ROOT / "src")
    base_environment["AIP_IDENTITY_BINDING_ENABLED"] = "true"
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    processes: list[tuple[str, subprocess.Popen[str], Any]] = []

    with tempfile.TemporaryDirectory(prefix="evidence-mesh-mtls-") as temporary:
        certificate_dir = Path(temporary)
        ca_key, ca_certificate, ca_path = make_ca(certificate_dir)
        leader_cert, leader_key = make_identity_certificate(
            certificate_dir,
            aic=LEADER_AIC,
            ca_key=ca_key,
            ca_certificate=ca_certificate,
            usage=ExtendedKeyUsageOID.CLIENT_AUTH,
        )
        partner_certificates: dict[str, tuple[Path, Path]] = {}
        for name, aic, _, _ in PARTNERS:
            partner_certificates[name] = make_identity_certificate(
                certificate_dir,
                aic=aic,
                ca_key=ca_key,
                ca_certificate=ca_certificate,
                usage=ExtendedKeyUsageOID.SERVER_AUTH,
                server_dns="localhost",
            )

        client_context = ssl.create_default_context(
            ssl.Purpose.SERVER_AUTH, cafile=str(ca_path)
        )
        client_context.minimum_version = ssl.TLSVersion.TLSv1_3
        client_context.load_cert_chain(str(leader_cert), str(leader_key))

        try:
            for name, aic, application, port in PARTNERS:
                cert_path, key_path = partner_certificates[name]
                environment = base_environment.copy()
                environment.update(
                    {
                        "AGENT_AIC": aic,
                        "PARTNER_APP": application,
                        "AIP_SERVER_HOST": "127.0.0.1",
                        "AIP_SERVER_PORT": str(port),
                        "AIP_SERVER_CA_FILE": str(ca_path),
                        "AIP_SERVER_CERT_FILE": str(cert_path),
                        "AIP_SERVER_KEY_FILE": str(key_path),
                    }
                )
                log_handle = (RUN_DIR / f"{name}.log").open("w", encoding="utf-8")
                process = subprocess.Popen(
                    [sys.executable, "-m", "evidence_mesh.serve_partner"],
                    cwd=ROOT,
                    env=environment,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                    creationflags=creationflags,
                )
                processes.append((name, process, log_handle))

            leader_environment = base_environment.copy()
            leader_environment.update(
                {
                    "LEADER_AIC": LEADER_AIC,
                    "SOURCE_VERIFIER_AIC": PARTNERS[0][1],
                    "EVIDENCE_GRADER_AIC": PARTNERS[1][1],
                    "CONTRADICTION_SCOUT_AIC": PARTNERS[2][1],
                    "SOURCE_VERIFIER_URL": "https://localhost:8441/rpc",
                    "EVIDENCE_GRADER_URL": "https://localhost:8442/rpc",
                    "CONTRADICTION_SCOUT_URL": "https://localhost:8443/rpc",
                    "AIP_CLIENT_CA_FILE": str(ca_path),
                    "AIP_CLIENT_CERT_FILE": str(leader_cert),
                    "AIP_CLIENT_KEY_FILE": str(leader_key),
                }
            )
            leader_log = (RUN_DIR / "leader.log").open("w", encoding="utf-8")
            leader_process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "evidence_mesh.leader_app:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8010",
                ],
                cwd=ROOT,
                env=leader_environment,
                stdout=leader_log,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=creationflags,
            )
            processes.append(("leader", leader_process, leader_log))

            with httpx.Client(verify=client_context, timeout=2.0) as mtls_client:
                health = {}
                for name, _, _, port in PARTNERS:
                    process = next(item[1] for item in processes if item[0] == name)
                    health[name] = wait_for_health(
                        process, mtls_client, f"https://localhost:{port}/health"
                    )

            with httpx.Client(timeout=2.0) as local_client:
                health["leader"] = wait_for_health(
                    leader_process, local_client, "http://127.0.0.1:8010/health"
                )
                response = local_client.post(
                    "http://127.0.0.1:8010/audit", json=SAMPLE_REQUEST, timeout=20.0
                )
                response.raise_for_status()
                passport = response.json()

            if passport.get("decision") != "supported":
                raise AssertionError(f"unexpected decision: {passport}")
            if len(passport.get("task_ids", {})) != 3:
                raise AssertionError("not all three Partner task IDs were returned")

            report = {
                "status": "passed",
                "scope": "local-temporary-ca-tls13-mtls",
                "proves": [
                    "three Partner sockets required a trusted client certificate",
                    "TLS 1.3 client and server contexts completed handshakes",
                    "Leader certificate AIC matched AIP command sender identity",
                    "Partner certificate AICs matched AIP result sender identities",
                    "Leader aggregated all three Partner products",
                ],
                "does_not_prove": [
                    "Registry-issued certificate validity",
                    "Discovery lookup",
                    "AMP telemetry",
                    "public-network reachability",
                    "competition-platform acceptance",
                ],
                "health": health,
                "request": SAMPLE_REQUEST,
                "response": passport,
                "certificate_persistence": "temporary test certificates deleted at exit",
            }
            output_path = RUN_DIR / "validation.json"
            output_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"PASS: {output_path}")
            print(f"decision={passport['decision']}")
            print(f"task_ids={len(passport['task_ids'])}")
            return 0
        finally:
            for _, process, _ in reversed(processes):
                if process.poll() is None:
                    process.terminate()
            for _, process, log_handle in reversed(processes):
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                log_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
