import sys
from pathlib import Path
import numpy as np
BACKEND=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BACKEND))
import dense_track_refinement as dtr, cv_detect
class Net:
 def setInput(self,_):pass
 def forward(self):
  # [1,84,N] expected; one low-conf sports ball and one high-conf person
  arr=np.zeros((1,84,2),dtype=np.float32)
  arr[0,0:4,0]=[320,320,20,20];arr[0,4+32,0]=0.04
  arr[0,0:4,1]=[300,300,100,180];arr[0,4+0,1]=max(float(cv_detect.CONF_T)+.1,.8)
  return arr
class Detector:
 ok=True
 net=Net()
def test_dense_ball_floor_is_fix10_only_and_preserves_low_conf_ball_proposal():
 frame=np.zeros((640,640,3),dtype=np.uint8)
 people,balls=dtr._detect_dense_people_and_ball(Detector(),frame)
 assert len(people)==1
 assert len(balls)==1
 assert 0.03 < balls[0]['confidence'] < 0.10
 assert dtr.DENSE_BALL_CONF_T==0.03
