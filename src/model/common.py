import math

import torch
import torch.nn as nn
import torch.nn.functional as F

from torch.autograd import Variable

def conv3x3(inFeat, outFeat, stride=1, padding=1, groups=1, bias=True):
    return nn.Conv2d(
        inFeat, outFeat, kernel_size=3,
        stride=stride, padding=padding, groups=groups, bias=bias)

def initGAN(m):
    className = m.__class__.__name__
    if className.find('Conv') >= 0:
        m.weight.data.normal_(0.0, 0.02)
    elif className.find('BatchNorm') >= 0:
        m.weight.data.normal_(1.0, 0.02)
        m.bias.data.fill_(0)

class MeanShift(nn.Module):
    def __init__(self, rgbMean):
        super(MeanShift, self).__init__()
        r = rgbMean[0]
        g = rgbMean[1]
        b = rgbMean[2]

        self.shifter = nn.Conv2d(3, 3, kernel_size=1, stride=1, padding=0)
        self.shifter.weight.data = torch.eye(3).view(3, 3, 1, 1)
        self.shifter.bias.data = torch.Tensor([r, g, b])

        # Freeze the meanShift layer
        for params in self.shifter.parameters():
            params.requires_grad = False

    def forward(self, x):
        x = self.shifter(x)

        return x

class BasicModule(nn.Module):
    def __init__(self, nFeat, bn=False, act=nn.ReLU(True)):
        super(BasicModule, self).__init__()

        self.modules = [nn.Conv2d(nFeat, nFeat, 3, 1, 1)]
        if bn:
            self.modules += [nn.BatchNorm2d(nFeat)]
        if act is not None:
            self.modules += [act]
        self.body = nn.Sequential(*self.modules)

    def forward(self, x):
        out = self.body(x)

        return out
        
class BTResBlock(nn.Module):
    def __init__(self, nFeat, nBTFeat, kernel_size=3, dilation=1, bn=False, act=nn.ReLU(True)):
        super(BTResBlock, self).__init__()

        if dilation == 1: 
            padding = 1
        elif dilation == 2: 
            padding = 2

        modules = []
        modules.append(nn.Conv2d(
            nFeat, nBTFeat, kernel_size=1))
        if bn:
            modules.append(nn.BatchNorm2d(nFeat))
        modules.append(act)

        modules.append(nn.Conv2d(
            nBTFeat, nBTFeat, kernel_size=3, dilation=dilation, padding=padding))
        if bn:
            modules.append(nn.BatchNorm2d(nFeat))
        modules.append(act)

        modules.append(nn.Conv2d(
            nBTFeat, nFeat, kernel_size=3, dilation=dilation, padding=padding))
        if bn:
            modules.append(nn.BatchNorm2d(nFeat))
        self.body = nn.Sequential(*modules)

    def forward(self, x):
        res = self.body(x)
        res *= 0.1
        res += x

        return res

class ResBlock(nn.Module):
    def __init__(self, nFeat, kernel_size=3, bn=False, act=nn.ReLU(True)):
        super(ResBlock, self).__init__()

        modules = []
        modules.append(nn.Conv2d(
            nFeat, nFeat, kernel_size=kernel_size, padding=kernel_size // 2))
        if bn:
            modules.append(nn.BatchNorm2d(nFeat))
        modules.append(act)

        modules.append(nn.Conv2d(
            nFeat, nFeat, kernel_size=kernel_size, padding=kernel_size // 2))
        if bn:
            modules.append(nn.BatchNorm2d(nFeat))
        self.body = nn.Sequential(*modules)

    def forward(self, x):
        res = self.body(x)
        res += x

        return res

class ResBlock_scale(ResBlock):
    def __init__(
        self, nFeat, kernel_size=3, bn=False, act=nn.ReLU(True), scale=1):
        super(ResBlock_scale, self).__init__(nFeat, kernel_size, bn, act)
        self.scale = scale

    def forward(self, x):
        res = self.body(x)
        res *= 0.1
        res += x

        return res

class Upsampler(nn.Module):
    def __init__(self, scale, nFeat, act=False):
        super(Upsampler, self).__init__()

        modules = []
        self.body = nn.Sequential()
        if scale == 2 or scale == 4 or scale == 8:
            for _ in range(int(math.log(scale, 2))):
                modules.append(conv3x3(nFeat, 4 * nFeat))
                modules.append(nn.PixelShuffle(2))
                if act:
                    modules.append(act())
        elif scale == 3:
            modules.append(conv3x3(nFeat, 9 * nFeat))
            modules.append(nn.PixelShuffle(3))
            if act:
                modules.append(act())

        self.body = nn.Sequential(*modules)

    def forward(self, x):
        x = self.body(x)

        return x

class vggNormalizer(nn.Module):
    def __init__(self, args):
        super(vggNormalizer, self).__init__()
        self.mean = torch.Tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
        self.std = torch.Tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
        self.mean.mul_(args.rgbRange)
        self.std.mul_(args.rgbRange)
        if args.cuda:
            self.mean = self.mean.cuda()
            self.std = self.std.cuda()
        self.mean = Variable(self.mean)
        self.std = Variable(self.std)

    def forward(self, x):
        normalized = (x - self.mean.expand_as(x)) / self.std.expand_as(x)

        return normalized
