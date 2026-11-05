"""task.finish 合成测试，不连接禅道。"""
import copy, importlib.util, unittest
from pathlib import Path
spec = importlib.util.spec_from_file_location('qa_finish', Path(__file__).resolve().parents[1] / 'scripts/zentao_qa.py')
qa = importlib.util.module_from_spec(spec); spec.loader.exec_module(qa)
class FinishClient:
    def __init__(self):
        self.task={'id':12,'type':'test','isParent':'0','status':'doing','story':'0','lastEditedDate':'2026-11-05 16:46:43','assignedTo':'alice','consumed':'2.00','left':'2.00','realStarted':'2026-11-05 16:46:43','parent':'13'}
        self.writes=0
    def detail(self,kind,oid): return copy.deepcopy(self.task) if oid==12 else {'id':13,'status':'doing'}
    def request(self,method,path,data):
        self.writes+=1
        assert (method,path,data['currentConsumed'],data['consumed'])==('PUT','/tasks/12/finish',1,3)
        self.task.update(status='done',consumed='3.00',left='0.00',finishedDate=data['finishedDate']);return {'status':'success'}
def op():
    return {'key':'finish-12','action':'task.finish','targetId':12,'expected':{'storyId':0,'lastEditedDate':'2026-11-05 16:46:43'},'data':{'currentConsumed':1,'consumed':2,'assignedTo':'alice','realStarted':'2026-11-05 16:46:43'}}
class FinishTests(unittest.TestCase):
    def test_finish_once_and_verify_work_hours(self):
        c=FinishClient();o=op();qa.validate_operation(o);qa.preflight(c,o);r=qa.submit(c,o);v=qa.verify(c,o,r)
        self.assertEqual(v['consumed'],'3.00');self.assertEqual(c.writes,1)
        with self.assertRaises(qa.QAError):qa.preflight(c,o)
    def test_stale_or_other_owner_is_rejected(self):
        c=FinishClient();o=op();c.task['assignedTo']='bob'
        with self.assertRaises(qa.QAError):qa.preflight(c,o)
        self.assertEqual(c.writes,0)
    def test_mismatched_consumed_is_rejected(self):
        c=FinishClient();o=op();o['data']['consumed']=0
        with self.assertRaises(qa.QAError):qa.preflight(c,o)
if __name__=='__main__': unittest.main()
