import torch
from uncertainty_vit import MultiHeadViT, TeacherViT
from util.pos_embed import interpolate_pos_embed
import torchvision.datasets as datasets
import util.misc as misc
import numpy as np
import torch.backends.cudnn as cudnn
import torchvision.transforms as transforms
import os
import wandb
from torch.utils.tensorboard import SummaryWriter
import argparse
from pathlib import Path
from tqdm import tqdm

# Verified in Colab
def quantile_loss(z_pred, z_gt, q):
    unreduced_loss = torch.maximum(z_gt - z_pred, torch.zeros_like(z_gt)) * q + \
        torch.maximum(z_pred - z_gt, torch.zeros_like(z_gt)) * (1 - q)
    reduced_loss = torch.mean(unreduced_loss)
    return reduced_loss

"""
Strats:
(1) Train quantile regressors from scratch
(2) Initialize quantile regressors to point estimator weights
(3) Re-train point estimator + quantile regressors with shared layers except for last few, 
    with original point estimator as teacher
"""

def train_latent_uncertainty(args, dataloader, pretrained_mae_weights):
    """
    (1) Use frozen MAE pretrained weights as teacher_encoder.
    (2) Uncertainty-aware backbone is initialized from teacher_encoder.
    (3) Use three different heads that share common uncertainty-aware backbone. 
        Backprop with quantile regression with teacher's latent code (cls token) as target, jointly
        through all three heads + backbone.
    (4) Return the backbone, plus the three heads. Prob use median head's cls token as representation,
        but can experiment with other two.
    """
    assert args.lower <= args.upper
    assert 0 <= args.lower <= 1 and 0 <= args.upper <= 1

    student = MultiHeadViT(backbone_path=pretrained_mae_weights, num_unshared_layers=args.num_unshared_layers,
                           freeze_backbone=args.freeze_backbone, return_all_tokens=args.return_all_tokens).cuda()

    # ready to train
    student.train()
    learnable_student_params = {x[0] for x in student.named_parameters() if x[1].requires_grad}
    all_student_params = {x[0] for x in student.named_parameters()}
    print(f"{len(learnable_student_params)} out of {len(all_student_params)} learnable")

    # frozen teacher encoder
    teacher = TeacherViT(backbone_path=pretrained_mae_weights, return_all_tokens=args.return_all_tokens).cuda()
    teacher.eval()

    wandb.watch(student, log_freq=args.log_interval)

    # make optimizer
    opt = torch.optim.AdamW(student.parameters(), lr=args.lr, betas=(0.9, 0.95), weight_decay=args.weight_decay)
    print(opt)

    for epoch in range(args.epochs):
        print(f'epoch {epoch} out of {args.epochs}')
        pbar = tqdm(total=len(dataloader))
        for idx, (img, label) in enumerate(dataloader):
            img = img.cuda()
            with torch.no_grad():
                z_gt = teacher(img)
                z_gt = z_gt.detach()
            low_z, mid_z, high_z = student(img)
            # get losses
            low_loss = quantile_loss(z_pred=low_z, z_gt=z_gt, q=args.lower)
            high_loss = quantile_loss(z_pred=high_z, z_gt=z_gt, q=args.upper)
            mid_loss = quantile_loss(z_pred=mid_z, z_gt=z_gt, q=0.5)
            # backprop
            total_loss = (low_loss + high_loss + mid_loss) / args.accum_iter
            total_loss.backward()
            if (idx + 1) % args.accum_iter == 0:
                # optimizer step
                opt.step()
                # clear grad
                opt.zero_grad()
            if idx % args.log_interval == 0:
                wandb.log({'total loss':total_loss, 
                           'low loss': low_loss, 'high loss': high_loss, 'mid loss': mid_loss},
                           step=idx+epoch*len(dataloader))

            pbar.set_postfix(loss=total_loss.item(), refresh=False)
            pbar.update(1)
    
    return student
    
def get_args_parser():
    parser = argparse.ArgumentParser('MAE confidence intervals', add_help=False)

    # Fine-tuning parameters
    parser.add_argument('--pretrained_weights', default='/home/gabeguo/vae_mae/cifar100_train/checkpoint-399.pth',
                        type=str, help='The MAE pretrained weights')
    parser.add_argument('--num_unshared_layers', default=1, type=int, help='Number of transformer blocks that we can finetune for each head')
    parser.add_argument('--freeze_backbone', action='store_true', help='Whether to freeze the backbone weights of the multi-head ViT')
    parser.add_argument('--return_all_tokens', action='store_true', help='Whether to return all the tokens, or just the cls token when training encoders')

    # Quantile regression parameters
    parser.add_argument('--lower', default=0.05, type=float, help='the lower quantile')
    parser.add_argument('--upper', default=0.95, type=float, help='the upper quantile')

    # General data parameters
    parser.add_argument('--data_path', default='../', type=str,
                        help='dataset path')
    parser.add_argument('--batch_size', default=64, type=int,
                        help='Batch size per GPU (effective batch size is batch_size * accum_iter * # gpus')
    parser.add_argument('--epochs', default=200, type=int)
    parser.add_argument('--accum_iter', default=1, type=int,
                        help='Accumulate gradient iterations (for increasing the effective batch size under memory constraints)')
    parser.add_argument('--input_size', default=224, type=int,
                        help='images input size')

    # Model parameters
    # parser.add_argument('--model', default='mae_vit_large_patch16', type=str, metavar='MODEL',
    #                     help='Name of model to train')

    # parser.add_argument('--input_size', default=224, type=int,
    #                     help='images input size')

    # parser.add_argument('--mask_ratio', default=0.75, type=float,
    #                     help='Masking ratio (percentage of removed patches).')

    # Optimizer parameters
    parser.add_argument('--weight_decay', type=float, default=0.05,
                        help='weight decay (default: 0.05)')
    parser.add_argument('--lr', type=float, default=None, metavar='LR',
                        help='learning rate (absolute lr)')
    parser.add_argument('--blr', type=float, default=1e-3, metavar='LR',
                        help='base learning rate: absolute_lr = base_lr * total_batch_size / 256')
    parser.add_argument('--min_lr', type=float, default=0., metavar='LR',
                        help='lower lr bound for cyclic schedulers that hit 0')
    # parser.add_argument('--warmup_epochs', type=int, default=40, metavar='N',
    #                     help='epochs to warmup LR')

    # Log parameters
    parser.add_argument('--output_dir', default='./cifar100_quantile',
                        help='path where to save, empty for no saving')
    parser.add_argument('--log_dir', default='./cifar100_quantile',
                        help='path where to tensorboard log')
    parser.add_argument('--device', default='cuda',
                        help='device to use for training / testing')
    parser.add_argument('--seed', default=0, type=int)
    parser.add_argument('--resume', default='',
                        help='resume from checkpoint')
    parser.add_argument('--log_interval', default=20, type=int, help='how many steps between log to wandb')

    # Miscellaneous parameters
    parser.add_argument('--start_epoch', default=0, type=int, metavar='N',
                        help='start epoch')
    parser.add_argument('--num_workers', default=10, type=int)
    parser.add_argument('--pin_mem', action='store_true',
                        help='Pin CPU memory in DataLoader for more efficient (sometimes) transfer to GPU.')
    parser.add_argument('--no_pin_mem', action='store_false', dest='pin_mem')
    parser.set_defaults(pin_mem=True)

    # distributed training parameters
    parser.add_argument('--world_size', default=1, type=int,
                        help='number of distributed processes')
    parser.add_argument('--local_rank', default=-1, type=int)
    parser.add_argument('--dist_on_itp', action='store_true')
    parser.add_argument('--dist_url', default='env://',
                        help='url used to set up distributed training')

    return parser

def main(args):

    # misc.init_distributed_mode(args)

    print('job dir: {}'.format(os.path.dirname(os.path.realpath(__file__))))
    print("{}".format(args).replace(', ', ',\n'))

    # fix the seed for reproducibility
    seed = args.seed + misc.get_rank()
    torch.manual_seed(seed)
    np.random.seed(seed)

    cudnn.benchmark = True

    # simple augmentation
    transform_train = transforms.Compose([
            transforms.RandomResizedCrop(args.input_size, scale=(0.2, 1.0), interpolation=3),  # 3 is bicubic
            transforms.RandomHorizontalFlip(),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])])
    dataset_train = datasets.CIFAR100(args.data_path, train=True, download=True, transform=transform_train)
    print(dataset_train[0][0].shape)

    # if True:  # args.distributed:
    #     num_tasks = misc.get_world_size()
    #     global_rank = misc.get_rank()
    #     sampler_train = torch.utils.data.DistributedSampler(
    #         dataset_train, num_replicas=num_tasks, rank=global_rank, shuffle=True
    #     )
    #     print("Sampler_train = %s" % str(sampler_train))
    # else:
    sampler_train = torch.utils.data.RandomSampler(dataset_train)

    # if global_rank == 0 and args.log_dir is not None:
    os.makedirs(args.log_dir, exist_ok=True)
    #     log_writer = SummaryWriter(log_dir=args.log_dir)
    # else:
    #     log_writer = None

    data_loader_train = torch.utils.data.DataLoader(
        dataset_train, sampler=sampler_train,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        pin_memory=args.pin_mem,
        drop_last=True,
    )

    eff_batch_size = args.batch_size * args.accum_iter * misc.get_world_size()
    
    if args.lr is None:  # only base_lr is specified
        args.lr = args.blr * eff_batch_size / 256

    print("base lr: %.2e" % (args.lr * 256 / eff_batch_size))
    print("actual lr: %.2e" % args.lr)

    print("accumulate grad iterations: %d" % args.accum_iter)
    print("effective batch size: %d" % eff_batch_size)

    wandb.init(config=args)

    student = train_latent_uncertainty(args, dataloader=data_loader_train, 
                             pretrained_mae_weights=args.pretrained_weights) 
    torch.save(student.state_dict(), os.path.join(args.output_dir, 'multihead_vit.pt'))

    
    return

if __name__ == "__main__":
    args = get_args_parser()
    args = args.parse_args()
    if args.output_dir:
        Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    main(args)

        


"""
Alt ideas: 
Latent:
(1) Post-hoc: Train three different regressors:
    disadvantage is that it's not clear which one to use for representation, and this may take too much compute.

Real space:
(1) Pixel uncertainty with three different decoders:
    advantage is that all knowledge goes into encoder, but pixel space is not semantically meaningful
"""