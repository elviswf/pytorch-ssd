from __future__ import print_function

import os
import argparse
import itertools

import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import torch.backends.cudnn as cudnn

import torchvision
import torchvision.transforms as transforms

from ssd import SSD300
from utils import progress_bar
from datagen import ListDataset
from encoder import DataEncoder
from multibox_loss import MultiBoxLoss

from torch.autograd import Variable


parser = argparse.ArgumentParser(description='PyTorch SSD Training')
parser.add_argument('--lr', default=1e-3, type=float, help='learning rate')
parser.add_argument('--resume', '-r', action='store_true', help='resume from checkpoint')
args = parser.parse_args()

use_cuda = torch.cuda.is_available()

# Data
print('==> Preparing data..')
transform = transforms.Compose([transforms.ToTensor(),
                                transforms.Lambda(lambda x: x.mul(255.)),
                                transforms.Normalize((123., 117., 104.), (1.,1.,1.))])

trainset = ListDataset(root='/search/liukuang/data/VOC2007/JPEGImages', list_file='./voc_data/index.txt', train=True, transform=transform)
trainloader = torch.utils.data.DataLoader(trainset, batch_size=32, shuffle=True, num_workers=4)

testset = ListDataset(root='/search/liukuang/data/VOC2007/JPEGImages', list_file='./voc_data/index.txt', train=False, transform=transform)
testloader = torch.utils.data.DataLoader(testset, batch_size=32, shuffle=False, num_workers=4)

data_encoder = DataEncoder()

# Model
net = SSD300()
criterion = MultiBoxLoss()
#net.load_state_dict(torch.load('./model/ssd.pth'))

if use_cuda:
    net = torch.nn.DataParallel(net, device_ids=[0,1,2,3,4,5,6,7])
    net.cuda()
    cudnn.benchmark = True

optimizer = optim.SGD(net.parameters(), lr=args.lr, momentum=0.9, weight_decay=1e-4)
#optimizer = optim.Adam(net.parameters(), lr=args.lr, weight_decay=1e-4)

# Training
def train(epoch):
    print('\nEpoch: %d' % epoch)
    net.train()
    train_loss = 0
    for batch_idx, (images, indices) in enumerate(trainloader):
        boxes, labels = trainset.load_boxes_and_labels(indices)
        batch_size = len(boxes)

        loc_targets = torch.Tensor(batch_size, 8732, 4)
        conf_targets = torch.LongTensor(batch_size, 8732)
        for i in range(batch_size):
            loc_target, conf_target = data_encoder.encode(boxes[i], labels[i])
            loc_targets[i] = loc_target
            conf_targets[i] = conf_target

        if use_cuda:
            images = images.cuda()
            loc_targets = loc_targets.cuda()
            conf_targets = conf_targets.cuda()

        images = Variable(images)
        loc_targets = Variable(loc_targets)
        conf_targets = Variable(conf_targets)

        optimizer.zero_grad()
        loc_preds, conf_preds = net(images)
        loss = criterion(loc_preds, loc_targets, conf_preds, conf_targets)
        loss.backward()
        optimizer.step()

        train_loss += loss.data[0]
        print('%.3f %.3f' % (loss.data[0], train_loss/(batch_idx+1)))

def test(epoch):
    print('\nTest')
    net.eval()
    test_loss = 0
    for batch_idx, (images, indices) in enumerate(testloader):
        boxes, labels = testset.load_boxes_and_labels(indices)
        batch_size = len(boxes)

        loc_targets = torch.Tensor(batch_size, 8732, 4)
        conf_targets = torch.LongTensor(batch_size, 8732)
        for i in range(batch_size):
            loc_target, conf_target = data_encoder.encode(boxes[i], labels[i])
            loc_targets[i] = loc_target
            conf_targets[i] = conf_target

        if use_cuda:
            images = images.cuda()
            loc_targets = loc_targets.cuda()
            conf_targets = conf_targets.cuda()

        images = Variable(images, volatile=True)
        loc_targets = Variable(loc_targets)
        conf_targets = Variable(conf_targets)

        loc_preds, conf_preds = net(images)
        loss = criterion(loc_preds, loc_targets, conf_preds, conf_targets)
        test_loss += loss.data[0]
        print('%.3f %.3f' % (loss.data[0], test_loss/(batch_idx+1)))


for epoch in range(200):
    train(epoch)
    test(epoch)
