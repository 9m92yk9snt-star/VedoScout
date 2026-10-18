"""Synthetic geometry only; these tests do not establish football perception."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from scripts.refine_contact_cluster import cluster_box


def test_cluster_proposal_keeps_nearby_potential_actors_and_original_pixel_bounds():
    image=np.zeros((800,1000,3),dtype=np.uint8);image[:]=(30,100,30)
    image[220:420,440:540]=(220,80,10)
    image[230:410,350:410]=(230,230,230)
    refs=[{'box':{'y':.4,'h':.3}}]
    box,policy=cluster_box(image,[0,200,1000,1000],refs,1000)
    assert box[0]<=350 and box[2]>=540 and box[1]<=220 and box[3]>=420
    assert 0<=box[0]<box[2]<=1000 and 0<=box[1]<box[3]<=800
    assert 'KIT_COMPONENT' in policy


def test_empty_or_uninformative_kit_mask_keeps_full_checked_source_band():
    image=np.zeros((800,1000,3),dtype=np.uint8);image[:]=(30,100,30)
    assert cluster_box(image,[0,200,1000,1000],[{'box':{'y':.4,'h':.3}}],1000)==(
        [0,0,1000,800],'FULL_CHECKED_SOURCE_BAND_FALLBACK')
