output_path=/local/zemel/gzg2104/_imagenet_models/08_16_24/batch1024_beta25
python main_pretrain.py \
    --dataset_name imagenet \
    --data_path /local/zemel/gzg2104/datasets/imagenet \
    --batch_size 256 \
    --blr 1.5e-4 \
    --accum_iter 2 \
    --output_dir $output_path \
    --log_dir $output_path \
    --model mae_vit_base_patch16 \
    --warmup_epochs 40 \
    --epochs 800 \
    --log_freq 20 \
    --num_workers 16 \
    --vae \
    --kld_beta 25 \
    --invisible_lr_scale 1e-2 \
    --mask_ratio 0.75 \
    --partial_vae \
    --dropout_ratio 0 \
    --eps 1e-8 \
    --weight_decay 0.05 \
    --mixed_precision \
    --wandb_project imagenet_hippo \
    --disable_zero_conv \
    --master_port 12356 \
    --resume /local/zemel/gzg2104/_imagenet_models/08_16_24/batch1024_beta25/checkpoint-120.pth \
    --object_mask \
    --add_default_mask \
    --var 1