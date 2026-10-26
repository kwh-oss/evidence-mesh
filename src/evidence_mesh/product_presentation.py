"""Readable AIP text with the complete machine contract in item metadata.

Consumers should read metadata.evidence_mesh_product first, then fall back to
legacy JSON text. Metadata is caller-visible protocol data, not a secret store.
"""
import json

from acps_sdk.aip import TextDataItem, StructuredDataItem

PRODUCT_KEY = 'evidence_mesh_product'


def readable_product_item(output):
    value = json.loads(output) if isinstance(output, str) else output
    if not isinstance(value, dict) or not isinstance(value.get('answer'), str):
        raise ValueError('product requires a readable answer')
    return TextDataItem(text=value['answer'], metadata={PRODUCT_KEY: value})


def read_product(products):
    items = [item for product in products or [] for item in product.dataItems]
    for item in items:
        value = (item.metadata or {}).get(PRODUCT_KEY)
        if isinstance(value, dict) and value.get('product_type'):
            return value
    for item in items:
        if isinstance(item, StructuredDataItem) and item.data.get('product_type'):
            return item.data
        if isinstance(item, TextDataItem):
            try:
                value = json.loads(item.text)
            except (ValueError, TypeError):
                continue
            if isinstance(value, dict) and value.get('product_type'):
                return value
    raise ValueError('no structured evidence product')
