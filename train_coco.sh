output_path=/local/zemel/gzg2104/_coco_models/07_03_24/beta15_blr1e-3
python main_pretrain.py \
    --dataset_name coco \
    --batch_size 384 \
    --blr 1e-3 \
    --accum_iter 1 \
    --output_dir $output_path \
    --log_dir $output_path \
    --model mae_vit_base_patch16 \
    --warmup_epochs 40 \
    --epochs 800 \
    --log_freq 40 \
    --vae \
    --kld_beta 15 \
    --invisible_lr_scale 0.1 \
    --mask_ratio 0.75 \
    --partial_vae \
    --dropout_ratio 0 \
    --eps 1e-6 \
    --weight_decay 0.025 \
    --mixed_precision \
    --wandb_project coco_pretrain \
    --disable_zero_conv