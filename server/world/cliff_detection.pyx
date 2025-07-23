# cliff_detection.pyx
import numpy as np
cimport numpy as np

def detect_cliffs(np.ndarray[np.float32_t, ndim=2] elevation_map,
                  np.ndarray[np.int32_t, ndim=2] biome_map,
                  float threshold=0.01,
                  float tall_threshold=0.03):
    cdef int size = elevation_map.shape[0]
    cdef np.ndarray[np.int32_t, ndim=2] result = np.zeros((size - 2, size - 2), dtype=np.int32)

    cdef int i, j
    cdef float center, n, s, e, w, ne, nw, se, sw
    cdef bint is_mountain

    for i in range(1, size - 1):
        for j in range(1, size - 1):
            center = elevation_map[i, j]
            n = elevation_map[i - 1, j]
            s = elevation_map[i + 1, j]
            e = elevation_map[i, j + 1]
            w = elevation_map[i, j - 1]
            ne = elevation_map[i - 1, j + 1]
            nw = elevation_map[i - 1, j - 1]
            se = elevation_map[i + 1, j + 1]
            sw = elevation_map[i + 1, j - 1]

            is_mountain = biome_map[i, j] == 10  # mountain ID

            if is_mountain:
                if center - s >= threshold and center - e >= threshold and center - se >= threshold:
                    result[i - 1, j - 1] = 12 if center - se >= tall_threshold else 11
                elif center - s >= threshold and center - w >= threshold and center - sw >= threshold:
                    result[i - 1, j - 1] = 14 if center - sw >= tall_threshold else 13
                elif center - n >= threshold and center - e >= threshold and center - ne >= threshold:
                    result[i - 1, j - 1] = 15
                elif center - n >= threshold and center - w >= threshold and center - nw >= threshold:
                    result[i - 1, j - 1] = 16
                elif center - s >= tall_threshold:
                    result[i - 1, j - 1] = 17
                elif center - s >= threshold:
                    result[i - 1, j - 1] = 18
                elif center - n >= threshold:
                    result[i - 1, j - 1] = 19
                elif center - e >= threshold:
                    result[i - 1, j - 1] = 20
                elif center - w >= threshold:
                    result[i - 1, j - 1] = 21

    return result
