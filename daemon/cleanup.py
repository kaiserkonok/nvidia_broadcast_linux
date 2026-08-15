"""Video cleanup: low-light enhancement + webcam noise removal (GPU).

Runs on the *captured frame* before matting, so it both cleans what you see and
gives the matting model a brighter, less noisy input (better masks in the dark).
Two independent stages, each strength-controlled:

  * temporal denoise  — motion-gated blend with the previous frame. Static areas
    average over time (sensor grain cancels out); moving areas keep the current
    frame (no ghosting). This is how good webcam denoise works, and it's cheap.
  * low-light         — adaptive gamma (only kicks in when the frame is actually
    dark, so a well-lit room is untouched) plus a mild local-contrast boost.

Everything is clamped and only active when enabled, so it never harms a good feed.
"""
from __future__ import annotations

import torch

from .compositor import _separable_blur


class VideoCleanup:
    def __init__(self):
        self.enabled = False
        self.strength = 0.6      # low-light strength (0..1)
        self.denoise = 0.5       # temporal denoise strength (0..1)
        self.ll_target = 0.45    # luminance we lift a dark frame toward
        self._prev: torch.Tensor | None = None

    def reset(self):
        self._prev = None

    @torch.inference_mode()
    def apply(self, x: torch.Tensor) -> torch.Tensor:
        """x: (1,3,H,W) float [0,1] -> cleaned (1,3,H,W)."""
        # ---- temporal, motion-gated denoise --------------------------------
        if self.denoise > 0:
            if self._prev is None or self._prev.shape != x.shape:
                self._prev = x
            diff = (x - self._prev).abs().mean(dim=1, keepdim=True)   # (1,1,H,W)
            # Estimate motion from a *blurred* diff: real motion is spatially
            # coherent, per-pixel sensor grain is not — so blurring rejects the
            # noise and stops it from masquerading as motion (which would defeat
            # the whole denoise).
            diff = _separable_blur(diff[0], 2.5).unsqueeze(0)
            motion = (diff / 0.03).clamp(0.0, 1.0)                    # 0 static..1 moving
            # keep more of the current frame where there's motion; average with
            # history where it's static (that's where grain lives).
            keep = motion + (1.0 - motion) * (1.0 - self.denoise)
            x = keep * x + (1.0 - keep) * self._prev
            self._prev = x
            # light edge-aware spatial pass: blur only flat areas (where grain
            # sits), keep edges crisp. The flat/edge mask is derived from two
            # *blurred* scales so noise can't fool it into skipping flat regions.
            sm = _separable_blur(x[0], 1.5).unsqueeze(0)
            coarse = _separable_blur(x[0], 4.0).unsqueeze(0)
            edge = (sm - coarse).abs().mean(dim=1, keepdim=True)      # structure only
            w = (1.0 - (edge / 0.02).clamp(0.0, 1.0)) * self.denoise * 0.7
            x = x * (1.0 - w) + sm * w

        # ---- low-light enhancement -----------------------------------------
        if self.strength > 0:
            lum = float(x.mean().clamp_min(1e-4))
            if lum < self.ll_target:
                deficit = self.ll_target - lum
                gamma = max(0.45, min(1.0, 1.0 - self.strength * deficit * 2.2))
                x = x.clamp(0.0, 1.0) ** gamma
            # gentle local contrast so brightening doesn't look flat/washed
            blur = _separable_blur(x[0], 3.0).unsqueeze(0)
            x = x + 0.15 * self.strength * (x - blur)

        return x.clamp(0.0, 1.0)
