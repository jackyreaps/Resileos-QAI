"""Measure the studio codec on sklearn digits and write the figures.

Run from the repo root:

    python3 scripts/studio/measure.py

Every number in ``outputs/metrics.json`` comes from this process.
The prior samples are a toy. The PNG says so.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = Path(__file__).resolve().parents[1]
for _path in (str(_REPO / "src"), str(_SCRIPTS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import numpy as np
from PIL import Image, ImageDraw

from studio.codec import (
    decode,
    encode,
    logical_bits,
    pack_packet,
    pca_bipolar_bases,
    pca_real_bases,
    random_bases,
    res201_layer0_product,
    unpack_packet,
)
from studio.prior import (
    code_vector,
    decode_code,
    fit_class_conditional,
    majority_code,
    sample_code,
)

OUT = Path(__file__).resolve().parent / "outputs"
RANKS = (1, 2, 4, 8)
LAYERS = (1, 2, 4, 8)
# Declared before looking at the curves. The grids and the toy prior use it.
HIGHLIGHT = {"rank": 4, "n_layers": 4, "scale_mode": "layer", "basis": "pca_bipolar"}
JPEG_QUALITIES = (5, 10, 20, 30, 50, 70, 90, 95)
SPLIT_SEED = 0
TEST_PER_CLASS = 36
PRIOR_COMPONENTS = 16
PRIOR_SEED = 0
SAMPLES_PER_CLASS = 8


def load_split() -> dict:
    from sklearn.datasets import load_digits

    bunch = load_digits()
    images = bunch.images.astype(np.float64) / 16.0
    labels = bunch.target.astype(int)
    train_idx: list[int] = []
    test_idx: list[int] = []
    rng = np.random.default_rng(SPLIT_SEED)
    for label in range(10):
        pool = np.flatnonzero(labels == label)
        order = rng.permutation(pool)
        test_idx.extend(int(i) for i in order[:TEST_PER_CLASS])
        train_idx.extend(int(i) for i in order[TEST_PER_CLASS:])
    return {
        "images": images,
        "labels": labels,
        "train_idx": np.array(train_idx, dtype=int),
        "test_idx": np.array(test_idx, dtype=int),
        "sklearn_note": "sklearn.datasets.load_digits, values divided by 16",
    }


def psnr(original: np.ndarray, recon: np.ndarray, peak: float = 1.0) -> float:
    mse = float(np.mean((original - recon) ** 2))
    if mse <= 0.0:
        return 99.0
    return float(10.0 * np.log10((peak * peak) / mse))


def global_ssim(original: np.ndarray, recon: np.ndarray, peak: float = 1.0) -> float:
    """Single-window SSIM over the whole image (Wang et al. 2004 formula).

    8x8 is smaller than the usual 11x11 local window, so this is not the
    mean of local windows that papers report as SSIM.
    """
    x = np.asarray(original, dtype=np.float64).ravel()
    y = np.asarray(recon, dtype=np.float64).ravel()
    n = x.size
    mu_x = float(x.mean())
    mu_y = float(y.mean())
    var_x = float(np.sum((x - mu_x) ** 2) / (n - 1))
    var_y = float(np.sum((y - mu_y) ** 2) / (n - 1))
    cov = float(np.sum((x - mu_x) * (y - mu_y)) / (n - 1))
    c1 = (0.01 * peak) ** 2
    c2 = (0.03 * peak) ** 2
    num = (2 * mu_x * mu_y + c1) * (2 * cov + c2)
    den = (mu_x**2 + mu_y**2 + c1) * (var_x + var_y + c2)
    return float(num / den)


def summarize(originals: np.ndarray, recons: np.ndarray) -> dict:
    mse = float(np.mean((originals - recons) ** 2))
    scores_psnr = [psnr(originals[i], recons[i]) for i in range(originals.shape[0])]
    scores_ssim = [global_ssim(originals[i], recons[i]) for i in range(originals.shape[0])]
    if mse <= 0.0:
        psnr_dataset = None
    else:
        psnr_dataset = float(10.0 * np.log10(1.0 / mse))
    return {
        "mse": mse,
        # PSNR of the holdout as one set. This is the number to quote.
        "psnr_from_mean_mse": psnr_dataset,
        # Mean of per-image PSNRs. Explodes when a few images are exact.
        "psnr_mean_of_images": float(np.mean(scores_psnr)),
        "psnr_median": float(np.median(scores_psnr)),
        "global_ssim_mean": float(np.mean(scores_ssim)),
    }


def codec_recons(
    images: np.ndarray,
    *,
    rank: int,
    n_layers: int,
    scale_mode: str,
    bases,
    basis: str,
    seed: int = 0,
) -> tuple[np.ndarray, int]:
    """Decode from the packed payload, so the quality matches float32 scales."""
    out = np.empty_like(images)
    packed = 0
    for i, matrix in enumerate(images):
        packet = encode(
            matrix,
            rank=rank,
            n_layers=n_layers,
            seed=seed,
            basis=basis,
            bases=bases,
            scale_mode=scale_mode,
        )
        blob = pack_packet(packet)
        packed = len(blob)
        out[i] = decode(unpack_packet(blob))
    return out, packed


def truncated_svd(matrix: np.ndarray, rank: int) -> np.ndarray:
    u, s, vt = np.linalg.svd(matrix, full_matrices=False)
    k = int(rank)
    return (u[:, :k] * s[:k]) @ vt[:k]


def svd_bits(m: int, n: int, rank: int) -> int:
    """float32 storage of U (m, k), singular values (k,), and Vt (k, n)."""
    return int(32 * (m * rank + rank + n * rank))


def jpeg_bytes_and_recon(image_uint8: np.ndarray, quality: int) -> tuple[bytes, np.ndarray]:
    from io import BytesIO

    buf = BytesIO()
    Image.fromarray(image_uint8, mode="L").save(buf, format="JPEG", quality=int(quality))
    blob = buf.getvalue()
    decoded = np.asarray(Image.open(BytesIO(blob)).convert("L"), dtype=np.float64) / 255.0
    return blob, decoded


def mosaic(images_uint8: np.ndarray, cols: int) -> tuple[np.ndarray, int, int]:
    count, height, width = images_uint8.shape
    rows = int(np.ceil(count / cols))
    canvas = np.zeros((rows * height, cols * width), dtype=np.uint8)
    for i, image in enumerate(images_uint8):
        r, c = divmod(i, cols)
        canvas[r * height : (r + 1) * height, c * width : (c + 1) * width] = image
    return canvas, rows, cols


def unmosaic(canvas: np.ndarray, count: int, height: int, width: int, cols: int) -> np.ndarray:
    out = np.empty((count, height, width), dtype=np.float64)
    for i in range(count):
        r, c = divmod(i, cols)
        tile = canvas[r * height : (r + 1) * height, c * width : (c + 1) * width]
        out[i] = tile
    return out


def to_uint8(images: np.ndarray) -> np.ndarray:
    return np.clip(np.rint(np.asarray(images) * 255.0), 0, 255).astype(np.uint8)


def control_packet_gap(images: np.ndarray) -> dict:
    """Mean error of Ub @ Vb from the RES-201 packet versus the studio decode."""
    rank = HIGHLIGHT["rank"]
    n_layers = HIGHLIGHT["n_layers"]
    naive_err = []
    studio_err = []
    for matrix in images:
        gap = res201_layer0_product(matrix, rank=rank, n_layers=n_layers, seed=0)
        naive_err.append(float(np.mean((gap["naive"] - matrix) ** 2)))
        packet = encode(matrix, rank=rank, n_layers=n_layers, seed=0, scale_mode="layer")
        studio_err.append(float(np.mean((decode(packet) - gap["engine_reconstruction"]) ** 2)))
    return {
        "config": {"rank": rank, "n_layers": n_layers, "basis": "random", "seed": 0},
        "n_images": int(images.shape[0]),
        "res201_naive_Ub_at_Vb_mse_vs_image_mean": float(np.mean(naive_err)),
        "studio_decode_mse_vs_engine_reconstruction_mean": float(np.mean(studio_err)),
        "note": (
            "The RES-201 packet stores layer 0 Ub and Vb only. "
            "Ub @ Vb is not the residual-stack reconstruction. "
            "The studio packet's decode matches the engine reconstruction."
        ),
    }


def fit_bases(train: np.ndarray) -> dict:
    fitted = {}
    for rank in RANKS:
        fitted[("pca_bipolar", rank)] = pca_bipolar_bases(train, rank)
        fitted[("pca_real", rank)] = pca_real_bases(train, rank)
        fitted[("random", rank)] = random_bases(train.shape[1], train.shape[2], rank, seed=0)
    return fitted


def sweep_codec(test: np.ndarray, bases: dict) -> list[dict]:
    rows = []
    m, n = test.shape[1], test.shape[2]
    for basis in ("random", "pca_bipolar", "pca_real"):
        for scale_mode in ("layer", "component"):
            for rank in RANKS:
                for n_layers in LAYERS:
                    recons, packed = codec_recons(
                        test,
                        rank=rank,
                        n_layers=n_layers,
                        scale_mode=scale_mode,
                        bases=bases[(basis, rank)],
                        basis=basis,
                    )
                    stats = summarize(test, recons)
                    rows.append(
                        {
                            "method": "studio_codec",
                            "basis": basis,
                            "scale_mode": scale_mode,
                            "rank": rank,
                            "n_layers": n_layers,
                            "logical_bits": logical_bits(m, n, rank, n_layers, scale_mode),
                            "packed_bytes": packed,
                            **stats,
                        }
                    )
    return rows


def sweep_svd(test: np.ndarray) -> list[dict]:
    m, n = test.shape[1], test.shape[2]
    rows = []
    for rank in range(1, min(m, n) + 1):
        recons = np.stack([truncated_svd(test[i], rank) for i in range(test.shape[0])])
        stats = summarize(test, recons)
        rows.append(
            {
                "method": "truncated_svd",
                "rank": rank,
                "logical_bits": svd_bits(m, n, rank),
                "storage": "float32 U, s, Vt per image",
                **stats,
            }
        )
    return rows


def sweep_jpeg(test: np.ndarray) -> dict:
    uint8 = to_uint8(test)
    # JPEG decodes to /255, so score against the uint8-quantized original,
    # and also report PSNR against the float original. Both are in the file.
    quantized = uint8.astype(np.float64) / 255.0
    per_image = []
    for quality in JPEG_QUALITIES:
        recons = []
        sizes = []
        for image in uint8:
            blob, recon = jpeg_bytes_and_recon(image, quality)
            recons.append(recon)
            sizes.append(len(blob))
        stacked = np.stack(recons)
        per_image.append(
            {
                "quality": quality,
                "bytes_mean": float(np.mean(sizes)),
                "bytes_min": int(np.min(sizes)),
                "bytes_max": int(np.max(sizes)),
                "bits_mean": float(np.mean(sizes) * 8),
                "vs_uint8_quantized": summarize(quantized, stacked),
                "vs_float_original": summarize(test, stacked),
            }
        )
    cols = 19
    canvas, _rows, _cols = mosaic(uint8, cols)
    mosaic_rows = []
    for quality in JPEG_QUALITIES:
        blob, recon = jpeg_bytes_and_recon(canvas, quality)
        tiles = unmosaic(recon, test.shape[0], test.shape[1], test.shape[2], cols)
        mosaic_rows.append(
            {
                "quality": quality,
                "file_bytes": len(blob),
                "bytes_per_image": len(blob) / test.shape[0],
                "bits_per_image": len(blob) * 8 / test.shape[0],
                "canvas_shape": list(canvas.shape),
                "vs_uint8_quantized": summarize(quantized, tiles),
                "vs_float_original": summarize(test, tiles),
            }
        )
    return {"per_image_8x8": per_image, "mosaic": mosaic_rows, "mosaic_cols": cols}


def closest(rows: list[dict], bits: float, key: str = "logical_bits") -> dict:
    return min(rows, key=lambda row: abs(float(row[key]) - bits))


def under_budget(rows: list[dict], bits: float, key: str = "logical_bits") -> dict | None:
    eligible = [row for row in rows if float(row[key]) <= bits + 1e-6]
    if not eligible:
        return None
    return max(eligible, key=psnr_of)


def psnr_of(row: dict) -> float:
    if "psnr_from_mean_mse" in row:
        value = row["psnr_from_mean_mse"]
        return float(value) if value is not None else 99.0
    return float(row["vs_float_original"]["psnr_from_mean_mse"])


def run_prior_config(
    train: np.ndarray,
    train_labels: np.ndarray,
    test: np.ndarray,
    bases,
    *,
    rank: int,
    n_layers: int,
    basis: str,
    scale_mode: str,
) -> dict:
    packets = [
        encode(
            matrix,
            rank=rank,
            n_layers=n_layers,
            basis=basis,
            bases=bases,
            scale_mode=scale_mode,
        )
        for matrix in train
    ]
    codes = np.stack([code_vector(packet) for packet in packets])
    model = fit_class_conditional(codes, train_labels, n_components=PRIOR_COMPONENTS)
    # The model holds arrays. JSON gets plain numbers; sampling uses the arrays.
    template = packets[0]
    rng = np.random.default_rng(PRIOR_SEED)
    samples = []
    sample_labels = []
    for label in range(10):
        for _ in range(SAMPLES_PER_CLASS):
            code = sample_code(model, label, rng)
            samples.append(decode_code(template, code))
            sample_labels.append(label)
    samples_arr = np.stack(samples)
    labels_arr = np.array(sample_labels)

    nn_mse = []
    nn_same = []
    exact = 0
    for image, label in zip(samples_arr, labels_arr):
        err = np.mean((train - image) ** 2, axis=(1, 2))
        nearest = int(np.argmin(err))
        nn_mse.append(float(err[nearest]))
        nn_same.append(int(train_labels[nearest] == label))
        if float(err[nearest]) == 0.0:
            exact += 1

    prototypes = []
    proto_psnr = []
    for label in range(10):
        class_codes = codes[train_labels == label]
        proto = decode_code(template, majority_code(class_codes))
        prototypes.append(proto)
        mean_image = train[train_labels == label].mean(axis=0)
        proto_psnr.append(psnr(mean_image, proto))

    class_mean_psnr = []
    for image, label in zip(samples_arr, labels_arr):
        mean_image = train[train_labels == label].mean(axis=0)
        class_mean_psnr.append(psnr(mean_image, image))

    recon_test = codec_recons(
        test,
        rank=rank,
        n_layers=n_layers,
        scale_mode=scale_mode,
        bases=bases,
        basis=basis,
    )[0]
    return {
        "label": "toy class-conditional PCA prior over residual codes",
        "config": {
            "rank": rank,
            "n_layers": n_layers,
            "scale_mode": scale_mode,
            "basis": basis,
        },
        "n_components": int(model["n_components"]),
        "code_dim": int(model["code_dim"]),
        "n_train_codes": int(model["n_codes"]),
        "explained_variance_ratio": float(model["explained_variance_ratio"]),
        "samples_per_class": SAMPLES_PER_CLASS,
        "same_class_nearest_train_rate": float(np.mean(nn_same)),
        "median_nearest_train_mse": float(np.median(nn_mse)),
        "min_nearest_train_mse": float(np.min(nn_mse)),
        "exact_train_copies": exact,
        "mean_sample_psnr_vs_class_mean_image": float(np.mean(class_mean_psnr)),
        "mean_prototype_psnr_vs_class_mean_image": float(np.mean(proto_psnr)),
        "test_reconstruction": summarize(test, recon_test),
        "class_counts": {key: int(model["classes"][key]["count"]) for key in model["classes"]},
        "_samples": samples_arr,
        "_prototypes": np.stack(prototypes),
    }


def _up(image: np.ndarray, scale: int = 6) -> Image.Image:
    uint8 = to_uint8(image)
    img = Image.fromarray(uint8, mode="L").convert("RGB")
    return img.resize((uint8.shape[1] * scale, uint8.shape[0] * scale), Image.Resampling.NEAREST)


def save_recon_grid(
    path: Path,
    originals: np.ndarray,
    rows: list[tuple[str, np.ndarray]],
) -> None:
    cell = 8 * 6
    pad = 4
    label_w = 210
    header = 36
    width = label_w + len(originals) * (cell + pad) + pad
    height = header + (1 + len(rows)) * (cell + pad) + 28
    canvas = Image.new("RGB", (width, height), (250, 248, 242))
    draw = ImageDraw.Draw(canvas)
    draw.text((8, 8), "Holdout digits. Codec rows are packed-payload decodes. Not generated.", fill=(20, 20, 20))
    labels = ["original"] + [name for name, _ in rows]
    frames = [originals] + [arr for _, arr in rows]
    for r, (label, frame) in enumerate(zip(labels, frames)):
        y = header + r * (cell + pad)
        draw.multiline_text((8, y + 8), label, fill=(20, 20, 20), spacing=2)
        for c in range(frame.shape[0]):
            x = label_w + c * (cell + pad)
            canvas.paste(_up(frame[c]), (x, y))
    canvas.save(path)


def save_prior_grid(
    path: Path,
    samples: np.ndarray,
    prototypes: np.ndarray,
    *,
    subtitle: str,
) -> None:
    cell = 8 * 6
    pad = 4
    label_w = 92
    header = 52
    # samples: 80 = 10 classes * 8, stored class-major
    per = SAMPLES_PER_CLASS
    width = label_w + 10 * (cell + pad) + pad
    height = header + (1 + per) * (cell + pad) + 8
    canvas = Image.new("RGB", (width, height), (250, 248, 242))
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (8, 6),
        "TOY. Class-conditional PCA prior on residual codes. Not a generative model.",
        fill=(140, 30, 20),
    )
    draw.text((8, 24), subtitle, fill=(20, 20, 20))
    y0 = header
    draw.text((8, y0 + 16), "mean code", fill=(20, 20, 20))
    for c in range(10):
        canvas.paste(_up(prototypes[c]), (label_w + c * (cell + pad), y0))
    for s in range(per):
        y = header + (1 + s) * (cell + pad)
        draw.text((8, y + 16), f"sample {s}", fill=(20, 20, 20))
        for c in range(10):
            canvas.paste(_up(samples[c * per + s]), (label_w + c * (cell + pad), y))
    canvas.save(path)


def save_curve(path: Path, series: list[tuple[str, tuple[int, int, int], list[tuple[float, float]]]]) -> None:
    import math

    width, height = 760, 480
    left, right, top, bottom = 56, 16, 48, 56
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    # Full-rank SVD of these 8x8 matrices is numerical roundoff. Clip the
    # axis so the rest of the curves stay readable. Raw values stay in JSON.
    y_cap = 45.0
    xs = [max(x, 1.0) for _, _, pts in series for x, _y in pts]
    log_min = math.log10(min(xs)) - 0.08
    log_max = math.log10(max(xs)) + 0.08
    ymin, ymax = 5.0, y_cap

    def xy(x: float, y: float) -> tuple[int, int]:
        lx = math.log10(max(x, 1.0))
        px = left + (lx - log_min) / (log_max - log_min) * (width - left - right)
        py = top + (ymax - min(y, y_cap)) / (ymax - ymin) * (height - top - bottom)
        return int(px), int(py)

    draw.text((8, 6), "Holdout PSNR from mean MSE vs bits/image. X is log10. Y clipped at 45 dB.", fill=(0, 0, 0))
    draw.text((8, 22), "SVD ranks 7 and 8 are numerical roundoff on 8x8 and are omitted. Y clips at 45 dB.", fill=(0, 0, 0))
    for y in (10, 20, 30, 40):
        _px, py = xy(10 ** log_min, y)
        draw.line([(left, py), (width - right, py)], fill=(230, 230, 230))
        draw.text((4, py - 6), str(y), fill=(60, 60, 60))
    for bits in (50, 100, 200, 500, 1000, 2000, 4000):
        px, _py = xy(bits, ymin)
        if left <= px <= width - right:
            draw.line([(px, top), (px, height - bottom)], fill=(245, 245, 245))
            draw.text((px - 12, height - bottom + 6), str(bits), fill=(60, 60, 60))
    draw.text((width // 2 - 40, height - 18), "bits / image", fill=(0, 0, 0))
    for name, color, pts in series:
        ordered = sorted(pts)
        coords = [xy(x, y) for x, y in ordered]
        if len(coords) >= 2:
            draw.line(coords, fill=color, width=2)
        for px, py in coords:
            draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill=color)
    # Legend
    lx, ly = width - 250, 28
    for name, color, _pts in series:
        draw.rectangle((lx, ly, lx + 10, ly + 10), fill=color)
        draw.text((lx + 14, ly - 2), name, fill=(0, 0, 0))
        ly += 14
    canvas.save(path)


def jsonable(value):
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items() if not str(k).startswith("_")}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    return value


def main() -> None:
    started = time.perf_counter()
    OUT.mkdir(parents=True, exist_ok=True)
    data = load_split()
    images = data["images"]
    labels = data["labels"]
    train = images[data["train_idx"]]
    test = images[data["test_idx"]]
    train_labels = labels[data["train_idx"]]
    test_labels = labels[data["test_idx"]]
    bases = fit_bases(train)

    codec_rows = sweep_codec(test, bases)
    svd_rows = sweep_svd(test)
    jpeg = sweep_jpeg(test)
    gap = control_packet_gap(test[:32])

    highlight_bits = logical_bits(8, 8, HIGHLIGHT["rank"], HIGHLIGHT["n_layers"], HIGHLIGHT["scale_mode"])
    budgets = sorted(
        {
            logical_bits(8, 8, rank, layers, "layer")
            for rank in (2, 4, 8)
            for layers in (2, 4, 8)
        }
    )
    reading = []
    families = {
        "random_layer": [r for r in codec_rows if r["basis"] == "random" and r["scale_mode"] == "layer"],
        "pca_bipolar_layer": [r for r in codec_rows if r["basis"] == "pca_bipolar" and r["scale_mode"] == "layer"],
        "pca_real_layer": [r for r in codec_rows if r["basis"] == "pca_real" and r["scale_mode"] == "layer"],
        "pca_real_component": [r for r in codec_rows if r["basis"] == "pca_real" and r["scale_mode"] == "component"],
        "truncated_svd": svd_rows,
        "jpeg_mosaic": jpeg["mosaic"],
        "jpeg_per_image": jpeg["per_image_8x8"],
    }
    for budget in budgets:
        cell = {"budget_bits": budget}
        for name, rows in families.items():
            if name.startswith("jpeg"):
                key = "bits_per_image" if name == "jpeg_mosaic" else "bits_mean"
                chosen = under_budget(rows, budget, key)
                if chosen is None:
                    cell[name] = None
                else:
                    cell[name] = {
                        "bits": chosen[key],
                        "psnr_vs_float": psnr_of(chosen),
                        "quality": chosen["quality"],
                    }
            else:
                key = "logical_bits"
                chosen = under_budget(rows, budget, key)
                if chosen is None:
                    cell[name] = None
                else:
                    cell[name] = {
                        "bits": chosen[key],
                        "psnr_from_mean_mse": chosen["psnr_from_mean_mse"],
                        "global_ssim_mean": chosen["global_ssim_mean"],
                        "mse": chosen["mse"],
                        "rank": chosen.get("rank"),
                        "n_layers": chosen.get("n_layers"),
                    }
        reading.append(cell)

    prior_bases = bases[(HIGHLIGHT["basis"], HIGHLIGHT["rank"])]
    prior = run_prior_config(
        train,
        train_labels,
        test,
        prior_bases,
        rank=HIGHLIGHT["rank"],
        n_layers=HIGHLIGHT["n_layers"],
        basis=HIGHLIGHT["basis"],
        scale_mode=HIGHLIGHT["scale_mode"],
    )
    # Second toy, chosen after the sweep. The predeclared layer-scale stack
    # does not keep digit shape, so samples from it cannot either. This one
    # uses the real PCA bases and one scale per component, rank 4, 4 layers.
    component_bases = bases[("pca_real", 4)]
    prior_component = run_prior_config(
        train,
        train_labels,
        test,
        component_bases,
        rank=4,
        n_layers=4,
        basis="pca_real",
        scale_mode="component",
    )

    # One of each class, in order, from the holdout.
    picks = []
    for label in range(10):
        picks.append(int(np.flatnonzero(test_labels == label)[0]))
    picked = test[picks]
    highlight_rows = []
    specs = [
        ("random bases, layer scale", "random", "layer"),
        ("PCA ±1 bases, layer scale", "pca_bipolar", "layer"),
        ("PCA real bases, layer scale", "pca_real", "layer"),
        ("PCA real bases, per-component scale", "pca_real", "component"),
    ]
    for title, basis, scale_mode in specs:
        recons, packed = codec_recons(
            picked,
            rank=HIGHLIGHT["rank"],
            n_layers=HIGHLIGHT["n_layers"],
            scale_mode=scale_mode,
            bases=bases[(basis, HIGHLIGHT["rank"])],
            basis=basis,
        )
        bits = logical_bits(8, 8, HIGHLIGHT["rank"], HIGHLIGHT["n_layers"], scale_mode)
        highlight_rows.append((f"{title}\n{bits} bits, {packed} B", recons))

    svd_match = closest(svd_rows, highlight_bits)
    svd_pick = np.stack([truncated_svd(picked[i], int(svd_match["rank"])) for i in range(picked.shape[0])])
    highlight_rows.append(
        (f"truncated SVD rank {svd_match['rank']}\n{svd_match['logical_bits']} bits", svd_pick)
    )
    jpeg_match = closest(jpeg["mosaic"], highlight_bits, "bits_per_image")
    uint8 = to_uint8(test)
    canvas, _r, cols = mosaic(uint8, 19)
    _blob, recon = jpeg_bytes_and_recon(canvas, int(jpeg_match["quality"]))
    tiles = unmosaic(recon, test.shape[0], 8, 8, cols)
    highlight_rows.append(
        (
            f"JPEG mosaic q{jpeg_match['quality']}\n{jpeg_match['bits_per_image']:.0f} bits/img",
            tiles[picks],
        )
    )

    save_recon_grid(OUT / "recon_grid.png", picked, highlight_rows)
    save_prior_grid(
        OUT / "prior_samples.png",
        prior["_samples"],
        prior["_prototypes"],
        subtitle="Declared config: PCA ±1 bases, one scale per layer, rank 4, 4 layers. Classes 0-9.",
    )
    save_prior_grid(
        OUT / "prior_samples_component.png",
        prior_component["_samples"],
        prior_component["_prototypes"],
        subtitle="After the sweep: PCA real bases, per-component scales, rank 4, 4 layers. Classes 0-9.",
    )

    def points(rows: list[dict], bits_key: str = "logical_bits") -> list[tuple[float, float]]:
        return [(float(row[bits_key]), psnr_of(row)) for row in rows]

    save_curve(
        OUT / "rate_distortion.png",
        [
            ("random layer", (30, 90, 180), points(families["random_layer"])),
            ("PCA ±1 layer", (20, 140, 60), points(families["pca_bipolar_layer"])),
            ("PCA real layer", (200, 120, 20), points(families["pca_real_layer"])),
            ("PCA real component", (180, 40, 40), points(families["pca_real_component"])),
            (
                "truncated SVD",
                (40, 40, 40),
                [pt for pt in points(families["truncated_svd"]) if pt[1] < 80.0],
            ),
            ("JPEG mosaic", (120, 40, 160), points(families["jpeg_mosaic"], "bits_per_image")),
        ],
    )

    # Representative originals next to prior samples, one class each, for the report.
    elapsed = time.perf_counter() - started
    import sklearn

    metrics = {
        "run": {
            "script": "scripts/studio/measure.py",
            "seconds": elapsed,
            "numpy": np.__version__,
            "sklearn": sklearn.__version__,
            "split_seed": SPLIT_SEED,
            "test_per_class": TEST_PER_CLASS,
            "n_images": int(images.shape[0]),
            "n_train": int(train.shape[0]),
            "n_test": int(test.shape[0]),
            "shape": [8, 8],
            "normalization": "sklearn digits / 16, so the peak for PSNR is 1",
            "dataset": data["sklearn_note"],
            "psnr": (
                "psnr_from_mean_mse is 10 log10(1 / mean squared error) on the "
                "holdout. psnr_mean_of_images is the mean of per-image PSNRs and "
                "is not the number to quote: it explodes when some images are exact."
            ),
            "global_ssim": "single window = the whole 8x8 image, N-1 variances, L=1. Not local-window SSIM.",
            "codec_quality": "PSNR/SSIM are computed from unpack(pack(packet)), scales stored as float32",
            "shared_bases_not_in_per_image_bits": True,
            "highlight_declared_before_the_sweep_was_read": HIGHLIGHT,
        },
        "control_packet_gap": gap,
        "codec": codec_rows,
        "truncated_svd": svd_rows,
        "jpeg": {k: v for k, v in jpeg.items()},
        "best_under_bit_budget": reading,
        "prior": jsonable(prior),
        "prior_component_after_sweep": jsonable(prior_component),
    }
    (OUT / "metrics.json").write_text(json.dumps(jsonable(metrics), indent=2) + "\n")
    print(f"wrote {OUT / 'metrics.json'} in {elapsed:.2f}s")
    print("highlight bits", highlight_bits)
    for row in codec_rows:
        if (
            row["rank"] == HIGHLIGHT["rank"]
            and row["n_layers"] == HIGHLIGHT["n_layers"]
            and row["scale_mode"] == "layer"
        ):
            print(
                f"{row['basis']:12} layer r4 L4  PSNR {row['psnr_from_mean_mse']:.3f}  "
                f"SSIM {row['global_ssim_mean']:.3f}  bits {row['logical_bits']}  bytes {row['packed_bytes']}"
            )
    print(
        "prior same-class NN",
        f"{prior['same_class_nearest_train_rate']:.3f}",
        "median NN mse",
        f"{prior['median_nearest_train_mse']:.5f}",
        "explained",
        f"{prior['explained_variance_ratio']:.3f}",
    )


if __name__ == "__main__":
    main()
