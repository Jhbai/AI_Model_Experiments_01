import os

# 1. 產生 pelt_cost.h 檔案
pelt_cost_h = r'''
#ifndef PELT_COST_H
#define PELT_COST_H

#include <stdlib.h>
#include <math.h>
#include <float.h>

#define CLIP_LOWER 1e-2
#define CLIP_UPPER 1e2

// 輔助函式：將 x 限制在 [lower, upper] 區間內
static inline double clip(double x, double lower, double upper) {
    if(x < lower) return lower;
    if(x > upper) return upper;
    return x;
}

/*
 * compute_gram
 * ------------
 * 計算整個信號的 Gram 矩陣（n x n），公式：
 *    G[i][j] = exp( - clip( gamma * (data[i]-data[j])^2, CLIP_LOWER, CLIP_UPPER ) )
 *
 * 參數：
 *   data  : 輸入信號陣列 (double*)，長度 n
 *   n     : 信號長度
 *   gamma : 核參數
 *
 * 傳回：
 *   Gram 矩陣（以 row-major 存放），使用者需在外部 free()。
 */
double* compute_gram(const double* data, int n, double gamma) {
    double* gram = (double*) malloc(n * n * sizeof(double));
    if (!gram) return NULL;
    for (int i = 0; i < n; i++){
        for (int j = 0; j < n; j++){
            double diff = data[i] - data[j];
            double sqdiff = diff * diff;
            double val = gamma * sqdiff;
            val = clip(val, CLIP_LOWER, CLIP_UPPER);
            gram[i * n + j] = exp(-val);
        }
    }
    return gram;
}

/*
 * cost_error_segment
 * --------------------
 * 利用預先計算好的 Gram 矩陣，計算區間 [tau, t) 的成本：
 *    cost = sum_{i=tau}^{t-1} G[i][i] - (1/(t-tau))*sum_{i,j=tau}^{t-1} G[i][j]
 *
 * 參數：
 *   gram : 預先計算好的 Gram 矩陣（大小為 N x N，N 為原信號長度）
 *   N    : 原信號長度
 *   tau, t: 區間索引，t 為不包含端
 *
 * 傳回：
 *   計算得到的成本值
 */
static inline double cost_error_segment(const double* gram, int N, int tau, int t) {
    int seg_len = t - tau;
    double diag_sum = 0.0;
    double total_sum = 0.0;
    for (int i = tau; i < t; i++) {
        diag_sum += gram[i * N + i];
        for (int j = tau; j < t; j++) {
            total_sum += gram[i * N + j];
        }
    }
    return diag_sum - total_sum / seg_len;
}

/*
 * compute_cost
 * ------------
 * 計算區間 [start, end) 上的成本。
 * cost_type = 0: L2 cost
 * cost_type = 1: RBF cost（此版本會重新計算局部 Gram 矩陣，僅作備援用途）
 */
double compute_cost(const double *data, int start, int end, int cost_type) {
    int n = end - start;
    if (n <= 0) return 0.0;
    if (cost_type == 0) { // L2 cost
        double sum = 0.0;
        for (int i = start; i < end; i++) {
            sum += data[i];
        }
        double mean = sum / n;
        double cost = 0.0;
        for (int i = start; i < end; i++) {
            double diff = data[i] - mean;
            cost += diff * diff;
        }
        return cost;
    } else if (cost_type == 1) { // RBF cost（較慢的備援版本）
        double gamma = 1.0;
        double* gram = compute_gram(data + start, n, gamma);
        if (gram == NULL) return 0.0;
        double cost = cost_error_segment(gram, n, 0, n);
        free(gram);
        return cost;
    }
    return 0.0;
}

/*
 * pelt_detect
 * -----------
 * 使用 PELT 演算法偵測切點。
 * 參數：
 *   data        : 輸入資料陣列 (double*)
 *   n           : 資料長度
 *   penalty     : penalty 參數
 *   changepoints: 輸出切點陣列 (int*)，大小至少 n+1
 *   n_cp        : 回傳的切點數量（指標）
 *   cost_type   : 0 (L2) 或 1 (RBF)
 *
 * 若 cost_type==1，預先計算整個 Gram 矩陣以避免重複計算（大幅優化效率）。
 */
void pelt_detect(const double *data, int n, double penalty, int *changepoints, int *n_cp, int cost_type) {
    double *F = (double *) malloc((n + 1) * sizeof(double));
    int *last = (int *) malloc((n + 1) * sizeof(int));
    int *R = (int *) malloc((n + 1) * sizeof(int));
    int R_size = 0;
    
    double* gram_all = NULL;
    if (cost_type == 1) {
        double gamma = 1.0;
        gram_all = compute_gram(data, n, gamma);
    }
    
    F[0] = -penalty;
    last[0] = 0;
    R[0] = 0;
    R_size = 1;
    
    for (int t = 1; t <= n; t++) {
        F[t] = DBL_MAX;
        int best_tau = 0;
        for (int i = 0; i < R_size; i++) {
            int tau = R[i];
            double cost;
            if (cost_type == 1) {
                cost = F[tau] + cost_error_segment(gram_all, n, tau, t) + penalty;
            } else {
                cost = F[tau] + compute_cost(data, tau, t, cost_type) + penalty;
            }
            if (cost < F[t]) {
                F[t] = cost;
                best_tau = tau;
            }
        }
        last[t] = best_tau;
        int new_R_size = 0;
        for (int i = 0; i < R_size; i++) {
            int tau = R[i];
            double cost;
            if (cost_type == 1) {
                cost = F[tau] + cost_error_segment(gram_all, n, tau, t);
            } else {
                cost = F[tau] + compute_cost(data, tau, t, cost_type);
            }
            if (cost <= F[t]) {
                R[new_R_size++] = tau;
            }
        }
        R[new_R_size++] = t;
        R_size = new_R_size;
    }
    
    int cp_count = 0;
    int index = n;
    while (index > 0) {
        changepoints[cp_count++] = index;
        index = last[index];
    }
    // 反轉切點順序
    for (int i = 0; i < cp_count / 2; i++) {
        int temp = changepoints[i];
        changepoints[i] = changepoints[cp_count - i - 1];
        changepoints[cp_count - i - 1] = temp;
    }
    *n_cp = cp_count;
    
    free(F);
    free(last);
    free(R);
    if (gram_all != NULL) free(gram_all);
}

#endif // PELT_COST_H
'''

with open("pelt_cost.h", "w+") as f:
    f.write(pelt_cost_h)

# 2. 產生 pelt_interface.pyx 檔案
pelt_interface_pyx = r'''
# distutils: language = c
# cython: boundscheck=False, wraparound=False

import numpy as np
cimport numpy as np
from libc.stdlib cimport malloc, free

# 引入剛剛建立的 header 檔案
cdef extern from "pelt_cost.h":
    double compute_cost(const double *data, int start, int end, int cost_type)
    void pelt_detect(const double *data, int n, double penalty, int *changepoints, int *n_cp, int cost_type)

def detect(np.ndarray[double, ndim=1] data, double penalty, int cost_type):
    """
    使用 PELT 演算法偵測切點。
    
    參數：
        data      : 一維 numpy 陣列 (double)，資料序列
        penalty   : 切點 penalty 參數
        cost_type : cost function 類型 (0: L2, 1: RBF)
        
    回傳：
        切點列表 (Python list of int)
    """
    cdef int n = data.shape[0]
    cdef int* changepoints = <int*> malloc((n + 1) * sizeof(int))
    cdef int n_cp = 0
    pelt_detect(<double*> data.data, n, penalty, changepoints, &n_cp, cost_type)
    cp_list = [changepoints[i] for i in range(n_cp)]
    free(changepoints)
    return cp_list[:-1]
'''

with open("pelt_interface.pyx", "w+") as f:
    f.write(pelt_interface_pyx)

from setuptools import setup
from Cython.Build import cythonize
import numpy as np

setup(
    name = "pelt_cython",
    ext_modules = cythonize("pelt_interface.pyx", compiler_directives={'language_level': "3"}),
    include_dirs = [np.get_include()],
)