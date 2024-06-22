output_path=/local/zemel/gzg2104/_emnist_models/06_22_24/common_encoder/disableZeroConv
python main_pretrain.py \
    --dataset_name emnist \
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
    --kld_beta 25 \
    --invisible_lr_scale 0.1 \
    --mask_ratio 0.75 \
    --partial_vae \
    --dropout_ratio 0 \
    --eps 1e-8 \
    --weight_decay 0.05 \
    --mixed_precision \
    --same_encoder \
    --disable_zero_conv \
    --wandb_project emnist_pretrain