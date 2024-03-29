"""
Testing RPNs. 
"""


"""
How to run on MILA cluster?

python test_kitti_rpn.py -dp "/network/tmp1/bhattdha/kitti_dataset" -mp "/network/tmp1/bhattdha/Denso-kitti-probabilistic-models/end_of_epoch_000000601500060.model"

"""

import torch
import os
import sys
import numpy as np
import math
import argparse
from PIL import Image, ImageDraw
import matplotlib.image as mpimg ## To load the image
from torch import optim
import os.path as path
## Inserting path of src directory
sys.path.insert(1, '../')
from src.architecture import FRCNN
from src.config import Cfg as cfg
from src.RPN import anchor_generator, RPN_targets
from src.preprocess import image_transform ## It's a function, not a class.  
from src.datasets import process_kitti_labels
from src.datasets import kitti_collate_fn
from src.datasets import KittiDataset # Dataloader
from src.loss import RPNLoss
from torchvision import datasets as dset
from torchvision import transforms as T
from src.utils import utils

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from PIL import Image

from src.NMS import nms as NMS


ap = argparse.ArgumentParser()
ap.add_argument("-dp", "--datasetpath", required = True, help="give dataset path")
ap.add_argument("-mp", "--modelpath", required = True, help="give path of the model to test")

args = vars(ap.parse_args())
dset_path = args["datasetpath"]
model_path = args["modelpath"]
checkpoint = torch.load(model_path)
cfg = checkpoint['cfg']


if not path.exists(dset_path):
	print("Dataset path doesn't exist")
	sys.exit(0)
# if not path.exists(model_dir_path):
# 	os.mkdir(model_dir_path)

# Setting the seeds
torch.manual_seed(cfg.RANDOMIZATION.SEED)
np.random.seed(cfg.RANDOMIZATION.SEED)

## setting default variable types
torch.set_default_tensor_type('torch.FloatTensor') 
torch.set_default_dtype(torch.float32)

### use cuda only if it's available and permitted

if torch.cuda.is_available() and not cfg.NO_GPU:
	cfg.USE_CUDA = True

#-----------------------------------------------#

### let's generate the dataset
transform , inverse_transform = image_transform(cfg)

kitti_dataset = KittiDataset(dset_path, transform = transform, cfg = cfg) #---- Dataloader
print("Number of Images in Dataset: ", len(kitti_dataset))

## Split into train & validation
train_len = int(cfg.TRAIN.DATASET_DIVIDE*len(kitti_dataset))
val_len = len(kitti_dataset) - train_len
kitti_train_dataset, kitti_val_dataset = torch.utils.data.random_split(kitti_dataset, [train_len, val_len])

## Dataloader for training
kitti_train_loader = torch.utils.data.DataLoader(kitti_train_dataset, batch_size=cfg.TRAIN.BATCH_SIZE, shuffle=cfg.TRAIN.DSET_SHUFFLE, collate_fn = kitti_collate_fn)
kitti_val_loader = torch.utils.data.DataLoader(kitti_val_dataset, batch_size=cfg.TRAIN.BATCH_SIZE, shuffle=cfg.TRAIN.DSET_SHUFFLE, collate_fn = kitti_collate_fn)

#----------------------------------------------#


#--------- Load the model ---------------#

frcnn = FRCNN(cfg)
if cfg.TRAIN.FREEZE_BACKBONE:
	for params in frcnn.backbone_obj.parameters():
		params.requires_grad = False


frcnn.load_state_dict(checkpoint['model_state_dict'])

rpn_target = RPN_targets(cfg)
if cfg.USE_CUDA:
	frcnn = frcnn.cuda()
	# loss_object = loss_object.cuda()
	# optimizer = optimizer.cuda()
	cfg.DTYPE.FLOAT = 'torch.cuda.FloatTensor'
	cfg.DTYPE.LONG = 'torch.cuda.LongTensor'

frcnn.eval()

## from prediction to box
def get_actual_coords(prediction, anchors):
	prediction = prediction.detach().cpu().numpy()
	prediction = prediction.reshape([prediction.shape[1], prediction.shape[2]])


	y_c = prediction[:,0]*(anchors[:,2] - anchors[:,0]) + anchors[:,0] + 0.5*(anchors[:,2] - anchors[:,0])
	x_c = prediction[:,1]*(anchors[:,3] - anchors[:,1]) + anchors[:,1] + 0.5*(anchors[:,3] - anchors[:,1])
	h = np.exp(prediction[:,2])*(anchors[:,2] - anchors[:,0])
	w = np.exp(prediction[:,3])*(anchors[:,3] - anchors[:,1])

	x1 = x_c - w/2.0
	y1 = y_c - h/2.0

	bbox_locs = np.vstack((x1, y1, w, h)).transpose() ## Final locations of the anchors
	bbox_locs_xy = np.vstack((x1, y1, x1+w, y1+h)).transpose() ## Final locations of the anchors

	# print(type(prediction), prediction.shape, anchors.shape)
	return bbox_locs, bbox_locs_xy

def check_validity(x1,y1,w,h, img_w, img_h):
	
	## bottom corner
	x2 = x1 + w
	y2 = y1 + h

	if (x1 > 0 and x2 < img_w) and (y1 > 0 and y2 < img_h):
		return True
	else:
		return False




image_number = 0

for images, labels, img_name in kitti_train_loader:
# for images, labels, img_name in kitti_val_loader:
	
	image_number += 1

	# if image_number < 7:
	# 	continue

	if cfg.USE_CUDA:
		input_image = images.cuda()

	## If there are no ground truth objects in an image, we do this to not run into an error
	if len(labels) is 0:
		continue

	targets = process_kitti_labels(cfg, labels)

	# TODO: Training pass
	# optimizer.zero_grad()
	prediction, out = frcnn.forward(input_image)

	bboxes = prediction[0]
	class_probs = prediction[1]
	uncertainties = prediction[2]
	
	print(input_image.shape, out.shape)
	# print(targets['boxes'])
	try:
		valid_anchors, valid_labels, orig_anchors = rpn_target.get_targets(input_image, out, targets)
	except:
		print("Inside exception!")
		continue
	target = {}
	target['gt_bbox'] = torch.unsqueeze(torch.from_numpy(valid_anchors),0)
	target['gt_anchor_label'] = torch.unsqueeze(torch.from_numpy(valid_labels).long(), 0) 
	valid_indices = np.where(valid_labels != -1)
	target['gt_bbox'] = target['gt_bbox'].type(cfg.DTYPE.FLOAT)
	target['gt_anchor_label'] = target['gt_anchor_label'].type(cfg.DTYPE.LONG)
	# print(orig_anchors.shape, prediction['bbox_pred'].shape)

	class_probs = torch.nn.functional.softmax(class_probs.type(cfg.DTYPE.FLOAT), dim=2)
	
	bbox_locs = utils.get_actual_coords((bboxes, class_probs, uncertainties), orig_anchors)
	
	nms = NMS(cfg.NMS_THRES)
	# print(prediction['bbox_class'].shape)
	index_to_keep = nms.apply_nms(bbox_locs, class_probs)
	index_to_keep = index_to_keep.numpy()

	print(index_to_keep)

	img = np.asarray(Image.open(img_name[0]))

	top_10_ind = index_to_keep[:15]

	box_array = []
	for i in np.arange(len(bbox_locs)):
		count = 0
		# print("Norm is: ",prediction['bbox_uncertainty_pred'][0,i,:].norm())
		# if prediction['bbox_class'][0,i,:][1].item() > 0.90 and prediction['bbox_uncertainty_pred'][0,i,:].norm() < 10.0 and i in index_to_keep:
		if class_probs[0,i,:][1].item() > 0.6:
			box_array.append(bbox_locs[i])
			# print(bbox_locs[i][0],bbox_locs[i][1],bbox_locs[i][2],bbox_locs[i][3])
			# print(prediction['bbox_class'][0,i,:][1].item(), prediction['bbox_uncertainty_pred'][0,i,:].norm())
			# valid_box = check_validity(bbox_locs[i][0],bbox_locs[i][1],bbox_locs[i][2],bbox_locs[i][3], img.shape[1], img.shape[0]) ## throw away those boxes which are not inside the image
			
	img_top10, top10pil = utils.draw_bbox(img, bbox_locs[top_10_ind])
	img, img_pil = utils.draw_bbox(img, box_array)
	# _ , img_ok = utils.draw_bbox(img, bbox_locs[valid_labels==1])

	img_pil.save('/network/home/bansaldi/Denso-OD/logs/hopefully_all_good/results/'+str(image_number).zfill(6)+'.png')
	top10pil.save('/network/home/bansaldi/Denso-OD/logs/hopefully_all_good/results/'+str(image_number).zfill(6)+'_top10.png')
	# img_ok.save('/network/home/bhattdha/'+str(image_number).zfill(6)+'_top10.png')

