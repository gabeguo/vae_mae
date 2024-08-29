python main_finetune.py \
    --model vit_base_patch16 \
    --finetune /local/zemel/gzg2104/_imagenet_models/08_02_24/revertSmallBatch/checkpoint-160.pth \
    --dataset_name imagenet \
    --data_path /local/zemel/gzg2104/datasets/imagenet \
    --nb_classes 1000 \
    --output_dir /local/zemel/gzg2104/_imagenet_models/08_02_24/revertSmallBatch/finetune_compareToNorm/160 \
    --batch_size 256 \
    --accum_iter 2 \
    --blr 5e-4 \
    --layer_decay 0.65 \
    --drop_path 0.1 \
    --log_dir /local/zemel/gzg2104/logs \
    --wandb_project linprobe_imagenet \
    --device cuda \
    --num_workers 8 \
    --master_port 12356 \
    --log_freq 5