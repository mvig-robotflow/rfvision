dataset_type = 'ABCTouchDataset'
data_root = '/hdd0/data/abc/'
anno_root = '/home/hanyang/rfvision/rfvision/models/detectors3d/touch_and_vision/data'
num_samples = 4000

model = dict(type='TouchEncoder',
             num_samples=num_samples,
             dim=100)

train_pipeline = [dict(type='Collect',
                       keys=['gt_points', 'sim_touch', 'empty',
                             'rot', 'rot_M', 'pos' # ref_frame
                             ],
                       meta_keys=['class', 'names'])]
data = dict(
    # batch_size: 128
    # random seed: 0
    samples_per_gpu=2,
    workers_per_gpu=0,
    train=dict(
        type=dataset_type,
        data_root=data_root,
        anno_root=anno_root,
        pipeline=train_pipeline,
        classes=['0001', '0002'],
        num_samples=num_samples,
        set_type='train',
        produce_sheets=False,
        test_mode=False),
    test=dict(
        type=dataset_type,
        data_root=data_root,
        anno_root=anno_root,
        pipeline=train_pipeline,
        classes=['0001', '0002'],
        num_samples=num_samples,
        set_type='test',
        produce_sheets=False,
        test_mode=True),
    val=dict(
        type=dataset_type,
        data_root=data_root,
        anno_root=anno_root,
        pipeline=train_pipeline,
        classes=['0001', '0002'],
        num_samples=num_samples,
        set_type='valid',
        produce_sheets=True,
        test_mode=False))

evaluation = dict(save_best='loss',
                  rule='less',
                  interval=1,
                  metric='loss')

optimizer = dict(type='Adam', lr=0.001, weight_decay=0)
optimizer_config = dict(grad_clip=None)
# learning policy
lr_config = dict(
    policy='fixed',
    warmup=None)
# lr_config = dict(
#     policy='step',
#     warmup=None,
#     step=[250, 275])
runner = dict(type='EpochBasedRunner', max_epochs=300)

checkpoint_config = dict(interval=30)
log_config = dict(
    interval=50,
    hooks=[
        dict(type='TextLoggerHook'),
        dict(type='TensorboardLoggerHook')
    ])
# yapf:enable
dist_params = dict(backend='nccl')
log_level = 'INFO'
work_dir = None
load_from = None
resume_from = None
workflow = [('train', 1)]