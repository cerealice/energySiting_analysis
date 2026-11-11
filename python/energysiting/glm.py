"""Binomial GLM with R-style inference (glm(..., family = binomial)).

scikit-learn's LogisticRegression gives point estimates but no standard errors,
p-values or AIC, which modeling.R needs for the 10-group coefficient table
(rst_s / rst_w), the AIC-based choice of the background group, and caret's
varImp for "glm" (|z|). This module reproduces R's ``glm.fit``:

* IRLS with the same convergence rule (|dev - dev_old| / (|dev| + 0.1) < 1e-8, maxit 25)
* aliased (linearly dependent) columns detected in formula order and reported as NA,
  like R's pivoting QR (dqrdc2) does.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import expit


def _alias_mask(X, tol=1e-7):
    """True for columns that are (numerically) linear combinations of earlier ones."""
    n, p = X.shape
    keep = np.zeros(p, bool)
    Q = np.zeros((n, 0))
    for j in range(p):
        v = X[:, j].astype(float)
        nv = np.linalg.norm(v)
        if nv == 0:
            continue
        r = v - Q @ (Q.T @ v) if Q.shape[1] else v
        r = r - Q @ (Q.T @ r) if Q.shape[1] else r   # re-orthogonalise
        nr = np.linalg.norm(r)
        if nr > tol * nv:
            keep[j] = True
            Q = np.column_stack([Q, r / nr])
    return ~keep


class BinomialGLM:
    def __init__(self, maxit=25, epsilon=1e-8):
        self.maxit, self.epsilon = maxit, epsilon

    def fit(self, X: pd.DataFrame, y):
        self.names_ = ["(Intercept)"] + list(X.columns)
        Xm = np.column_stack([np.ones(len(X)), X.to_numpy(float)])
        y = np.asarray(y, float)
        aliased = _alias_mask(Xm)
        Xa = Xm[:, ~aliased]
        # mustart = (y + 0.5) / 2 as in binomial()$initialize
        mu = (y + 0.5) / 2
        eta = np.log(mu / (1 - mu))
        dev_old = np.inf
        beta = np.zeros(Xa.shape[1])
        self.converged_ = False
        for it in range(self.maxit):
            mu = expit(eta)
            mu = np.clip(mu, 1e-15, 1 - 1e-15)
            w = mu * (1 - mu)
            z = eta + (y - mu) / w
            sw = np.sqrt(w)
            beta, *_ = np.linalg.lstsq(Xa * sw[:, None], z * sw, rcond=None)
            eta = Xa @ beta
            mu = np.clip(expit(eta), 1e-15, 1 - 1e-15)
            dev = -2 * np.sum(y * np.log(mu) + (1 - y) * np.log(1 - mu))
            if abs(dev - dev_old) / (abs(dev) + 0.1) < self.epsilon:
                self.converged_ = True
                break
            dev_old = dev
        self.iter_ = it + 1
        w = mu * (1 - mu)
        cov = np.linalg.pinv((Xa * w[:, None]).T @ Xa)
        se = np.sqrt(np.clip(np.diag(cov), 0, None))
        full_b = np.full(len(self.names_), np.nan)
        full_se = np.full(len(self.names_), np.nan)
        full_b[~aliased], full_se[~aliased] = beta, se
        self.coef_, self.se_, self.aliased_ = full_b, full_se, aliased
        self.deviance_ = dev
        self.rank_ = int((~aliased).sum())
        self.aic_ = dev + 2 * self.rank_          # binomial, 0/1 response: -2LL = deviance
        self.fitted_ = mu
        return self

    def summary(self) -> pd.DataFrame:
        z = self.coef_ / self.se_
        p = 2 * stats.norm.sf(np.abs(z))
        return pd.DataFrame({"Estimate": self.coef_, "Std. Error": self.se_,
                             "z value": z, "Pr(>|z|)": p}, index=self.names_).dropna()

    def predict_proba1(self, X: pd.DataFrame):
        b = np.nan_to_num(self.coef_)              # predict.glm drops aliased terms
        return expit(b[0] + X.to_numpy(float) @ b[1:])
