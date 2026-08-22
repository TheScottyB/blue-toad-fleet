"""Score normalized signature enlargements against the 1200px source crop."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parent
TRUTH = ROOT / "source" / "signature_truth_360x270.png"
VARIANTS = ROOT / "comparisons" / "normalized"

# The blue nameplate band containing the complete silver autograph. Excluding
# the large white jersey areas prevents uniform fabric from dominating scores.
SIGNATURE_ROI = (0, 25, 275, 145)  # left, top, right, bottom


def luma(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("L"), dtype=np.float64)


def gaussian_blur(image: np.ndarray, size: int = 11, sigma: float = 1.5) -> np.ndarray:
    radius = size // 2
    axis = np.arange(-radius, radius + 1, dtype=np.float64)
    kernel = np.exp(-(axis * axis) / (2.0 * sigma * sigma))
    kernel /= kernel.sum()

    padded_x = np.pad(image, ((0, 0), (radius, radius)), mode="reflect")
    windows_x = np.lib.stride_tricks.sliding_window_view(padded_x, size, axis=1)
    blurred_x = np.tensordot(windows_x, kernel, axes=([2], [0]))

    padded_y = np.pad(blurred_x, ((radius, radius), (0, 0)), mode="reflect")
    windows_y = np.lib.stride_tricks.sliding_window_view(padded_y, size, axis=0)
    return np.tensordot(windows_y, kernel, axes=([2], [0]))


def ssim(reference: np.ndarray, candidate: np.ndarray) -> float:
    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2

    mu_x = gaussian_blur(reference)
    mu_y = gaussian_blur(candidate)
    sigma_x = gaussian_blur(reference * reference) - mu_x * mu_x
    sigma_y = gaussian_blur(candidate * candidate) - mu_y * mu_y
    sigma_xy = gaussian_blur(reference * candidate) - mu_x * mu_y

    numerator = (2.0 * mu_x * mu_y + c1) * (2.0 * sigma_xy + c2)
    denominator = (mu_x * mu_x + mu_y * mu_y + c1) * (sigma_x + sigma_y + c2)
    return float(np.mean(numerator / denominator))


def metrics(reference: np.ndarray, candidate: np.ndarray) -> dict[str, float]:
    error = reference - candidate
    mse = float(np.mean(error * error))
    psnr = math.inf if mse == 0 else 10.0 * math.log10((255.0 * 255.0) / mse)
    return {
        "psnr": round(psnr, 4),
        "ssim": round(ssim(reference, candidate), 6),
        "mae": round(float(np.mean(np.abs(error))), 4),
    }


def main() -> None:
    truth = luma(TRUTH)
    left, top, right, bottom = SIGNATURE_ROI
    truth_roi = truth[top:bottom, left:right]
    results: list[dict[str, object]] = []

    for path in sorted(VARIANTS.glob("*.png")):
        candidate = luma(path)
        if candidate.shape != truth.shape:
            raise ValueError(f"{path.name}: {candidate.shape} != {truth.shape}")
        results.append(
            {
                "variant": path.stem,
                "whole_crop": metrics(truth, candidate),
                "signature_roi": metrics(
                    truth_roi, candidate[top:bottom, left:right]
                ),
            }
        )

    results.sort(
        key=lambda item: item["signature_roi"]["ssim"],  # type: ignore[index]
        reverse=True,
    )
    repeat_paths = sorted(VARIANTS.glob("3.1-flash_r*.png"))
    repeat_consistency: list[dict[str, object]] = []
    for index, left_path in enumerate(repeat_paths):
        left_image = luma(left_path)
        for right_path in repeat_paths[index + 1 :]:
            right_image = luma(right_path)
            repeat_consistency.append(
                {
                    "left": left_path.stem,
                    "right": right_path.stem,
                    "whole_crop": metrics(left_image, right_image),
                    "signature_roi": metrics(
                        left_image[top:bottom, left:right],
                        right_image[top:bottom, left:right],
                    ),
                }
            )

    payload = {
        "truth": str(TRUTH.relative_to(ROOT)),
        "signature_roi": list(SIGNATURE_ROI),
        "colorspace": "8-bit luma",
        "ssim": "11x11 Gaussian, sigma=1.5, C1/C2 per Wang et al.",
        "results": results,
        "gemini_flash_repeat_consistency": repeat_consistency,
    }
    (ROOT / "scores.json").write_text(json.dumps(payload, indent=2) + "\n")

    print("variant\tROI PSNR\tROI SSIM\twhole PSNR\twhole SSIM")
    for item in results:
        roi = item["signature_roi"]
        whole = item["whole_crop"]
        print(
            f"{item['variant']}\t{roi['psnr']:.2f}\t{roi['ssim']:.4f}"
            f"\t{whole['psnr']:.2f}\t{whole['ssim']:.4f}"
        )

    print("\nGemini 3.1 Flash repeat consistency")
    print("pair\tROI PSNR\tROI SSIM\twhole PSNR\twhole SSIM")
    for item in repeat_consistency:
        roi = item["signature_roi"]
        whole = item["whole_crop"]
        print(
            f"{item['left']} vs {item['right']}\t{roi['psnr']:.2f}"
            f"\t{roi['ssim']:.4f}\t{whole['psnr']:.2f}\t{whole['ssim']:.4f}"
        )


if __name__ == "__main__":
    main()
