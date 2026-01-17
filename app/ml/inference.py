"""
DINOv3-based Table State Classifier.

Classifies table states (clean, occupied, dirty) from crop images.
Uses a DINOv3 backbone with attention pooling for robust classification.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Union

import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms
from transformers import AutoModel

LOGGER = logging.getLogger("restaurant-ml")

# HuggingFace model IDs
HF_MODELS = {
    "dinov3_vits16": "facebook/dinov3-vits16-pretrain-lvd1689m",
    "dinov3_vitb16": "facebook/dinov3-vitb16-pretrain-lvd1689m",
    "dinov3_vitl16": "facebook/dinov3-vitl16-pretrain-lvd1689m",
}

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


class AttentionPool(nn.Module):
    """Attention-based pooling over patch tokens."""

    def __init__(self, dim: int, hidden: int = 128):
        super().__init__()
        self.attn = nn.Sequential(
            nn.Linear(dim, hidden),
            nn.Tanh(),
            nn.Linear(hidden, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        weights = F.softmax(self.attn(x), dim=1)
        return (weights * x).sum(dim=1)


class DINOv3Classifier(nn.Module):
    """
    Classifier using DINOv3 backbone with attention pooling.

    Combines CLS token and attention-pooled patch tokens for classification.
    """

    def __init__(
        self,
        backbone: nn.Module,
        embed_dim: int,
        num_classes: int,
        dropout: float = 0.4,
        use_attn_pool: bool = True,
    ):
        super().__init__()
        self.backbone = backbone
        self.backbone.eval()
        for param in backbone.parameters():
            param.requires_grad = False

        self.use_attn_pool = use_attn_pool
        if use_attn_pool:
            self.attn_pool = AttentionPool(embed_dim)

        feat_dim = embed_dim * 2
        self.head = nn.Sequential(
            nn.LayerNorm(feat_dim),
            nn.Linear(feat_dim, 512),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(512, 128),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(128, num_classes),
        )
        self.embed_dim = embed_dim

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        with torch.no_grad():
            out = self.backbone(x)
            if hasattr(out, "last_hidden_state"):
                cls_token = out.last_hidden_state[:, 0]
                patches = out.last_hidden_state[:, 1:]
            else:
                cls_token = out["x_norm_clstoken"]
                patches = out["x_norm_patchtokens"]

        if self.use_attn_pool:
            pooled = self.attn_pool(patches)
        else:
            pooled = patches.mean(dim=1)

        features = torch.cat([cls_token, pooled], dim=1)
        return self.head(features)

    def eval(self):
        super().eval()
        self.backbone.eval()
        return self


class TableClassifier:
    """
    Table state classifier using DINOv3 backbone.

    Args:
        weights_path: Path to the .pt checkpoint file
        device: 'cuda', 'mps', 'cpu', or None (auto-detect)
    """

    def __init__(self, weights_path: str, device: str = None):
        # Auto-detect device
        if device is None:
            if torch.cuda.is_available():
                device = "cuda"
            elif torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"
        self.device = torch.device(device)

        checkpoint = torch.load(weights_path, map_location=self.device)
        self.id2label = checkpoint["id2label"]
        self.label2id = {v: k for k, v in self.id2label.items()}
        embed_dim = checkpoint["embed_dim"]
        backbone_name = checkpoint["backbone"]
        use_attn_pool = checkpoint.get("use_attn_pool", True)

        hf_model_id = HF_MODELS.get(backbone_name, backbone_name)
        LOGGER.info("Loading backbone: %s", hf_model_id)
        backbone = AutoModel.from_pretrained(hf_model_id, trust_remote_code=True)

        num_classes = len(self.id2label)
        self.model = DINOv3Classifier(
            backbone=backbone,
            embed_dim=embed_dim,
            num_classes=num_classes,
            use_attn_pool=use_attn_pool,
        )

        self.model.head.load_state_dict(checkpoint["head"])
        if use_attn_pool and "attn_pool" in checkpoint:
            self.model.attn_pool.load_state_dict(checkpoint["attn_pool"])

        self.model.to(self.device)
        self.model.eval()

        self.transform = transforms.Compose(
            [
                transforms.Resize(256),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
            ]
        )

        LOGGER.info("Model loaded on %s", self.device)
        LOGGER.info("Classes: %s", list(self.id2label.values()))

    @torch.no_grad()
    def predict(self, image: Union[str, Path, Image.Image]) -> Dict[str, object]:
        """
        Predict table state from image.

        Args:
            image: File path or PIL Image

        Returns:
            Dict with 'label', 'confidence', and 'probabilities'
        """
        if isinstance(image, (str, Path)):
            image = Image.open(image)

        if image.mode != "RGB":
            image = image.convert("RGB")

        x = self.transform(image).unsqueeze(0).to(self.device)
        logits = self.model(x)
        probs = F.softmax(logits, dim=1)[0]

        pred_idx = probs.argmax().item()
        pred_label = self.id2label[pred_idx]
        confidence = probs[pred_idx].item()

        return {
            "label": pred_label,
            "confidence": round(confidence, 4),
            "probabilities": {
                self.id2label[i]: round(p.item(), 4) for i, p in enumerate(probs)
            },
        }
