def get_radial_sorted_chunks(center_x, center_y, radius_x, radius_y, margin):
    cx_min = center_x - radius_x - margin
    cx_max = center_x + radius_x + margin
    cy_min = center_y - radius_y - margin
    cy_max = center_y + radius_y + margin

    chunks = []
    for cx in range(cx_min, cx_max + 1):
        for cy in range(cy_min, cy_max + 1):
            dist = ((cx - center_x) ** 2 + (cy - center_y) ** 2) ** 0.5
            chunks.append(((cx, cy), dist))

    chunks.sort(key=lambda x: x[1])  # sort by Euclidean distance
    return [coord for coord, _ in chunks]
