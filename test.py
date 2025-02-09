# test_consumer_producer.py
import consumer_producer as consumer_producer

# 定義 producer 函式：
def producer1(a, b):
    """
    此 producer 函式接受兩個數字，並回傳其和。
    """
    print("producer1 執行中： a =", a, ", b =", b)
    return a + b

def producer2(x, y):
    """
    此 producer 函式接受兩個數字，並回傳其乘積。
    """
    print("producer2 執行中： x =", x, ", y =", y)
    return x * y

# 定義 consumer 函式：
def consumer1(prod_output, increment):
    """
    此 consumer 函式接受 producer 的輸出與一個增量值，並回傳兩者相加的結果。
    """
    print("consumer1 執行中： prod_output =", prod_output, ", increment =", increment)
    return prod_output + increment

def consumer2(prod_output, factor):
    """
    此 consumer 函式接受 producer 的輸出與一個乘數，並回傳兩者相乘的結果。
    """
    print("consumer2 執行中： prod_output =", prod_output, ", factor =", factor)
    return prod_output * factor

if __name__ == '__main__':
    # 建立 producer 與 consumer 的清單
    producers = [producer1, producer2]
    # 每個 producer 的參數必須為 tuple (對應到 cp_run_pair 中的呼叫方式)
    producer_params = [
        (10, 5),   # 傳給 producer1 的參數：10 與 5，預期輸出 15
        (3, 7)     # 傳給 producer2 的參數：3 與 7，預期輸出 21
    ]
    
    consumers = [consumer1, consumer2]
    # 每個 consumer 的參數若為 tuple，會自動組合成 (producer 輸出, 其他參數)
    consumer_params = [
        (2,),      # 傳給 consumer1 的參數：將 producer1 的輸出 15 組合成 (15, 2)，預期回傳 17
        (4,)       # 傳給 consumer2 的參數：將 producer2 的輸出 21 組合成 (21, 4)，預期回傳 84
    ]
    
    # 呼叫 consumer_producer.cp_runner 進行整體運算
    results = consumer_producer.cp_runner(producers, producer_params, consumers, consumer_params)
    
    # 印出最終結果
    print("最終測試結果：", results)
