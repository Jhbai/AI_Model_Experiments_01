#!/usr/bin/env python3
import time
from parallel import parallel_run

# ---------------------------
# Mandelbrot 計算相關函式
# ---------------------------
def mandelbrot(c, max_iter=256):
    """
    計算複數 c 的 Mandelbrot 迭代次數：
      z_{n+1} = z_n^2 + c, 以 z_0 = 0 起始
    若在 max_iter 次內 |z| 超過 2 則返回迭代次數，
    否則返回 max_iter.
    """
    z = 0 + 0j
    for i in range(max_iter):
        z = z*z + c
        if abs(z) > 2.0:
            return i
    return max_iter

def compute_row(row, width, height, re_start, re_end, im_start, im_end, max_iter):
    """
    計算影像中指定 row 的每個像素的迭代次數，
    並回傳一個 list。
    """
    row_data = []
    # 計算此列對應的虛軸座標
    im = im_start + (im_end - im_start) * row / (height - 1)
    for col in range(width):
        # 計算實軸座標
        re = re_start + (re_end - re_start) * col / (width - 1)
        c = complex(re, im)
        row_data.append(mandelbrot(c, max_iter))
    return row_data

# ---------------------------
# Serial 與 Parallel 版本的 Mandelbrot 計算
# ---------------------------
def serial_mandelbrot(width, height, re_start, re_end, im_start, im_end, max_iter):
    """
    依序計算影像中所有列的 Mandelbrot 結果，
    回傳一個二維 list（每個元素為一列的結果）。
    """
    result = []
    for row in range(height):
        result.append(compute_row(row, width, height, re_start, re_end, im_start, im_end, max_iter))
    return result

def parallel_mandelbrot(width, height, re_start, re_end, im_start, im_end, max_iter):
    """
    利用 parallel_run 平行計算影像中每一列的 Mandelbrot 結果，
    每個 thread 負責計算一列，回傳一個二維 list。
    """
    # 為每一列建立一個工作項目：函式均為 compute_row，
    # 參數為 (row, width, height, re_start, re_end, im_start, im_end, max_iter)
    funcs = [compute_row] * height
    args = [(row, width, height, re_start, re_end, im_start, im_end, max_iter) for row in range(height)]
    return parallel_run(funcs, args)

# ---------------------------
# 測試主程式
# ---------------------------
if __name__ == '__main__':
    # 影像參數
    width = 800
    height = 600
    re_start, re_end = -2.0, 1.0
    im_start, im_end = -1.0, 1.0
    max_iter = 256

    print("開始 Serial Mandelbrot 計算 ...")
    start = time.time()
    serial_result = serial_mandelbrot(width, height, re_start, re_end, im_start, im_end, max_iter)
    serial_time = time.time() - start
    print("Serial 計算完成，共耗時 {:.3f} 秒".format(serial_time))

    print("\n開始 Parallel Mandelbrot 計算 ...")
    start = time.time()
    parallel_result = parallel_mandelbrot(width, height, re_start, re_end, im_start, im_end, max_iter)
    parallel_time = time.time() - start
    print("Parallel 計算完成，共耗時 {:.3f} 秒".format(parallel_time))

    print("\nSpeedup: {:.2f}x".format(serial_time / parallel_time if parallel_time > 0 else float('inf')))
