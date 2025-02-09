import requests
import json
import datetime
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, Any, List, Tuple

def fix_missing_data(records: List[Dict[str, Any]], start_str: str, end_str: str) -> List[Dict[str, Any]]:
    """
    檢查並修正資料：  
      - 對於同一分鐘出現多筆資料，只取最後一筆  
      - 若缺少某分鐘的資料，則利用最近的前一筆資料來補值  
    參數:
      records: 原始查詢資料 (每筆記錄需有 "datetime" 欄位，格式為 "%Y-%m-%d %H:%M:%S")
      start_str: 預期起始時間 (完整字串，例如 "2025-02-06 00:00:00")
      end_str: 預期結束時間 (完整字串，例如 "2025-02-07 00:00:00")
    回傳:
      經過補值與重複資料過濾後的資料列表，資料點數固定
    """
    try:
        start_dt = datetime.datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
        end_dt = datetime.datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print("日期格式錯誤，無法進行資料補值：", e)
        return records

    # 計算預期資料點數：每分鐘一筆
    expected_count = int((end_dt - start_dt).total_seconds() // 60)
    # 用字典以分鐘為 key 儲存記錄，遇到重複則覆蓋（最後一筆保留）
    minute_dict: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        try:
            rec_dt = datetime.datetime.strptime(rec["datetime"], "%Y-%m-%d %H:%M:%S")
        except Exception as e:
            print("資料中 datetime 格式錯誤：", rec.get("datetime"), e)
            continue
        minute_key = rec_dt.strftime("%Y-%m-%d %H:%M")  # 以分鐘為單位
        minute_dict[minute_key] = rec  # 後遇到的會覆蓋先前的

    fixed_data = []
    previous_record: Optional[Dict[str, Any]] = None
    current = start_dt
    for _ in range(expected_count):
        key = current.strftime("%Y-%m-%d %H:%M")
        if key in minute_dict:
            record = minute_dict[key]
            # 為確保時間欄位與預期一致，更新時間欄位
            record = record.copy()
            record["datetime"] = current.strftime("%Y-%m-%d %H:%M:%S")
            previous_record = record
        else:
            # 若缺少該分鐘的資料，使用最近的前一筆
            if previous_record is not None:
                # 複製前一筆並更新時間欄位
                record = previous_record.copy()
                record["datetime"] = current.strftime("%Y-%m-%d %H:%M:%S")
            else:
                # 若無前一筆，則建立一筆預設的空資料，可依需求修改預設值
                record = {"name": None, "value": None, "datetime": current.strftime("%Y-%m-%d %H:%M:%S")}
        fixed_data.append(record)
        current += datetime.timedelta(minutes=1)
    return fixed_data

def query_api(api_url: str, payload: Dict[str, Any], timeout: int = 30) -> Optional[List[Dict[str, Any]]]:
    """
    發送單次 POST 請求查詢 API，並回傳 JSON 格式的資料列表。
    若查詢失敗則回傳 None。  
    加入資料完整性檢查：
      - 查詢後，檢查資料是否完整（例如預期有 1440 筆資料），
        若不足則依照每分鐘一筆的要求進行修正：
          * 重複時間點取最後一筆
          * 缺漏的以最近前一筆補上
    """
    
    try:
        response = requests.post(api_url, json=payload, timeout=timeout)
        response.raise_for_status()  # 檢查 HTTP 狀態碼是否正常
        data = response.json()

        # 檢查資料格式是否正確 (假設回傳的是列表，每筆資料包含 name、value、datetime)
        if isinstance(data, list):
            for item in data:
                if not all(key in item for key in ["name", "value", "datetime"]):
                    raise ValueError(f"回傳資料格式不完整：{item}")
        elif isinstance(data, dict):
            # 若 API 回傳單一字典，則包裝成列表
            if not all(key in data for key in ["name", "value", "datetime"]):
                raise ValueError(f"回傳資料格式不完整：{data}")
            data = [data]
        else:
            raise ValueError("未知的回傳資料格式")
        
        # 檢查是否需要進行資料完整性修正
        # 假設 payload 的 start_date 與 end_date 為完整時間字串 "%Y-%m-%d %H:%M:%S"
        try:
            start_dt = datetime.datetime.strptime(payload["start_date"], "%Y-%m-%d %H:%M:%S")
            end_dt = datetime.datetime.strptime(payload["end_date"], "%Y-%m-%d %H:%M:%S")
            expected_count = int((end_dt - start_dt).total_seconds() // 60)
        except Exception as e:
            print("無法解析 payload 中的日期格式，跳過資料補正：", e)
            expected_count = None

        if expected_count is not None and len(data) != expected_count:
            print(f"資料點數不符，預期 {expected_count} 筆，實際 {len(data)} 筆，進行資料修正")
            data = fix_missing_data(data, payload["start_date"], payload["end_date"])
        

        return data

    except Exception as e:
        # 將例外往上拋出，方便後續統一處理
        raise e

def segmented_query(api_url: str, payload: Dict[str, Any], segment_days: int, timeout: int) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
    """
    執行單一區段查詢，並回傳區間字串與查詢結果（或 None）。
    此函式可用於平行查詢時作為目標函式。
    """
    try:
        current_start = payload["start_date"]
        current_end = payload["end_date"]
        print(f"開始查詢區間：{current_start} ~ {current_end}")
        data = query_api(api_url, payload, timeout)
        return (f"{current_start} ~ {current_end}", data)
    except Exception as e:
        print(f"查詢區間 {payload['start_date']} ~ {payload['end_date']} 時發生例外：{e}")
        return (f"{payload['start_date']} ~ {payload['end_date']}", None)

def parallel_segmented_query(api_url: str, payload: Dict[str, Any], segment_days: int = 1, timeout: int = 30, max_workers: int = 5) -> List[Dict[str, Any]]:
    """
    利用多執行緒對整個長時間區間進行分段查詢，並合併所有成功查詢的結果。  
    同時會記錄各區段是否有例外發生，方便追蹤錯誤。
    """
    aggregated_results = []
    error_segments = []  # 用來記錄查詢失敗的區間

    # 解析 payload 中的日期，這裡假設 payload["start_date"] 與 payload["end_date"] 為完整時間字串
    try:
        start_dt = datetime.datetime.strptime(payload["start_date"], "%Y-%m-%d %H:%M:%S")
        end_dt = datetime.datetime.strptime(payload["end_date"], "%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print("日期格式錯誤或缺少必要參數：", e)
        return aggregated_results

    # 建立所有分段的 payload 清單
    tasks_payloads = []
    current_start = start_dt
    while current_start < end_dt:
        current_end = current_start + datetime.timedelta(days=segment_days)
        if current_end > end_dt:
            current_end = end_dt

        segmented_payload = payload.copy()
        segmented_payload["start_date"] = current_start.strftime("%Y-%m-%d %H:%M:%S")
        segmented_payload["end_date"] = current_end.strftime("%Y-%m-%d %H:%M:%S")
        tasks_payloads.append(segmented_payload)

        current_start = current_end

    # 使用 ThreadPoolExecutor 來平行執行各段查詢
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_segment = {
            executor.submit(segmented_query, api_url, seg_payload, segment_days, timeout): seg_payload
            for seg_payload in tasks_payloads
        }

        for future in as_completed(future_to_segment):
            segment_info, result = future.result()
            if result is None:
                print(f"區間 {segment_info} 查詢失敗。")
                error_segments.append(segment_info)
            else:
                print(f"區間 {segment_info} 查詢成功，共 {len(result)} 筆資料。")
                aggregated_results.extend(result)
    
    if error_segments:
        print("以下區段查詢失敗：", ", ".join(error_segments))
    
    return aggregated_results

# 測試程式碼
if __name__ == "__main__":
    api_url = "https://api.example.com/data"
    # 此處的 payload 要求 start_date 與 end_date 為完整的時間字串，
    # 例如查詢一天的資料，從 2025-02-06 00:00:00 到 2025-02-07 00:00:00（預期有 1440 筆資料）
    payload = {
        "query": "some_query",
        "start_date": "2025-02-06 00:00:00",
        "end_date": "2025-02-07 00:00:00"
    }
    
    results = parallel_segmented_query(api_url, payload, segment_days=1, timeout=60, max_workers=4)
    
    print(f"\n最終合併結果筆數：{len(results)}")
