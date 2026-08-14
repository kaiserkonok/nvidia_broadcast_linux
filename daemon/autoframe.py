"""Auto-Frame: keep the subject centered and nicely sized, like NVIDIA Broadcast.

Instead of a separate face detector, we reuse the alpha matte we already have:
its bounding box IS the subject. We smooth that box over time (so it glides
instead of jittering), turn it into a crop rectangle with the output's aspect
ratio, and resize that crop back to full size — a smooth virtual pan/zoom.
"""
from __future__ import annotations

import torch
import torch.nn.functional as F


class AutoFrame:
    def __init__(self):
        self.enabled = False
        self.zoom = 1.15       # framing tightness (padding around the subject)
        self.smooth = 0.92     # EMA on the crop rect (higher = calmer)
        self.deadzone = 0.06   # ignore tiny subject moves (fraction of frame)
        self._rect: torch.Tensor | None = None   # (x0, y0, x1, y1) in [0,1]

    def reset(self):
        self._rect = None

    @torch.inference_mode()
    def apply(self, frame: torch.Tensor, pha: torch.Tensor) -> torch.Tensor:
        """frame (3,H,W), pha (1,H,W) -> reframed (3,H,W)."""
        if not self.enabled:
            return frame
        _, H, W = frame.shape
        box = self._subject_box(pha, H, W)
        if box is None:
            return frame

        target = self._crop_rect(box, W / H)
        if self._rect is None:
            self._rect = target
        else:
            # deadzone: don't chase sub-pixel wiggles
            if (self._rect - target).abs().max() > self.deadzone:
                self._rect = self.smooth * self._rect + (1 - self.smooth) * target
        return self._resample(frame, self._rect)

    def _subject_box(self, pha, H, W):
        # Downsample the matte for a cheap, stable bounding box.
        small = F.interpolate(pha.unsqueeze(0), size=(min(H, 180), min(W, 320)),
                              mode="bilinear", align_corners=False)[0, 0]
        mask = small > 0.4
        if not bool(mask.any()):
            return None
        rows = torch.where(mask.any(dim=1))[0]
        cols = torch.where(mask.any(dim=0))[0]
        sh, sw = small.shape
        y0, y1 = rows[0].item() / sh, (rows[-1].item() + 1) / sh
        x0, x1 = cols[0].item() / sw, (cols[-1].item() + 1) / sw
        return (x0, y0, x1, y1)

    def _crop_rect(self, box, aspect):
        x0, y0, x1, y1 = box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        bw, bh = (x1 - x0) * self.zoom, (y1 - y0) * self.zoom
        # frame a bit above center so the head has headroom, not dead-center
        cy = cy - bh * 0.05
        # fit an aspect-correct rectangle around the subject box
        rw = max(bw, bh * aspect)
        rh = rw / aspect
        rw = min(rw, 1.0)
        rh = min(rh, 1.0)
        x0 = min(max(cx - rw / 2, 0.0), 1.0 - rw)
        y0 = min(max(cy - rh / 2, 0.0), 1.0 - rh)
        return torch.tensor([x0, y0, x0 + rw, y0 + rh])

    def _resample(self, frame, rect):
        _, H, W = frame.shape
        x0, y0, x1, y1 = rect.tolist()
        # affine grid mapping output -> the crop region
        theta = torch.tensor([
            [(x1 - x0), 0.0, (x0 + x1) - 1.0],
            [0.0, (y1 - y0), (y0 + y1) - 1.0],
        ], device=frame.device, dtype=frame.dtype).unsqueeze(0)
        grid = F.affine_grid(theta, (1, 3, H, W), align_corners=False)
        return F.grid_sample(frame.unsqueeze(0), grid, mode="bilinear",
                             padding_mode="border", align_corners=False)[0]
