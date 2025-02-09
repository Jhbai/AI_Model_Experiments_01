from setuptools import setup, Extension
from Cython.Build import cythonize
import os

# ----------------------------
# 1. 產生 consumer_producer.h 檔案
# ----------------------------
header_code = r'''\
#ifndef CONSUMER_PRODUCER_H
#define CONSUMER_PRODUCER_H

#include <Python.h>
#include <pthread.h>

/*
  cp_run_pair：針對一組 producer 與 consumer 的運算流程
  輸入：
    - producer：一個 Python 函數，其參數放在 prod_args 中 (必須為 tuple)
    - prod_args：傳遞給 producer 的參數 tuple
    - consumer：一個 Python 函數，其第一個引數為 producer 的輸出，後續參數放在 cons_args 中
    - cons_args：傳遞給 consumer 的參數 (可為 tuple 或單一物件)
  回傳：
    - consumer 運算的結果 (PyObject*)，錯誤則傳回 NULL
*/
static inline PyObject* cp_run_pair(PyObject* producer, PyObject* prod_args, PyObject* consumer, PyObject* cons_args) {
    // 呼叫 producer 函數，傳入參數 tuple
    PyObject* produced = PyObject_Call(producer, prod_args, NULL);
    if (produced == NULL) {
        return NULL;
    }

    PyObject* new_args = NULL;
    // 如果 cons_args 為 tuple，則建立一個新的 tuple，其第一項為 produced，其後依序為 cons_args 裡的元素
    if (PyTuple_Check(cons_args)) {
        Py_ssize_t len = PyTuple_Size(cons_args);
        new_args = PyTuple_New(len + 1);
        if (new_args == NULL) {
            Py_DECREF(produced);
            return NULL;
        }
        // 將 produced 放在第一項
        PyTuple_SET_ITEM(new_args, 0, produced);
        for (Py_ssize_t i = 0; i < len; i++) {
            PyObject* item = PyTuple_GET_ITEM(cons_args, i);
            Py_INCREF(item);
            PyTuple_SET_ITEM(new_args, i + 1, item);
        }
    } else {
        // 若 cons_args 不是 tuple，則組成 (produced, cons_args) 兩項的 tuple
        new_args = PyTuple_New(2);
        if (new_args == NULL) {
            Py_DECREF(produced);
            return NULL;
        }
        PyTuple_SET_ITEM(new_args, 0, produced);
        Py_INCREF(cons_args);
        PyTuple_SET_ITEM(new_args, 1, cons_args);
    }
    // 呼叫 consumer 函數
    PyObject* consumed = PyObject_Call(consumer, new_args, NULL);
    Py_DECREF(new_args);
    return consumed;
}

/* ===================== pthread 平行處理部分 ===================== */

/* 定義傳遞給執行緒的參數結構 */
typedef struct {
    PyObject* producer;
    PyObject* prod_args;
    PyObject* consumer;
    PyObject* cons_args;
    PyObject* result;  // consumer 的運算結果
} cp_pair_args;

/* 執行緒函式，呼叫 cp_run_pair 並儲存結果 */
static void* cp_run_pair_thread(void* arg) {
    cp_pair_args* pair = (cp_pair_args*) arg;
    /* 因為在新執行緒中呼叫 Python API，需要先取得 GIL */
    PyGILState_STATE gstate = PyGILState_Ensure();
    pair->result = cp_run_pair(pair->producer, pair->prod_args, pair->consumer, pair->cons_args);
    PyGILState_Release(gstate);
    return NULL;
}

/*
  cp_run_pairs_parallel：使用 pthread 並行處理多組 producer-consumer 配對
  輸入：
    - producers: Python list，每個元素為 producer 函數
    - producer_params: Python list，每個元素為 producer 的參數 (tuple)
    - consumers: Python list，每個元素為 consumer 函數
    - consumer_params: Python list，每個元素為 consumer 的參數 (tuple 或單一物件)
  回傳：
    - Python list，包含每一組 consumer 運算結果
*/
static PyObject* cp_run_pairs_parallel(PyObject* producers, PyObject* producer_params,
                                        PyObject* consumers, PyObject* consumer_params) {
    Py_ssize_t n = PyList_Size(producers);
    if (PyList_Size(producer_params) != n || PyList_Size(consumers) != n || PyList_Size(consumer_params) != n) {
        PyErr_SetString(PyExc_ValueError, "所有輸入的 list 長度必須一致");
        return NULL;
    }
    cp_pair_args* args_array = (cp_pair_args*) malloc(n * sizeof(cp_pair_args));
    if (args_array == NULL) {
        PyErr_NoMemory();
        return NULL;
    }
    pthread_t* threads = (pthread_t*) malloc(n * sizeof(pthread_t));
    if (threads == NULL) {
        free(args_array);
        PyErr_NoMemory();
        return NULL;
    }
    for (Py_ssize_t i = 0; i < n; i++) {
        args_array[i].producer = PyList_GetItem(producers, i);
        args_array[i].prod_args = PyList_GetItem(producer_params, i);
        args_array[i].consumer = PyList_GetItem(consumers, i);
        args_array[i].cons_args = PyList_GetItem(consumer_params, i);
        args_array[i].result = NULL;
        /* 增加引用計數，因為這些物件將在執行緒中被使用 */
        Py_INCREF(args_array[i].producer);
        Py_INCREF(args_array[i].prod_args);
        Py_INCREF(args_array[i].consumer);
        Py_INCREF(args_array[i].cons_args);
    }
    /* 建立執行緒 */
    for (Py_ssize_t i = 0; i < n; i++) {
        int err = pthread_create(&threads[i], NULL, cp_run_pair_thread, (void*) &args_array[i]);
        if (err != 0) {
            for (Py_ssize_t j = 0; j < i; j++) {
                pthread_join(threads[j], NULL);
            }
            for (Py_ssize_t j = 0; j < n; j++) {
                Py_DECREF(args_array[j].producer);
                Py_DECREF(args_array[j].prod_args);
                Py_DECREF(args_array[j].consumer);
                Py_DECREF(args_array[j].cons_args);
            }
            free(args_array);
            free(threads);
            PyErr_SetString(PyExc_RuntimeError, "無法建立執行緒");
            return NULL;
        }
    }
    /* 等待所有執行緒結束，並釋放 GIL 讓 worker 執行緒能正常取得 GIL */
    Py_BEGIN_ALLOW_THREADS;
    for (Py_ssize_t i = 0; i < n; i++) {
        pthread_join(threads[i], NULL);
    }
    Py_END_ALLOW_THREADS;
    /* 建立結果的 Python list */
    PyObject* results_list = PyList_New(n);
    if (results_list == NULL) {
        for (Py_ssize_t i = 0; i < n; i++) {
            Py_DECREF(args_array[i].producer);
            Py_DECREF(args_array[i].prod_args);
            Py_DECREF(args_array[i].consumer);
            Py_DECREF(args_array[i].cons_args);
        }
        free(args_array);
        free(threads);
        return NULL;
    }
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject* res = args_array[i].result;
        if (res == NULL) {
            res = Py_None;
            Py_INCREF(Py_None);
        }
        PyList_SET_ITEM(results_list, i, res);
        Py_DECREF(args_array[i].producer);
        Py_DECREF(args_array[i].prod_args);
        Py_DECREF(args_array[i].consumer);
        Py_DECREF(args_array[i].cons_args);
    }
    free(args_array);
    free(threads);
    return results_list;
}

#endif // CONSUMER_PRODUCER_H
'''

# 利用 with open 寫入 consumer_producer.h
with open("consumer_producer.h", "w+", encoding="utf-8") as f:
    f.write(header_code)

# ----------------------------
# 2. 產生 consumer_producer.pyx 檔案
# ----------------------------
pyx_code = r'''\
from cpython.object cimport PyObject

# 引用 C header 檔
cdef extern from "consumer_producer.h":
    object cp_run_pair(PyObject* producer, PyObject* prod_args, PyObject* consumer, PyObject* cons_args)
    PyObject* cp_run_pairs_parallel(PyObject* producers, PyObject* producer_params, PyObject* consumers, PyObject* consumer_params)

def cp_runner(list producers, list producer_params, list consumers, list consumer_params):
    """
    此函式依序執行每一組 producer 與 consumer 的運算流程（序列化處理）：
      1. 呼叫 producer(*producer_param) 得到 produced
      2. 呼叫 consumer(produced, *consumer_param) 得到 result
    返回所有 consumer 運算結果組成的 list。
    """
    cdef Py_ssize_t n = len(producers)
    if len(producer_params) != n or len(consumers) != n or len(consumer_params) != n:
        raise ValueError("所有輸入的 list 長度必須一致")
    cdef list outputs = []
    cdef Py_ssize_t i
    cdef object prod, prod_param, cons, cons_param, result
    for i in range(n):
        prod = producers[i]
        prod_param = producer_params[i]
        cons = consumers[i]
        cons_param = consumer_params[i]
        result = cp_run_pair(<PyObject*>prod, <PyObject*>prod_param, <PyObject*>cons, <PyObject*>cons_param)
        if result is None:
            raise RuntimeError("運算中發生錯誤")
        outputs.append(result)
    return outputs

def cp_runner_parallel(list producers, list producer_params, list consumers, list consumer_params):
    """
    此函式使用 pthread 並行執行每一組 producer 與 consumer 的運算流程，
    返回所有 consumer 運算結果組成的 list。
    """
    return <object>cp_run_pairs_parallel(<PyObject*>producers,
                                           <PyObject*>producer_params,
                                           <PyObject*>consumers,
                                           <PyObject*>consumer_params)
'''

# 利用 with open 寫入 consumer_producer.pyx
with open("consumer_producer.pyx", "w+", encoding="utf-8") as f:
    f.write(pyx_code)

# ----------------------------
# 3. 使用 cythonize 設定 Extension 模組
# ----------------------------
ext_modules = [
    Extension(
        name="consumer_producer",
        sources=["consumer_producer.pyx"],
        language="c",
        libraries=["pthread"],  # 連結 pthread 函式庫
    )
]

setup(
    name="consumer_producer",
    ext_modules=cythonize(ext_modules),
    zip_safe=False,
)
