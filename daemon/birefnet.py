"""BiRefNet 'Ultra' matting — SOTA mask/edge quality, lower frame rate.

Drops into MattingProcessor via the same infer() contract as RVM's Matting
(returns fgr (3,H,W), pha (1,H,W)). BiRefNet is dichotomous segmentation, not
alpha matting, so there's no foreground decontamination — but its boundary
precision is far higher and it holds up on hard poses where RVM leaves holes.

Slower: ~12 fps @768px, ~6 fps @1024px on an RTX 5060 Ti. Intended as an opt-in
maximum-quality tier. A temporal EMA steadies the mask frame-to-frame.
"""
from __future__ import annotations

import torch
import torch.nn.functional as F


class BiRefNetMatting:
    def __init__(self, device: str = "cuda", size: int = 768,
                 fp16: bool = True, ema: float = 0.5):
        from transformers import AutoModelForImageSegmentation

        self.device = torch.device(device)
        self.size = size
        self.dtype = torch.float16 if fp16 else torch.float32
        model = AutoModelForImageSegmentation.from_pretrained(
            "ZhengPeng7/BiRefNet", trust_remote_code=True)
        self.model = model.to(self.device).to(self.dtype).eval()
        self.mean = torch.tensor([0.485, 0.456, 0.406], device=self.device).view(1, 3, 1, 1)
        self.std = torch.tensor([0.229, 0.224, 0.225], device=self.device).view(1, 3, 1, 1)
        self.ema = ema
        self._prev: torch.Tensor | None = None

    @torch.inference_mode()
    def infer(self, src: torch.Tensor):
        """src (1,3,H,W) float [0,1] -> (fgr (3,H,W), pha (1,H,W))."""
        h, w = src.shape[2:]
        x = F.interpolate(src, (self.size, self.size), mode="bilinear", align_corners=False)
        x = ((x - self.mean) / self.std).to(self.dtype)
        pred = self.model(x)[-1].sigmoid().float()
        pha = F.interpolate(pred, (h, w), mode="bilinear", align_corners=False)
        if self.ema > 0:
            if self._prev is None or self._prev.shape != pha.shape:
                self._prev = pha
            pha = self.ema * self._prev + (1 - self.ema) * pha
            self._prev = pha
        return src[0], pha[0]

    def reset(self):
        self._prev = None

    def close(self):
        self._prev = None
