# 이 프로젝트에서 쓰는 SCM 핵심 개념 정리

이 프로젝트(반도체 장비 제조사를 가정한 AI 기반 자재소요계획 시스템)를 이해하는 데 필요한 SCM 개념만 최소한으로 정리했다. 면접에서 이 프로젝트를 설명할 때 아래 용어를 그대로 쓰면 된다.

## 1. BOM (Bill of Materials, 자재명세서)

완제품 하나를 만들기 위해 어떤 하위 부품/조립품이 몇 개씩 필요한지를 나무 구조로 표현한 것. 이 프로젝트에서는 3단 구조를 쓴다.

- Level 0: 완제품 (예: 플라즈마 에처 장비 PE-3000)
- Level 1: 서브시스템 (예: Process Chamber, RF Generator, Gas Delivery System, Robot Transfer Module, Chiller Unit)
- Level 2: 부품/소모성 부품 (예: RF Matching Network, MFC, Turbo Pump, Wafer Sensor, O-ring Kit)

BOM에는 상위 1개당 하위가 몇 개 들어가는지(소요량, quantity per)도 함께 정의된다. 예를 들어 장비 1대에 Gas Delivery System이 2개 들어가고, Gas Delivery System 1개에 MFC가 4개 들어간다면, 장비 1대 = MFC 8개가 필요하다. 이걸 여러 레벨에 걸쳐 곱해서 펼치는 걸 **BOM 전개(BOM explosion)**라고 한다.

## 2. 수요예측 (Demand Forecasting)

MRP는 "완제품을 얼마나 팔 것인가(수요)"를 입력값으로 받아야 시작할 수 있다. 이 프로젝트에서는 과거 월별 출하량 데이터를 시계열 모델에 학습시켜 향후 수요를 예측한다. 여기서 "AI"가 들어가는 지점이다 — 단순 평균이 아니라 추세(trend)와 계절성(seasonality, 반도체 장비는 고객사 CAPEX 사이클과 맞물려 특정 분기에 몰리는 경향이 있다)을 학습해서 예측한다.

## 3. MRP (Material Requirements Planning, 자재소요계획)

수요예측(또는 확정 수주)을 입력으로 받아, BOM을 타고 내려가며 "언제, 무엇을, 얼마나 발주해야 하는지"를 계산하는 로직. 핵심 3단계:

1. **총소요량 계산 (Gross Requirement)**: BOM 전개로 상위 계층 수요를 하위 부품 수요로 환산
2. **넷팅 (Netting)**: 총소요량에서 현재고(on-hand)와 입고예정분(scheduled receipt)을 빼서 순소요량(net requirement) 계산
3. **리드타임 오프셋 (Lead Time Offsetting)**: 순소요량이 필요한 시점에서 부품별 조달 리드타임만큼 앞당겨서 "발주 시점(planned order release)"을 결정

여기에 **로트사이징(lot sizing)** 규칙을 더한다 — Lot-for-Lot(필요한 만큼만 주문)처럼 단순한 방식부터, 최소주문수량(MOQ)을 고려한 방식까지 있는데, 이 프로젝트는 Lot-for-Lot + MOQ 반영 버전을 쓴다.

## 4. 안전재고 (Safety Stock) / 재주문점 (Reorder Point)

수요예측은 항상 틀릴 수 있고 리드타임도 변동하기 때문에, 예측 오차와 리드타임 변동성을 흡수할 완충재고가 필요하다. 이 프로젝트는 수요의 표준편차와 리드타임을 이용한 표준 안전재고 공식(서비스 수준 Z값 반영)을 적용해서, 부품별로 "이 정도는 항상 깔고 있어야 안전하다"는 수량을 계산하고, MRP 넷팅 시 가용재고에서 안전재고만큼은 쓰지 않도록 반영한다.

## 이 개념들이 프로젝트에서 어떻게 이어지는가

```
과거 수요 데이터 → [AI 예측 모델] → 향후 수요 예측
                                        │
완제품 BOM (3단) ──────────[BOM 전개]───┤
                                        ▼
                              부품별 총소요량
                                        │
현재고 + 입고예정 + 안전재고 ──[넷팅]───┤
                                        ▼
                              부품별 순소요량
                                        │
부품별 리드타임 ──────[리드타임 오프셋]──┤
                                        ▼
                    부품별·시점별 발주 계획 (Planned Order Release)
```
