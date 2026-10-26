"""Render known outcomes without upgrading rule results into verified facts."""
from .rule_signals import effective_contradiction_status, rule_signal_explanation
LABELS = {'supported': '文字支持（规则初筛）',
    'needs-review': '需要复核，不能确认支持成立', 'conflicting': '规则发现冲突线索，需核对语境',
    'no-evidence': '规则未找到支持依据',
    'incomplete': '核验未完成，不能作出结论'}

def human_summary(result):
    rows = result.get('claim_results') or [result]
    lines = ['检查方式：规则初筛。']
    for index, row in enumerate(rows, 1):
        claim = row.get('checked_claim', '')
        lines.append(f'{index}. 待核验回答：{claim}\n   结果：{LABELS.get(row["decision"], "尚未核实")}。')
        missing = row.get('missing_information') or []
        if missing:
            lines.append('   缺失材料：' + '；'.join(missing) + '。')
        for name, product in row.get('partner_products', {}).items():
            assessment = product.get('input_assessment', {})
            if assessment.get('inspection_performed') is False:
                lines.append(f'   {name}：未执行检查，返回状态不能作为核验结论。')
                continue
            payload = product.get('payload', {})
            if name == 'source-verifier' and payload.get('status') != 'verified':
                fields = {'source identifier is missing': '来源编号', 'source title is missing': '来源标题', 'source locator is missing': '原文位置'}
                missing_fields = [fields[issue] for issue in payload.get('issues', []) if issue in fields]
                evidence_note = ('已收到原文，但不认证来源真实性。' if assessment.get('evidence_provided') is True
                    else '没有收到原文，未进行内容比对。' if assessment.get('evidence_provided') is False
                    else '原文是否参与比对尚未确认。')
                lines.append('   来源记录不完整' + ('，缺少：' + '、'.join(missing_fields) if missing_fields else '') + '；' + evidence_note)
            if name == 'evidence-grader':
                levels = {'direct':'规则匹配到原文中的直接文字', 'indirect':'文字相关，但未覆盖完整主张', 'conditional':'发现条件或范围限制线索', 'unsupported':'规则未找到足够文字支持', 'conflicting':'规则发现相反表述'}
                lines.append('   证据分级：' + levels.get(payload.get('level'), '未知') + '（规则初筛）。')
            if name == 'contradiction-scout':
                labels = {'none-found':'规则未发现冲突线索', 'possible':'发现可能冲突线索', 'confirmed':'规则匹配到冲突线索，仍需人工核对'}
                lines.append('   冲突检查：' + labels.get(effective_contradiction_status(product), '未知') + '。')
                explanation = rule_signal_explanation(product)
                if explanation:
                    lines.append('   ' + explanation)
        if row.get('task_ids'):
            lines.append('   子任务ID：' + '；'.join(f'{k}={v}' for k,v in row['task_ids'].items()))
    return '\n'.join(lines)
