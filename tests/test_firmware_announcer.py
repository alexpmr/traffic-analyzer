"""No network or radio: actual catalog, persistent outbox and backend integration."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import firmware_announcer as f
import traffic_analyzer_web as w

TEMPLATE='Meshtastic {kind}: {version} — {url}'

def record(number,kind='stable'):
    return {'id':kind+str(number),'version':'v2.8.'+str(number),'kind':kind,'published':number,
            'url':'https://nightly.meshtastic.org/' if kind=='nightly' else 'https://github.com/meshtastic/firmware/releases/tag/v2.8.'+str(number)}

class FirmwareTests(unittest.TestCase):
    def setUp(self):
        self.state={};self.disk={};self.sent=[];self.enabled={k:True for k in f.KINDS}
    def save(self,state):self.disk=json.loads(json.dumps(state))
    def send(self,record,text):self.sent.append((record,text));return True
    def run_check(self,rows,now=1000,send=None,available=f.KINDS):
        return f.process(self.state,rows,available,self.enabled,self.save,send or self.send,now,TEMPLATE)
    def test_all_categories_baseline_then_each_new_version_and_restart(self):
        old=[record(1,k) for k in f.KINDS];self.run_check(old)
        self.assertEqual(self.sent,[])
        new=[record(2,k) for k in f.KINDS]+[record(3)]
        for now in [1100,1200,1300,1400]:
            self.run_check(new+old,now)
            self.state=copy.deepcopy(self.disk)
        self.assertEqual(len(self.sent),4)
        self.assertEqual({x[0]['id'] for x in self.sent},{r['id'] for r in new})
        self.run_check(new+old,2000);self.assertEqual(len(self.sent),4)
    def test_disabled_category_does_not_replay_on_enable(self):
        self.run_check([record(1)]);self.enabled['stable']=False
        self.run_check([record(2)],1100);self.enabled['stable']=True
        self.run_check([record(2)],1200);self.assertFalse(self.sent)
        self.run_check([record(3)],1300);self.assertEqual(len(self.sent),1)
    def test_rate_limit_and_bounded_retry_of_explicit_rejection(self):
        self.run_check([record(1)])
        reject=lambda *_:False
        self.run_check([record(2)],1100,send=reject)
        self.run_check([record(2)],1150,send=reject)
        self.assertEqual(self.state['firmwareOutbox']['stable2']['attempts'],1)
        self.run_check([record(2)],1700,send=reject)
        self.run_check([record(2)],2900,send=reject)
        self.assertEqual(self.state['firmwareOutbox']['stable2']['status'],'failed')
        self.assertEqual(self.state['firmwareOutbox']['stable2']['attempts'],3)
    def test_uncertain_send_or_crash_never_blindly_retries(self):
        self.run_check([record(1)])
        def fail(*_):raise TimeoutError('unknown TX outcome')
        self.run_check([record(2)],1100,send=fail)
        self.state=copy.deepcopy(self.disk)
        self.run_check([record(2)],3000)
        self.assertFalse(self.sent)
        self.assertEqual(self.state['firmwareOutbox']['stable2']['status'],'uncertain')
        self.state['firmwareOutbox']['stable2']['status']='sending'
        self.run_check([record(2)],4000)
        self.assertFalse(self.sent)
    def test_state_write_failure_prevents_tx(self):
        self.run_check([record(1)])
        def fail(_):raise OSError('disk full')
        with self.assertRaises(OSError):
            f.process(self.state,[record(2)],f.KINDS,self.enabled,fail,self.send,1100,TEMPLATE)
        self.assertFalse(self.sent)
    def test_catalog_classifies_official_versions_and_rejects_bad_nightly(self):
        data=[{'id':i,'tag_name':tag,'prerelease':pre,'published_at':'2026-10-17T00:00:00Z'}
              for i,tag,pre in [(1,'v2.8.0',False),(2,'v2.9.0-beta.1',True),(3,'nightly-abc',True)]]
        self.assertEqual([r['kind'] for r in f.release_records(data)],['stable','unstable','nightly'])
        self.assertEqual(f.nightly_record({'id':'v2.9.0.abc1234'})['id'],'nightly:v2.9.0.abc1234')
        self.assertEqual(f.nightly_record({'version':'2.9.0.abc1234'})['kind'],'nightly')
        for row in [{},{'id':'../../bad'},{'id':'<script>'}]:
            with self.assertRaises(ValueError):f.nightly_record(row)
    def test_short_messages_preserve_category_version_and_official_link(self):
        for kind in f.KINDS:
            text=f.message(record(2,kind));self.assertLessEqual(len(text.encode()),200)
            self.assertIn(f.LABELS[kind],text);self.assertIn(record(2,kind)['url'],text)
        for template in ['{url.__class__}','{kind}','x'*251,'{{kind}} {version} {url}']:
            with self.assertRaises(ValueError):f.message(record(2),template)

class IntegrationTests(unittest.TestCase):
    def test_settings_partial_save_defaults_and_restart(self):
        with tempfile.TemporaryDirectory() as d,patch.object(w,'NOTICE_SETTINGS_FILE',Path(d)/'settings.json'):
            settings=w._automatic_notice_settings()
            self.assertTrue(all(settings[x] for x in ['meshtasticEnabled','meshtasticStableEnabled','meshtasticUnstableEnabled','meshtasticNightlyEnabled']))
            w._save_automatic_notice_settings({'inmetEnabled':False,'pollSeconds':900})
            w._save_automatic_notice_settings({'meshtasticNightlyEnabled':False})
            settings=w._automatic_notice_settings()
            self.assertFalse(settings['inmetEnabled']);self.assertFalse(settings['meshtasticNightlyEnabled'])
            self.assertEqual(settings['pollSeconds'],900)
            for bad in [{'pollSeconds':1},{'meshtasticEnabled':'false'},{'unknown':1}]:
                with self.assertRaises(ValueError):w._save_automatic_notice_settings(bad)
    def test_sources_backoff_independent_nightly_and_no_tx_on_error(self):
        with tempfile.TemporaryDirectory() as d,patch.object(w,'NOTICE_STATE_FILE',Path(d)/'state.json'),patch.object(w,'_meshtastic_releases',return_value=[]) as releases,patch.object(f,'fetch_json',side_effect=urllib.error.HTTPError(f.NIGHTLY_URL,429,'limited',{'Retry-After':'1200'},None)) as nightly,patch.object(w,'_firmware_send') as sender:
            state={};settings=w._automatic_notice_settings()
            sent,errors=w._run_firmware_notice_check(state,settings,1000)
            self.assertFalse(sent);self.assertTrue(errors);sender.assert_not_called()
            self.assertNotIn('nightly',state['firmwareInitialized'])
            w._run_firmware_notice_check(state,settings,1600)
            self.assertEqual(nightly.call_count,1);self.assertEqual(releases.call_count,2)
    def test_transmits_only_primary_channel_and_records_accepted_not_delivery(self):
        with patch.object(w,'_mm_api_post',return_value={'success':True}) as post,patch.object(w,'_record_automatic_notice') as log:
            self.assertTrue(w._firmware_send(record(2),f.message(record(2))))
            args=post.call_args.args
            self.assertEqual(args[1]['channel'],0)
            self.assertIn('/messages',args[0]);self.assertTrue(log.call_args.args[4])
