"""Frame processor interface.

A Processor takes an RGB uint8 frame and returns an RGB uint8 frame. Phase 0
ships only Passthrough; Phase 1 adds the matting/compositing processor behind
this same interface so the pipeline loop never changes.
"""
from __future__ import annotations

import numpy as np


class Processor:
    def process(self, rgb: np.ndarray) -> np.ndarray:  # pragma: no cover - iface
        raise NotImplementedError

    def close(self) -> None:
        pass


class Passthrough(Processor):
    """Identity — used to validate the capture->output plumbing."""

    def process(self, rgb: np.ndarray) -> np.ndarray:
        return rgb


class MattingProcessor(Processor):
    """RVM matting + background compositing, GPU-resident.

    One upload per frame (HWC uint8 -> CHW float on GPU), one download at the
    end (CHW float -> HWC uint8). Everything in between stays on the GPU.
    """

    def __init__(
        self,
        weights: str,
        device: str = "cuda",
        variant: str = "mobilenetv3",
        downsample_ratio: float = 0.25,
        fp16: bool = True,
    ):
        import torch  # local import so Passthrough works without torch

        from .compositor import Compositor
        from .matting import Matting

        self.torch = torch
        self.device = torch.device(device)
        self.matting = Matting(
            weights, variant=variant, device=device,
            downsample_ratio=downsample_ratio, fp16=fp16,
        )
        self.compositor = Compositor(device=device)

    # convenience passthroughs to configure the background live
    def set_blur(self, sigma: float):
        self.compositor.set_blur(sigma)

    def set_image(self, path: str):
        self.compositor.set_image(path)

    def set_color(self, rgb):
        self.compositor.set_color(rgb)

    def process(self, rgb: np.ndarray) -> np.ndarray:
        torch = self.torch
        with torch.inference_mode():
            src = (
                torch.from_numpy(rgb)
                .to(self.device, non_blocking=True)
                .permute(2, 0, 1)
                .unsqueeze(0)
                .float()
                .div_(255.0)
            )
            fgr, pha = self.matting.infer(src)
            out = self.compositor.composite(fgr, pha, src[0])
            out_u8 = (
                out.clamp_(0.0, 1.0)
                .mul_(255.0)
                .round_()
                .byte()
                .permute(1, 2, 0)
                .contiguous()
                .cpu()
                .numpy()
            )
        return out_u8

    def close(self):
        self.matting.close()
