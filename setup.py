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
        // 將 produced 放在第一項，注意此處採用偷取引用的方式
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

cdef extern from "consumer_producer.h":
    object cp_run_pair(PyObject* producer, PyObject* prod_args, PyObject* consumer, PyObject* cons_args)

def cp_runner(list producers, list producer_params, list consumers, list consumer_params):
    """
    此函式依序執行每一組 producer 與 consumer 的運算流程：
      1. 呼叫 producer(*producer_param) 得到 produced
      2. 呼叫 consumer(produced, *consumer_param) 得到 result
    返回所有 consumer 運算結果組成的 list。
    
    參數：
      - producers：producer 函數的 list
      - producer_params：對應 producer 的參數 (每個元素預期為 tuple)
      - consumers：consumer 函數的 list
      - consumer_params：對應 consumer 的參數 (每個元素預期為 tuple 或單一物件)
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
    )
]

setup(
    name="consumer_producer",
    ext_modules=cythonize(ext_modules),
    zip_safe=False,
)
