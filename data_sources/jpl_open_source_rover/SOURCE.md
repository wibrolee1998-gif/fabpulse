# 데이터 출처 — NASA JPL Open Source Rover

이 폴더의 두 CSV는 학습용으로 재작성한 게 아니라, **NASA 제트추진연구소(JPL)가 실제로 공개한 원본 파일**입니다.

- 프로젝트: [nasa-jpl/open-source-rover](https://github.com/nasa-jpl/open-source-rover)
  ("build-it-yourself" 6륜 로버, 화성 로버 설계를 참고해 JPL이 교육용으로 만듦)
- 원본 경로:
  - `parts_list.csv` ← `parts_list/parts_list.csv` (기구부 BOM, 5개 어셈블리)
  - `digikey_bom.csv` ← `parts_list/digikey_bom.csv` (전장부 BOM, Digikey 발주 가능한 형식)
- 라이선스: Apache License 2.0 (Copyright 2018 California Institute of Technology,
  Government Sponsorship Acknowledged)
- 가져온 날짜: 2026-09-07

## 왜 이 데이터를 선택했는지

반도체 장비 BOM은 대부분 영업비밀이라 구할 수 없다는 걸 확인했지만(`scm-질문로그.md` 8번), 이 프로젝트는
공공기관(JPL)이 재현 가능성을 위해 실제 부품번호·공급업체·단가·수량을 전부 공개해뒀습니다. FabPulse의
BOM 처리 로직(다단 BOM 전개, 공유 부품 합산, 원가 롤업)이 **합성 데이터가 아닌 실제 산업 데이터에도
그대로 통하는지** 검증하는 용도로 사용합니다.

## 이 데이터의 한계 (정직하게 밝힘)

- 이 로버는 대량생산 제품이 아니라 "한 대씩 직접 만드는" 오픈소스 키트라, **월별 판매/생산 실적 같은
  수요 이력 데이터가 존재하지 않습니다.** 그래서 FabPulse 메인 대시보드의 AI 수요예측 로직은 이 데이터로
  검증할 수 없고, 이 모듈은 BOM 전개·원가 롤업·다중 수량 시나리오까지만 다룹니다
  (`src/real_bom_validate.py`, `reports/real_bom_validation.md` 참고).
- `parts_list.csv`의 리드타임·MOQ·재고 컬럼은 원본에 아예 없습니다 — 실제 판매자(goBILDA 등)가
  공개하지 않기 때문입니다. 이 모듈에서는 그 값을 임의로 지어내지 않고, 원본에 실제로 있는 값
  (부품번호·단가·수량·공급업체)만 사용합니다.
