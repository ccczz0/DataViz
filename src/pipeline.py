"""
Olist CRM Dashboard — data pipeline
-----------------------------------
อ่าน Olist Brazilian E-Commerce dataset (CSV) -> ทำความสะอาด -> คำนวณตัวชี้วัด
แล้วเขียนผลเป็น dashboard/data.js (window.DASH_DATA = {...}) ให้หน้าเว็บอ่าน

คำถามที่ dashboard ตอบ (จาก Worksheet ส่วนที่ 5)
  Q1  ลูกค้ากลับมาซื้อซ้ำห่างกันกี่วัน -> ควรส่งโปรโมชันกระตุ้นตอนไหน
  Q2  กลุ่มลูกค้าตาม RFM มีสัดส่วนและสร้างรายได้ต่างกันแค่ไหน
  Q3  คะแนนรีวิว / การส่งของล่าช้า สัมพันธ์กับการกลับมาซื้อซ้ำอย่างไร

Usage:
    python src/pipeline.py --data <folder with olist_*.csv> --out dashboard/data.js
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- settings
START = pd.Timestamp("2017-01-01")      # ก่อนหน้านี้ข้อมูลบางมาก (2016 มี ~330 ออเดอร์)
END = pd.Timestamp("2018-09-01")        # หลัง ส.ค. 2018 ข้อมูลขาด (ก.ย.-ต.ค. มี 20 ออเดอร์)
REF_DATE = END                          # วันอ้างอิงสำหรับคำนวณ Recency
SAME_BASKET_DAYS = 1                    # ออเดอร์ห่างกัน < 1 วัน = ตะกร้าเดียวกัน (split order)
REPEAT_WINDOW = 180                     # หน้าต่างวัดการซื้อซ้ำสำหรับ Q3 (วัน)
GAP_BIN = 15                            # ความกว้าง bin ของ histogram (วัน)
GAP_MAX = 360

SEGMENTS = [  # (key, Thai label, rule description)
    ("champions", "Champions", "ซื้อ ≥2 ครั้ง และซื้อล่าสุดภายใน 180 วัน"),
    ("cant_lose", "Can't Lose", "ซื้อ ≥2 ครั้ง แต่หายไปเกิน 180 วัน"),
    ("new", "New", "ซื้อครั้งเดียว ภายใน 90 วัน"),
    ("about_sleep", "About to Sleep", "ซื้อครั้งเดียว เมื่อ 91–180 วันก่อน"),
    ("hibernating", "Hibernating", "ซื้อครั้งเดียว เมื่อ 181–365 วันก่อน"),
    ("lost", "Lost", "ซื้อครั้งเดียว นานกว่า 365 วัน"),
]


def load(data_dir: Path) -> pd.DataFrame:
    """โหลดและรวมตาราง orders + customers + payments + reviews ให้เหลือ 1 แถวต่อออเดอร์"""
    ts = ["order_purchase_timestamp", "order_delivered_customer_date", "order_estimated_delivery_date"]
    orders = pd.read_csv(data_dir / "olist_orders_dataset.csv", parse_dates=ts)
    customers = pd.read_csv(data_dir / "olist_customers_dataset.csv")
    payments = pd.read_csv(data_dir / "olist_order_payments_dataset.csv")
    reviews = pd.read_csv(data_dir / "olist_order_reviews_dataset.csv",
                          parse_dates=["review_answer_timestamp"])

    raw = {"orders_raw": len(orders), "customers_raw": customers.customer_unique_id.nunique()}

    # ยอดชำระต่อออเดอร์ (1 ออเดอร์จ่ายได้หลายช่องทาง/หลายงวด -> sum)
    pay = payments.groupby("order_id", as_index=False).payment_value.sum()

    # รีวิว: บางออเดอร์มีหลายรีวิว -> เก็บรีวิวที่ตอบล่าสุด
    rev = (reviews.sort_values("review_answer_timestamp")
                  .drop_duplicates("order_id", keep="last")[["order_id", "review_score"]])
    raw["dup_reviews_removed"] = len(reviews) - len(rev)

    df = (orders.merge(customers[["customer_id", "customer_unique_id", "customer_state"]], on="customer_id")
                .merge(pay, on="order_id", how="left")
                .merge(rev, on="order_id", how="left"))

    # กรอง: เฉพาะออเดอร์ที่ส่งถึงลูกค้าแล้ว + อยู่ในช่วงเวลาวิเคราะห์ + มียอดชำระ
    n0 = len(df)
    df = df[df.order_status.eq("delivered")]
    raw["removed_not_delivered"] = n0 - len(df)
    n1 = len(df)
    df = df[df.order_purchase_timestamp.between(START, END, inclusive="left")]
    raw["removed_out_of_range"] = n1 - len(df)
    n2 = len(df)
    df = df[df.payment_value.notna() & (df.payment_value > 0)]
    raw["removed_no_payment"] = n2 - len(df)

    # ส่งช้ากว่ากำหนด?
    df["delay_days"] = (df.order_delivered_customer_date.dt.normalize()
                        - df.order_estimated_delivery_date.dt.normalize()).dt.days
    raw["missing_delivery_date"] = int(df.delay_days.isna().sum())
    raw["missing_review"] = int(df.review_score.isna().sum())
    return df.reset_index(drop=True), raw


def add_occasions(df: pd.DataFrame) -> pd.DataFrame:
    """รวมออเดอร์ที่ลูกค้าคนเดิมสั่งห่างกัน < 1 วันเป็น 'ครั้งซื้อ' (occasion) เดียวกัน
    เพราะ Olist แตกตะกร้าเดียวเป็นหลายออเดอร์ตามผู้ขาย ถ้าไม่รวมจะได้ 'ซื้อซ้ำภายใน 0 วัน' ปลอม"""
    df = df.sort_values(["customer_unique_id", "order_purchase_timestamp"]).copy()
    gap = df.groupby("customer_unique_id").order_purchase_timestamp.diff().dt.total_seconds() / 86400
    df["new_occ"] = gap.isna() | (gap >= SAME_BASKET_DAYS)
    df["occ_no"] = df.groupby("customer_unique_id").new_occ.cumsum().astype(int)
    return df


def occasions_table(df: pd.DataFrame) -> pd.DataFrame:
    occ = (df.groupby(["customer_unique_id", "occ_no"])
             .agg(ts=("order_purchase_timestamp", "min"),
                  state=("customer_state", "first"),
                  value=("payment_value", "sum"),
                  review=("review_score", "min"),       # ถ้าตะกร้าเดียวมีหลายรีวิว ใช้คะแนนต่ำสุด
                  delay=("delay_days", "max"),
                  n_orders=("order_id", "size"))
             .reset_index())
    occ["gap_days"] = occ.groupby("customer_unique_id").ts.diff().dt.total_seconds() / 86400
    return occ


def customers_table(occ: pd.DataFrame) -> pd.DataFrame:
    cust = (occ.groupby("customer_unique_id")
               .agg(state=("state", "first"),
                    first_ts=("ts", "min"), last_ts=("ts", "max"),
                    F=("occ_no", "max"), M=("value", "sum"))
               .reset_index())
    cust["R"] = (REF_DATE - cust.last_ts).dt.days

    def seg(r):
        if r.F >= 2:
            return "champions" if r.R <= 180 else "cant_lose"
        if r.R <= 90:
            return "new"
        if r.R <= 180:
            return "about_sleep"
        if r.R <= 365:
            return "hibernating"
        return "lost"

    cust["segment"] = cust.apply(seg, axis=1)
    first = occ[occ.occ_no == 1].set_index("customer_unique_id")
    cust = cust.join(first[["review", "delay"]].rename(columns={"review": "first_review",
                                                                  "delay": "first_delay"}),
                     on="customer_unique_id")
    second = occ[occ.occ_no == 2].set_index("customer_unique_id").gap_days
    cust["days_to_2nd"] = cust.customer_unique_id.map(second)
    return cust


def rnd(x, n=1):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


def summarize(df, occ, cust) -> dict:
    """คำนวณทุกอย่างที่ dashboard ใช้ สำหรับข้อมูลชุดหนึ่ง (ทั้งประเทศ หรือรายรัฐ)"""
    out = {}
    n_cust = len(cust)
    repeaters = cust[cust.F >= 2]
    revenue = float(occ.value.sum())

    # ---------- KPI
    out["kpi"] = {
        "customers": n_cust,
        "orders": int(len(df)),
        "revenue": round(revenue),
        "aov": rnd(df.payment_value.mean(), 2),
        "repeat_rate": rnd(100 * len(repeaters) / n_cust if n_cust else np.nan, 2),
        "repeaters": int(len(repeaters)),
        "median_gap": rnd(repeaters.days_to_2nd.median(), 0),
        "avg_review": rnd(df.review_score.mean(), 2),
        "late_pct": rnd(100 * (df.delay_days > 0).mean(), 1),
    }

    # ---------- เทรนด์รายเดือน: ครั้งซื้อของลูกค้าใหม่ vs ลูกค้าเก่า
    m = occ.assign(month=occ.ts.dt.to_period("M").astype(str),
                   kind=np.where(occ.occ_no == 1, "new", "returning"))
    piv = m.pivot_table(index="month", columns="kind", values="value", aggfunc="size", fill_value=0)
    months = pd.period_range(START, END - pd.Timedelta(days=1), freq="M").astype(str)
    piv = piv.reindex(months, fill_value=0)
    rev_m = m.groupby("month").value.sum().reindex(months, fill_value=0)
    dm = df.assign(month=df.order_purchase_timestamp.dt.to_period("M").astype(str))
    late_m = dm.groupby("month").delay_days.apply(lambda x: 100 * (x > 0).mean()).reindex(months)
    rev_score_m = dm.groupby("month").review_score.mean().reindex(months)
    out["monthly"] = {
        "late_pct": [rnd(v, 1) for v in late_m],
        "avg_review": [rnd(v, 2) for v in rev_score_m],
        "months": list(months),
        "new": [int(v) for v in piv.get("new", pd.Series(0, index=months))],
        "returning": [int(v) for v in piv.get("returning", pd.Series(0, index=months))],
        "revenue": [round(float(v)) for v in rev_m],
    }

    # ---------- Q1: ระยะห่างจากการซื้อครั้งแรก -> ครั้งที่ 2
    g = repeaters.days_to_2nd.dropna()
    edges = list(range(0, GAP_MAX + GAP_BIN, GAP_BIN))
    counts = np.histogram(g.clip(upper=GAP_MAX - 0.001), bins=edges)[0]
    out["gap"] = {
        "n": int(len(g)),
        "bins": [f"{a}–{a + GAP_BIN}" for a in edges[:-1]],
        "bins_end": edges[1:],
        "counts": [int(c) for c in counts],
        "cum_pct": [rnd(100 * c / len(g), 1) if len(g) else None for c in np.cumsum(counts)],
        "p25": rnd(g.quantile(.25), 0), "p50": rnd(g.median(), 0), "p75": rnd(g.quantile(.75), 0),
        "within_30": rnd(100 * (g <= 30).mean(), 1) if len(g) else None,
        "within_90": rnd(100 * (g <= 90).mean(), 1) if len(g) else None,
        "beyond_last": int((g >= GAP_MAX).sum()),
        "cdf": [rnd(100 * (g <= day).mean(), 1) if len(g) else None for day in range(0, GAP_MAX + 1, 3)],
    }

    # ---------- Q2: RFM segments
    seg_rows = []
    for key, label, rule in SEGMENTS:
        s = cust[cust.segment == key]
        seg_rows.append({
            "key": key, "label": label, "rule": rule,
            "customers": int(len(s)),
            "cust_pct": rnd(100 * len(s) / n_cust if n_cust else np.nan, 2),
            "revenue": round(float(s.M.sum())),
            "rev_pct": rnd(100 * s.M.sum() / revenue if revenue else np.nan, 2),
            "avg_ltv": rnd(s.M.mean(), 2),
            "avg_recency": rnd(s.R.mean(), 0),
        })
    out["segments"] = seg_rows

    # Pareto: ลูกค้า top 10% ตามยอดใช้จ่าย สร้างรายได้กี่ %
    srt = cust.M.sort_values(ascending=False)
    top = max(1, int(round(len(srt) * 0.10))) if len(srt) else 0
    cum = srt.cumsum().to_numpy()
    curve = []
    for pct in range(0, 101, 2):
        k = int(round(len(srt) * pct / 100))
        curve.append(rnd(100 * cum[k - 1] / revenue, 1) if k > 0 and revenue else 0.0)
    out["pareto"] = {
        "curve": curve,
        "top10_rev_pct": rnd(100 * srt.head(top).sum() / revenue if revenue else np.nan, 1),
        "repeat_rev_pct": rnd(100 * repeaters.M.sum() / revenue if revenue else np.nan, 1),
        "ltv_repeat": rnd(repeaters.M.mean(), 2),
        "ltv_single": rnd(cust[cust.F == 1].M.mean(), 2),
    }

    # ---------- Q3: รีวิวครั้งแรก / การส่งช้า vs การกลับมาซื้อซ้ำภายใน 180 วัน
    #  cohort = ลูกค้าที่ซื้อครั้งแรกก่อน REF_DATE - 180 วัน (ทุกคนมีเวลาครบ 180 วันให้กลับมา)
    cohort = cust[cust.first_ts < REF_DATE - pd.Timedelta(days=REPEAT_WINDOW)].copy()
    cohort["rep"] = cohort.days_to_2nd.le(REPEAT_WINDOW)
    by_review = []
    for s in [1, 2, 3, 4, 5]:
        c = cohort[cohort.first_review == s]
        by_review.append({"score": s, "n": int(len(c)),
                          "repeat_pct": rnd(100 * c.rep.mean(), 2) if len(c) else None})
    delay_buckets = [("ก่อนกำหนด ≥7 วัน", -999, -7), ("ก่อนกำหนด 1–6 วัน", -6, -1),
                     ("ตรงวันกำหนด", 0, 0), ("ช้า 1–7 วัน", 1, 7), ("ช้า 8+ วัน", 8, 9999)]
    by_delay = []
    for label, lo, hi in delay_buckets:
        d = df[df.delay_days.between(lo, hi)]
        c = cohort[cohort.first_delay.between(lo, hi)]
        by_delay.append({"label": label, "orders": int(len(d)),
                         "avg_review": rnd(d.review_score.mean(), 2),
                         "low_review_pct": rnd(100 * (d.review_score <= 2).mean(), 1) if len(d) else None,
                         "repeat_pct": rnd(100 * c.rep.mean(), 2) if len(c) else None,
                         "cohort_n": int(len(c))})
    out["q3"] = {
        "cohort_n": int(len(cohort)),
        "overall_repeat_pct": rnd(100 * cohort.rep.mean(), 2) if len(cohort) else None,
        "by_review": by_review,
        "by_delay": by_delay,
    }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--out", default=Path("dashboard/data.js"), type=Path)
    args = ap.parse_args()

    df, raw = load(args.data)
    df = add_occasions(df)
    occ = occasions_table(df)
    cust = customers_table(occ)

    result = {
        "meta": {
            "source": "Brazilian E-Commerce Public Dataset by Olist (CC BY-NC-SA 4.0)",
            "period": f"{START.date()} – {(END - pd.Timedelta(days=1)).date()}",
            "ref_date": str(REF_DATE.date()),
            "repeat_window": REPEAT_WINDOW,
            "cleaning": {**raw,
                         "orders_clean": int(len(df)),
                         "occasions": int(len(occ)),
                         "split_orders_merged": int(len(df) - len(occ)),
                         "customers_clean": int(len(cust))},
            "segments": [{"key": k, "label": l, "rule": r} for k, l, r in SEGMENTS],
        },
        "all": summarize(df, occ, cust),
        "states": {},
    }
    state_sizes = cust.state.value_counts()
    rows = []
    for st in state_sizes.index:
        cs = cust[cust.state == st]
        ds = df[df.customer_unique_id.isin(set(cs.customer_unique_id))]
        rows.append({"state": st, "customers": int(len(cs)),
                     "repeat_rate": rnd(100 * (cs.F >= 2).mean(), 2),
                     "late_pct": rnd(100 * (ds.delay_days > 0).mean(), 1),
                     "avg_review": rnd(ds.review_score.mean(), 2),
                     "deliv_days": rnd(((ds.order_delivered_customer_date - ds.order_purchase_timestamp)
                                        .dt.total_seconds() / 86400).median(), 1)})
    result["state_table"] = rows
    result["meta"]["state_customers"] = {k: int(v) for k, v in state_sizes.items()}
    for st in state_sizes.index:
        cs = cust[cust.state == st]
        ids = set(cs.customer_unique_id)
        result["states"][st] = summarize(df[df.customer_unique_id.isin(ids)],
                                         occ[occ.customer_unique_id.isin(ids)], cs)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("window.DASH_DATA = " + json.dumps(result, ensure_ascii=False,
                                                            separators=(",", ":")) + ";\n",
                        encoding="utf-8")
    k = result["all"]["kpi"]
    print(json.dumps(result["meta"]["cleaning"], indent=1))
    print(json.dumps(k, indent=1))
    print(json.dumps(result["all"]["gap"], ensure_ascii=False)[:600])
    print(json.dumps(result["all"]["segments"], ensure_ascii=False, indent=0))
    print(json.dumps(result["all"]["pareto"]))
    print(json.dumps(result["all"]["q3"], ensure_ascii=False, indent=0))
    print("wrote", args.out, args.out.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
