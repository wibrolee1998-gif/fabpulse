"""dashboard/template.html + data/dashboard_bundle.json -> dashboard/index.html 조립.

run_pipeline.py -> export_dashboard_data.py -> build_dashboard.py 순으로 실행하면
데이터 생성부터 대시보드까지 전체가 재현된다.
"""
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")
TEMPLATE_PATH = os.path.join(ROOT, "dashboard", "template.html")
DATA_PATH = os.path.join(ROOT, "data", "dashboard_bundle.json")
OUT_PATH = os.path.join(ROOT, "dashboard", "index.html")


def main():
    with open(DATA_PATH, encoding="utf-8") as f:
        data_json = f.read().replace("</script>", "<\\/script>")
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()

    out = template.replace("__DASHBOARD_DATA__", data_json)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(out)

    print(f"저장됨: {OUT_PATH} ({len(out) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
