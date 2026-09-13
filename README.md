# FabPulse — 반도체 장비 AI 수요예측 & MRP 시뮬레이터

기계공학 전공자가 SCM/Material Planning 직무로 이직하면서, "SCM을 몰라도 만들면서 배운다"는
목표로 만든 포트폴리오 프로젝트입니다. 반도체 장비(플라즈마 에처) 제조사를 가정해서,
① AI로 완제품 수요를 예측하고 ② BOM을 전개해 ③ MRP(자재소요계획) 로직으로 부품별
발주 시점·수량·금액을 자동 산출하는 파이프라인 + 대시보드입니다.

**대시보드 데모:** `dashboard/index.html` (브라우저로 바로 열람 가능, 외부 리소스 없이 동작)

> **업데이트:** 설계변경(ECN) 대응 시뮬레이터를 추가했습니다 — 부품이 단종(EOL)되거나 규제로 소재가
> 바뀌는 상황을 가정해, PLM의 Where-Used 조회 → 대체품 탐색(Drop-in A/B/C 등급) → MRP 재계산까지
> 이어지는 실무 워크플로우를 그대로 구현했습니다. 아래 "무엇을 만들었나"의 두 번째 다이어그램 참고.

## 왜 이 프로젝트인가

대한오션웍스 해저케이블 프로젝트에서 CLB(케이블 포설 바지선) 개조 및 운영 과정에 참여하면서,
텐셔너 베어링 같은 예비 부품을 리드타임을 감안해 미리 확보해야 했던 경험이 있습니다.
그때는 감(experience)과 현장 판단으로 처리했던 문제를, 이번에는 "수요예측 → BOM 전개
→ 안전재고 → 넷팅 → 리드타임 오프셋"이라는 SCM의 표준 프레임워크로 구조화하고,
AI 예측 모델까지 얹어서 시스템화해봤습니다.

## 무엇을 만들었나

```
과거 수요 이력 (36개월)                     PE-3000 BOM (3단, 17개 부품)
  + Book-to-Bill Ratio (선행지표)                  │
        │                                          │
        ▼                                          ▼
 [AI 수요예측 모델]                          [BOM 전개 (qty per 누적)]
  Holt-Winters / SARIMAX+B2B 비교                   │
  → 향후 6개월 예측 + 90% 신뢰구간                    │
        │                                          │
        └──────────────┬───────────────────────────┘
                        ▼
              부품별 총소요량 (Gross Requirement)
                        │
   현재고 + 입고예정 + 안전재고(서비스수준 95%) → [넷팅]
                        │
                 부품별 순소요량
                        │
        부품별 조달 리드타임 → [리드타임 오프셋 + MOQ 로트사이징]
                        │
                        ▼
        부품별·월별 발주 계획 (Planned Order Release)
                        │
                        ▼
              FabPulse 대시보드 (dashboard/index.html)
```

### 설계변경(ECN) 대응 시뮬레이터

기존 MRP 결과 위에, 부품이 실제로 단종(EOL)되거나 환경규제로 대체돼야 하는 상황을 시뮬레이션하는
기능을 추가했습니다. 실무의 Engineering Change Management(ECM) 워크플로우를 그대로 코드로 옮긴
구조입니다 (`src/eco_simulator.py`).

```
단종/규제 공지 감지                Where-Used 조회 (PLM)         대체품 탐색 + Drop-in 등급
(Z2Data/SiliconExpert류 툴)   →   부품 → 서브시스템 → 완제품   →   (Z2Data/SiliconExpert류 툴)
                                                                   A: 재인증 불필요
                                                                   B: 경미한 검토 필요
                                                                   C: 전체 재인증 필요
                                                                          │
                                                                          ▼
                                                        CCB(Change Control Board) 승인
                                                     ← 사람이 판단 (시뮬레이터는 판단 재료만 제공)
                                                                          │
                                                                          ▼
                                          ECO 반영 → 부품마스터(리드타임/단가) 갱신 → MRP 재계산
                                                  → 발주 시점·6개월 발주액 변화를 Before/After 비교
```

### 이익 임팩트 (Profit Impact) — "그래서 이 시스템이 회사 이익에 뭘 하는가"

MRP/ECN 결과는 그 자체로는 "몇 월에 몇 개 발주해야 한다"는 운영 지표일 뿐, 경영진 입장에서
와닿는 언어(매출·마진·투자수익)로 바뀌지 않으면 설득력이 떨어집니다. `src/profit_impact.py`는
Action Queue의 조달 리스크를 **1) 방치했을 때의 매출/마진 손실**과 **2) 그 손실을 줄이려고
안전재고를 더 쌓을 때 드는 재고 자본비용**, 두 가지를 같은 단위($)로 환산해 서로 비교합니다.

```
[Action Queue: Past Due 부품]                    [안전재고 서비스수준 Z]
        │                                                │
        ▼                                                ▼
지연 개월수 × 해당 기간 완제품 수요            안전재고 = Z × σ(리드타임 동안의 수요)
        │                                                │
        ▼                                                ▼
막힌 완제품 대수 × ASP(판매단가)              단위정규손실함수 L(z)로 "기대 품절 수량" 계산
        │                                                │
        ▼                                                ▼
   Revenue at Risk → × 매출총이익률                기대 마진 리스크 (서비스수준별)
        │                                                │
        ▼                                                ▼
     마진 리스크($)                    재고 증가분 × 자본비용률(WACC 근사) = 자본비용 델타
        └───────────────────┬────────────────────────────┘
                             ▼
              순이익 임팩트 = (지킨 마진) − (추가로 든 자본비용)
                    → 서비스수준을 "감"이 아니라 재무 트레이드오프로 판단
```

이 계산에 쓰인 완제품 판매단가(ASP)·매출총이익률·자본비용률은 모두 **명시적으로 라벨링된 가정치**이며
(매출총이익률은 반도체 장비업계 공개 보도치를 참고), 실제 특정 기업의 재무 수치가 아닙니다.
핵심은 절대 금액이 아니라 **"리스크를 $로 환산하고 서비스수준별 트레이드오프를 계산하는 방법론"**
자체입니다. 대시보드의 "이익 임팩트" 패널에서도 이 가정치를 항상 함께 표시합니다.

### 핵심 결과 (합성 데이터 · 가정치 기준)

- 반도체 업계 실제 선행지표인 **Book-to-Bill Ratio**를 SARIMAX 외생변수로 반영한 모델이,
  naive 예측(22.0% MAPE) · Holt-Winters(32.6% MAPE) 대비 **15.5% MAPE**로 오차를 크게 줄임
- 2024~2025년 반도체 CAPEX 다운턴 이후 2026년 AI向 수요 반등 국면에서, 기존 재고 수준으로는
  대응이 어려운 **17개 부품 중 12개**가 "즉시 발주 필요(Past Due)" 상태로 식별됨
  — 리드타임이 가장 긴 Turbo Molecular Pump, RF Power Amplifier가 최우선 리스크
- 향후 6개월 총 발주 예상 금액 약 **$11.6M**
- 위험 부품 3종(Turbo Pump·RF Amp·Electrostatic Chuck)의 단종/규제 시나리오를 시뮬레이션한 결과,
  **Drop-in 등급이 높다고 항상 조달 지연이 해소되는 건 아님**을 확인 — 리드타임이 실제로 짧아지는
  대체품이 아니면 등급(A/B/C)과 무관하게 여전히 발주가 밀려 있는 경우가 많았음
- (가정치 기준) 최대 위험 부품(Turbo Molecular Pump) 지연이 방치되면 마진 리스크 약 **$140M**;
  현재 서비스수준(95%) 대비 99%로 전환하면 추가 재고 자본비용을 감안하고도 순이익 임팩트
  약 **+$1.22M**로 계산됨 — 단, 90/95/99% 세 지점만 비교한 결과이며 "몇 %가 정답"이 아니라
  이 트레이드오프를 정량적으로 따질 수 있다는 방법론이 핵심

## 프로젝트 구조

```
semi-mrp-ai/
├── src/
│   ├── bom.py                 # 3단 BOM 정의 + BOM 전개(explosion) 로직
│   ├── part_master.py         # 부품 마스터 (단가/리드타임/공급업체/MOQ/재고)
│   ├── demand_data.py         # 수요 이력 + Book-to-Bill Ratio 합성 데이터 생성
│   ├── forecasting.py         # Holt-Winters / SARIMAX+B2B 수요예측 + 백테스트
│   ├── mrp_engine.py          # 안전재고 계산 + MRP 넷팅 + 리드타임 오프셋
│   ├── eco_simulator.py       # 설계변경(ECN) 시뮬레이터: Where-Used + 대체품 Drop-in 등급 + MRP 재계산
│   ├── profit_impact.py       # 이익 임팩트: Revenue at Risk + 안전재고 서비스수준 트레이드오프($)
│   ├── real_bom_validate.py   # (부록) 실제 공개 BOM(NASA JPL 로버)으로 BOM 전개/원가 롤업 검증
│   ├── run_pipeline.py        # 전체 파이프라인 실행 -> data/*.csv 생성
│   ├── export_dashboard_data.py  # data/*.csv -> dashboard_bundle.json
│   └── build_dashboard.py     # template.html + JSON -> dashboard/index.html
├── data/                      # 파이프라인 산출물 (CSV/JSON)
├── data_sources/
│   └── jpl_open_source_rover/ # NASA JPL이 공개한 실제 BOM 원본 (SOURCE.md에 출처/라이선스)
├── dashboard/
│   ├── template.html          # 대시보드 템플릿 (데이터 자리에 __DASHBOARD_DATA__)
│   └── index.html             # 완성된 대시보드 (더블클릭으로 바로 열람 가능)
├── reports/
│   ├── scm_concepts.md        # BOM/MRP/안전재고 등 핵심 SCM 개념 정리
│   └── real_bom_validation.md # (부록) 실제 BOM 검증 리포트
├── requirements.txt
└── README.md
```

## 실행 방법

```bash
pip install -r requirements.txt

cd src
python run_pipeline.py            # 데이터 생성 -> 예측 -> MRP -> data/*.csv, summary.json
python export_dashboard_data.py   # data/*.csv -> data/dashboard_bundle.json
python build_dashboard.py         # -> dashboard/index.html 재생성
```

각 모듈은 단독 실행도 가능합니다 (예: `python forecasting.py`로 백테스트 결과만 바로 확인).

## 설계 노트 / 의도적으로 단순화한 부분

- **수요·재고 데이터는 전부 합성(synthetic) 데이터**입니다. 특정 기업의 실제 수치가 아니며,
  반도체 장비 산업의 통상적인 패턴(CAPEX 사이클, 분기말 밀어내기, Book-to-Bill 선행성)을
  참고해 만들었습니다.
- Book-to-Bill Ratio는 실제로 3개월 정도 출하를 선행하는 지표라, SARIMAX 모델에서 이미
  관측된 과거 값만으로 예측이 가능합니다. 다만 예측 지평이 3개월을 넘어가는 구간(4~6개월 뒤)은
  미래 B2B 값이 없어 최신 값을 그대로 이월(carry-forward)한다는 단순화를 뒀습니다 — 실무라면
  SEMI 발표치나 업계 컨센서스로 대체할 부분입니다.
- MRP는 월 단위 버킷의 Lot-for-Lot + MOQ 로트사이징만 구현했습니다. 실제 ERP는 여기에
  EOQ, 주 단위 버킷, 다중 창고 로직 등이 추가로 붙습니다.
- 대체 부품(substitute part) 시나리오는 `eco_simulator.py`에 3건(단종 2건 + 규제대응 1건)을
  수동으로 정의해뒀습니다. 실제로는 Z2Data/SiliconExpert 같은 툴이 부품 스펙 DB를 기반으로
  대체품과 Drop-in 등급을 자동 추천하는데, 여기서는 그 출력값을 합성 데이터로 흉내냈습니다.
  또한 기존 재고(on_hand)는 대체품 적용 후에도 그대로 유지된다고 단순화했습니다 — 실무에서도
  보유 재고는 소진될 때까지 쓰고 신규 발주분부터 대체품 스펙이 적용되는 경우가 많아 이 단순화가
  결과를 크게 왜곡하지는 않습니다.
- "즉시 발주 필요(Past Due)" 판정이 다수 나오는 것은 버그가 아니라, 다운턴 이후 급격한
  수요 반등 국면에서 리드타임이 긴 부품일수록 기존 재고 정책이 이미 뒤처져 있다는 뜻입니다.
  실제 MRP 운영에서도 이런 "action message"는 흔히 발생하며, 이 프로젝트가 보여주고 싶은
  핵심 가치도 여기에 있습니다: **이런 리스크를 사람이 놓치기 전에 시스템이 먼저 잡아낸다.**
- 이익 임팩트 계산의 완제품 판매단가·매출총이익률·자본비용률은 실제 공시 재무제표가 아니라
  업계 통상 수준을 참고해 만든 가정치입니다. 부품별 병목(bottleneck) 가정도 단순화했습니다 —
  실제로는 여러 부품이 동시에 지연되면 "가장 늦게 도착하는 부품"이 출하를 막는 것이 맞지만,
  이 모델은 그 최댓값(max) 로직으로 단순화해 여러 지연이 완전히 독립적으로 누적되는 과대추정은
  피했습니다.

## 이력서/면접 스토리텔링 포인트

- "실무에서 예비 부품(텐셔너 베어링)을 리드타임을 감안해 사전 확보했던 경험을, AI 수요예측
  + BOM/MRP 로직으로 일반화한 시스템을 개인 프로젝트로 구현함"
- "SCM 표준 개념(BOM 전개, 넷팅, 리드타임 오프셋, 안전재고)을 Python으로 직접 구현하며 학습함"
- "반도체 장비 업계 실제 선행지표(Book-to-Bill Ratio)를 조사해 시계열 예측 모델의 설명변수로
  반영, naive 대비 예측 오차(MAPE)를 22.0%→15.5%로, 상대적으로 약 30% 줄임"
- "수요 급변 시나리오(다운턴 → AI 붐)에서 재고 정책의 리스크를 정량적으로 식별하는 대시보드를
  직접 설계·구현함 (Python 백엔드 + 커스텀 데이터 시각화)"
- "PLM Where-Used 조회 → 대체품 Drop-in 등급 평가 → MRP 재계산으로 이어지는 설계변경(ECN) 대응
  워크플로우를 시뮬레이터로 구현, 부품 단종/규제 대응 시 조달 리스크를 사전에 정량화함"
- "합성 데이터로 검증한 BOM 전개·원가 롤업 로직을, NASA JPL이 공개한 실제 오픈소스 하드웨어
  BOM(94개 부품)에 그대로 적용해 재현 검증함 — 계산된 원가가 공식 공개값과 정확히 일치"
- "조달 리스크를 운영 지표(발주 시점·수량)에서 그치지 않고, 매출 리스크(Revenue at Risk)와
  안전재고 서비스수준의 재무 트레이드오프(단위정규손실함수 기반)로 환산해, '이 시스템이 회사
  이익에 어떤 영향을 주는가'를 대시보드에서 바로 보여주는 이익 임팩트 모듈을 설계·구현함"

SCM 핵심 개념 자체를 더 찬찬히 짚고 싶다면 `reports/scm_concepts.md`를 참고하세요.

## 부록 — 실제 공개 BOM으로 검증 (NASA JPL Open Source Rover)

반도체 장비 BOM은 대부분 영업비밀이라 구할 수 없었지만, NASA JPL이 공개한 오픈소스 로버
프로젝트([nasa-jpl/open-source-rover](https://github.com/nasa-jpl/open-source-rover), Apache 2.0)는
실제 부품번호·공급업체(goBILDA, Digikey)·단가·수량이 전부 공개돼 있습니다. 이 데이터로 FabPulse의
BOM 전개·원가 롤업 로직이 합성 데이터가 아닌 **실제 산업 데이터**에도 정확히 통하는지 별도로
검증했습니다.

```bash
python src/real_bom_validate.py   # -> reports/real_bom_validation.md
```

- 6개 어셈블리·94개 BOM 라인(고유 부품 92개)을 전개해서 계산한 로버 1대 총원가가, JPL이 README에
  직접 공개한 총원가($1,421.18)와 **정확히 일치**함을 확인 (일종의 회귀 테스트)
- 여러 어셈블리에 걸쳐 재사용되는 공유 부품을 올바르게 합산하는 것도 확인
- 다만 이 데이터는 1회성 키트 제품이라 월별 수요 이력이 없어서, AI 수요예측·안전재고·MRP 넷팅
  로직까지는 이 실제 데이터로 검증하지 못했습니다 — 그 부분은 여전히 반도체 장비 합성 시나리오로만
  시연합니다. 자세한 내용과 한계는 `data_sources/jpl_open_source_rover/SOURCE.md`와
  `reports/real_bom_validation.md` 참고.
