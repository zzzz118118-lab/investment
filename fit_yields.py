# -*- coding: utf-8 -*-
"""하나증권 Complex/Simple Crack에 맞춰 수율을 회귀 추정한다.

크랙은 모두 Dubai 기준이므로, 수율 합이 1이면
    Complex Crack = Σ(수율 × 제품크랙) − 운영비
가 성립한다. 따라서 절편이 곧 −운영비다.

data/hana_reference.csv 를 입력으로 쓴다.
"""
import numpy as np
import pandas as pd

import config

X_COLS = ["crack_naphtha", "crack_gasoline", "crack_kerosene", "crack_diesel", "crack_bc"]
NAMES = ["납사", "가솔린", "등유", "경유", "B-C"]


def fit(df, target, sum_to_one=True):
    X = df[X_COLS].values
    y = df[target].values
    n, k = X.shape

    if sum_to_one:
        # w5 = 1 - w1..w4 를 대입해 자유 파라미터를 줄인다.
        #   y = Σ wi*xi + c  =  Σ_{i<5} wi*(xi - x5) + x5 + c
        Z = X[:, :k - 1] - X[:, [k - 1]]
        A = np.hstack([Z, np.ones((n, 1))])
        b = y - X[:, k - 1]
        sol, *_ = np.linalg.lstsq(A, b, rcond=None)
        w = np.append(sol[:k - 1], 1 - sol[:k - 1].sum())
        c = sol[-1]
    else:
        A = np.hstack([X, np.ones((n, 1))])
        sol, *_ = np.linalg.lstsq(A, y, rcond=None)
        w, c = sol[:k], sol[-1]

    pred = X @ w + c
    resid = y - pred
    ss_res = (resid ** 2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    r2 = 1 - ss_res / ss_tot
    return w, c, pred, resid, r2


def report(df, target, sum_to_one=True):
    w, c, pred, resid, r2 = fit(df, target, sum_to_one)
    tag = "수율합=1 제약" if sum_to_one else "제약 없음"
    print("\n[%s / %s]" % (target, tag))
    for name, wi in zip(NAMES, w):
        print("   %-8s %7.3f" % (name, wi))
    print("   %-8s %7.3f  (= 운영비 %.2f $/bbl)" % ("절편", c, -c))
    print("   수율합 %.3f | R2 %.4f | 잔차 최대 %.2f | RMSE %.3f"
          % (w.sum(), r2, np.abs(resid).max(), np.sqrt((resid ** 2).mean())))
    return w, c, pred, resid


if __name__ == "__main__":
    df = pd.read_csv(config.DATA / "hana_reference.csv", parse_dates=["date"])
    print("관측 %d일 (%s ~ %s)" % (len(df), df.date.min().date(), df.date.max().date()))

    wc, cc, pred, resid, _ = fit(df, "complex_crack", sum_to_one=False)
    report(df, "complex_crack", sum_to_one=False)
    report(df, "complex_crack", sum_to_one=True)

    print("\n[일자별 적합도 - Complex, 제약 없음]")
    print("%-12s %8s %8s %8s" % ("date", "실제", "예측", "잔차"))
    for d, a, p, r in zip(df.date, df.complex_crack, pred, resid):
        print("%-12s %8.1f %8.3f %+8.3f" % (d.date(), a, p, r))

    ws, cs, _, _, _ = fit(df, "simple_crack", sum_to_one=False)
    report(df, "simple_crack", sum_to_one=False)

    keys = ["crack_naphtha", "crack_gasoline95", "crack_kerosene",
            "crack_diesel005", "crack_hsfo180"]
    print("\n" + "=" * 60)
    print("config.py 에 넣을 값")
    print("=" * 60)
    for label, w, c in [("COMPLEX", wc, cc), ("SIMPLE", ws, cs)]:
        print("%s_YIELDS = {" % label)
        for k, wi in zip(keys, w):
            print('    "%s": %.4f,' % (k, wi))
        print("}")
        print("%s_OPEX = %.4f\n" % (label, -c))
