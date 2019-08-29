'''
Program to test RPN target generation.
'''

import torch
import sys
import numpy as np

## Inserting path of src directory
sys.path.insert(1, '../..')
from src.backbone import Backbone
from src.config import Cfg as cfg
from src.RPN import *
# from src.RPN import RPN


# Generate random input
# TODO: replace with actual image later,with vision tranforms(normalization)
input_image = torch.randn(1,3,800,800)
bbox = np.array([[20,30,400,500], [300,400,500,600], [100,200,500,600], [400,400,500,500]]) ## y1, x1, y2, x2 format!
labels = np.array([2,7])
targets = {'boxes':bbox, 'labels':labels}

backbone_obj = Backbone(cfg)
out = backbone_obj.forward(input_image)

in_channels = out.size()[1]

rpn_model = RPN(in_channels, cfg)
rpn_output = rpn_model.forward(out)
print("shape of rpn_output is: ", rpn_output['regression'].size(), rpn_output['classification'].size())

rpn_target = RPN_targets(cfg)
valid_anchors, valid_labels = rpn_target.get_targets(input_image, out, targets)
print("Shape of target output is: ", valid_anchors.shape, valid_labels.shape)

print(np.where(valid_labels==1)[0][31])
print(valid_anchors[3258,:])

## Test resnet-101
# out = backbone_obj.resnet101_backbone(input_image)
print(out.shape) 