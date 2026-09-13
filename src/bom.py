"""
반도체 장비(플라즈마 에처 PE-3000) 3단 BOM 정의.

Level 0: 완제품
Level 1: 서브시스템 (모듈)
Level 2: 구매/제작 부품 (MRP 대상)

실제 반도체 장비 구조를 단순화해서 참고했다 (RF/Chamber/Gas/Robot/Vacuum 5대 모듈 구성은
플라즈마 에처/CVD 장비의 통상적인 서브시스템 분류를 따른 것).
"""

PRODUCT_ID = "PE-3000"
PRODUCT_NAME = "Plasma Etcher PE-3000"

# (parent_id, parent_name, child_id, child_name, level, qty_per)
# qty_per = 상위 조립품 1개당 필요한 하위 품목 수량
BOM_EDGES = [
    # Level 0 -> Level 1 (서브시스템)
    (PRODUCT_ID, PRODUCT_NAME, "SUB-PCM", "Process Chamber Module", 1, 1),
    (PRODUCT_ID, PRODUCT_NAME, "SUB-RFG", "RF Generator Assembly", 1, 2),
    (PRODUCT_ID, PRODUCT_NAME, "SUB-GDS", "Gas Delivery System", 1, 1),
    (PRODUCT_ID, PRODUCT_NAME, "SUB-WHR", "Wafer Handling Robot", 1, 1),
    (PRODUCT_ID, PRODUCT_NAME, "SUB-CVM", "Chiller & Vacuum Module", 1, 1),

    # Level 1 -> Level 2 : Process Chamber Module
    ("SUB-PCM", "Process Chamber Module", "PRT-ESC", "Ceramic Electrostatic Chuck", 2, 1),
    ("SUB-PCM", "Process Chamber Module", "PRT-LNR", "Quartz Chamber Liner", 2, 1),
    ("SUB-PCM", "Process Chamber Module", "PRT-FRS", "Focus Ring Set", 2, 2),
    ("SUB-PCM", "Process Chamber Module", "PRT-VPW", "Viewport Window", 2, 2),

    # Level 1 -> Level 2 : RF Generator Assembly (장비당 2개 조립되므로 배수로 반영됨)
    ("SUB-RFG", "RF Generator Assembly", "PRT-RFM", "RF Matching Network", 2, 1),
    ("SUB-RFG", "RF Generator Assembly", "PRT-RFA", "RF Power Amplifier Module", 2, 1),
    ("SUB-RFG", "RF Generator Assembly", "PRT-RFS", "RF Sensor/Coupler", 2, 2),

    # Level 1 -> Level 2 : Gas Delivery System
    ("SUB-GDS", "Gas Delivery System", "PRT-MFC", "Mass Flow Controller", 2, 6),
    ("SUB-GDS", "Gas Delivery System", "PRT-GVM", "Gas Valve Manifold", 2, 2),
    ("SUB-GDS", "Gas Delivery System", "PRT-PTR", "Pressure Transducer", 2, 2),

    # Level 1 -> Level 2 : Wafer Handling Robot
    ("SUB-WHR", "Wafer Handling Robot", "PRT-SVM", "Servo Motor Actuator", 2, 3),
    ("SUB-WHR", "Wafer Handling Robot", "PRT-EEF", "Robot Arm End Effector", 2, 2),
    ("SUB-WHR", "Wafer Handling Robot", "PRT-WPS", "Wafer Position Sensor", 2, 4),

    # Level 1 -> Level 2 : Chiller & Vacuum Module
    ("SUB-CVM", "Chiller & Vacuum Module", "PRT-TMP", "Turbo Molecular Pump", 2, 1),
    ("SUB-CVM", "Chiller & Vacuum Module", "PRT-DVP", "Dry Vacuum Pump", 2, 1),
    ("SUB-CVM", "Chiller & Vacuum Module", "PRT-CCU", "Chiller Compressor Unit", 2, 1),
    ("SUB-CVM", "Chiller & Vacuum Module", "PRT-CFS", "Coolant Flow Sensor", 2, 2),
]


def bom_dataframe():
    import pandas as pd
    return pd.DataFrame(
        BOM_EDGES,
        columns=["parent_id", "parent_name", "child_id", "child_name", "level", "qty_per"],
    )


def explode_bom_to_top(top_units: float) -> dict:
    """완제품 top_units 대수를 만들기 위해 필요한 최종(Level 2) 부품별 총소요 수량을 반환.

    다단계 BOM을 재귀적으로 곱해서(qty_per 누적) Level 2까지 전개한다.
    """
    df = bom_dataframe()
    # child -> (level, list of (parent_id, qty_per))
    children_of = {}
    for _, row in df.iterrows():
        children_of.setdefault(row.parent_id, []).append((row.child_id, row.qty_per, row.level, row.child_name))

    totals = {}

    def walk(node_id, multiplier):
        for child_id, qty_per, level, child_name in children_of.get(node_id, []):
            new_mult = multiplier * qty_per
            if level == 2:
                totals[child_id] = totals.get(child_id, 0) + new_mult
            else:
                walk(child_id, new_mult)

    walk(PRODUCT_ID, top_units)
    return totals


if __name__ == "__main__":
    totals = explode_bom_to_top(1)
    for part_id, qty in sorted(totals.items()):
        print(f"{part_id}: {qty}")
