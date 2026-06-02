def get_limited_color_transforms(input_grid, output_grid):
    input_colors = sorted(set(np.unique(input_grid)) - {0})
    output_colors = sorted(set(np.unique(output_grid)) - {0})

    if not input_colors or not output_colors:
        return []

    transforms = []

    # Add recolor transformations
    for i in input_colors:
        for j in output_colors:
            if i != j:
                transforms.append(
                    (f"recolor_{i}_{j}", lambda g, f, i=i, j=j: self.recolor_pair(g, f, i, j))
                )

    # Add filter transforms only for colors that are removed
    removed_colors = set(input_colors) - set(output_colors)
    for c in removed_colors:
        transforms.append(
            (f"filter_out_{c}", lambda g, f, c=c: self.filter_out_color(g, f, c))
        )

    return transforms
