import threading
import unittest
from app import team_starter as module

class LabGates(unittest.TestCase):
    def test_01_parallel_collection(self):
        barrier=threading.Barrier(3,timeout=2)
        def call(role):
            barrier.wait()
            return {'verdict':'ERROR' if role=='risk' else 'CLEAR'}
        result=module.collect_parallel(call,('policy','order','risk'))
        self.assertEqual(set(result),{'policy','order','risk'})
        self.assertEqual(result['risk']['verdict'],'ERROR')
        self.assertEqual(result['policy']['verdict'],'CLEAR')

    def test_02_bounded_supervisor(self):
        clear={r:{'verdict':'CLEAR'} for r in ('policy','order','risk')}
        self.assertEqual(module.supervise(clear,1)['action'],'READY')
        missing={**clear,'risk':{'verdict':'ERROR'}}
        first=module.supervise(missing,1)
        self.assertEqual((first['action'],first['target']),('FOLLOW_UP','risk'))
        self.assertEqual(module.supervise(missing,2)['action'],'BLOCKED')
        conflict={**clear,'order':{'verdict':'BLOCK'}}
        self.assertEqual(module.supervise(conflict,1)['action'],'BLOCKED')
        self.assertEqual(module.supervise({'policy':{'verdict':'CLEAR'}},1)['action'],'BLOCKED')
        self.assertEqual(module.supervise({**clear,'policy':{'verdict':'REVIEW'}},1)['action'],'BLOCKED')
        self.assertEqual(module.supervise({**conflict,'risk':{'verdict':'ERROR'}},1)['action'],'BLOCKED')

if __name__=='__main__':unittest.main()
