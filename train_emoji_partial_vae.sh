output_path=/local/zemel/gzg2104/_emoji_models/06_12_24_batchSize_384_epochs_3000
python main_pretrain.py \
    --data_path /home/gzg2104/uncertainty_mae/dataset_generation/columbia_emoji/train \
    --dataset_name emoji \
    --batch_size 384 \
    --blr 1e-3 \
    --accum_iter 1 \
    --output_dir $output_path \
    --log_dir $output_path \
    --model mae_vit_base_patch16 \
    --warmup_epochs 100 \
    --epochs 3000 \
    --log_freq 200 \
    --vae \
    --kld_beta 20 \
    --invisible_lr_scale 0.1 \
    --mask_ratio 0.75 \
    --partial_vae \
    --dropout_ratio 0 \
    --eps 1e-6 \
    --weight_decay 0.025 \
    --mixed_precision