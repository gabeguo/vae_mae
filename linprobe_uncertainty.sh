python main_linprobe.py \
    --model vit_base_patch16 \
    --finetune /local/zemel/gzg2104/_coco_models/07_24_24/beta30_addDefault_eps1e-8_scale0_025/checkpoint-350.pth \
    --dataset_name cifar \
    --data_path /local/zemel/gzg2104/datasets/imagenet \
    --nb_classes 100 \
    --output_dir /local/zemel/gzg2104/_coco_models/07_24_24/beta30_addDefault_eps1e-8_scale0_025/linprobe \
    --batch_size 1024 \
    --log_dir /local/zemel/gzg2104/logs \
    --wandb_project linprobe_cifar \
    --device cuda \
    --master_port 12357

