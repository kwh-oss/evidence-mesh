from .aip_partner import build_partner_app
from .processors import verify_source


app = build_partner_app(
    service_name="source-verifier",
    product_type="source-check",
    processor=verify_source,
)
