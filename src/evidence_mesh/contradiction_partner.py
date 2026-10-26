from .aip_partner import build_partner_app
from .processors import find_contradiction
from .semantic_conflict import semantic_conflict_product


app = build_partner_app(
    service_name="contradiction-scout",
    product_type="contradiction-check",
    processor=find_contradiction,
    product_builder=semantic_conflict_product,
)
