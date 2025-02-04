import numpy as np
import matplotlib.pyplot as plt
from scipy.special import betaln, gammaln

def log_predictive_prob(x, alpha, beta):
    """
    計算 Beta-Bernoulli 模型下，對於觀測值 x 的 log 預測機率。
    當 x = 1 時，預測機率 = alpha / (alpha+beta)；
    當 x = 0 時，預測機率 = beta / (alpha+beta)。
    為了數值穩定性，我們計算對數機率。
    """
    if x == 1:
        return np.log(alpha) - np.log(alpha + beta)
    else:
        return np.log(beta) - np.log(alpha + beta)

def bocpd(data, alpha0=1.0, beta0=1.0, hazard_a0=1.0, hazard_b0=1.0):
    """
    使用 BOCD 方法對 0/1 序列進行變化點檢測，並以自適應方式更新 hazard rate。
    
    參數:
        data: list 或 numpy array，0 與 1 的時間序列資料。
        alpha0, beta0: float，Beta-Bernoulli 模型的先驗參數（可設為非資訊性先驗 1,1)）。
        hazard_a0, hazard_b0: float，hazard rate 先驗 Beta 分布的參數，
                               初始可設為 1,1，代表均勻分布。
    
    回傳:
        R_store: 二維 numpy array，儲存每個時間點各 run-length 的對數後驗機率（log probability）。
        maxes: 一維 numpy array，記錄每個時間點最可能的 run-length（用於參考）。
        h_list: 每個時間點使用的自適應 hazard rate 值。
    """
    T = len(data)
    # 為避免 underflow，使用對數機率
    log_R = -np.inf * np.ones(T+1)  # 當前時間步的 run-length 分布，以對數機率表示
    log_R[0] = 0.0  # 初始時刻 r=0 的機率為 1 (log(1)=0)
    
    # 為每個可能的 run-length維護 Beta 模型參數 (alpha, beta)
    # 我們採用 list 來儲存參數，初始只有 r=0 的成員，參數為 (alpha0, beta0)
    alphas = [alpha0]
    betas = [beta0]
    
    # 儲存每個時間點的 run-length分布（以對數機率表示），用於後續檢視或分析
    R_store = np.zeros((T, T+1)) - np.inf  # 每列代表一個時間點，最多 T+1 個 run-length 狀態
    
    # 儲存每次更新後最可能的 run-length（方便追蹤）
    maxes = np.zeros(T, dtype=int)
    
    # 儲存每個時間點所採用的 hazard rate（自適應更新）
    h_list = []
    # 初始化 hazard rate先驗的 Beta 分布參數
    hazard_a = hazard_a0
    hazard_b = hazard_b0
    
    for t in range(T):
        x = data[t]
        # 根據當前 hazard 先驗計算預期 hazard rate h_t
        h_t = hazard_a / (hazard_a + hazard_b)
        h_list.append(h_t)
        
        # 存放新的對數 run-length 分布，維度 t+2 (因為新 run-length 0 加上原本各狀態延長一單位)
        log_R_new = -np.inf * np.ones(t+2)
        
        # 先計算 run-length 0 的部分：變化點發生
        # 所有上一時刻的狀態均可跳至 r=0，加上 hazard 的貢獻，
        # 並使用初始 Beta 先驗 (alpha0, beta0) 計算預測機率。
        log_sum = -np.inf
        for r in range(t+1):
            # 加上 hazard rate 的對數： log(h_t)
            log_sum = np.logaddexp(log_sum, log_R[r] + np.log(h_t))
        # 加上對數預測機率：以先驗 (alpha0, beta0) 計算
        log_R_new[0] = log_sum + log_predictive_prob(x, alpha0, beta0)
        
        # 對於 r >= 0 的情形：延續上一個 run-length狀態
        for r in range(t+1):
            # 此處延長 run-length (r -> r+1) 表示未發生變化，故乘上 (1 - h_t)
            lp = log_R[r] + np.log(1 - h_t)
            # 使用 Beta-Bernoulli 模型對應 r 狀態下的參數 (alphas[r], betas[r])
            lp += log_predictive_prob(x, alphas[r], betas[r])
            # 更新到新的 run-length r+1
            log_R_new[r+1] = lp
        
        # 正規化新的 run-length分布（以對數方式）
        log_R_new = log_R_new - np.logaddexp.reduce(log_R_new)
        
        # 儲存當前的 run-length分布
        R_store[t, :t+2] = log_R_new.copy()
        
        # 找出最可能的 run-length作為參考
        maxes[t] = np.argmax(log_R_new)
        
        # 更新 Beta 模型參數對應到各個 run-length狀態
        new_alphas = []
        new_betas = []
        # 當 r=0 時：若發生變化點，參數重新初始化
        new_alphas.append(alpha0)
        new_betas.append(beta0)
        # 當 r>=1：延續上一狀態，對應 r-1 的參數更新
        for r in range(1, t+2):
            # 如果 r-1 對應的狀態延長到 r，更新參數：alpha + x, beta + (1-x)
            new_alphas.append(alphas[r-1] + x)
            new_betas.append(betas[r-1] + (1 - x))
        # 因為新的分布長度為 t+2，所以只保留前 t+2 個狀態
        alphas = new_alphas[:t+2]
        betas = new_betas[:t+2]
        
        # 自適應更新 hazard rate 的先驗：根據本次新分布中 r=0 的後驗機率
        # 本次發生變化點的機率 = exp(log_R_new[0])
        p_cp = np.exp(log_R_new[0])
        # 將此機率作為觀測值來更新 hazard 先驗 Beta 分布的參數
        hazard_a += p_cp      # 累加變化點出現的「成功」次數
        hazard_b += (1 - p_cp)  # 累加未發生變化的「失敗」次數
        
        # 將新的分布賦值給 log_R，並為下一時刻補齊維度
        log_R = log_R_new.copy()
    
    return R_store, maxes, h_list

if __name__ == '__main__':
    # 模擬一段包含變化點的 0/1 時間序列資料
    np.random.seed(42)  # 固定隨機種子以方便重現
    T = 500
    change_point = 250  # 設定變化點位置
    p0 = 0.1           # 變化前「1」出現機率
    p1 = 0.4           # 變化後「1」出現機率
    
    data = np.zeros(T, dtype=int)
    for t in range(T):
        if t < change_point:
            data[t] = 1 if np.random.rand() < p0 else 0
        else:
            data[t] = 1 if np.random.rand() < p1 else 0
    
    # 執行 BOCD，初始 Beta 先驗參數 (alpha0, beta0) 設為 (1,1)，hazard 先驗參數也設為 (1,1)
    R_store, max_runlength, h_list = bocpd(data, alpha0=1.0, beta0=1.0, hazard_a0=1.0, hazard_b0=1.0)
    
    # 將 run-length 分布的對數機率轉換成機率（僅觀察最後一個時間點的分布）
    last_R = np.exp(R_store[-1, :np.max(max_runlength)+1])
    
    # 繪製最後一個時間點的 run-length 後驗分布
    plt.figure(figsize=(10,4))
    plt.bar(range(len(last_R)), last_R)
    plt.xlabel("Run-length")
    plt.ylabel("Posterior probability")
    plt.title("the last moment of run-length posterior distribution")
    plt.grid(True)
    plt.savefig("posterior.png")
    
    # 繪製自適應 hazard rate 隨時間變化的趨勢
    plt.figure(figsize=(10,4))
    plt.plot(h_list, label='adaptive hazard rate')
    plt.xlabel("time t")
    plt.ylabel("hazard rate")
    plt.title("the adapative hazard rate wrt time")
    plt.grid(True)
    plt.legend()
    plt.savefig("feature.png")
    
    # 繪製偵測到的變化點指示：通常當最可能的 run-length接近 0 時，表示變化剛剛發生
    plt.figure(figsize=(10,4))
    plt.plot(data, label="observations", marker='o', linestyle='-', markersize=3)
    # 將最可能的 run-length在 0 附近的時間點標記出來
    cp_indices = [t for t in range(len(max_runlength)) if max_runlength[t] < 5]  # 此閥值可根據需求調整
    plt.scatter(cp_indices, data[cp_indices], color='red', label="change point")
    plt.xlabel("time t")
    plt.ylabel("observation")
    plt.title("data and change point")
    plt.legend()
    plt.grid(True)
    plt.savefig("output.png")
