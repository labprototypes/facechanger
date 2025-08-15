from typing import Dict, List

SKU_BY_CODE: Dict[str, int] = {}
SKU_COUNTER = 100
FRAME_COUNTER = 1

FRAMES: Dict[int, dict] = {}           # frame_id -> frame dict
SKU_FRAMES: Dict[int, List[int]] = {}  # sku_id -> [frame_ids]
GENERATIONS: Dict[str, dict] = {}      # gen_id -> meta

def next_sku_id() -> int:
    global SKU_COUNTER
    SKU_COUNTER += 1
    return SKU_COUNTER

def next_frame_id() -> int:
    global FRAME_COUNTER
    FRAME_COUNTER += 1
    return FRAME_COUNTER
