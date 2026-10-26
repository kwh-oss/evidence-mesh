"""Pure transforms for approved identity replacements; preserve code and budget."""
import copy
from pathlib import PurePosixPath

PREFIXES={'source-verifier':'SOURCE_VERIFIER','evidence-grader':'EVIDENCE_GRADER','contradiction-scout':'CONTRADICTION_SCOUT'}

def clone_agent(service, role, approved, cert_root):
    value=copy.deepcopy(service)
    env=dict(value['environment'])
    assert env['AIP_IDENTITY_BINDING_ENABLED']=='true' and env['GROUP_ENABLED']=='false'
    agent=approved[role]
    env['AGENT_AIC']=agent['new_aic']
    if role=='leader':
        env['LEADER_AIC']=agent['new_aic']
        for partner,prefix in PREFIXES.items():
            env[prefix+'_AIC']=approved[partner]['new_aic']
            env[prefix+'_URL']=approved[partner]['candidate_endpoint']
    for stem in ('AIP_SERVER','AIP_CLIENT'):
        for field,filename in [('CA','trust-bundle.pem'),('CERT','server-cert.pem' if stem=='AIP_SERVER' else 'client-cert.pem'),
            ('KEY','server-key.pem' if stem=='AIP_SERVER' else 'client-key.pem')]:
            env[stem+'_'+field+'_FILE']='/run/acps-v040/'+filename
    env['AMP_AUDIT_CERT_FILE']='/run/acps-v040/server-cert.pem'
    env['AMP_AUDIT_KEY_FILE']='/run/acps-v040/server-key.pem'
    value['environment']=env
    logs=None
    volumes=[]
    for original in value['volumes']:
        volume=copy.deepcopy(original)
        if volume['target'] in ('/run/acps','/run/acps-v031'):
            assert volume['type']=='bind' and volume.get('read_only') is True
            continue
        if volume['target']=='/var/log/acps':
            assert volume['type']=='bind'
            logs=str(PurePosixPath(volume['source']).parent/(role+'-v040'))
            volume['source']=logs
            volume['bind']={**volume.get('bind',{}),'create_host_path':False}
        volumes.append(volume)
    assert logs
    volumes.append({'type':'bind','source':cert_root+'/'+role,'target':'/run/acps-v040',
        'read_only':True,'bind':{'create_host_path':False}})
    value['volumes']=volumes
    inner=int(env['AIP_SERVER_PORT'])
    outer=int(agent['candidate_endpoint'].split(':')[-1].split('/')[0])
    value['ports']=[{'target':inner,'published':str(outer),'protocol':'tcp','mode':'ingress'}]
    value['container_name']='evidence-v040-'+role
    for network in value.get('networks',{}).values():
        if isinstance(network,dict) and 'aliases' in network:
            network['aliases']=['evidence-v040-'+role]
    return value,logs


def switch_web(service, approved, cert_root):
    value=copy.deepcopy(service)
    env=dict(value['environment'])
    env['WEB_TEST_LEADER_AIC']=approved['leader']['new_aic']
    env['WEB_TEST_LEADER_URL']=approved['leader']['candidate_endpoint']
    env['WEB_TEST_CALLER_AIC']=approved['source-verifier']['new_aic']
    import json
    env['WEB_TEST_PARTNERS']=json.dumps({r:{'aic':approved[r]['new_aic'],'version':'0.4.0'} for r in PREFIXES})
    matched=set()
    for volume in value['volumes']:
        target=volume['target']
        for filename in ('client-cert.pem','client-key.pem','trust-bundle.pem'):
            if target=='/run/acps/'+filename:
                assert volume['type']=='bind' and volume.get('read_only') is True
                volume['source']=cert_root+'/source-verifier/'+filename
                volume['bind']={**volume.get('bind',{}),'create_host_path':False}
                matched.add(filename)
    assert len(matched)==3
    value['environment']=env
    return value
