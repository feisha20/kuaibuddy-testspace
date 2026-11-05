"""task.activate 合成测试，不连接禅道。"""
import copy, importlib.util, unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('qa_activate',Path(__file__).resolve().parents[1]/'scripts/zentao_qa.py')
qa=importlib.util.module_from_spec(spec);spec.loader.exec_module(qa)
class Client:
 def __init__(self):self.t={'id':1,'type':'test','status':'done','story':'0','lastEditedDate':'2026-11-05 16:58:50','assignedTo':'alice','consumed':'1.00','left':'0.00'};self.writes=0
 def detail(self,k,i):return copy.deepcopy(self.t)
 def request(self,m,p,d):
  self.writes+=1
  assert (m,p)==('PUT','/tasks/1/activate') and 'consumed' not in d
  self.t.update(status='doing',left='2.00');return {'status':'success'}
def op():return {'key':'activate-1','action':'task.activate','targetId':1,'expected':{'storyId':0,'lastEditedDate':'2026-11-05 16:58:50'},'data':{'left':2,'assignedTo':'alice','consumed':1}}
class Tests(unittest.TestCase):
 def test_activate_and_preserve_hours(self):
  c=Client();o=op();qa.validate_operation(o);r=qa.submit(c,o);self.assertEqual(qa.verify(c,o,r)['consumed'],'1.00')
  with self.assertRaises(qa.QAError):qa.preflight(c,o)
 def test_stale_or_invalid_hours(self):
  c=Client();o=op();o['data']['consumed']=0
  with self.assertRaises(qa.QAError):qa.preflight(c,o)
  o=op();o['data']['left']=0
  with self.assertRaises(qa.QAError):qa.validate_operation(o)
  self.assertEqual(c.writes,0)
if __name__=='__main__':unittest.main()
