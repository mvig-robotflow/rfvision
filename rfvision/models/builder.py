import warnings

from rflib.cnn import MODELS as RFLIB_MODELS
from rflib.utils import Registry

MODELS = Registry('models', parent=RFLIB_MODELS)

BACKBONES = MODELS
NECKS = MODELS
ROI_EXTRACTORS = MODELS
SHARED_HEADS = MODELS
HEADS = MODELS
LOSSES = MODELS
DETECTORS = MODELS
FUSION_LAYERS = MODELS
POSE_ESTIMATORS = MODELS
HUMAN_ANALYZERS = MODELS


def build_backbone(cfg):
    """Build backbone."""
    return BACKBONES.build(cfg)


def build_neck(cfg):
    """Build neck."""
    return NECKS.build(cfg)


def build_roi_extractor(cfg):
    """Build roi extractor."""
    return ROI_EXTRACTORS.build(cfg)


def build_shared_head(cfg):
    """Build shared head."""
    return SHARED_HEADS.build(cfg)


def build_head(cfg):
    """Build head."""
    return HEADS.build(cfg)


def build_loss(cfg):
    """Build loss."""
    return LOSSES.build(cfg)

def build_fusion_layer(cfg):
    """Build fusion layer."""
    return FUSION_LAYERS.build(cfg)

def build_detector(cfg, train_cfg=None, test_cfg=None):
    """Build detector."""
    if train_cfg is not None or test_cfg is not None:
        warnings.warn(
            'train_cfg and test_cfg is deprecated, '
            'please specify them in model', UserWarning)
    assert cfg.get('train_cfg') is None or train_cfg is None, \
        'train_cfg specified in both outer field and model field '
    assert cfg.get('test_cfg') is None or test_cfg is None, \
        'test_cfg specified in both outer field and model field '
    return DETECTORS.build(
        cfg, default_args=dict(train_cfg=train_cfg, test_cfg=test_cfg))


def build_human_analyzer(cfg, train_cfg=None, test_cfg=None):
    """Build human_analyzer."""
    if train_cfg is not None or test_cfg is not None:
        warnings.warn(
            'train_cfg and test_cfg is deprecated, '
            'please specify them in model', UserWarning)
    assert cfg.get('train_cfg') is None or train_cfg is None, \
        'train_cfg specified in both outer field and model field '
    assert cfg.get('test_cfg') is None or test_cfg is None, \
        'test_cfg specified in both outer field and model field '
    return HUMAN_ANALYZERS.build(
        cfg, default_args=dict(train_cfg=train_cfg, test_cfg=test_cfg))


def build_pose_estimator(cfg, train_cfg=None, test_cfg=None):
    """Build pose_estimator."""
    if train_cfg is not None or test_cfg is not None:
        warnings.warn(
            'train_cfg and test_cfg is deprecated, '
            'please specify them in model', UserWarning)
    assert cfg.get('train_cfg') is None or train_cfg is None, \
        'train_cfg specified in both outer field and model field '
    assert cfg.get('test_cfg') is None or test_cfg is None, \
        'test_cfg specified in both outer field and model field '
    return POSE_ESTIMATORS.build(
        cfg, default_args=dict(train_cfg=train_cfg, test_cfg=test_cfg))

VALID_TAG_LIST = ["detector", "human_analyzer", "pose_estimator", "touch_processor"]

def build_model(model_tag, cfg, train_cfg=None, test_cfg=None):
    if model_tag in VALID_TAG_LIST:
        return eval("build_{}".format(model_tag))(cfg, train_cfg=train_cfg, test_cfg=test_cfg)
    else:
        raise ValueError("model tag {} is not supported right now, it has to be one of ({}).".format(model_tag, ",".join(VALID_TAG_LIST)))