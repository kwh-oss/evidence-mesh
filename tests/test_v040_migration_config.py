import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from v040_migration_config import clone_agent,switch_web


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.agents={r:{'new_aic':'new-'+r,'candidate_endpoint':f'https://api.example:{8480+i}/rpc'}
            for i,r in enumerate(('leader','source-verifier','evidence-grader','contradiction-scout'))}
        self.service={'image':'existing-image','command':['python','existing-entry'],
            'environment':{'AIP_IDENTITY_BINDING_ENABLED':'true','GROUP_ENABLED':'false',
                'AIP_SERVER_PORT':'8460','AGENT_AIC':'stale-legacy-alias','LEADER_AIC':'old',
                'DEEPSEEK_MAX_CALLS':'50','DEEPSEEK_BUDGET_FILE':'/var/lib/budget/quota.sqlite3'},
            'volumes':[{'type':'bind','source':'/old/cert','target':'/run/acps','read_only':True},
                {'type':'bind','source':'/old/code.py','target':'/app/src/evidence_mesh/leader.py','read_only':True},
                {'type':'bind','source':'/persistent-budget','target':'/var/lib/budget','read_only':False},
                {'type':'bind','source':'/history/leader','target':'/var/log/acps'}],
            'ports':[{'target':8460,'published':'8460'}]}

    def test_new_leader_routes_every_partner_and_preserves_budget_and_code(self):
        baseline=copy.deepcopy(self.service)
        value,logs=clone_agent(self.service,'leader',self.agents,'/new/certs')
        self.assertEqual(self.service,baseline)
        self.assertEqual(value['environment']['AGENT_AIC'],self.agents['leader']['new_aic'])
        self.assertEqual(value['environment']['LEADER_AIC'],self.agents['leader']['new_aic'])
        for role,prefix in [('source-verifier','SOURCE_VERIFIER'),('evidence-grader','EVIDENCE_GRADER'),('contradiction-scout','CONTRADICTION_SCOUT')]:
            self.assertEqual(value['environment'][prefix+'_AIC'],self.agents[role]['new_aic'])
            self.assertEqual(value['environment'][prefix+'_URL'],self.agents[role]['candidate_endpoint'])
        self.assertEqual(value['environment']['DEEPSEEK_MAX_CALLS'],'50')
        self.assertIn(baseline['volumes'][1],value['volumes'])
        self.assertIn(baseline['volumes'][2],value['volumes'])
        self.assertEqual(logs,'/history/leader-v040')
        self.assertEqual(value['ports'][0]['published'],'8480')
        self.assertEqual(value['image'],baseline['image'])
        self.assertEqual(value['command'],baseline['command'])

    def test_new_partner_does_not_gain_leader_only_caller_restrictions(self):
        self.service['environment'].pop('LEADER_AIC')
        result,_=clone_agent(self.service,'source-verifier',self.agents,'/new/certs')
        self.assertNotIn('LEADER_AIC',result['environment'])
        self.assertEqual(result['environment']['AIP_IDENTITY_BINDING_ENABLED'],'true')
        self.assertEqual(result['environment']['GROUP_ENABLED'],'false')

    def test_bridge_switch_preserves_site_auth_and_updates_both_identity_and_certificate(self):
        service={'environment':{'WEB_TEST_TOKEN_FILE':'/run/web-test/token.txt','WEB_TEST_LEADER_AIC':'old'},
            'volumes':[{'type':'bind','source':'/old/'+n,'target':'/run/acps/'+n,'read_only':True}
                for n in ('client-cert.pem','client-key.pem','trust-bundle.pem')]}
        old=copy.deepcopy(service)
        value=switch_web(service,self.agents,'/new/certs')
        self.assertEqual(service,old)
        self.assertEqual(value['environment']['WEB_TEST_CALLER_AIC'],'new-source-verifier')
        self.assertEqual(value['environment']['WEB_TEST_TOKEN_FILE'],old['environment']['WEB_TEST_TOKEN_FILE'])
        self.assertEqual(set(json.loads(value['environment']['WEB_TEST_PARTNERS'])),set(self.agents)-{'leader'})
        self.assertTrue(all(v['source'].startswith('/new/certs/source-verifier/') for v in value['volumes']))
