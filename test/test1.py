import unittest
import sys
sys.path.append("../")
import sshtest
import time
import threading


class Test(unittest.TestCase):

    def test_schedule(self):
      test = sshtest.SshTest("../config.json")
      test.interval = 3
      t = threading.Thread(target=sshtest.schedule, args=(test.main, test.interval))
      t.start()
      startTime = test.timer
      while  True:
          if test.timer - startTime > 0:
            break
      startTime = test.timer
      for _ in range(5):   
          time.sleep(3)  
          self.assertTrue(2.98 < (test.timer - startTime) < 3.02)
          startTime = test.timer
          

if __name__ == '__main__':
    unittest.main()