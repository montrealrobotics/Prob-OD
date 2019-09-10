'''
Program to test RPN target generation.
'''

import torch
import sys
import numpy as np
import matplotlib.image as mpimg ## To load the image

## Inserting path of src directory
sys.path.insert(1, '../..')
from src.backbone import Backbone
from src.config import Cfg as cfg
from src.RPN import *
from src.preprocess import image_transform ## It's a function, not a class. 
from PIL import Image
# from src.RPN import RPN


# Generate random input
# TODO: replace with actual image later,with vision tranforms(normalization)
img = mpimg.imread('test.jpg')		## Gives RGB image of dimension H x W x C with inten values between 0-255
print(img.shape)
tranform = image_transform(cfg)
# print(list(cfg.INPUT.MEAN))
input_image = tranform(img)
input_image = torch.unsqueeze(input_image, dim=0)
print(input_image.shape)
bbox = np.array([[20,30,400,500], [300,400,500,600], [100,200,500,600], [400,400,500,500]]) ## y1, x1, y2, x2 format!
labels = np.array([2,7,3,2])
targets = {'boxes':bbox, 'labels':labels}

backbone_obj = Backbone(cfg)
rpn_model = RPN(backbone_obj.out_channels, cfg)

heights = [550,650,734,616,734,892,581,520]
widths = [635,724,519,643,829,871,757,420]

for h in heights:
    for w in widths:
        input_image = torch.randn(1,3,h,w)

        out = backbone_obj.forward(input_image)
        rpn_output = rpn_model.forward(out)

        print("shape of rpn_output is: ", rpn_output['bbox_pred'].size(), rpn_output['bbox_class'].size())

        rpn_target = RPN_targets(cfg)
        valid_anchors, valid_labels = rpn_target.get_targets(input_image, out, targets)
        print("Shape of target output is: ", valid_anchors.shape, valid_labels.shape)

## Test resnet-101
# out = backbone_obj.resnet101_backbone(input_image)
print(out.shape) 


