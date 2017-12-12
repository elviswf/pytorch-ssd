import argparse
import os

import torch
import torch.backends.cudnn as cudnn
import torch.optim as optim
import torchvision.transforms as transforms
from torch.autograd import Variable

from data.datagen import ListDataset
from models.multibox_loss import MultiBoxLoss
from models.ssd import SSD300
from utils.utils import progress_bar

# CUDA_VISIBLE_DEVICES=0,1,2 python train.py
parser = argparse.ArgumentParser(description='PyTorch SSD Training')
parser.add_argument('--lr', default=1e-3, type=float, help='learning rate')
parser.add_argument('--resume', '-r', action='store_true', help='resume from checkpoint')
args = parser.parse_args()
BATCH_SIZE = 1
use_cuda = torch.cuda.is_available()
# CUDA_VISIBLE_DEVICES = 0, 1, 2
best_loss = float('inf')  # best test loss
start_epoch = 0  # start from epoch 0 or last epoch

# Model
net = SSD300()
if args.resume:
    print('==> Resuming from checkpoint..')
    checkpoint = torch.load('./checkpoint/ckpt.pth')
    net.load_state_dict(checkpoint['net'])
    best_loss = checkpoint['loss']
    start_epoch = checkpoint['epoch']
# else:
    # Convert from pretrained VGG model.
    # net.load_state_dict(torch.load('./log/model/vgg16-397923af.pth'))

# Data
print('==> Preparing data..')
transform = transforms.Compose([transforms.ToTensor(),
                                transforms.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225))])

trainset = ListDataset(root='/home/elvis/data/pascalVOC/VOCdevkit/VOC2012/JPEGImages',
                       list_file='./voc_data/voc12_train.txt', train=True, transform=transform)
trainloader = torch.utils.data.DataLoader(trainset, batch_size=BATCH_SIZE, shuffle=True, num_workers=4)

testset = ListDataset(root='/home/elvis/data/pascalVOC/VOCdevkit/VOC2012/JPEGImages',
                      list_file='./voc_data/voc12_test.txt', train=False, transform=transform)
testloader = torch.utils.data.DataLoader(testset, batch_size=BATCH_SIZE, shuffle=False, num_workers=4)

criterion = MultiBoxLoss()
if use_cuda:
    net = torch.nn.DataParallel(net, device_ids=[0, 1, 2, 3, 4, 5, 6, 7])
    net.cuda()
    cudnn.benchmark = True

optimizer = optim.SGD(net.parameters(), lr=args.lr, momentum=0.9, weight_decay=1e-4)


# Training
def train(epoch):
    print('\nEpoch: %d' % epoch)
    net.train()
    train_loss = 0
    for batch_idx, (images, loc_targets, conf_targets) in enumerate(trainloader):
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
        # print('%.3f %.3f' % (loss.data[0], train_loss / (batch_idx + 1)))
        progress_bar(batch_idx, len(trainloader), "iter Loss: %.3f | Avg Loss: %.3f%%"
                     % (loss.data[0], train_loss / (batch_idx + 1)))


def test(epoch):
    print('\nTest')
    net.eval()
    test_loss = 0
    for batch_idx, (images, loc_targets, conf_targets) in enumerate(testloader):
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
        print('%.3f %.3f' % (loss.data[0], test_loss / (batch_idx + 1)))
        progress_bar(batch_idx, len(testloader), "iter Loss: %.3f | Avg Loss: %.3f%%"
                     % (loss.data[0], test_loss / (batch_idx + 1)))

    # Save checkpoint.
    global best_loss
    test_loss /= len(testloader)
    if test_loss < best_loss:
        print('Saving..')
        state = {
            'net': net.module.state_dict(),
            'loss': test_loss,
            'epoch': epoch,
        }
        if not os.path.isdir('checkpoint'):
            os.mkdir('checkpoint')
        torch.save(state, './checkpoint/ckpt.pth')
        best_loss = test_loss


for epoch in range(start_epoch, start_epoch + 200):
    train(epoch)
    test(epoch)
