from setuptools import setup
from Cython.Build import cythonize
import numpy as np

setup(
    ext_modules=cythonize([
        "world/cliff_detection.pyx",
        "world/chunk_processor.pyx"
    ], compiler_directives={"language_level": "3"}),
    include_dirs=[np.get_include()]
)
