"""Read a public-test export offline; structural checks are NOT semantic grading."""
import argparse
import json
from pathlib import Path


def summarize(value, source_excerpt=None):
    passport = value.get('passport') or {}
    review = passport.get('semantic_review') or {}
    claims = review.get('claims') or []
    checked = passport.get('checked_claim', '')
    claim_spans_valid = bool(claims) and isinstance(checked, str)
    excerpt = source_excerpt if source_excerpt is not None else passport.get('source_excerpt')
    quote_anchors_valid = bool(claims) if isinstance(excerpt, str) else None
    seen_spans = set()
    for row in claims:
        span = row.get('claim_span')
        claim_spans_valid = claim_spans_valid and (
            isinstance(span, str) and bool(span.strip())
            and span in checked and span not in seen_spans)
        if isinstance(span, str):
            seen_spans.add(span)
        quotes = row.get('quotes')
        if not isinstance(quotes, list):
            quote_anchors_valid = False
            continue
        if row.get('status') in ('supported', 'overstated', 'contradicted') and not quotes:
            quote_anchors_valid = False
        for quote in quotes:
            if excerpt is None:
                continue
            start, end = quote.get('start'), quote.get('end')
            quote_anchors_valid = quote_anchors_valid and (
                isinstance(excerpt, str) and type(start) is int and type(end) is int
                and 0 <= start < end <= len(excerpt)
                and quote.get('text') == excerpt[start:end])
    units = review.get('input_review_units') or []
    seen, units_valid = set(), bool(units)
    previous_end = 0
    for unit in units:
        start, end = unit.get('start'), unit.get('end')
        identifier = unit.get('unit_id')
        valid = (type(start) is int and type(end) is int
                 and previous_end <= start < end <= len(checked)
                 and unit.get('text') == checked[start:end]
                 and isinstance(identifier, str) and identifier not in seen
                 and (unit.get('premise_unit_id') is None or unit['premise_unit_id'] in seen))
        units_valid = units_valid and valid
        if valid:
            previous_end = end
            seen.add(identifier)
    products = (value.get('raw_final_result') or {}).get('products') or []
    summaries = [item for product in products if product.get('name') == '中文核验说明'
                 for item in product.get('dataItems', []) if item.get('type') == 'text']
    summary_matches = len(summaries) == 1 and summaries[0].get('text') == passport.get('answer')
    structural_checks = {
        'completed': value.get('state') == 'completed',
        'mtls_binding': value.get('mtls_identity_binding') is True,
        'model_full_coverage': review.get('status') == 'model-suggestion' and review.get('coverage_complete') is True,
        'no_rejections_or_omissions': not review.get('rejected_claims') and not review.get('unreviewed_spans'),
        'readable_product_matches_answer': summary_matches,
        'source_risk_retained': 'claim:source-not-verified' in passport.get('risk_flags', []),
        'atomic_claims_match': [r.get('original_span') for r in passport.get('atomic_claims', [])]
                               == [r.get('claim_span') for r in claims],
        'claim_spans_nonempty_and_present': claim_spans_valid,
        'quote_offsets_match_material': quote_anchors_valid,
        'unit_offsets_and_links_valid': units_valid,
        'source_authentication_not_claimed': passport.get('source_authenticity_verified') is False,
    }
    return {'task_id': value.get('leader_task_id'), 'structural_checks': structural_checks,
            'structural_pass': all(structural_checks.values()),
            'claim_statuses': [row.get('status') for row in claims],
            'semantic_acceptance': 'requires-human-evidence-review',
            'material_audit_note': ('Material supplied for offset checking.' if isinstance(excerpt, str)
                                    else 'Original material absent from export; supply --material to check quote offsets. Missing is not mismatch.'),
            'quota_remaining': None,
            'quota_note': 'Not inferred from this export; read the persistent server counter.',
            'note': 'Structural pass never certifies reasoning, source authenticity, or real-world readiness.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export', type=Path)
    parser.add_argument('--material', type=Path, help='UTF-8 text containing exactly the submitted source excerpt, not the complete task.')
    args = parser.parse_args()
    material = args.material.read_text(encoding='utf-8-sig') if args.material else None
    result = summarize(json.loads(args.export.read_text(encoding='utf-8-sig')), material)
    print(json.dumps(result, ensure_ascii=False, indent=2))
