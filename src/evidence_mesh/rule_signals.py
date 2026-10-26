"""Explain weak rule signals without upgrading them to semantic contradictions."""

WEAK_INDICATORS = frozenset({'numeric-mismatch', 'certainty-boundary-conflict'})


def is_weak_indicator(indicator):
    # Opposite words in one bundle may concern different metrics, objects or
    # dates (e.g. improve teaching quality and reduce workload). Not a refutation.
    return isinstance(indicator, str) and (indicator in WEAK_INDICATORS
                                           or indicator.startswith('internal:'))


def effective_contradiction_status(product):
    assessment = product.get('input_assessment', {})
    payload = product.get('payload', {})
    status = payload.get('status')
    indicators = payload.get('indicators', [])
    # Older deployed partners used confirmed even for unaligned number sets.
    # Preserve their raw product; only downgrade the Leader's interpretation.
    if (status == 'confirmed'
            and assessment.get('inspection_scope') == 'supplied-text-rules'
            and isinstance(indicators, list) and indicators
            and all(is_weak_indicator(i) for i in indicators)):
        return 'possible'
    return status


def rule_signal_explanation(product):
    assessment = product.get('input_assessment', {})
    if (assessment.get('inspection_performed') is not True
            or assessment.get('evidence_provided') is not True
            or assessment.get('inspection_scope') != 'supplied-text-rules'):
        return ''
    indicators = product.get('payload', {}).get('indicators', [])
    if not isinstance(indicators, list):
        return ''
    notes = []
    if 'numeric-mismatch' in indicators:
        notes.append('数字检查发现待核对线索：两段文本的数字写法不同；'
                     '尚未对齐这些数字对应的人群、时间、单位和指标，不能据此确认冲突。')
    if 'certainty-boundary-conflict' in indicators:
        notes.append('确定性检查发现待核对线索：帖子含肯定措辞，材料含限定措辞；'
                     '尚未核对这些措辞是否针对同一主张，不能据此确认冲突。')
    if any(isinstance(i, str) and i.startswith('internal:') for i in indicators):
        notes.append('材料中同时出现相反方向词，仅为待核对线索；它们可能描述不同对象、'
                     '指标、条件或时间，不能据此确认材料自相矛盾或反驳帖子。')
    return '\n'.join(notes)
