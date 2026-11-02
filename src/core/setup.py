import os
from setuptools import setup
from pybind11.setup_helpers import Pybind11Extension, build_ext

# Get directory of setup.py to resolve source paths correctly
script_dir = os.path.dirname(os.path.abspath(__file__))
sources = [os.path.join(script_dir, "analytics.cpp")]

ext_modules = [
    Pybind11Extension(
        "vct_core",
        sources,
        cxx_std=17,
    ),
]

setup(
    name="vct_core_package",
    version="0.1.0",
    author="VCT Project",
    description="High-performance analytics core for VCT match prediction, powered by C++ and Pybind11.",
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext},
    zip_safe=False,
    python_requires=">=3.9",
)