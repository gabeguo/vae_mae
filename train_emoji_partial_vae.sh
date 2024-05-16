python main_pretrain.py \
    --data_path /home/gzg2104/uncertainty_mae/dataset_generation/columbia_emoji/train \
    --dataset_name emoji \
    --batch_size 128 \
    --blr 1e-3 \
    --accum_iter 1 \
    --output_dir /local/zemel/gzg2104/emoji_train_partial_vae_separate_mean_var \
    --log_dir /local/zemel/gzg2104/emoji_train_partial_vae_separate_mean_var \
    --model mae_vit_base_patch16 \
    --epochs 4000 \
    --log_freq 200 \
    --vae \
    --kld_beta 20 \
    --mask_ratio 0.75 \
    --partial_vae