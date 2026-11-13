"""Offline candidate decoder tests; no player/event authority granted."""
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv_detect as cv
from scripts.benchmark_local_bytetrack import person_proposals


def prediction(rows, classes, scores):
    return cv.Predictions(np.asarray(rows,dtype=float).reshape(-1,4),
                          np.asarray(classes),np.asarray(scores),None)


def test_low_confidence_person_retained_for_second_association():
    p=prediction([[100,100,20,40],[200,100,20,40],[300,100,20,40]], [0,0,32],[.8,.15,.9])
    boxes,scores=person_proposals(p,1280,720,cv,np)
    assert len(boxes)==2 and np.allclose(scores,[.8,.15])
    assert np.allclose(boxes[0],[180,160,220,240])


def test_empty_candidates_have_valid_shape():
    boxes,scores=person_proposals(prediction([],[],[]),640,480,cv,np)
    assert boxes.shape==(0,4) and scores.shape==(0,)


def test_duplicate_person_boxes_suppressed():
    p=prediction([[100,100,20,40],[100,100,20,40]],[0,0],[.8,.15])
    boxes,scores=person_proposals(p,640,480,cv,np)
    assert len(boxes)==1 and scores[0]==.8


def test_invalid_and_outside_boxes_never_become_tracks():
    p=prediction([[float('nan'),100,20,40],[100,100,-20,40],[1000,1000,20,40]],[0,0,0],[.8,.8,.8])
    boxes,_=person_proposals(p,640,480,cv,np)
    assert len(boxes)==0
