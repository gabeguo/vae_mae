python main_pretrain.py \
    --data_path /home/gabe/uncertainty_mae/dataset_generation/columbia_emoji \
    --dataset_name emoji \
    --batch_size 64 \
    --accum_iter 1 \
    --output_dir emoji_train_couple \
    --log_dir emoji_train_couple \
    --model mae_vit_base_patch16 \
    --epochs 20000 \
    --log_freq 2000 \
    --image_keywords couple