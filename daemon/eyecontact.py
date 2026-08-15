"""Eye contact / gaze correction (experimental).

Nudges the irises toward the eye centre so you appear to look *at the camera*
even while reading your screen — NVIDIA Broadcast's "Eye Contact".

Pipeline: MediaPipe FaceLandmarker (iris landmarks) on the CPU numpy frame,
then a local, falloff-weighted cv2 warp that shifts each iris. Everything is
optional and lazy: if MediaPipe or the model is missing, the feature simply
stays off — it can never break an existing install or the video pipeline.

Honest caveats: this is a landmark-driven warp, not a trained redirection GAN.
It looks natural for the common case (looking a little below the lens) and gets
less convincing at large angles. Off by default; tune with `strength`.
"""
from __future__ import annotations

import os

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

# MediaPipe 478-pt FaceMesh indices
_L_IRIS, _R_IRIS = 468, 473
_L_EYE = (33, 133, 159, 145)      # outer, inner, upper lid, lower lid
_R_EYE = (362, 263, 386, 374)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODEL = os.path.join(_ROOT, "models", "weights", "face_landmarker.task")


def _warp_eye(img: np.ndarray, iris: np.ndarray, eye_center: np.ndarray,
              iris_r: float, strength: float) -> None:
    """In-place: shift the iris toward `eye_center` by `strength`, with a smooth
    radial falloff so the sclera and lids stay put (no seams)."""
    if cv2 is None or iris_r < 1.5:
        return
    h, w = img.shape[:2]
    delta = (eye_center - iris) * strength          # move iris toward centre
    # cap so landmark jitter can't produce a wild warp
    m = float(np.hypot(*delta))
    if m > iris_r * 1.2:
        delta *= (iris_r * 1.2) / (m + 1e-6)

    cx, cy = float(iris[0]), float(iris[1])
    rad = iris_r * 2.4                                # ROI half-size
    x0, y0 = max(0, int(cx - rad)), max(0, int(cy - rad))
    x1, y1 = min(w, int(cx + rad)), min(h, int(cy + rad))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return

    gy, gx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    dist = np.hypot(gx - cx, gy - cy)
    t = np.clip(dist / (iris_r * 1.6), 0.0, 1.0)     # 0 at iris .. 1 at falloff edge
    wgt = 1.0 - t * t * (3.0 - 2.0 * t)              # smoothstep, 0 at the border
    mapx = (gx - x0) - delta[0] * wgt
    mapy = (gy - y0) - delta[1] * wgt
    roi = img[y0:y1, x0:x1]
    img[y0:y1, x0:x1] = cv2.remap(
        roi, mapx, mapy, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


class EyeContact:
    def __init__(self):
        self.enabled = False
        self.strength = 0.5           # 0..1 how far the iris moves toward centre
        self._lm = None               # lazy FaceLandmarker
        self._unavailable = False     # tried and failed -> don't retry every frame
        self._t = 0

    def reset(self):
        self._t = 0

    def _ensure(self) -> bool:
        if self._lm is not None:
            return True
        if self._unavailable:
            return False
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mtp
            from mediapipe.tasks.python import vision
            if not os.path.exists(_MODEL):
                raise FileNotFoundError(_MODEL)
            opt = vision.FaceLandmarkerOptions(
                base_options=mtp.BaseOptions(model_asset_path=_MODEL),
                running_mode=vision.RunningMode.VIDEO, num_faces=1)
            self._lm = vision.FaceLandmarker.create_from_options(opt)
            self._mp = mp
            return True
        except Exception as e:                        # noqa: BLE001
            print(f"[eyecontact] unavailable ({e}); feature disabled")
            self._unavailable = True
            return False

    def apply(self, rgb: np.ndarray) -> np.ndarray:
        """rgb: HxWx3 uint8 -> same, with corrected gaze (best-effort)."""
        if not self.enabled or self.strength <= 0 or not self._ensure():
            return rgb
        h, w = rgb.shape[:2]
        try:
            mp = self._mp
            image = mp.Image(image_format=mp.ImageFormat.SRGB,
                             data=np.ascontiguousarray(rgb))
            self._t += 33
            res = self._lm.detect_for_video(image, self._t)
            if not res.face_landmarks:
                return rgb
            lm = res.face_landmarks[0]
            pts = np.array([[p.x * w, p.y * h] for p in lm], dtype=np.float32)
            out = rgb.copy()
            for iris_i, eye in ((_L_IRIS, _L_EYE), (_R_IRIS, _R_EYE)):
                iris = pts[iris_i]
                corners = pts[list(eye)]
                eye_center = corners.mean(axis=0)
                eye_w = float(np.hypot(*(pts[eye[0]] - pts[eye[1]])))
                _warp_eye(out, iris, eye_center, eye_w * 0.22, self.strength)
            return out
        except Exception as e:                        # noqa: BLE001 - never kill the feed
            print(f"[eyecontact] frame skipped: {e}")
            return rgb

    def close(self):
        if self._lm is not None:
            try:
                self._lm.close()
            except Exception:
                pass
            self._lm = None
