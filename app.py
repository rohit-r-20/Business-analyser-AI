from flask import Flask, render_template, request, jsonify, make_response
import pandas as pd
import os
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# ---------------- BASIC SETUP ----------------
app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------- UTILITY ----------------
def detect_column(df, keywords):
    for col in df.columns:
        for key in keywords:
            if key in col.lower():
                return col
    return None

# ---------------- MAIN ROUTE ----------------
@app.route("/", methods=["GET", "POST"])
def upload():
    if request.method == "POST":

        file = request.files["file"]
        path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(path)

        df = pd.read_excel(path)
        df.columns = df.columns.str.lower()

        # ---- CLEAN NUMERIC TEXT ----
        for col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.replace("₹", "", regex=False)
                .str.replace("/-", "", regex=False)
                .str.strip()
            )

        # ---- DETECT COLUMNS ----
        product_col = detect_column(df, ["product", "item", "material", "description", "particular"])
        qty_col = detect_column(df, ["qty", "quantity", "units", "nos"])
        rate_col = detect_column(df, ["rate", "price"])
        credit_col = detect_column(df, ["credit"])

        amount_col = detect_column(
            df,
            ["amount", "total", "value", "net", "bill amount", "invoice amount", "gross", "sales value"]
        )

        # ---- AMOUNT RESOLUTION ----
        if amount_col:
            df["amount"] = pd.to_numeric(df[amount_col], errors="coerce")

        elif credit_col:
            df["amount"] = pd.to_numeric(df[credit_col], errors="coerce")

        elif qty_col and rate_col:
            df["amount"] = (
                pd.to_numeric(df[qty_col], errors="coerce") *
                pd.to_numeric(df[rate_col], errors="coerce")
            )

        else:
            numeric_cols = df.apply(pd.to_numeric, errors="coerce")
            likely_amount_col = numeric_cols.sum().idxmax()
            df["amount"] = numeric_cols[likely_amount_col]

        df["amount"] = df["amount"].fillna(0)

        # ---- METRICS ----
        revenue = round(df["amount"].sum(), 2)

        if product_col:
            sales_by_product = df.groupby(product_col)["amount"].sum().to_dict()
            quantity_by_product = (
                df.groupby(product_col)[qty_col].sum().to_dict()
                if qty_col else {}
            )
        else:
            sales_by_product = {"Overall Sales": revenue}
            quantity_by_product = {}

        insights = [
            f"Total revenue is ₹{revenue}",
            "Focus on high-value products",
            "Improve slow-moving items"
        ]

        return render_template(
            "dashboard.html",
            revenue=revenue,
            sales_by_product=sales_by_product,
            quantity_by_product=quantity_by_product,
            insights=insights
        )

    return render_template("upload.html")

# ---------------- PDF DOWNLOAD (REPORTLAB) ----------------
@app.route("/download-pdf", methods=["POST"])
def download_pdf():

    revenue = request.form.get("revenue")

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 50
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, y, "Business Analytics Report")

    y -= 40
    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, y, f"Total Revenue: ₹ {revenue}")

    y -= 30
    pdf.drawString(50, y, "Key Insights:")

    y -= 20
    pdf.drawString(70, y, "- Focus on high-performing products")
    y -= 20
    pdf.drawString(70, y, "- Improve slow-moving items")
    y -= 20
    pdf.drawString(70, y, "- Monitor revenue trends regularly")

    pdf.showPage()
    pdf.save()

    buffer.seek(0)

    response = make_response(buffer.read())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "attachment; filename=Business_Report.pdf"

    return response

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)
