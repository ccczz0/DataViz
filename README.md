# Olist Customer Pulse

**Live dashboard:** https://ccczz0.github.io/DataViz/

Term project — 01219482 Data Visualization, Kasetsart University Chalermphrakiat Sakon Nakhon Province Campus

Web dashboard สำหรับฝ่ายดูแลลูกค้าสัมพันธ์ (CRM) ตอบคำถาม **"ควรส่งโปรโมชันกระตุ้นตอนไหน"** จากข้อมูลการสั่งซื้อจริงของแพลตฟอร์ม Olist (บราซิล) ม.ค. 2017 – ส.ค. 2018

หน้าเว็บเล่าเรื่องแบบ scrollytelling: กราฟค้างอยู่ในกรอบ (sticky) แล้วซูมเข้า/ออกและตัดสลับกราฟตามข้อความที่เลื่อนผ่าน

| ส่วน | กราฟ |
|---|---|
| Q1 ลูกค้ากลับมาซื้อครั้งที่ 2 หลังกี่วัน | Histogram → เส้นสะสม (CDF) พร้อม P50/P75 |
| บริบท 20 เดือน | Stacked bar ลูกค้าใหม่/ซื้อซ้ำ → % ส่งช้ารายเดือน → รีวิวเฉลี่ยรายเดือน |
| Q2 กลุ่ม RFM | % ลูกค้า vs % รายได้ → LTV ต่อกลุ่ม → Pareto curve (top 10%) |
| Q3 ส่งช้า/รีวิว กับการซื้อซ้ำ | รีวิวตามความล่าช้า → scatter รายรัฐ (คลิกเพื่อกรอง) → % ซื้อซ้ำตามรีวิวแรก |

ไฟล์หน้าเว็บ: `index.html` (เวอร์ชันหลัก โทนสว่าง), `night.html` (โทนมืด), `classic.html` (เวอร์ชันแรกแบบ dashboard ธรรมดา)

ตัวกรอง: รัฐของลูกค้า (27 รัฐ + ทั้งประเทศ) ทุกกราฟ ตัวเลข และข้อเสนอ CRM เปลี่ยนตามตัวกรอง

## โครงสร้าง

```
src/pipeline.py      อ่าน CSV → clean → คำนวณตัวชี้วัด → dashboard/data.js
dashboard/index.html หน้า dashboard (ECharts 5.4.3 จาก cdnjs)
dashboard/data.js    ผลลัพธ์ที่คำนวณแล้ว (ไม่ต้องมี backend)
src/build_site.py    สร้างเว็บพร้อม deploy ลง docs/
docs/                เว็บที่ GitHub Pages เสิร์ฟ
```

## วิธีรัน

1. ดาวน์โหลด dataset: <https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce> (หรือ <https://github.com/olist/work-at-olist-data>) แตกไฟล์ไว้ใน `data/`
2. ติดตั้งและรัน pipeline

```bash
pip install -r requirements.txt
python src/pipeline.py --data data --out dashboard/data.js
```

3. เปิด `dashboard/index.html` ในเบราว์เซอร์ได้เลย หรือ deploy โฟลเดอร์ `dashboard/` ขึ้น GitHub Pages / Vercel

## Deploy ขึ้น GitHub Pages

```bash
python src/build_site.py      # dashboard/*.html → docs/ (เติม <head>, charset, viewport ให้ครบ)
```

Settings → Pages → Source: *Deploy from a branch* → Branch `main`, folder `/docs` → Save
ได้ลิงก์ `https://<user>.github.io/<repo>/`

## นิยามที่ใช้

- นับลูกค้าด้วย `customer_unique_id` (เพราะ `customer_id` เปลี่ยนทุกออเดอร์)
- ใช้เฉพาะออเดอร์สถานะ `delivered` ช่วง 2017-01-01 ถึง 2018-08-31
- ออเดอร์ของลูกค้าคนเดิมที่ห่างกันไม่ถึง 1 วัน = การซื้อครั้งเดียว (ตะกร้าที่ถูกแยกตามผู้ขาย)
- ยอดเงิน = ผลรวม `payment_value` ต่อออเดอร์ (R$)
- RFM: วันอ้างอิง 2018-09-01 · Champions (ซื้อ ≥2 ครั้ง, ล่าสุด ≤180 วัน) · Can't Lose (≥2 ครั้ง, >180 วัน) · New (1 ครั้ง, ≤90 วัน) · About to Sleep (91–180) · Hibernating (181–365) · Lost (>365)
- Q3 cohort: ลูกค้าที่ซื้อครั้งแรกก่อน 2018-03-04 วัดว่ากลับมาซื้อภายใน 180 วันหรือไม่
- ส่งช้า = `order_delivered_customer_date` หลัง `order_estimated_delivery_date`

## Data license

Brazilian E-Commerce Public Dataset by Olist — CC BY-NC-SA 4.0
