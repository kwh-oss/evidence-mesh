from .aip_partner import build_partner_app
from .processors import grade_evidence


app = build_partner_app(
    service_name="evidence-grader",
    product_type="evidence-finding",
    processor=grade_evidence,
)
