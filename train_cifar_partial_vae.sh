python main_pretrain.py \
    --dataset_name cifar \
    --batch_size 256 \
    --blr 1e-3 \
    --accum_iter 1 \
    --output_dir /local/zemel/gzg2104/cifar_train_partial_vae_base_vit_batch_256_beta_5_epochs_800 \
    --log_dir /local/zemel/gzg2104/cifar_train_partial_vae_base_vit_batch_256_beta_5_epochs_800 \
    --model mae_vit_base_patch16 \
    --warmup_epochs 40 \
    --epochs 800 \
    --log_freq 40 \
    --vae \
    --kld_beta 5 \
    --mask_ratio 0.75 \
    --partial_vae \
    --dropout_ratio 0 \
    --eps 1e-4 \
    --weight_decay 0.05 \
    --mixed_precision