"""
Training RPNs. 
"""


"""
How to run on MILA cluster?

python train_scenes.py -dp "/network/tmp1/bhattdha/Nuscenes/" -ap "/network/tmp1/bhattdha/Nuscenes/2d_car_annotations.json" -mp "/network/tmp1/bhattdha/Denso-nuscenes-models/"

"""

import torch
import os
import sys
import numpy as np
import math
import argparse
from PIL import Image
import matplotlib.image as mpimg ## To load the image
from torch import optim
import os.path as path
## Inserting path of src directory
sys.path.insert(1, '../')
from src.architecture import FRCNN
from src.config import Cfg as cfg
from src.RPN import anchor_generator, RPN_targets
from src.preprocess import image_transform ## It's a function, not a class.  
from src.datasets import process_nuscenes_labels
from src.datasets import nuscenes_collate_fn
from src.datasets import NuscDataset
from src.loss import RPNLoss
from torchvision import datasets as dset
from torchvision import transforms as T

ap = argparse.ArgumentParser()
ap.add_argument("-dp", "--datasetpath", required = True, help="give dataset path")
ap.add_argument("-ap", "--annotationpath", required = True, help="give annotation file path")
ap.add_argument("-mp", "--modelpath", required = True, help="give model directory path")

args = vars(ap.parse_args())
dset_path = args["datasetpath"]
ann_path = args["annotationpath"]
model_dir_path = args["modelpath"]

if not path.exists(dset_path):
	print("Dataset path doesn't exist")
if not path.exists(ann_path):
	print("Annotation path doesn't exist")
if not path.exists(model_dir_path):
	os.mkdir(model_dir_path)

# Setting the seeds
torch.manual_seed(5)
np.random.seed(5)

## setting default variable types
torch.set_default_tensor_type('torch.FloatTensor') 
torch.set_default_dtype(torch.float32)

### use cuda only if it's available and permitted

if torch.cuda.is_available() and not cfg.NO_GPU:
	cfg.USE_CUDA = True

### let's generate the dataset
transform = image_transform(cfg)

## With the Nuscenes dataloader
nusc_dataset = NuscDataset(dset_path, ann_path, transform = transform, cfg = cfg) 

## Split into train test
train_len = int(cfg.TRAIN.DATASET_DIVIDE*len(nusc_dataset))
test_len = len(nusc_dataset) - train_len
nusc_train_dataset, nusc_test_dataset = torch.utils.data.random_split(nusc_dataset, [train_len, test_len])

## Dataloader for training
nusc_train_loader = torch.utils.data.DataLoader(nusc_train_dataset, batch_size=cfg.TRAIN.BATCH_SIZE, shuffle=cfg.TRAIN.DSET_SHUFFLE, collate_fn = nuscenes_collate_fn)
nusc_test_loader = torch.utils.data.DataLoader(nusc_test_dataset, batch_size=cfg.TRAIN.BATCH_SIZE, shuffle=cfg.TRAIN.DSET_SHUFFLE, collate_fn = nuscenes_collate_fn)

frcnn = FRCNN(cfg)
if cfg.TRAIN.FREEZE_BACKBONE:
	for params in frcnn.backbone_obj.parameters():
		params.requires_grad = False

## Initialize RPN params

if cfg.TRAIN.OPTIM.lower() == 'adam':
	optimizer = optim.Adam(frcnn.parameters(), lr=cfg.TRAIN.LR)
elif cfg.TRAIN.OPTIM.lower() == 'sgd':
	optimizer = optim.SGD(frcnn.parameters(), lr=cfg.TRAIN.LR, momentum=cfg.TRAIN.MOMENTUM)
else:
	raise ValueError('Optimizer must be one of \"sgd\" or \"adam\"')

checkpoint_path = model_dir_path + 'checkpoint.txt'

if path.exists(checkpoint_path):
	with open(checkpoint_path, "r") as f: 
		model_path = f.readline().strip('\n')

	## Only load if such a model exists
	if path.exists(model_path):

		checkpoint = torch.load(model_path)
		frcnn.load_state_dict(checkpoint['model_state_dict'])


		## TO load the optimizer state with cuda
		optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
		for state in optimizer.state.values():
			for k, v in state.items():
				if isinstance(v, torch.Tensor):
					state[k] = v.cuda() 
		epoch = checkpoint['epoch']
		loss = checkpoint['loss']

	else:
		optimizer = optim.Adam(frcnn.parameters(), lr=cfg.TRAIN.ADAM_LR)
		epoch = 0
		loss = 0
else:
	# ## When you are running for the first time.
	# with open(checkpoint_path, 'w') as f:
	# 	f.writelines('')
	# optimizer = optim.Adam(frcnn.parameters(), lr=cfg.TRAIN.LR)
	epoch = 0
	loss = 0

## Initializing RPN biases

loss_object = RPNLoss(cfg)

rpn_target = RPN_targets(cfg)
if cfg.USE_CUDA:
	frcnn = frcnn.cuda()
	loss_object = loss_object.cuda()
	# optimizer = optimizer.cuda()
	cfg.DTYPE.FLOAT = 'torch.cuda.FloatTensor'
	cfg.DTYPE.LONG = 'torch.cuda.LongTensor'


epochs = cfg.TRAIN.EPOCHS
## Learning rate scheduler
# lr_scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=cfg.TRAIN.LR_DECAY_EPOCHS, gamma=cfg.TRAIN.LR_DECAY, last_epoch=-1)

lr_scheduler = optim.lr_scheduler.MultiStepLR(optimizer, milestones = cfg.TRAIN.MILESTONES, gamma=cfg.TRAIN.LR_DECAY, last_epoch=-1)
frcnn.train()

# for n, p in frcnn.rpn_model.named_parameters():
# 	print(n)

while epoch <= epochs:
	epoch += 1
	image_number = 0
	running_loss = 0
	running_loss_classify = 0.
	running_loss_regress = 0.

	batch_loss = 0.
	batch_loss_regress = 0.
	batch_loss_classify = 0.
	batch_loss_regress_bbox = 0.
	batch_loss_regress_sigma = 0.
	batch_loss_regress_neg = 0.
	batch_loss_regress_bbox_only = 0.

	for idx, (images, labels, paths) in enumerate(nusc_train_loader):
		
		# get ground truth in correct format
		
		input_image = images
		if cfg.USE_CUDA:
			input_image = input_image.cuda()

		## If there are no ground truth objects in an image, we do this to not run into an error
		if len(labels) is 0:
			continue

		targets = process_nuscenes_labels(cfg, labels)
		# optimizer.zero_grad()

		prediction, out = frcnn.forward(input_image)

		try:
			valid_anchors, valid_labels, xx = rpn_target.get_targets(input_image, out, targets)
		except:
			print("Inside exception!")
			continue

		
		# print(targets['boxes'])
		
		image_number += 1
		target = {}
		target['gt_bbox'] = torch.unsqueeze(torch.from_numpy(valid_anchors),0)
		target['gt_anchor_label'] = torch.unsqueeze(torch.from_numpy(valid_labels).long(), 0) 
		valid_indices = np.where(valid_labels != -1)
		prediction['bbox_pred'] = prediction['bbox_pred'].type(cfg.DTYPE.FLOAT)
		prediction['bbox_uncertainty_pred'] = prediction['bbox_uncertainty_pred'].type(cfg.DTYPE.FLOAT)
		prediction['bbox_class'] = prediction['bbox_class'].type(cfg.DTYPE.FLOAT)
		target['gt_bbox'] = target['gt_bbox'].type(cfg.DTYPE.FLOAT)
		target['gt_anchor_label'] = target['gt_anchor_label'].type(cfg.DTYPE.LONG)
		loss_classify, loss_regress_bbox, loss_regress_sigma, loss_regress_neg, loss_regress_bbox_only = loss_object(prediction, target, valid_indices)

		batch_loss_classify += loss_classify
		# batch_loss_regress += loss_regress
		batch_loss_regress_bbox += loss_regress_bbox
		batch_loss_regress_sigma += loss_regress_sigma
		batch_loss_regress_neg += loss_regress_neg
		batch_loss_regress_bbox_only += loss_regress_bbox_only

		# if math.isnan(loss_classify.item()) or math.isnan(loss_regress.item()):
		# 	print("NaN detected.")
		# 	continue

		if cfg.TRAIN.FAKE_BATCHSIZE > 0 and image_number % cfg.TRAIN.FAKE_BATCHSIZE == 0 and idx > 0:
			batch_loss_regress = batch_loss_regress_bbox + batch_loss_regress_sigma + batch_loss_regress_neg
			batch_loss = (batch_loss_regress + cfg.TRAIN.CLASS_LOSS_SCALE*batch_loss_classify)/cfg.TRAIN.FAKE_BATCHSIZE
			batch_loss.backward()
			# batch_loss_classify.backward()
			# batch_loss_regress.backward()
			optimizer.step()
			print("Class/Reg loss:", batch_loss_classify.item()/cfg.TRAIN.FAKE_BATCHSIZE, " ", batch_loss_regress.item()/cfg.TRAIN.FAKE_BATCHSIZE, " epoch and image_number: ", epoch, image_number)
			print("only:", batch_loss_regress_bbox_only.item(), "bbox: ", batch_loss_regress_bbox.item(), 
				"sigma:", batch_loss_regress_sigma.item(), "neg:", batch_loss_regress_neg.item())
			# print("Class/Reg grads: ", frcnn.rpn_model.classification_layer.weight.grad.norm().item(), frcnn.rpn_model.reg_layer.weight.grad.norm().item())
			# paramList = list(filter(lambda p : p.grad is not None, [param for param in frcnn.rpn_model.parameters()]))
			# totalNorm = sum([(p.grad.data.norm(2.) ** 2.) for p in paramList]) ** (1. / 2)
			# print('gradNorm: ', str(totalNorm.item()))
			optimizer.zero_grad()
			# batch_loss.detach()
			# batch_loss_regress.detach()
			# batch_loss_classify.detach()
			batch_loss = 0.
			batch_loss_classify = 0.
			batch_loss_regress = 0.
			batch_loss_regress_bbox = 0.
			batch_loss_regress_sigma = 0.
			batch_loss_regress_neg = 0.
			batch_loss_regress_bbox_only = 0.

		# print(loss.item(), loss, loss.type(), targets)
		# loss.backward()

		# print("class and reg grads are: ",frcnn.rpn_model.classification_layer.weight.grad.norm().item(), frcnn.rpn_model.reg_layer.weight.grad.norm().item())
		# print("class grad is: ",frcnn.rpn_model.classification_layer.weight.grad.norm().item())
		# optimizer.step()
		# running_loss += (loss_regress.item() + loss_classify.item())
		running_loss_classify += loss_classify.item()
		running_loss_regress += (loss_regress_bbox.item() + loss_regress_sigma.item() + loss_regress_neg.item())

		# print("Classification loss is:", loss_object.class_loss.item(), " and regression loss is:", loss_object.reg_loss.item(), " epoch and image_number: ", epoch, image_number)
		# print(f"Training loss: {loss.item()}", " epoch and image_number: ", epoch, image_number)

		### Save model and other things at every 10000 images.
		### TODO: Make this number a variable for config file

		# if image_number%1000 == 0:
		# 	### Save model!
		# 	model_path = model_dir_path + str(image_number).zfill(10) +  str(epoch).zfill(5) + '.model'
		# 	torch.save({
		# 			'epoch': epoch,
		# 			'model_state_dict': frcnn.state_dict(),
		# 			'optimizer_state_dict': optimizer.state_dict(),
		# 			'loss': loss,
		# 			'cfg': cfg
		# 			 }, model_path)

		# 	with open(checkpoint_path, 'w') as f:
		# 		f.writelines(model_path)		

	print(f"Running loss (classification) {running_loss_classify/(len(nusc_train_loader) // cfg.TRAIN.FAKE_BATCHSIZE)}, \t Running loss (regression): {running_loss_regress/(len(nusc_train_loader) // cfg.TRAIN.FAKE_BATCHSIZE)}")

	# # Saving at the end of the epoch
	if epoch % cfg.TRAIN.SAVE_MODEL_EPOCHS == 0:
		model_path = model_dir_path + "end_of_epoch_" + str(image_number).zfill(10) +  str(epoch).zfill(5) + '.model'
		torch.save({
				'epoch': epoch,
				'model_state_dict': frcnn.state_dict(),
				'optimizer_state_dict': optimizer.state_dict(),
				'loss': running_loss,
				'cfg': cfg
				 }, model_path)

		with open(checkpoint_path, 'w') as f:
			f.writelines(model_path)

	## For learing rate decay
	lr_scheduler.step()