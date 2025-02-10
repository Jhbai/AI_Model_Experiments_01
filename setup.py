from setuptools import setup, Extension
from Cython.Build import cythonize
import os

# -------------------------------
# Step 1. 產生 C header 檔案 mythreads.h
# -------------------------------
with open("mythreads.h", "w+") as f:
    f.write(r'''
#ifndef MYTHREADS_H
#define MYTHREADS_H

#include <Python.h>
#include <pthread.h>

// 定義每個 thread 的資料
typedef struct {
    PyObject* func;   // 要呼叫的 Python function
    PyObject* arg;    // 傳給 function 的參數 (必須是 tuple 或單一物件，視 function 定義而定)
    PyObject* result; // 存放 function 呼叫的結果
} ThreadData;

// 每個 thread 執行的 worker function
// 注意：在呼叫 Python function 前必須取得 GIL
static void* thread_worker(void* arg) {
    ThreadData* data = (ThreadData*) arg;
    // 取得 GIL
    PyGILState_STATE gstate = PyGILState_Ensure();
    // 呼叫 Python function；使用 data->arg 作為參數
    data->result = PyObject_CallObject(data->func, data->arg);
    // 釋放 GIL
    PyGILState_Release(gstate);
    return NULL;
}

#endif /* MYTHREADS_H */
''')

# -------------------------------
# Step 2. 產生 Cython 檔案 parallel.pyx
# -------------------------------
with open("parallel.pyx", "w+") as f:
    f.write(r'''
# distutils: language = c
# cython: language_level=3

from cpython.object cimport PyObject
from cpython.ref cimport Py_INCREF, Py_DECREF
from libc.stdlib cimport malloc, free

# 載入 pthread 相關的函式與型別宣告，並標示為 nogil safe
cdef extern from "pthread.h":
    ctypedef unsigned long pthread_t
    int pthread_create(pthread_t *thread, void *attr, void* (*start_routine)(void*), void *arg) nogil
    int pthread_join(pthread_t thread, void **retval) nogil

# 從我們自訂的 header 載入 ThreadData 結構與 thread_worker 函式
cdef extern from "mythreads.h":
    ctypedef struct ThreadData:
         PyObject* func
         PyObject* arg
         PyObject* result
    void* thread_worker(void* arg)

def parallel_run(list funcs, list args):
    """
    同時平行呼叫 funcs 與 args 中各對應的項目，
    每個函式呼叫的結果會回傳在一個 list 中。

    - funcs: Python function 物件的 list
    - args: 傳給每個函式的參數（若有多個參數請以 tuple 傳入）
    """
    cdef int n = len(funcs)
    if n != len(args):
         raise ValueError("functions 與 parameters 的數量必須相同")
    
    # 申請 ThreadData 陣列與 pthread_t 陣列
    cdef ThreadData* data_array = <ThreadData*> malloc(n * sizeof(ThreadData))
    cdef pthread_t* threads = <pthread_t*> malloc(n * sizeof(pthread_t))
    if data_array == NULL or threads == NULL:
         raise MemoryError("無法配置記憶體")
    
    cdef int i, err

    # 建立每個工作項目的資料並啟動 thread
    for i in range(n):
         data_array[i].func = <PyObject*>funcs[i]
         data_array[i].arg = <PyObject*>args[i]
         Py_INCREF(<object>data_array[i].func)
         Py_INCREF(<object>data_array[i].arg)
         data_array[i].result = NULL
         err = pthread_create(&threads[i], NULL, thread_worker, <void*> &data_array[i])
         if err != 0:
             free(data_array)
             free(threads)
             raise RuntimeError("建立 thread 時發生錯誤")
    
    # 在等待 thread 完成時釋放 GIL，
    # 這樣 worker threads 才能在等待期間順利取得 GIL
    with nogil:
        for i from 0 <= i < n:
             pthread_join(threads[i], NULL)
    
    # 收集結果
    cdef list result_list = [None] * n
    for i in range(n):
         result_list[i] = <object>data_array[i].result
         Py_DECREF(<object>data_array[i].func)
         Py_DECREF(<object>data_array[i].arg)
    
    free(data_array)
    free(threads)
    return result_list
''')

# -------------------------------
# Step 3. 設定 Extension 模組 (需要連結 pthread)
# -------------------------------
extensions = [
    Extension(
        "parallel",              # 模組名稱
        sources=["parallel.pyx"],# Cython 檔案來源
        libraries=["pthread"],   # Linux 平台需要連結 pthread 套件
    )
]

setup(
    name="parallel",
    ext_modules=cythonize(extensions),
)
