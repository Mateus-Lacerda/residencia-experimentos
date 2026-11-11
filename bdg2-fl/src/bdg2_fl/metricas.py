import numpy as np


def rmse_cv(real, prev):
    real, prev = np.asarray(real), np.asarray(prev)
    rmse = float(np.sqrt(np.mean((real - prev) ** 2)))
    return {"rmse": rmse, "cv_rmse": rmse / float(np.mean(real))}
