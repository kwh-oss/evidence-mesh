"""Environment-driven deployment settings with fail-closed identity checks."""

import os
from pathlib import Path
import ssl


TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def env_flag(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(
        f"{name} must be one of {sorted(TRUE_VALUES | FALSE_VALUES)}; got {value!r}"
    )


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required when AIP identity binding is enabled")
    return value


def partner_identity(service_name: str) -> tuple[str, bool]:
    enabled = env_flag("AIP_IDENTITY_BINDING_ENABLED", default=False)
    if enabled:
        return required_env("AGENT_AIC"), True
    return os.getenv("AGENT_AIC", service_name).strip() or service_name, False


def leader_identity() -> tuple[str, bool]:
    enabled = env_flag("AIP_IDENTITY_BINDING_ENABLED", default=False)
    if enabled:
        return required_env("LEADER_AIC"), True
    return os.getenv("LEADER_AIC", "evidence-audit-leader").strip() or "evidence-audit-leader", False


def build_client_ssl_context() -> ssl.SSLContext:
    ca_file = _required_file("AIP_CLIENT_CA_FILE")
    cert_file = _required_file("AIP_CLIENT_CERT_FILE")
    key_file = _required_file("AIP_CLIENT_KEY_FILE")
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(ca_file))
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(certfile=str(cert_file), keyfile=str(key_file))
    return context


def _required_file(name: str) -> Path:
    path = Path(required_env(name)).expanduser()
    if not path.is_file():
        raise ValueError(f"{name} does not point to a readable file: {path}")
    return path
