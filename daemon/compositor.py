"""GPU compositing of the matted subject over a new background.

Core equation (all tensors GPU float32, CHW, values in [0,1]):

    out = fgr * pha + bg * (1 - pha)

`fgr` is RVM's *decontaminated* foreground, so background colour spill at the
edges is already removed -- the single biggest "looks fake" fix. Backgrounds:
  - blur  : the original scene, heavily blurred (classic privacy blur)
  - image : a static replacement image
  - color : a solid colour

Phase 2 will layer light-wrap, edge feather, temporal EMA and grain on top; the
seams for those live here so the pipeline never changes.
"""
from __future__ import annotations

import cv2
import numpy as np
import torch
import torch.nn.functional as F


def _gaussian_kernel1d(sigma: float, device, dtype) -> torch.Tensor:
    radius = max(1, int(round(3.0 * sigma)))
    x = torch.arange(-radius, radius + 1, device=device, dtype=dtype)
    k = torch.exp(-(x**2) / (2 * sigma * sigma))
    return k / k.sum()


def _separable_blur(img: torch.Tensor, sigma: float) -> torch.Tensor:
    """Separable Gaussian blur on a (3,H,W) tensor.

    For large blurs we downscale first, blur, then upscale -- a big, cheap,
    bokeh-like defocus rather than an expensive full-res large-kernel conv.
    """
    c, h, w = img.shape
    scale = 1.0
    if sigma > 6.0:                # heavy blur -> work at 1/4 res
        scale = 0.25
    x = img.unsqueeze(0)
    if scale != 1.0:
        x = F.interpolate(x, scale_factor=scale, mode="bilinear", align_corners=False)
        sigma = sigma * scale
    k = _gaussian_kernel1d(sigma, img.device, img.dtype)
    ksz = k.numel()
    pad = ksz // 2
    kh = k.view(1, 1, 1, ksz).expand(c, 1, 1, ksz)
    kv = k.view(1, 1, ksz, 1).expand(c, 1, ksz, 1)
    x = F.conv2d(F.pad(x, (pad, pad, 0, 0), mode="reflect"), kh, groups=c)
    x = F.conv2d(F.pad(x, (0, 0, pad, pad), mode="reflect"), kv, groups=c)
    if scale != 1.0:
        x = F.interpolate(x, size=(h, w), mode="bilinear", align_corners=False)
    return x.squeeze(0)


class Compositor:
    def __init__(self, device: str = "cuda"):
        self.device = torch.device(device)
        self.mode = "blur"            # blur | image | color
        self.blur_sigma = 12.0
        self.color = (30, 30, 30)     # RGB solid bg
        self._bg_image: torch.Tensor | None = None   # (3,H,W) cached at frame size
        self._bg_src_hw: tuple[int, int] | None = None

        # ---- realism pass (Phase 2) -----------------------------------------
        # These turn a clean matte composite into one that reads as photoreal.
        self.realism = True
        self.shrink = 1.0            # erode matte inward (px) to kill halo
        self.feather_sigma = 1.2     # soften the alpha edge
        self.temporal = 0.0          # EMA on the matte (RVM is already stable)
        self.lightwrap_strength = 0.30   # bleed bg light around the silhouette
        self.lightwrap_sigma = 10.0      # how far the light wraps
        self.grain = 0.0             # unify texture (std in [0,1], e.g. 0.004)
        self._pha_prev: torch.Tensor | None = None

        # ---- scene match: subject adopts the background's light -------------
        # The biggest "pasted-on" cue is a colour/exposure mismatch between the
        # subject and the new background. We gently grade the foreground toward
        # the background's white balance and tonal range (kept subtle + smoothed
        # over time so faces never flicker or wash out).
        self.scene_match = True
        self.wb_strength = 0.35      # pull fg white balance toward bg
        self.exposure_strength = 0.18  # pull fg brightness toward bg (kept low)
        self.match_smooth = 0.9      # temporal EMA on the grade (anti-flicker)
        self._grade_gain: torch.Tensor | None = None

        # ---- finishing (applies in every mode) ------------------------------
        self.vignette = 0.0          # 0..1 subtle edge darkening
        self._vig_mask: torch.Tensor | None = None
        self._vig_hw: tuple[int, int] | None = None

    # ---- background configuration -------------------------------------------
    def set_blur(self, sigma: float):
        self.mode = "blur"
        self.blur_sigma = float(sigma)

    def set_color(self, rgb):
        self.mode = "color"
        self.color = tuple(int(c) for c in rgb)

    def set_image(self, path: str):
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        if img is None:
            raise FileNotFoundError(f"background image not found: {path}")
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        self._bg_image = (
            torch.from_numpy(rgb).to(self.device).permute(2, 0, 1).float().div_(255.0)
        )
        self._bg_src_hw = None
        self.mode = "image"

    # ---- background resolution ----------------------------------------------
    def _background(self, src: torch.Tensor) -> torch.Tensor:
        """Return a (3,H,W) background matching `src`'s size."""
        c, h, w = src.shape
        if self.mode == "blur":
            return _separable_blur(src, self.blur_sigma)
        if self.mode == "color":
            col = torch.tensor(
                [c / 255.0 for c in self.color], device=self.device
            ).view(3, 1, 1)
            return col.expand(3, h, w)
        # image: cover-fit to frame, cache the resized result. If no image has
        # been chosen yet, fall back to a blur so we never crash or show black.
        if self._bg_image is None:
            return _separable_blur(src, self.blur_sigma)
        if self._bg_src_hw != (h, w):
            self._bg_resized = self._cover_fit(self._bg_image, h, w)
            self._bg_src_hw = (h, w)
        return self._bg_resized

    def _cover_fit(self, img: torch.Tensor, h: int, w: int) -> torch.Tensor:
        _, ih, iw = img.shape
        scale = max(w / iw, h / ih)
        nh, nw = int(round(ih * scale)), int(round(iw * scale))
        r = F.interpolate(img.unsqueeze(0), size=(nh, nw),
                          mode="bilinear", align_corners=False)[0]
        top, left = (nh - h) // 2, (nw - w) // 2
        return r[:, top:top + h, left:left + w].contiguous()

    # ---- realism stages -----------------------------------------------------
    def _refine_matte(self, pha: torch.Tensor) -> torch.Tensor:
        """Erode slightly + feather the alpha edge (and optional temporal EMA)."""
        a = pha
        if self.temporal > 0:
            if self._pha_prev is None or self._pha_prev.shape != a.shape:
                self._pha_prev = a
            a = self.temporal * self._pha_prev + (1.0 - self.temporal) * a
            self._pha_prev = a
        if self.shrink > 0:
            k = int(self.shrink) * 2 + 1
            # morphological erosion = -maxpool(-a): pulls the edge inward so the
            # feather sits on the true boundary instead of leaving a bg halo.
            a = -F.max_pool2d(-a.unsqueeze(0), k, stride=1, padding=k // 2)[0]
        if self.feather_sigma > 0:
            a = _separable_blur(a, self.feather_sigma)
        return a.clamp(0.0, 1.0)

    def _scene_match(self, fgr: torch.Tensor, bg: torch.Tensor,
                     pha: torch.Tensor) -> torch.Tensor:
        """Grade the foreground toward the background's light.

        Decomposes the shift into white balance (per-channel colour ratio) and
        exposure (overall luminance), each with its own strength, then smooths
        the gain over time so faces don't flicker. Gains are clamped so a dark
        subject on a bright scene is nudged, never blown out.
        """
        if not self.scene_match or (self.wb_strength <= 0 and self.exposure_strength <= 0):
            return fgr
        eps = 1e-4
        w = pha.sum() + eps
        fg_mean = (fgr * pha).sum(dim=(1, 2), keepdim=True) / w   # alpha-weighted
        bg_mean = bg.mean(dim=(1, 2), keepdim=True)
        fg_lum = fg_mean.mean().clamp_min(eps)
        bg_lum = bg_mean.mean().clamp_min(eps)

        fg_ratio = fg_mean / fg_lum                              # chroma, luminance-free
        bg_ratio = bg_mean / bg_lum
        # A real coloured wall tints you a little, not fully. Back the white-
        # balance match off as the background gets more saturated, so a solid
        # green/teal/blue doesn't dye the subject that colour.
        bg_sat = (bg_ratio.max() - bg_ratio.min()).clamp(0.0, 3.0)
        sat_atten = 1.0 - ((bg_sat - 0.35) / 1.0).clamp(0.0, 1.0) * 0.85
        wb_eff = self.wb_strength * sat_atten
        target_ratio = fg_ratio * (1 - wb_eff) + bg_ratio * wb_eff
        target_lum = fg_lum * (1 - self.exposure_strength) + bg_lum * self.exposure_strength
        gain = (target_ratio * target_lum) / (fg_mean + eps)
        gain = gain.clamp(0.6, 1.7)

        if self._grade_gain is None or self._grade_gain.shape != gain.shape:
            self._grade_gain = gain
        else:
            self._grade_gain = (self.match_smooth * self._grade_gain
                                + (1 - self.match_smooth) * gain)
        return (fgr * self._grade_gain).clamp(0.0, 1.0)

    def _light_wrap(self, comp: torch.Tensor, bg: torch.Tensor,
                    pha: torch.Tensor) -> torch.Tensor:
        """Bleed softened background light around the subject edge (screen blend).

        The subject then looks lit by the scene instead of pasted onto it.
        """
        if self.lightwrap_strength <= 0:
            return comp
        # Ease off on saturated/solid backgrounds so the wrap doesn't read as
        # colour spill on the edges.
        bg_mean = bg.mean(dim=(1, 2), keepdim=True)
        r = bg_mean / bg_mean.mean().clamp_min(1e-4)
        sat = (r.max() - r.min()).clamp(0.0, 3.0)
        strength = self.lightwrap_strength * (1.0 - ((sat - 0.35) / 1.0).clamp(0.0, 1.0) * 0.8)

        bg_soft = _separable_blur(bg, self.lightwrap_sigma)
        a_blur = _separable_blur(pha, self.lightwrap_sigma)
        band = (pha * (1.0 - a_blur)).clamp(0.0, 1.0)   # thin band just inside edge
        w = (band * strength).clamp(0.0, 1.0)
        screened = 1.0 - (1.0 - comp) * (1.0 - bg_soft)
        return comp * (1.0 - w) + screened * w

    def _vignette(self, out: torch.Tensor) -> torch.Tensor:
        if self.vignette <= 0:
            return out
        _, H, W = out.shape
        if self._vig_hw != (H, W):
            yy = torch.linspace(-1, 1, H, device=self.device).view(H, 1)
            xx = torch.linspace(-1, 1, W, device=self.device).view(1, W)
            r = (xx * xx + yy * yy).sqrt()
            self._vig_mask = (1.0 - ((r - 0.6) / 0.8).clamp(0.0, 1.0)).clamp(0.0, 1.0)
            self._vig_hw = (H, W)
        m = 1.0 - self.vignette * (1.0 - self._vig_mask)
        return out * m

    # ---- compositing --------------------------------------------------------
    @torch.inference_mode()
    def composite(self, fgr: torch.Tensor, pha: torch.Tensor,
                  src: torch.Tensor) -> torch.Tensor:
        """fgr (3,H,W), pha (1,H,W), src (3,H,W) -> out (3,H,W), all GPU float32."""
        bg = self._background(src)
        if not self.realism:
            out = fgr * pha + bg * (1.0 - pha)
        else:
            a = self._refine_matte(pha)
            fgr = self._scene_match(fgr, bg, a)
            out = fgr * a + bg * (1.0 - a)
            out = self._light_wrap(out, bg, a)

        out = self._vignette(out)
        if self.grain > 0:
            out = out + torch.randn_like(out) * self.grain
        return out.clamp(0.0, 1.0)
