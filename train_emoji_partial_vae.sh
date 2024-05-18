python main_pretrain.py \
    --data_path /home/gzg2104/uncertainty_mae/dataset_generation/columbia_emoji/train \
    --dataset_name emoji \
    --batch_size 256 \
    --blr 1e-3 \
    --accum_iter 1 \
    --output_dir /local/zemel/gzg2104/emoji_train_partial_vae_mixed_precision_base_vit_batch_size_256 \
    --log_dir /local/zemel/gzg2104/emoji_train_partial_vae_mixed_precision_base_vit_batch_size_256 \
    --model mae_vit_base_patch16 \
    --warmup_epochs 40 \
    --epochs 4000 \
    --log_freq 200 \
    --vae \
    --kld_beta 20 \
    --mask_ratio 0.75 \
    --partial_vae \
    --dropout_ratio 0 \
    --eps 1e-4 \
    --weight_decay 0.1 \
    --mixed_precision