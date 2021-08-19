cmake_minimum_required(VERSION 2.8.12)
project(btfs)

add_subdirectory(pybind11)
pybind11_add_module(btfs btfs.cpp)
