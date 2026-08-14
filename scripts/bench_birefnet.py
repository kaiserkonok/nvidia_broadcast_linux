"""Benchmark BiRefNet (SOTA background matting) at several input sizes on this GPU.

Prints ms/frame + fps so we can decide whether it's viable real-time or an
'Ultra' tier. Downloads the model on first run (~900 MB).
"""
import time

import torch


def main():
    from transformers import AutoModelForImageSegmentation
    torch.set_grad_enabled(False)
    print("loading BiRefNet…", flush=True)
    t0 = time.time()
    model = AutoModelForImageSegmentation.from_pretrained(
        "ZhengPeng7/BiRefNet", trust_remote_code=True)
    model = model.to("cuda").half().eval()
    torch.cuda.synchronize()
    print(f"loaded in {time.time()-t0:.1f}s", flush=True)

    for size in (512, 768, 1024):
        x = torch.randn(1, 3, size, size, device="cuda", dtype=torch.float16)
        for _ in range(5):
            model(x)
        torch.cuda.synchronize()
        ts = []
        for _ in range(15):
            s = time.perf_counter()
            out = model(x)
            torch.cuda.synchronize()
            ts.append((time.perf_counter() - s) * 1000)
        import numpy as np
        ms = float(np.mean(ts))
        print(f"BiRefNet @{size}px: {ms:6.1f} ms -> {1000/ms:4.1f} fps", flush=True)


if __name__ == "__main__":
    main()
