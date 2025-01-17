# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.

# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.
# --------------------------------------------------------
# References:
# DeiT: https://github.com/facebookresearch/deit
# BEiT: https://github.com/microsoft/unilm/tree/master/beit
# --------------------------------------------------------
import math
import sys
from typing import Iterable
import wandb
import random

import torch

import util.misc as misc
import util.lr_sched as lr_sched
from util.pos_embed import interpolate_pos_embed
from uncertainty_mae import UncertaintyMAE

from main_linprobe import set_head

import models_vit

REAL_LABEL = 1.
FAKE_LABEL = 0.

def train_one_epoch(model: torch.nn.Module,
                    data_loader: Iterable, optimizer: torch.optim.Optimizer,
                    device: torch.device, epoch: int, loss_scaler, max_norm: float = 0,
                    log_writer=None, args=None,
                    netD=None, optimizerD=None, optimizerG=None):
    model.train(True)
    metric_logger = misc.MetricLogger(delimiter="  ")
    metric_logger.add_meter('lr', misc.SmoothedValue(window_size=1, fmt='{value:.6f}'))
    header = 'Epoch: [{}]'.format(epoch)
    print_freq = 20 if device == 0 else len(data_loader)

    accum_iter = args.accum_iter

    optimizer.zero_grad()

    if log_writer is not None:
        print('log_dir: {}'.format(log_writer.log_dir))

    errG = 0
    for data_iter_step, the_data in enumerate(metric_logger.log_every(data_loader, print_freq, header)):
        do_gan = args.gan and random.random() < args.dropout_ratio # if gan, randomly dropout
        if do_gan:
            model.module.dropout_ratio = 1 # use noise
        else:
            model.module.dropout_ratio = 0 # use invisible encoder
        # if data_iter_step > 300:
        #     break
        if args.dataset_name in ['imagenet_sketch', 'coco']:
            samples = the_data['image']
        else:
            (samples, _) = the_data
        # we use a per iteration (instead of per epoch) lr scheduler
        if data_iter_step % accum_iter == 0:
            lr_sched.adjust_learning_rate(optimizer, data_iter_step / len(data_loader) + epoch, args)
            if args.gan:
                for the_opt in [optimizerD, optimizerG]:
                    lr_sched.adjust_learning_rate(the_opt, data_iter_step / len(data_loader) + epoch, args)

        samples = samples.to(device, non_blocking=True)

        with torch.cuda.amp.autocast(enabled=args.mixed_precision):
            if isinstance(model.module, UncertaintyMAE):
                if args.dataset_name == 'coco' and args.object_mask:
                    mask_layout = the_data['token_mask'].to(device=samples.device)
                    B = mask_layout.shape[0]
                    assert mask_layout.shape == (B, 14, 14), f"{mask_layout.shape}"
                    mask_layout = mask_layout.reshape(B, -1)
                    keep_indices = torch.where(mask_layout == 1)
                    mask_indices = torch.where(mask_layout == 0)
                    assert keep_indices[0][0] == keep_indices[0][1] # assert that it's blocked by batch
                    assert mask_indices[0][-1] == mask_indices[0][-2]
                    keep_indices = keep_indices[1].reshape(B, -1) # patches to keep by image
                    mask_indices = mask_indices[1].reshape(B, -1)
                    assert keep_indices.shape[0] == mask_indices.shape[0] == B
                    assert keep_indices.shape[1] + mask_indices.shape[1] == 14 * 14
                    assert len(keep_indices.shape) == 2 and len(mask_indices.shape) == 2
                    ids_shuffle = torch.cat((keep_indices, mask_indices), dim=1)
                    assert ids_shuffle.shape == (B, 14 * 14)
                    # keep_indices should be B * L
                    mask_ratio = 1 - keep_indices.shape[1] / ids_shuffle.shape[1]
                    force_mask = (keep_indices, mask_indices)
                else:
                    mask_ratio = args.mask_ratio
                    force_mask = None

                loss, pred, mask, reconstruction_loss, kld_loss = \
                    model(samples, mask_ratio=mask_ratio, return_component_losses=True, 
                          force_mask=force_mask, add_default_mask=args.add_default_mask)
            else:
                loss, _, _ = model(samples, mask_ratio=args.mask_ratio)
                assert not args.gan

        loss_value = loss.item()

        if not math.isfinite(loss_value):
            print("Loss is {}, stopping training".format(loss_value))
            # for name, param in model.named_parameters():
            #     if param.requires_grad:
            #         print(name, param.grad)
            #         print('has nan grad', any(torch.isnan(param.grad).flatten().tolist()))
            raise ValueError("Loss is {}, stopping training".format(loss_value))
        # else:
        #     print("Loss is {}, continue training".format(loss_value))

        if args.gan and do_gan:
            errD_real, errD_fake, errG, recon_loss_visible = calc_gan_loss(args, gt=samples, fake=pred, netG=model, netD=netD, optimizerG=optimizerG, optimizerD=optimizerD, device=device, accum_iter=accum_iter, data_iter_step=data_iter_step, max_norm=max_norm, loss_scaler=loss_scaler, mask=mask, last_errG=errG)
        else:
            loss /= accum_iter
            if args.mixed_precision:
                loss_scaler(loss, optimizer, clip_grad=max_norm,
                            parameters=model.parameters(),
                            update_grad=(data_iter_step + 1) % accum_iter == 0)
            else:
                loss.backward()
            if (data_iter_step + 1) % accum_iter == 0:
                if (not args.mixed_precision): # loss scaler didn't weight update in full precision
                    optimizer.step()
                optimizer.zero_grad()

        torch.cuda.synchronize()

        metric_logger.update(loss=loss_value)
        if isinstance(model, UncertaintyMAE) or isinstance(model.module, UncertaintyMAE):
            if args.gan and do_gan:
                if errD_real is not None and errD_fake is not None:
                    metric_logger.update(errD_real=errD_real)
                    metric_logger.update(errD_fake=errD_fake)
                metric_logger.update(errG=errG)
                metric_logger.update(recon_loss_visible=recon_loss_visible)
                metric_logger.update(lr_G=optimizerG.param_groups[0]["lr"])
                metric_logger.update(lr_D=optimizerD.param_groups[0]["lr"])
            else:
                metric_logger.update(reconstruction_loss=reconstruction_loss)
                metric_logger.update(kld_loss=kld_loss)

        lr = optimizer.param_groups[0]["lr"]
        metric_logger.update(lr=lr)
        if (args.invisible_lr_scale is not None) and (args.invisible_lr_scale > 0) and \
                (not args.same_encoder):
            metric_logger.update(invisible_lr=optimizer.param_groups[2]["lr"])
            assert len(optimizer.param_groups) == 4
            assert optimizer.param_groups[0]["lr"] == optimizer.param_groups[1]["lr"]
            assert optimizer.param_groups[2]["lr"] == optimizer.param_groups[3]["lr"]

        loss_value_reduce = misc.all_reduce_mean(loss_value)
        if log_writer is not None and (data_iter_step + 1) % accum_iter == 0:
            """ We use epoch_1000x as the x-axis in tensorboard.
            This calibrates different curves when batch size changes.
            """
            epoch_1000x = int((data_iter_step / len(data_loader) + epoch) * 1000)
            if args.gan and do_gan:
                if errD_real is not None and errD_fake is not None:
                    log_writer.add_scalar('errD_fake', errD_fake, epoch_1000x)
                    log_writer.add_scalar('errD_real', errD_real, epoch_1000x)
                log_writer.add_scalar('errG', errG, epoch_1000x)
                log_writer.add_scalar('recon_loss_visible', recon_loss_visible, epoch_1000x)
            else:
                log_writer.add_scalar('train_loss', loss_value_reduce, epoch_1000x)
                log_writer.add_scalar('lr', lr, epoch_1000x)
        # print intermediate results, because GANs train slower (only on main device!)
        if device == 0 and data_iter_step % print_freq == 0 and args.gan:
            train_stats = {k: meter.global_avg for k, meter in metric_logger.meters.items()}
            partial_epoch = epoch + data_iter_step / len(data_loader)
            the_log_step = epoch * len(data_loader) + data_iter_step
            log_stats = {**{f'train_{k}': v for k, v in train_stats.items()},
                            'epoch': partial_epoch, 'step': the_log_step}
            wandb.log(log_stats, step=the_log_step)


    # gather the stats from all processes
    metric_logger.synchronize_between_processes()
    print("Averaged stats:", metric_logger)
    return {k: meter.global_avg for k, meter in metric_logger.meters.items()}


def calc_gan_loss(args, gt, fake, netG, netD, optimizerG, optimizerD, device,
    accum_iter, data_iter_step, max_norm, loss_scaler, mask, last_errG):
    patched_fake = fake
    assert mask.shape == patched_fake.shape[:2]
    assert len(patched_fake.shape) == 3
    fake = netG.module.visible_mae.unpatchify(fake).to(dtype=gt.dtype)
    assert len(fake.shape) == 4

    assert args.gan

    # Thanks https://pytorch.org/tutorials/beginner/dcgan_faces_tutorial.html

    if last_errG < args.errG_threshold:
        ############################
        # (1) Update D network: maximize log(D(x)) + log(1 - D(G(z)))
        ###########################
        ## Train with all-real batch
        netD.zero_grad()
        # Format batch
        real_cpu = gt.to(device)
        b_size = real_cpu.size(0)
        label = torch.full((b_size,), REAL_LABEL, dtype=torch.float, device=device)
        # Forward pass real batch through D
        output = netD(real_cpu).view(-1)
        # Calculate loss on all-real batch
        errD_real = torch.nn.functional.binary_cross_entropy_with_logits(input=output, target=label)
        # Calculate gradients for D in backward pass
        # errD_real.backward()
        backprop_loss(args, loss=args.discriminator_lr_scale * errD_real, accum_iter=accum_iter, data_iter_step=data_iter_step, model=netD, optimizer=optimizerD, max_norm=max_norm, loss_scaler=loss_scaler)
        D_x = output.mean().item()

        label.fill_(FAKE_LABEL)
        # Classify all fake batch with D
        output = netD(fake.detach()).view(-1)
        # Calculate D's loss on the all-fake batch
        errD_fake = torch.nn.functional.binary_cross_entropy_with_logits(input=output, target=label)
        # Calculate the gradients for this batch, accumulated (summed) with previous gradients
        # errD_fake.backward()
        backprop_loss(args, loss=args.discriminator_lr_scale * errD_fake, accum_iter=accum_iter, data_iter_step=data_iter_step, model=netD, optimizer=optimizerD, max_norm=max_norm, loss_scaler=loss_scaler)
        D_G_z1 = output.mean().item()

        # Compute error of D as sum over the fake and the real batches
        errD = errD_real + errD_fake
        # Update D
        # optimizerD.step()
        step_optimizer(args=args, optimizer=optimizerD, accum_iter=accum_iter, data_iter_step=data_iter_step)
    else:
        label = torch.full((fake.shape[0],), REAL_LABEL, dtype=torch.float, device=device)
        errD_real = None
        errD_fake = None

    ############################
    # (2) Update G network: maximize log(D(G(z)))
    ###########################
    netG.zero_grad()
    label.fill_(REAL_LABEL)  # fake labels are real for generator cost
    # Since we just updated D, perform another forward pass of all-fake batch through D
    output = netD(fake).view(-1)
    # Calculate G's loss based on this output
    errG = torch.nn.functional.binary_cross_entropy_with_logits(input=output, target=label)
    # Also get reconstruction loss on observed space
    inverted_mask = torch.ones_like(mask) - mask
    assert torch.sum(inverted_mask) < torch.sum(mask) # less visible than invisible patches
    recon_loss = netG.module.visible_mae.forward_loss(imgs=gt, pred=patched_fake, mask=inverted_mask)
    total_loss_G = args.gan_lambda * errG + recon_loss # weight, following https://openaccess.thecvf.com/content_cvpr_2016/papers/Pathak_Context_Encoders_Feature_CVPR_2016_paper.pdf
    # Calculate gradients for G
    # errG.backward()
    backprop_loss(args, loss=total_loss_G, accum_iter=accum_iter, data_iter_step=data_iter_step, model=netG, optimizer=optimizerG, max_norm=max_norm, loss_scaler=loss_scaler)
    D_G_z2 = output.mean().item()
    # Update G
    # optimizerG.step()
    step_optimizer(args=args, optimizer=optimizerG, accum_iter=accum_iter, data_iter_step=data_iter_step)

    return errD_real, errD_fake, errG, recon_loss

def backprop_loss(args, loss, accum_iter, data_iter_step, model, optimizer, max_norm, loss_scaler):
    loss /= accum_iter
    if args.mixed_precision:
        loss_scaler(loss, optimizer, clip_grad=max_norm,
                    parameters=model.parameters(),
                    update_grad=(data_iter_step + 1) % accum_iter == 0)
    else:
        loss.backward()
    return

def step_optimizer(args, optimizer, accum_iter, data_iter_step):
    if (data_iter_step + 1) % accum_iter == 0:
        if (not args.mixed_precision): # loss scaler didn't weight update in full precision
            optimizer.step()
        optimizer.zero_grad()
    return

def create_discriminator(args, mae):
    # since we only test base
    discriminator = models_vit.__dict__['vit_base_patch16'](
        num_classes=1,
        drop_path_rate=args.discriminator_drop_path,
        global_pool=args.discriminator_global_pool,
    )

    checkpoint_model = mae.module.visible_mae.state_dict()

    # interpolate position embedding (as in main_finetune.py)
    interpolate_pos_embed(discriminator, checkpoint_model)

    # load pre-trained model
    msg = discriminator.load_state_dict(checkpoint_model, strict=False)
    print("Discriminator:", msg)

    return discriminator