from .aip_partner import build_partner_app
from .processors import find_contradiction


app = build_partner_app(
    service_name="contradiction-scout",
    product_type="contradiction-check",
    processor=find_contradiction,
)
