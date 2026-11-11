"""Logistic GLMM with random intercept/slopes by group — replaces lme4::glmer.

scikit-learn has no mixed models, so this is a compact numpy implementation:

    logit P(y=1) = Xβ + Z_g b_g,     b_g ~ N(0, Σ)   (Σ unstructured, q×q)

Estimation alternates (i) a Newton step on the joint penalised log-likelihood
in (β, b) — the PIRLS step glmer performs with nAGQ = 0 — and (ii) an EM-type
update  Σ = mean_g( b_g b_gᵀ + V_g ), with V_g the conditional covariance of
b_g. Results mirror ``ranef(fit)`` (conditional modes) and ``condVar``
(posterior variances). A fit is flagged *singular* — like lme4::isSingular —
when Σ collapses (smallest relative eigenvalue < 1e-4).
"""
from __future__ import annotations

import numpy as np
from scipy.special import expit


class LogitGLMM:
    def __init__(self, max_outer=300, tol=1e-6, singular_tol=1e-4):
        self.max_outer, self.tol, self.singular_tol = max_outer, tol, singular_tol

    def fit(self, X, Z, groups, y):
        """X: (n,p) fixed design incl. intercept; Z: (n,q) random design
        (column 0 = intercept); groups: (n,) labels; y: (n,) 0/1."""
        X, Z, y = np.asarray(X, float), np.asarray(Z, float), np.asarray(y, float)
        self.levels_, g = np.unique(groups, return_inverse=True)
        n, p = X.shape
        q, J = Z.shape[1], len(self.levels_)
        Sigma = np.eye(q) * 0.5
        beta, b = np.zeros(p), np.zeros((J, q))
        # warm start β from a plain logistic fit
        for _ in range(25):
            mu = expit(X @ beta)
            w = mu * (1 - mu) + 1e-10
            beta = beta + np.linalg.lstsq(X.T @ (X * w[:, None]) + 1e-8 * np.eye(p),
                                          X.T @ (y - mu), rcond=None)[0]
        self.converged_ = False
        for outer in range(self.max_outer):
            Sinv = np.linalg.pinv(Sigma)
            # Newton iterations on (β, b) given Σ
            for _ in range(30):
                eta = X @ beta + np.einsum("nq,nq->n", Z, b[g])
                mu = expit(eta)
                w = mu * (1 - mu) + 1e-10
                r = y - mu
                # gradient
                gb = X.T @ r
                gu = np.zeros((J, q))
                np.add.at(gu, g, Z * r[:, None])
                gu -= b @ Sinv.T
                # Hessian (negative)
                Hbb = X.T @ (X * w[:, None])
                Hbu = np.zeros((p, J, q))
                Huu = np.zeros((J, q, q))
                for j in range(J):
                    m = g == j
                    Hbu[:, j, :] = X[m].T @ (Z[m] * w[m, None])
                    Huu[j] = Z[m].T @ (Z[m] * w[m, None]) + Sinv
                H = np.zeros((p + J * q, p + J * q))
                H[:p, :p] = Hbb
                H[:p, p:] = Hbu.reshape(p, J * q)
                H[p:, :p] = H[:p, p:].T
                for j in range(J):
                    s = p + j * q
                    H[s:s + q, s:s + q] = Huu[j]
                grad = np.concatenate([gb, gu.ravel()])
                step = np.linalg.lstsq(H + 1e-9 * np.eye(len(H)), grad, rcond=None)[0]
                beta = beta + step[:p]
                b = b + step[p:].reshape(J, q)
                if np.max(np.abs(step)) < 1e-8:
                    break
            Hinv = np.linalg.pinv(H)
            V = np.stack([Hinv[p + j * q:p + (j + 1) * q, p + j * q:p + (j + 1) * q] for j in range(J)])
            Sigma_new = (b[:, :, None] * b[:, None, :] + V).mean(axis=0)
            Sigma_new = (Sigma_new + Sigma_new.T) / 2 + 1e-12 * np.eye(q)
            if np.max(np.abs(Sigma_new - Sigma)) < self.tol * (1 + np.max(np.abs(Sigma))):
                Sigma = Sigma_new
                self.converged_ = True
                break
            Sigma = Sigma_new
        self.n_outer_ = outer + 1
        self.beta_, self.b_, self.Sigma_, self.condvar_ = beta, b, Sigma, V
        sd = np.sqrt(np.clip(np.diag(Sigma), 0, None))
        ev = np.linalg.eigvalsh(Sigma / max(np.max(np.diag(Sigma)), 1e-300))
        self.singular_ = bool(np.min(sd) < 1e-3 or ev.min() < self.singular_tol)
        self.beta_se_ = np.sqrt(np.clip(np.diag(Hinv)[:p], 0, None))
        return self
