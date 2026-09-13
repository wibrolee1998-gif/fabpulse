"""
Level 2 부품 마스터 데이터 (합성 데이터).

unit_cost: 단가 (USD)
lead_time_weeks: 발주 후 입고까지 걸리는 조달 리드타임 (주)
supplier: 공급업체명 (합성)
moq: 최소발주수량 (Minimum Order Quantity)
on_hand: 현재 가용 재고
demand_cv: 이 부품 수요의 변동계수(coefficient of variation) 가정치 -> 안전재고 계산에 사용
"""
import pandas as pd

PART_MASTER = [
    # part_id, part_name,                     unit_cost, lead_time_weeks, supplier,              moq, on_hand, demand_cv
    ("PRT-ESC", "Ceramic Electrostatic Chuck",     8200,  10, "CeramTech Korea",        2,  36, 0.20),
    ("PRT-LNR", "Quartz Chamber Liner",            3100,   6, "SiQuartz Industries",    4,  32, 0.18),
    ("PRT-FRS", "Focus Ring Set",                    950,   4, "SiQuartz Industries",   10,  70, 0.35),
    ("PRT-VPW", "Viewport Window",                   410,   3, "OptiGlass Co.",         10,  56, 0.15),
    ("PRT-RFM", "RF Matching Network",              6400,   8, "RF Dynamics",            2,  70, 0.22),
    # RFA: 리드타임 12주로 가장 길고 단가도 최고가($11,200)라 재고를 보수적으로만 들고 있는 상태
    # -> 이번 MRP 결과에서 '즉시 발주 필요' 최우선 리스크 부품으로 식별되도록 의도적으로 설계
    ("PRT-RFA", "RF Power Amplifier Module",       11200,  12, "RF Dynamics",            2,  30, 0.25),
    ("PRT-RFS", "RF Sensor/Coupler",                 780,   5, "SensorTek",              5, 122, 0.20),
    ("PRT-MFC", "Mass Flow Controller",             2650,   7, "FlowMaster Inc.",        6, 190, 0.18),
    ("PRT-GVM", "Gas Valve Manifold",               1450,   6, "FlowMaster Inc.",        4,  64, 0.20),
    ("PRT-PTR", "Pressure Transducer",               520,   4, "SensorTek",              8,  58, 0.16),
    ("PRT-SVM", "Servo Motor Actuator",             1850,   6, "PrecisionMotion",        6,  96, 0.22),
    ("PRT-EEF", "Robot Arm End Effector",           2200,   5, "PrecisionMotion",        4,  66, 0.24),
    ("PRT-WPS", "Wafer Position Sensor",             340,   3, "SensorTek",             10, 114, 0.19),
    # TMP: 리드타임이 전체 부품 중 가장 긴 14주 -> 소폭의 수요 증가에도 즉시 발주 리스크로 잡히도록 설계
    ("PRT-TMP", "Turbo Molecular Pump",             9800,  14, "VacuTech Global",        2,  20, 0.28),
    ("PRT-DVP", "Dry Vacuum Pump",                  6100,  10, "VacuTech Global",        2,  38, 0.24),
    ("PRT-CCU", "Chiller Compressor Unit",          4300,   9, "ThermoChill Systems",    2,  35, 0.20),
    ("PRT-CFS", "Coolant Flow Sensor",                290,   3, "ThermoChill Systems",   10,  58, 0.17),
]

COLUMNS = [
    "part_id", "part_name", "unit_cost", "lead_time_weeks",
    "supplier", "moq", "on_hand", "demand_cv",
]


def part_master_df() -> pd.DataFrame:
    return pd.DataFrame(PART_MASTER, columns=COLUMNS)


if __name__ == "__main__":
    df = part_master_df()
    print(df.to_string(index=False))
