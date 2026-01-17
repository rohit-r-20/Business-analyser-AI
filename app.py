from flask import Flask, render_template, request, jsonify, make_response
import pandas as pd
import numpy as np
import os
import datetime
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from analytics_engine import generate_insights, forecast_sales

# ---------------- CONFIGURATION ----------------
app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------- UTILITY ----------------
def clean_currency(value):
    if isinstance(value, str):
        return value.replace(",", "").replace("₹", "").replace("/-", "").strip()
    return value

def process_file(path, filename):
    ext = os.path.splitext(filename)[1].lower()
    
    if ext == '.csv':
        df = pd.read_csv(path)
    elif ext == '.xlsx':
        df = pd.read_excel(path, engine='openpyxl')
    elif ext == '.xls':
        df = pd.read_excel(path, engine='xlrd')
    else:
        # Fallback
        df = pd.read_excel(path) 
        
    df.columns = df.columns.str.lower()
    
    # 1. Clean Numeric
    for col in df.columns:
        if df[col].dtype == object:
             df[col] = df[col].apply(clean_currency)

    # 2. Detect Columns
    def get_col(keywords):
        for col in df.columns:
            if any(k in col for k in keywords):
                return col
        return None

    prod_col = get_col(["product", "item", "description", "particular"])
    qty_col = get_col(["qty", "quantity", "units", "nos"])
    rate_col = get_col(["rate", "price"])
    amt_col = get_col(["amount", "total", "value", "net"])
    date_col = get_col(["date", "time", "day"])

    # 3. Resolve Amount
    if amt_col:
        df["amount"] = pd.to_numeric(df[amt_col], errors="coerce").fillna(0)
    elif qty_col and rate_col:
        df["amount"] = (pd.to_numeric(df[qty_col], errors="coerce") * pd.to_numeric(df[rate_col], errors="coerce")).fillna(0)
    else:
        numeric_cols = df.select_dtypes(include=[np.number])
        if not numeric_cols.empty:
            df["amount"] = numeric_cols.sum(axis=1)
        else:
             df["amount"] = 0

    if not prod_col:
        df["product"] = "Unknown Item"
        prod_col = "product"
    
    return df, prod_col, qty_col, date_col

# ---------------- ROUTES ----------------

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file = request.files["file"]
        if file and file.filename != "":
            path = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(path)

            try:
                df, prod_col, qty_col, date_col = process_file(path, file.filename)
                
                revenue = round(df["amount"].sum(), 2)
                insights = generate_insights(df, revenue)
                forecast = forecast_sales(df) or 0
                
                sales_by_product = df.groupby(prod_col)["amount"].sum().sort_values(ascending=False).to_dict()
                
                quantity_by_product = {}
                if qty_col:
                    quantity_by_product = df.groupby(prod_col)[qty_col].sum().sort_values(ascending=False).to_dict()
                
                # Format for charts
                chart_labels = list(sales_by_product.keys())[:10]
                chart_data = list(sales_by_product.values())[:10]

                return render_template(
                    "dashboard.html",
                    revenue=revenue,
                    sales_by_product=sales_by_product,
                    quantity_by_product=quantity_by_product,
                    insights=insights,
                    forecast=round(forecast, 2),
                    chart_labels=chart_labels,
                    chart_data=chart_data
                )
            except Exception as e:
                return render_template("upload.html", error=str(e))

    return render_template("upload.html")

@app.route("/download-pdf", methods=["POST"])
def download_pdf():
    revenue = request.form.get("revenue")
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    p.setFont("Helvetica-Bold", 20)
    p.drawString(50, 800, "Executive Business Report")
    
    p.setFont("Helvetica", 12)
    p.drawString(50, 770, f"Generated on: {datetime.datetime.now().strftime('%Y-%m-%d')}")
    p.drawString(50, 750, f"Total Revenue: {revenue}")
    
    p.showPage()
    p.save()
    buffer.seek(0)
    
    response = make_response(buffer.read())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "attachment; filename=Report.pdf"
    return response

if __name__ == "__main__":
    app.run(debug=True)
