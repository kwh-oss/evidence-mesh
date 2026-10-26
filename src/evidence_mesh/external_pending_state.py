"""Shared status predicate; safe to use in the website bridge without keys."""


def hybrid_supplement(passport):
    value = passport.get('external_supplement', {})
    return (value.get('internal_answer_preserved') is True
            and value.get('affects_core_verdict') is False
            and value.get('scope') == 'public-lookup-only-not-internal-evidence')


def pending_external_children(passport):
    hybrid = hybrid_supplement(passport)
    if passport.get('decision_scope')!='external-consultation' and not hybrid:
        return False
    return (passport.get('external_supplement', {}).get('status') == 'pending' if hybrid
            else passport.get('consultation_status')=='pending') or any(
        r.get('recovery_required') or r.get('status') == 'pending'
        or r.get('aip_state') in ('accepted','working','awaiting-completion')
        for r in passport.get('external_collaboration',{}).get('reviews',[]))
