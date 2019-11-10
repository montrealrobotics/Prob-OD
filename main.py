import torch
import os
import sys
import numpy as np
import math
import argparse
from PIL import Image, ImageDraw
import matplotlib.image as mpimg ## To load the image
import matplotlib.pyplot as plt
from torch import optim
import os.path as path
from torchvision import transforms as T
## Inserting path of src directory
# sys.path.insert(1, '../')

from src.architecture import FasterRCNN
from src.config import Cfg as cfg # Configuration file
from src.datasets import process_kitti_labels
from src.datasets import kitti_collate_fn
from src.datasets import KittiDataset # Dataloader
from src.utils import utils, Boxes
# from src.pytorch_nms import nms as NMS


from torchvision import datasets as dset
from torchvision import transforms as T
import torchvision
from torch.utils import tensorboard


#----- Initial paths setup and loading config values ------ #

print("\n--- Setting up the training/testing \n")

ap = argparse.ArgumentParser()
ap.add_argument("-name", "--experiment_comment", required = True, help="Comments for the experiment")
ap.add_argument("-mode", "--mode",required = True, choices=['train', 'test'])

args = vars(ap.parse_args())

dataset_path = cfg.PATH.DATASET
experiment_dir = cfg.PATH.LOGS + "/" + args["experiment_comment"]

results_dir = experiment_dir+"/results"
graph_dir = experiment_dir+"/tf_summary"
model_save_dir = experiment_dir+"/models"

if not path.exists(dataset_path):
	print("Dataset path doesn't exist")
if not path.exists(experiment_dir):
	os.mkdir(experiment_dir)
	os.mkdir(results_dir)
	os.mkdir(model_save_dir)
	os.mkdir(graph_dir)

device = torch.device("cuda") if (torch.cuda.is_available() and cfg.USE_CUDA) else torch.device("cpu")

mode = args['mode']

if mode=='train':
	is_training = True
else:
	is_training = False

torch.manual_seed(cfg.RANDOMIZATION.SEED)
np.random.seed(cfg.RANDOMIZATION.SEED)
tb_writer = tensorboard.SummaryWriter(graph_dir)

#-----------------------------------------------#5


#---------Modelling and Trainer Building------#
print("--- Building the Model \n")

model = FasterRCNN(cfg)
model = model.to(device)
model.eval()

if cfg.TRAIN.OPTIM.lower() == 'adam':
	optimizer = optim.Adam(model.parameters(), lr=cfg.TRAIN.LR, weight_decay=0.01)
elif cfg.TRAIN.OPTIM.lower() == 'sgd':
	optimizer = optim.SGD(model.parameters(), lr=cfg.TRAIN.LR, momentum=cfg.TRAIN.MOMENTUM, weight_decay=0.01)
else:
	raise ValueError('Optimizer must be one of \"sgd\" or \"adam\"')

#-------- Dataset loading and manipulation-------#

transform = utils.image_transform(cfg) # this is tranform to normalise/standardise the images

if mode=="train":
	print("--- Loading Training Dataset \n ")
	kitti_dataset = KittiDataset(dataset_path, transform = transform, cfg = cfg) #---- Dataloader
	dataset_len = len(kitti_dataset)
	## Split into train & validation
	train_len = int(cfg.TRAIN.DATASET_DIVIDE*dataset_len)
	val_len = dataset_len - train_len

	print("--- Data Loaded--- Number of Images in Dataset: {} \n".format(dataset_len))

	kitti_train_dataset, kitti_val_dataset = torch.utils.data.random_split(kitti_dataset, [train_len, val_len])

	kitti_train_loader = torch.utils.data.DataLoader(kitti_train_dataset, batch_size=cfg.TRAIN.BATCH_SIZE, 
		shuffle=cfg.TRAIN.DSET_SHUFFLE, collate_fn = kitti_collate_fn, drop_last=True)
	kitti_val_loader = torch.utils.data.DataLoader(kitti_val_dataset, batch_size=cfg.TRAIN.BATCH_SIZE, 
		shuffle=cfg.TRAIN.DSET_SHUFFLE, collate_fn = kitti_collate_fn, drop_last=True)

else:
	print("---Loading Testing Dataset")
	kitti_test_dataset = KittiDataset(dataset_path, transform = transform, cfg = cfg) #---- Dataloader
	kitti_test_loader = torch.utils.data.DataLoader(kitti_test_dataset, batch_size=cfg.TRAIN.BATCH_SIZE, 
						shuffle=cfg.TRAIN.DSET_SHUFFLE, collate_fn = kitti_collate_fn)
	print("---Data Loaded---- Number of Images in Dataset: ", len(kitti_dataset))

#----------------------------------------------#

#---------Training Cycle-----------#
print("Starting the training in 3.   2.   1.   Go \n")

epochs = cfg.TRAIN.EPOCHS
epoch = 0
lr_scheduler = optim.lr_scheduler.MultiStepLR(optimizer, milestones = cfg.TRAIN.MILESTONES, 
				gamma=cfg.TRAIN.LR_DECAY, last_epoch=-1)

while epoch <= epochs:

	epoch += 1
	running_loss = {}
	print("Epoch | Iteration | Loss ")

	for idx, batch_sample in enumerate(kitti_train_loader):

		in_images = batch_sample['image'].to(device)
		target = [x.to(device) for x in batch_sample['target']]

		boxes, rpn_proposals, proposal_losses, detector_losses = model(in_images, target, is_training)
			
		loss_dict = {}
		loss_dict.update(proposal_losses)
		# loss_dict.update(detector_losses) 

		loss = 0.0 
		for k, v in loss_dict.items():
			loss += v
		loss_dict.update({'tot_loss':loss})

		optimizer.zero_grad()
		loss.backward()
		optimizer.step()

		if (idx)%10==0:
			
			with torch.no_grad():
				#----------- Logging and Printing ----------#
				print("{:<8d} {:<9d} {:<7.4f}".format(epoch, idx, loss.item()))

				for loss_name, value in loss_dict.items():	
					tb_writer.add_scalar('Loss/'+loss_name, value.item(), epoch+0.01*idx)
				

				for key, value in loss_dict.items():
					if len(running_loss)<len(loss_dict):
						running_loss[key] = 0.0
					running_loss[key] = 0.9*running_loss[key] + 0.1*loss_dict[key].item()
				# print(running_loss)

				
				utils.tb_logger(in_images, tb_writer, boxes, rpn_proposals, "Training")
			#------------------------------------------------#

	val_loss = {}
	# val_loss_error = []

	with torch.no_grad():
		for idx, batch_sample in enumerate(kitti_val_loader):
			
			in_images = batch_sample['image'].to(device)
			target = [x.to(device) for x in batch_sample['target']]

			boxes, rpn_proposals, proposal_losses, detector_losses = model(in_images, target, is_training)

			loss_dict = {}
			loss_dict.update(proposal_losses)
			# loss_dict.update(detector_losses)

			loss = 0.0 
			for k, v in loss_dict.items():
				loss += v
			loss_dict.update({'tot_loss':loss})

			for key, value in loss_dict.items():
				if len(val_loss)<len(loss_dict):
					val_loss[key] = []
				val_loss[key].append(loss_dict[key].item())

			utils.tb_logger(in_images, tb_writer, boxes, rpn_proposals, "Validation")

		for key, value in  val_loss.items():
			val_loss[key] = np.mean(val_loss[key])

		for key in val_loss.keys():
			tb_writer.add_scalars('loss/'+key, {'validation': val_loss[key], 'train': running_loss[key]}, epoch)


		print("Epoch ---- {} ".format(epoch))
		print("Epoch      Training   Validation")
		print("{} {:>13.4f}    {:0.4f}".format(epoch, running_loss['tot_loss'], val_loss['tot_loss']))
		
	## Decaying learning rate
	lr_scheduler.step()

	print("Epoch Complete: ", epoch)
	# # Saving at the end of the epoch
	if epoch % cfg.TRAIN.SAVE_MODEL_EPOCHS == 0:
		model_path = model_save_dir + "/epoch_" +  str(epoch).zfill(5) + '.model'
		torch.save({
				'epoch': epoch,
				'model_state_dict': model.state_dict(),
				'optimizer_state_dict': optimizer.state_dict(),
				'loss': running_loss,
				'cfg': cfg
				 }, model_path)

		# with open(checkpoint_path, 'w') as f:
		# 	f.writelines(model_path)

tb_writer.close()
# file.close()