"""神經代理模型：FiLM 條件化的小型 U-Net，以及三個變體的預測器。

## 三個變體，一次只差一件事

`se-ml-lifecycle` Stage 5：「只改一個主要假設」。這三個變體是同一個網路、
同一份 folds、同一組超參數，差別只在**輸入與目標怎麼定義**：

| 變體 | 輸入 | 目標 | 檢驗的假設 |
|---|---|---|---|
| `direct` | 原始功率圖 ＋ kt/h/Lx/Ly（用 training fold 的統計量標準化） | θ（同樣標準化） | 對照組：不做物理無因次化會怎樣 |
| `norm` | p_norm ＋ (m·Lx, m·Ly) | θ_norm | 無因次化買到什麼 |
| `residual` | p_norm ＋ 物理基準場 ＋ (m·Lx, m·Ly) | θ_norm − 基準 | 學殘差買到什麼 |

`direct` 存在的唯一理由是**證偽**。無因次化在紙上看起來一定對——θ 對功率線性，
除掉尺度之後功率外推變成恆等式。但「聽起來一定對」不是證據，
而這三行的差距就是那個決策實際值多少。

## 條件化用 FiLM 而不是把純量廣播成通道

m·Lx 決定的是**核有多寬**，那是一個全域的、乘性的效應。廣播成一張常數圖之後，
網路要從空間卷積裡把一個常數重新萃取出來；FiLM 直接讓它調變每個通道的增益，
少繞一圈。這是選擇，不是定論——`direct` 變體就是用廣播通道做的。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from .baselines import greens_theta_norm
from .dataset import Dataset

__all__ = ["UNet", "NeuralPredictor", "compute_greens_norm", "resolve_device"]


def resolve_device(prefer_cuda: bool = True) -> torch.device:
    return torch.device("cuda" if prefer_cuda and torch.cuda.is_available() else "cpu")


def compute_greens_norm(ds: Dataset, images: int = 1) -> np.ndarray:
    """整批算無因次物理基準場，形狀 (n, ny, nx)。慢，所以要快取。"""
    m = ds.m
    out = np.empty(ds.power_map.shape, dtype=np.float32)
    p_norm = ds.p_norm
    for i in range(len(ds)):
        out[i] = greens_theta_norm(
            p_norm[i].astype(np.float64),
            float(m[i] * ds.ly[i]),
            float(m[i] * ds.lx[i]),
            images=images,
        ).astype(np.float32)
    return out


class FiLM(nn.Module):
    """由條件向量產生每個通道的 (scale, shift)。"""

    def __init__(self, cond_dim: int, channels: int) -> None:
        super().__init__()
        self.to_params = nn.Linear(cond_dim, 2 * channels)
        nn.init.zeros_(self.to_params.weight)
        nn.init.zeros_(self.to_params.bias)

    def forward(self, x: torch.Tensor, cond: torch.Tensor) -> torch.Tensor:
        scale, shift = self.to_params(cond).chunk(2, dim=1)
        return x * (1.0 + scale[:, :, None, None]) + shift[:, :, None, None]


class Block(nn.Module):
    def __init__(self, cin: int, cout: int, cond_dim: int) -> None:
        super().__init__()
        self.c1 = nn.Conv2d(cin, cout, 3, padding=1)
        self.c2 = nn.Conv2d(cout, cout, 3, padding=1)
        self.n1 = nn.GroupNorm(8, cout)
        self.n2 = nn.GroupNorm(8, cout)
        self.film = FiLM(cond_dim, cout)

    def forward(self, x: torch.Tensor, cond: torch.Tensor) -> torch.Tensor:
        x = F.silu(self.n1(self.c1(x)))
        x = self.film(x, cond)
        return F.silu(self.n2(self.c2(x)))


class UNet(nn.Module):
    """三層下採樣的 U-Net。輸出一張場，形狀與輸入的空間維度相同。"""

    def __init__(self, in_channels: int, cond_dim: int, base: int = 32) -> None:
        super().__init__()
        c1, c2, c3 = base, base * 2, base * 4
        self.cond = nn.Sequential(nn.Linear(cond_dim, 64), nn.SiLU(), nn.Linear(64, 64))
        self.e1 = Block(in_channels, c1, 64)
        self.e2 = Block(c1, c2, 64)
        self.e3 = Block(c2, c3, 64)
        self.mid = Block(c3, c3, 64)
        self.d3 = Block(c3 + c3, c2, 64)
        self.d2 = Block(c2 + c2, c1, 64)
        self.d1 = Block(c1 + c1, c1, 64)
        self.out = nn.Conv2d(c1, 1, 1)

    def forward(self, x: torch.Tensor, cond_raw: torch.Tensor) -> torch.Tensor:
        cond = self.cond(cond_raw)
        s1 = self.e1(x, cond)
        s2 = self.e2(F.avg_pool2d(s1, 2), cond)
        s3 = self.e3(F.avg_pool2d(s2, 2), cond)
        m = self.mid(F.avg_pool2d(s3, 2), cond)

        u3 = F.interpolate(m, scale_factor=2, mode="nearest")
        u3 = self.d3(torch.cat([u3, s3], 1), cond)
        u2 = F.interpolate(u3, scale_factor=2, mode="nearest")
        u2 = self.d2(torch.cat([u2, s2], 1), cond)
        u1 = F.interpolate(u2, scale_factor=2, mode="nearest")
        u1 = self.d1(torch.cat([u1, s1], 1), cond)
        return self.out(u1).squeeze(1)


class NeuralPredictor:
    """實作 `predictors.Predictor`。`fit` 只拿得到 training fold，見 `predictors.py`。

    `under_weight` > 1 時對**低估**加權——錯誤成本不對稱是問題定義第 5 題就寫下的事實，
    而對稱的 L1 損失把它當成不存在。這個開關是 Stage 5 的一個獨立實驗，
    預設關閉（=1.0），因為「加權會改善決策」在跑之前只是一個假設。
    """

    def __init__(
        self,
        variant: str = "norm",
        epochs: int = 40,
        batch_size: int = 32,
        lr: float = 2e-3,
        base_channels: int = 32,
        under_weight: float = 1.0,
        seed: int = 0,
        device: torch.device | None = None,
        greens_key: str = "greens_norm",
    ) -> None:
        if variant not in ("direct", "norm", "residual"):
            raise ValueError(f"未知 variant {variant!r}")
        self.variant = variant
        self.epochs = epochs
        self.batch_size = batch_size
        self.lr = lr
        self.base_channels = base_channels
        self.under_weight = under_weight
        self.seed = seed
        self.device = device or resolve_device()
        self.greens_key = greens_key
        self.name = f"unet_{variant}" + ("" if under_weight == 1.0 else f"_uw{under_weight:g}")
        self.model_: UNet | None = None
        self.stats_: dict[str, np.ndarray] = {}

    # --- 特徵組裝 ---------------------------------------------------------

    def _greens(self, ds: Dataset) -> np.ndarray:
        if self.greens_key in ds.arrays:
            return ds.arrays[self.greens_key]
        return compute_greens_norm(ds)

    def _features(self, ds: Dataset) -> tuple[np.ndarray, np.ndarray]:
        if self.variant == "direct":
            scalars = np.stack(
                [ds.kt, ds.h_conv, ds.lx, ds.ly], axis=1
            ).astype(np.float32)
            scalars = (scalars - self.stats_["cond_mean"]) / self.stats_["cond_std"]
            x = (ds.power_map / self.stats_["p_scale"])[:, None].astype(np.float32)
            return x, scalars

        cond = np.log(np.stack([ds.m * ds.lx, ds.m * ds.ly], axis=1)).astype(np.float32)
        p_norm = ds.p_norm[:, None].astype(np.float32)
        if self.variant == "norm":
            return p_norm, cond
        g = self._greens(ds)[:, None].astype(np.float32)
        return np.concatenate([p_norm, g], axis=1), cond

    def _target(self, ds: Dataset) -> np.ndarray:
        if self.variant == "direct":
            theta = ds.temperature - ds.t_amb[:, None, None]
            return (theta / self.stats_["theta_scale"]).astype(np.float32)
        if self.variant == "norm":
            return ds.theta_norm.astype(np.float32)
        return (ds.theta_norm - self._greens(ds)).astype(np.float32)

    def _to_temperature(self, ds: Dataset, out: np.ndarray) -> np.ndarray:
        if self.variant == "direct":
            theta = out * self.stats_["theta_scale"]
            return theta + ds.t_amb[:, None, None]
        theta_norm = out if self.variant == "norm" else out + self._greens(ds)
        return ds.to_temperature(theta_norm)

    # --- 訓練與推論 -------------------------------------------------------

    def fit(self, train: Dataset) -> None:
        torch.manual_seed(self.seed)
        np.random.seed(self.seed)

        if self.variant == "direct":
            # 這些統計量**只**從 training fold 算，是 CLAUDE.md 節奏第 3 條的落地。
            scalars = np.stack([train.kt, train.h_conv, train.lx, train.ly], axis=1)
            self.stats_ = {
                "cond_mean": scalars.mean(axis=0).astype(np.float32),
                "cond_std": scalars.std(axis=0).astype(np.float32),
                "p_scale": np.float32(train.power_map.std()),
                "theta_scale": np.float32(
                    (train.temperature - train.t_amb[:, None, None]).std()
                ),
            }

        x, cond = self._features(train)
        y = self._target(train)

        xt = torch.from_numpy(x)
        ct = torch.from_numpy(cond)
        yt = torch.from_numpy(y)

        model = UNet(xt.shape[1], ct.shape[1], base=self.base_channels).to(self.device)
        opt = torch.optim.AdamW(model.parameters(), lr=self.lr, weight_decay=1e-4)
        n = len(xt)
        steps = max(1, n // self.batch_size) * self.epochs
        sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=self.lr, total_steps=steps)

        model.train()
        step = 0
        g = torch.Generator().manual_seed(self.seed)
        for _ in range(self.epochs):
            order = torch.randperm(n, generator=g)
            for s in range(0, n - self.batch_size + 1, self.batch_size):
                idx = order[s : s + self.batch_size]
                xb = xt[idx].to(self.device, non_blocking=True)
                cb = ct[idx].to(self.device, non_blocking=True)
                yb = yt[idx].to(self.device, non_blocking=True)

                pred = model(xb, cb)
                err = pred - yb
                if self.under_weight != 1.0:
                    w = torch.where(err < 0, self.under_weight, 1.0)
                    loss = (w * err.abs()).mean()
                else:
                    loss = err.abs().mean()

                opt.zero_grad(set_to_none=True)
                loss.backward()
                opt.step()
                if step < steps - 1:
                    sched.step()
                step += 1

        self.model_ = model.eval()

    @torch.no_grad()
    def predict(self, ds: Dataset) -> np.ndarray:
        if self.model_ is None:
            raise RuntimeError("尚未 fit")
        x, cond = self._features(ds)
        outs = []
        for s in range(0, len(x), 256):
            xb = torch.from_numpy(x[s : s + 256]).to(self.device)
            cb = torch.from_numpy(cond[s : s + 256]).to(self.device)
            outs.append(self.model_(xb, cb).float().cpu().numpy())
        return self._to_temperature(ds, np.concatenate(outs).astype(np.float64))


    # --- 存取權重 ---------------------------------------------------------

    _CONFIG_FIELDS = (
        "variant",
        "epochs",
        "batch_size",
        "lr",
        "base_channels",
        "under_weight",
        "seed",
    )

    def save(self, path: str | Path) -> None:
        """存權重、超參數與 `direct` 變體的正規化常數。

        統計量必須跟權重一起存。少了它們，`direct` 變體載回來之後會用一組
        **不同的**正規化常數做推論——模型還是會給出數字，只是那些數字沒有意義。
        這正是最難察覺的那類部署錯誤。
        """
        if self.model_ is None:
            raise RuntimeError("尚未 fit")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "state_dict": self.model_.state_dict(),
                "config": {k: getattr(self, k) for k in self._CONFIG_FIELDS},
                "stats": {k: np.asarray(v) for k, v in self.stats_.items()},
                "in_channels": self.model_.e1.c1.in_channels,
                "cond_dim": self.model_.cond[0].in_features,
            },
            path,
        )

    @classmethod
    def load(cls, path: str | Path, device: torch.device | None = None) -> "NeuralPredictor":
        blob = torch.load(path, map_location="cpu", weights_only=False)
        obj = cls(device=device or resolve_device(), **blob["config"])
        model = UNet(blob["in_channels"], blob["cond_dim"], base=obj.base_channels)
        model.load_state_dict(blob["state_dict"])
        obj.model_ = model.to(obj.device).eval()
        obj.stats_ = {k: np.asarray(v) for k, v in blob["stats"].items()}
        return obj
