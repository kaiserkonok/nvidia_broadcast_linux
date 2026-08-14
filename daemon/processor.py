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
        weights_dir: str | None = None,
        device: str = "cuda",
        quality: str = "best",           # best (resnet50) | balanced (mobilenetv3)
        downsample_ratio: float = 0.4,   # higher internal res -> sharper edges
        fp16: bool = True,
    ):
        import os

        import torch  # local import so Passthrough works without torch

        from .autoframe import AutoFrame
        from .compositor import Compositor

        self.torch = torch
        self.device = torch.device(device)
        self.downsample_ratio = downsample_ratio
        self.fp16 = fp16
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.weights_dir = weights_dir or os.path.join(root, "models", "weights")

        self.quality = None
        self.matting = None
        self._load(quality)              # picks the best available model

        self.compositor = Compositor(device=device)
        self.autoframe = AutoFrame()
        self.enabled = True   # when False, process() is a passthrough

    def _load(self, quality: str):
        import os

        if quality == "ultra":           # BiRefNet: max quality, lower fps
            try:
                from .birefnet import BiRefNetMatting
                new = BiRefNetMatting(device=str(self.device), fp16=self.fp16)
            except Exception as e:        # missing deps / download fail -> keep current
                print(f"[processor] Ultra unavailable ({e}); staying on {self.quality}")
                return
            if self.matting is not None:
                self.matting.close()
            self.matting = new
            self.quality = "ultra"
            return

        from .matting import Matting
        variant = "resnet50" if quality == "best" else "mobilenetv3"
        w = os.path.join(self.weights_dir, f"rvm_{variant}.pth")
        if not os.path.exists(w):        # fall back to whatever is present
            variant, quality = "mobilenetv3", "balanced"
            w = os.path.join(self.weights_dir, "rvm_mobilenetv3.pth")
        if self.matting is not None:
            self.matting.close()
        self.matting = Matting(
            w, variant=variant, device=str(self.device),
            downsample_ratio=self.downsample_ratio, fp16=self.fp16,
        )
        self.quality = quality

    def set_quality(self, quality: str):
        """ultra = BiRefNet (SOTA, lower fps) | best = resnet50 | balanced = mobilenetv3."""
        if quality != self.quality:
            self._load(quality)

    # convenience passthroughs to configure the background live
    def set_blur(self, sigma: float):
        self.enabled = True
        self.compositor.set_blur(sigma)

    def set_image(self, path: str):
        self.enabled = True
        self.compositor.set_image(path)

    def set_color(self, rgb):
        self.enabled = True
        self.compositor.set_color(rgb)

    def set_mode(self, mode: str):
        """mode: none | blur | image | color (keeps existing per-mode params)."""
        if mode == "none":
            self.enabled = False
        else:
            self.enabled = True
            self.compositor.mode = mode

    def set_realism(self, on: bool):
        """Toggle the photoreal pass (edge feather + light-wrap)."""
        self.compositor.realism = bool(on)

    def set_autoframe(self, on: bool):
        self.autoframe.enabled = bool(on)
        if not on:
            self.autoframe.reset()

    def set_zoom(self, zoom: float):
        self.autoframe.zoom = float(zoom)

    def set_vignette(self, amount: float):
        self.compositor.vignette = float(amount)

    def set_grain(self, amount: float):
        self.compositor.grain = float(amount)

    def set_dof(self, amount: float):
        self.compositor.dof = float(amount)

    def process(self, rgb: np.ndarray) -> np.ndarray:
        # Run matting if we need a background effect OR auto-frame (which needs
        # the alpha to locate the subject).
        if not self.enabled and not self.autoframe.enabled:
            return rgb
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
            out = self.compositor.composite(fgr, pha, src[0]) if self.enabled else src[0]
            out = self.autoframe.apply(out, pha)
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
