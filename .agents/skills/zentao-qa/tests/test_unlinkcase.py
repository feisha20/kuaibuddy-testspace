"""移除用例关联的预检与回读验证。"""
import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('qaunlink',Path(__file__).resolve().parents[1]/'scripts/zentao_qa.py')
qa=importlib.util.module_from_spec(spec);spec.loader.exec_module(qa)
class Client:
 def __init__(self): self.rows=[{'id':11,'case':21,'lastRunResult':'blocked'},{'id':12,'case':22,'lastRunResult':'pass'}]
 def testtask(self,oid): return {'testcases':self.rows}
 def request(self,method,path,data=None,params=None):
  assert (method,path,params)==('PUT','/testtasks/unlinkCase',{'runID':11})
  self.rows=self.rows[1:]; return {'status':'success'}
class Tests(unittest.TestCase):
 def op(self): return {'key':'unlink-test','action':'testtask.unlinkcase','data':{'testtaskId':1,'caseId':21,'runId':11,'replacementCaseId':22}}
 def test_preflight_submit_verify(self):
  c=Client();o=self.op();qa.validate_operation(o);qa.preflight(c,o);qa.verify(c,o,qa.submit(c,o))
 def test_requires_passed_replacement(self):
  c=Client();c.rows[1]['lastRunResult']='blocked'
  with self.assertRaises(qa.QAError):qa.preflight(c,self.op())
 def test_rejects_wrong_run(self):
  c=Client();c.rows[0]['id']=13
  with self.assertRaises(qa.QAError):qa.preflight(c,self.op())
