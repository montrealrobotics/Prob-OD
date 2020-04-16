import sys
import os
import time

import numpy as np
import matplotlib.pyplot as plt

import torch
from torch import optim
from torch.utils import tensorboard
from torchvision import transforms as T

from ..architecture import build_model
from ..datasets import build_dataset
from ..eval.detection_map import DetectionMAP
from ..tracker import MultiObjTracker
from ..utils import Instances, Boxes, utils


class General_Solver(object):
    """
    This is a General Solver class which comprises of 
    all different parts realted to training or 
    inference. 
    """
    def __init__(self, cfg, mode, args):
        super(General_Solver, self).__init__()

        self.device = torch.device("cuda") if (torch.cuda.is_available() and cfg.USE_CUDA) else torch.device("cpu")
        print("--- Using the device for training: {} \n".format(self.device))
        self.setup_dirs(cfg, args.name)

        self.model = self.get_model(cfg)
        self.optimizer, self.lr_scheduler = self.build_optimizer(cfg)

        if args.weights or args.resume:
            self.load_checkpoint(cfg, args)

        self.train_loader, self.val_loader = self.get_dataloader(cfg, mode)
        
        self.tb_writer = tensorboard.SummaryWriter(os.path.join(self.exp_dir,"tf_summary"))
        self.is_training = True
        self.epoch = 0

    def get_model(self, cfg):
        print("--- Building the Model \n")
        # print(cfg.ROI_HEADS.SCORE_THRESH_TEST)
        model = build_model(cfg.ARCHITECTURE.MODEL)(cfg)
        model = model.to(self.device)

        return model
    
    def save_checkpoint(self):
        model_path = os.path.join(self.exp_dir,"models", "epoch_"+str(epoch).zfill(5)+ ".model")
        torch.save({
                'model_state_dict': self.model.state_dict(),
                'optimizer_state_dict': self.optimizer.state_dict(),
                'lr_scheduler' : self.lr_scheduler.state_dict(),
                 }, model_path)

    def load_checkpoint(self, cfg, args):
        if args.weights:
            print("--- Using pretrainted weights from: {}".format(args.weights))
            checkpoint = torch.load(args.weights)
            self.model.load_state_dict(checkpoint['model_state_dict'], strict=False)

        elif args.resume:
            print("    :Resuming the training \n")
            self.epoch = args['epoch'] #With which epoch you want to resume the training.
            checkpoint = torch.load(model_save_dir + "/epoch_" +  str(epoch).zfill(5) + '.model')
            
            self.model.load_state_dict(checkpoint['model_state_dict'], strict=False)
            self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
            self.lr_scheduler.load_state_dict(checkpoint['lr_scheduler'])

        
    def get_dataloader(self, cfg, mode):
        dataset = build_dataset(cfg.DATASET.NAME)
        dataset_path = cfg.DATASET.PATH
        assert os.path.exists(dataset_path), "Dataset path doesn't exist."
        
        transform = utils.image_transform(cfg) # this is tranform to normalise/standardise the images
        batch_size = cfg.TRAIN.BATCH_SIZE

        print("--- Loading Training Dataset \n ")
        tracks = [str(i).zfill(4) for i in range(11)]
        train_dataset = dataset(dataset_path, tracks,transform = transform, cfg = cfg) #---- Dataloader
        
        print("--- Loading Validation Dataset \n ")
        tracks = [str(i).zfill(4) for i in range(11,14)]
        val_dataset = dataset(dataset_path, tracks, transform=transform, cfg=cfg)

        print("--- Data Loaded---")
        print("Number of Images in Train Dataset: {} \n".format(len(train_dataset)))
        print("Number of Images in Val Dataset: {} \n".format(len(val_dataset)))
        print("Number of Classes in Dataset: {} \n".format(cfg.INPUT.NUM_CLASSES))

        # train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_len, val_len])

        train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=batch_size,
                    shuffle=cfg.TRAIN.DSET_SHUFFLE, collate_fn = train_dataset.collate_fn, drop_last=True)

        val_loader = torch.utils.data.DataLoader(val_dataset, batch_size=batch_size,
                    shuffle=False, collate_fn = val_dataset.collate_fn, drop_last=True)

        # print(train_dataset[500], train_dataset[501])
        # print(train_dataset.collate_fn([train_dataset[500], train_dataset[501]]))

        return train_loader, val_loader

    def build_optimizer(self, cfg):
        if cfg.SOLVER.OPTIM.lower() == 'adam':
            optimizer = optim.Adam(self.model.parameters(), lr=cfg.TRAIN.LR, weight_decay=0.01)
        elif cfg.SOLVER.OPTIM.lower() == 'sgd':
            optimizer = optim.SGD(self.model.parameters(), lr=cfg.TRAIN.LR, momentum=cfg.TRAIN.MOMENTUM, weight_decay=0.01)
        else:
            raise ValueError('Optimizer must be one of \"sgd\" or \"adam\"')

        lr_scheduler = optim.lr_scheduler.MultiStepLR(optimizer, milestones = cfg.TRAIN.MILESTONES,
                        gamma=cfg.TRAIN.LR_DECAY, last_epoch=-1)

        return optimizer, lr_scheduler

    def setup_dirs(self, cfg, name):
        self.exp_dir = os.path.join(cfg.LOGS.BASE_PATH, name)
        if not os.path.exists(self.exp_dir):
            os.mkdir(self.exp_dir)
            os.mkdir(os.path.join(self.exp_dir,"models"))
            os.mkdir(os.path.join(self.exp_dir,"results"))
            os.mkdir(os.path.join(self.exp_dir,"tf_summary"))
        else:
            "Directory exists, You may want to resume instead of starting fresh."
    
    def train_step(self, batch_sample):
        pass

    def validation_step(self):
        pass
    
    def train(self, epochs, saving_freq):
        assert self.model.train
        self.is_training = True
        while self.epoch <= epochs:

            running_loss = {}
            print("Epoch | Iteration | Loss ")

            for idx, batch_sample in enumerate(self.train_loader):
                loss_dict = self.train_step(batch_sample)
                
                if bool(loss_dict):                
                    if (idx)%10==0:
                        with torch.no_grad():
                            #----------- Logging and Printing ----------#
                            print("{:<8d} {:<9d} {:<7.4f}".format(epoch, idx, loss_dict['tot_loss'].item()))
                            for loss_name, value in loss_dict.items():
                                self.tb_writer.add_scalar('Loss/'+loss_name, value.item(), epoch+0.01*idx)
                            for key, value in loss_dict.items():
                                if len(running_loss)<len(loss_dict):
                                    running_loss[key] = 0.0
                                running_loss[key] = 0.9*running_loss[key] + 0.1*loss_dict[key].item()
                            # utils.tb_logger(in_images, tb_writer, rpn_proposals, instances, "Training")
                        #------------------------------------------------#
            val_loss = self.validation_step()
            
            for key in val_loss.keys():
                tb_writer.add_scalars('loss/'+key, {'validation': val_loss[key], 'train': running_loss[key]}, epoch)

            # print("Epoch ---- {} ".format(self.epoch))
            print("Epoch      Training   Validation")
            print("{} {:>13.4f}    {:0.4f}".format(epoch, running_loss['tot_loss'], val_loss['tot_loss']))

            ## Decaying learning rate
            self.lr_scheduler.step()

            print("Epoch Complete: ", self.epoch)
            # # Saving at the end of the epoch
            if self.epoch % saving_freq == 0:
                self.save_checkpoint()

            self.epoch += 1

        self.tb_writer.close()
    

class BackpropKF_Solver(General_Solver):
    """docstring for BackpropKF_Solver"""
    def __init__(self, cfg, mode, args):
        super(BackpropKF_Solver, self).__init__(cfg, mode, args)
        pass

    def train_step(self, batch_sample):
        self.model.tracker.reinit_state()
        for seq in batch_sample:
            in_images = seq['image'].to(self.device)
            target = [x.to(self.device) for x in seq['target']]
            rpn_proposals, instances, tracks, _, _, track_loss = self.model(in_images, target, self.is_training)
        
        loss_dict = {}
        loss_dict.update(track_loss)
        # loss_dict.update(detector_losses)
        
        loss = 0.0
        for k, v in loss_dict.items():
            loss += v
        loss_dict.update({'tot_loss':loss})

        self.optimizer.zero_grad()
        if loss!=0.0:
            loss.backward()
        self.optimizer.step()

        return loss_dict

    def validation_step(self):
        self.model.eval()
        val_loss = {}
        with torch.no_grad():
            for idx, batch_sample in enumerate(self.val_loader):
                for seq in batch_sample:
                    in_images = seq['image'].to(self.device)
                    target = [x.to(self.device) for x in seq['target']]
                    rpn_proposals, instances, tracks,_, _, track_loss = self.model(in_images, target, self.is_training)

                loss_dict = {}
                loss_dict.update(track_loss)
                # loss_dict.update(detector_losses)

                loss = 0.0
                for k, v in loss_dict.items():
                    loss += v
                loss_dict.update({'tot_loss':loss})

                for key, value in loss_dict.items():
                    if len(val_loss)<len(loss_dict):
                        val_loss[key] = [loss_dict[key].item()]
                    val_loss[key].append(loss_dict[key].item())

                # utils.tb_logger(in_images, tb_writer, rpn_proposals, instances, "Validation")

            for key, value in  val_loss.items():
                val_loss[key] = np.mean(val_loss[key])

        self.model.train()
        return val_loss

    def train(self, epochs, saving_freq):
        self.is_training = True
        while self.epoch <= epochs:

            running_loss = {}
            print("Epoch | Iteration | Loss ")

            #batch_sample: [seq_length, batch_size, input_size]
            for idx, batch_sample in enumerate(self.train_loader):
                loss_dict = self.train_step(batch_sample)

                if idx%10==0:
                    print(loss_dict['tot_loss'])
                
            #     if loss_dict['tot_loss']!=0:
            #         if (idx)%10==0:
            #             with torch.no_grad():
            #                 #----------- Logging and Printing ----------#
            #                 print("{:<8d} {:<9d} {:<7.4f}".format(self.epoch, idx, loss_dict['tot_loss'].item()))
            #                 for loss_name, value in loss_dict.items():
            #                     self.tb_writer.add_scalar('Loss/'+loss_name, value.item(), self.epoch+0.01*idx)
            #                 for key, value in loss_dict.items():
            #                     if len(running_loss)<len(loss_dict):
            #                         running_loss[key] = 0.0
            #                     running_loss[key] = 0.9*running_loss[key] + 0.1*loss_dict[key].item()
            #                 # utils.tb_logger(in_images, tb_writer, rpn_proposals, instances, "Training")
            #         #------------------------------------------------#
            # val_loss = self.validation_step()
            
            # for key in val_loss.keys():
            #     tb_writer.add_scalars('loss/'+key, {'validation': val_loss[key], 'train': running_loss[key]}, self.epoch)

            # # print("Epoch ---- {} ".format(self.epoch))
            # print("Epoch      Training   Validation")
            # print("{} {:>13.4f}    {:0.4f}".format(self.epoch, running_loss['tot_loss'], val_loss['tot_loss']))

            ## Decaying learning rate
            self.lr_scheduler.step()

            # print("Epoch Complete: ", self.epoch)
            # # Saving at the end of the epoch
            if self.epoch % saving_freq == 0:
                self.save_checkpoint()

            self.epoch += 1

        self.tb_writer.close()




        