import numpy as np
import pelt_interface  # 編譯後產生的 extension 模組
# 設定 cost function 類型
# 0 -> 使用 L2 cost (平方誤差)
# 1 -> 使用 RBF cost (高斯核)

data = np.random.normal(0, 0.2, size = (250)).tolist() + np.random.normal(3, 0.2, size = (250)).tolist()
data = np.array(data, dtype = np.double)

# 設定 penalty 參數，例如設定為 1.5
penalty = 1.5
cost_type = 0

# 呼叫 pelt_interface 中的 detect 函式
changepoints = pelt_interface.detect(data, penalty, cost_type)

# 顯示偵測到的切點
print("偵測到的切點：", changepoints)



data = np.random.normal(0, 0.2, size = (300)).tolist() + np.random.normal(0, 5, size = (150)).tolist()
data = np.array(data, dtype = np.double)

# 設定 penalty 參數，例如設定為 1.5
penalty = 5
cost_type = 1

# 呼叫 pelt_interface 中的 detect 函式
changepoints = pelt_interface.detect(data, penalty, cost_type)

# 顯示偵測到的切點
print("偵測到的切點：", changepoints)