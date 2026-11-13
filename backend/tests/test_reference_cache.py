import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sequence_pilot_transport as transport
import sequence_run_checkpoint as checkpoint


class ReferenceCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name)/'reference.jpg'
        path.write_bytes(b'exact image bytes')
        self.items = [{'type':'text','text':'unchanged instructions'},
                      {'type':'image','path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()},
                      {'type':'text','text':'timeline question'}]
        _, self.payload, self.audit = transport.build_request('emergent','gpt-6-astra',self.items,
            reasoning_effort='medium',image_detail='high',max_output_tokens=10000)

    def test_wire_changes_only_cache_metadata(self):
        wire, audit = transport.cached_wire_payload('emergent','gpt-6-astra',self.payload,2)
        body=json.loads(wire)
        self.assertEqual(body.pop('prompt_cache_options'),{'mode':'explicit'})
        self.assertEqual(body['messages'][0]['content'][1].pop('prompt_cache_breakpoint'),{'mode':'explicit'})
        self.assertEqual(json.dumps(body,separators=(',',':')).encode(),self.payload)
        self.assertEqual(audit['wire_payload_sha256'],hashlib.sha256(wire).hexdigest())

    def test_without_hint_wire_is_byte_identical(self):
        self.assertEqual(transport.cached_wire_payload('emergent','gpt-6-astra',self.payload),(self.payload,{}))

    def test_invalid_boundaries_and_unsupported_models(self):
        for boundary in (True,0,-1,1,3,4,'2'):
            with self.subTest(boundary=boundary), self.assertRaises(ValueError):
                transport.cached_wire_payload('emergent','gpt-6-astra',self.payload,boundary)
        with self.assertRaises(ValueError):
            transport.cached_wire_payload('gemini','gemini-2.5-pro',self.payload,2)

    def test_worker_preserves_old_receipt_key_and_records_actual_wire(self):
        sent=[]; receipts=[]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return json.dumps({'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]}).encode()
        class Connection:
            def send(self,value):receipts.append(value)
            def close(self):pass
        def request(req,**kwargs):sent.append(req.data);return Response()
        job={'packet_id':'p','items':self.items,'reasoning_effort':'medium','image_detail':'high',
             'max_output_tokens':10000,'reference_cache_prefix_items':2}
        with patch.dict(transport.os.environ,{'EMERGENT_LLM_KEY':'test-only'}), patch.object(transport.urllib.request,'urlopen',request):
            transport._worker(Connection(),job,'emergent','gpt-6-astra',1)
        receipt=receipts[0]
        self.assertEqual(receipt['status'],'COMPLETED')
        self.assertEqual(receipt['payload_sha256'],self.audit['payload_sha256'])
        self.assertEqual(receipt['wire_payload_sha256'],hashlib.sha256(sent[0]).hexdigest())
        self.assertTrue(checkpoint.reusable_receipt(receipt,self.audit,provider='emergent',model='gpt-6-astra',packet_id='p'))
        receipt.pop('wire_payload_sha256');receipt.pop('wire_payload_bytes');receipt.pop('reference_cache_prefix_items')
        self.assertTrue(checkpoint.reusable_receipt(receipt,self.audit,provider='emergent',model='gpt-6-astra',packet_id='p'))
        changed={**self.audit,'payload_sha256':'different'}
        self.assertFalse(checkpoint.reusable_receipt(receipt,changed,provider='emergent',model='gpt-6-astra',packet_id='p'))

    def test_exact_previous_release_migration_rejects_changed_analysis(self):
        old=checkpoint._PRE_REFERENCE_CACHE_CODE
        current={**old,'sequence_pilot_transport.py':'new','sequence_run_checkpoint.py':'new'}
        self.assertTrue(checkpoint.retry_code_compatible(old,current))
        self.assertTrue(checkpoint.writer_source_code_compatible(old,current))
        current['sequence_pilot.py']='different prompt'
        self.assertFalse(checkpoint.retry_code_compatible(old,current))


if __name__ == '__main__':
    unittest.main()
