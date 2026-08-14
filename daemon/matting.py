"""Robust Video Matting inference wrapper.

Holds the recurrent network + its temporal state and turns an RGB uint8 frame
into a GPU-resident (foreground, alpha) pair:

    fgr : (3, H, W) float in [0,1]  -- decontaminated foreground colour
    pha : (1, H, W) float in [0,1]  -- soft alpha matte

Both stay on the GPU so the compositor can blend without a round-trip to CPU.
The recurrent state (r1..r4) is carried frame-to-frame, which is what makes the
matte temporally stable instead of flickering.

RVM is GPL-3.0 (vendored under daemon/rvm/, see daemon/rvm/LICENSE).
"""
from __future__ import annotations

import torch

from .rvm import MattingNetwork


class Matting:
    def __init__(
        self,
        weights: str,
        variant: str = "mobilenetv3",
        device: str = "cuda",
        downsample_ratio: float = 0.25,  # RVM's recommended value for 720p
        fp16: bool = True,
    ):
        self.device = torch.device(device)
        self.fp16 = fp16 and self.device.type == "cuda"
        self.downsample_ratio = downsample_ratio

        model = MattingNetwork(variant).eval().to(self.device)
        model.load_state_dict(torch.load(weights, map_location=self.device))
        if self.fp16:
            model = model.half()
        self.model = model
        self.dtype = torch.float16 if self.fp16 else torch.float32

        # Recurrent temporal state; None on the first frame.
        self.rec: list = [None, None, None, None]

    def reset(self):
        """Drop temporal state (e.g. after a source switch)."""
        self.rec = [None, None, None, None]

    @torch.inference_mode()
    def infer(self, src):
        """src: (1, 3, H, W) float32 in [0,1] on GPU -> (fgr, pha) GPU tensors.

        Returns fgr (3,H,W) and pha (1,H,W) in float32 for stable compositing.
        """
        x = src.to(self.dtype)
        fgr, pha, *self.rec = self.model(
            x, *self.rec, downsample_ratio=self.downsample_ratio
        )
        return fgr[0].float(), pha[0].float()

    def close(self):
        self.rec = [None, None, None, None]
