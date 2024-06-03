python main_pretrain.py \
    --data_path /home/gzg2104/uncertainty_mae/dataset_generation/columbia_emoji/train \
    --dataset_name emoji \
    --batch_size 256 \
    --blr 1e-3 \
    --accum_iter 1 \
    --output_dir /local/zemel/gzg2104/_emoji_models/06_03_24_full_vae_beta_5 \
    --log_dir /local/zemel/gzg2104/_emoji_models/06_03_24_full_vae_beta_5 \
    --model mae_vit_base_patch16 \
    --warmup_epochs 40 \
    --epochs 4000 \
    --log_freq 200 \
    --vae \
    --kld_beta 5 \
    --mask_ratio 1 \
    --partial_vae \
    --dropout_ratio 0 \
    --eps 1e-4 \
    --weight_decay 0.05 \
    --mixed_precision