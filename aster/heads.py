"""Training-only head transformations; no prediction clipping or pooled scaling."""
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler


class StableRidge:
    def __init__(self, mode="center", alpha=10, floor=0.1):
        if mode not in {"standard", "center", "floor", "filter"} or alpha <= 0 or floor <= 0:
            raise ValueError("Invalid ridge recipe")
        self.mode, self.alpha, self.floor = mode, alpha, floor

    def fit(self, x, y):
        # Preserve sklearn's existing float32 standardization in the control arm.
        x = np.asarray(x)
        self.scaler_ = StandardScaler(with_std=self.mode != "center").fit(x)
        self.mask_ = np.ones(x.shape[1], dtype=bool)
        if self.mode == "floor":
            self.scaler_.scale_ = np.maximum(np.sqrt(self.scaler_.var_), self.floor)
        elif self.mode == "filter":
            self.mask_ = np.sqrt(self.scaler_.var_) >= self.floor
        self.mean_target_ = float(np.mean(y))
        self.model_ = None
        if self.mask_.any():
            self.model_ = Ridge(alpha=self.alpha).fit(self.transform(x), y)
        return self

    def transform(self, x):
        return self.scaler_.transform(x)[:, self.mask_]

    def predict(self, x):
        if self.model_ is None:
            return np.full(len(x), self.mean_target_)
        return self.model_.predict(self.transform(x))

    def linear_coefficients(self):
        """Equivalent untransformed linear function, for neural head initialization."""
        coef = np.zeros(len(self.mask_), dtype=np.float64)
        if self.model_ is None:
            return coef, self.mean_target_
        scale = self.scaler_.scale_ if self.scaler_.with_std else np.ones(len(coef))
        coef[self.mask_] = self.model_.coef_ / scale[self.mask_]
        intercept = float(self.model_.intercept_ - self.scaler_.mean_ @ coef)
        return coef, intercept


def make_head(recipe):
    return StableRidge(**{k: v for k, v in recipe.items() if k != "id"})
