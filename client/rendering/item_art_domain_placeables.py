"""Item art registry for placeable items and stations."""


def get_item_fns(art):
    return {
        200: art._crafting_table_item,
        201: art._furnace_item,
        202: lambda sc, x, y, s: art._alloy_forge_item(sc, x, y, s),
        203: lambda sc, x, y, s: art._chest_item(sc, x, y, s),
        204: lambda sc, x, y, s: art._part_maker_item(sc, x, y, s),
        205: lambda sc, x, y, s: art._part_combiner_item(sc, x, y, s),
        206: lambda sc, x, y, s: art._embedder_item(sc, x, y, s),
        207: art._campfire_item,
        214: art._torch_item,
        215: art._lantern_item,
        220: art._bed_item,
        250: art._wood_wall_item,
        251: art._stone_wall_item,
        252: art._door_item,
        253: art._stone_brick_wall_item,
        254: art._stone_brick_floor_item,
    }
