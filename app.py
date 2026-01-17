from flask import Flask, render_template, request, jsonify, make_response
import pandas as pd
import numpy as np
import os
import datetime
from io import BytesIO

# ReportLab imports for advanced PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

from analytics_engine import generate_insights, forecast_sales

# ---------------- CONFIGURATION ----------------
app = Flask(__name__)
# REMOVED: os.makedirs(UPLOAD_FOLDER) to support serverless (read-only) environments

# ---------------- UTILITY ----------------
def clean_currency(value):
    if isinstance(value, str):
        return value.replace(",", "").replace("₹", "").replace("/-", "").strip()
    return value

def process_file_stream(file_stream, filename):
    ext = os.path.splitext(filename)[1].lower()
    
    if ext == '.csv':
        df = pd.read_csv(file_stream)
    elif ext == '.xlsx':
        df = pd.read_excel(file_stream, engine='openpyxl')
    elif ext == '.xls':
        df = pd.read_excel(file_stream, engine='xlrd')
    else:
        # Fallback
        df = pd.read_excel(file_stream) 
        
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
    # ... (Rest of logic remains identical)
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
             # FIX: Do not save to disk (read-only). Process directly from memory.
            try:
                # Iterate on the stream directly
                df, prod_col, qty_col, date_col = process_file_stream(file, file.filename)
                
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
                return render_template("upload.html", error=f"Processing Error: {str(e)}")

    return render_template("upload.html")

@app.route("/download-pdf", methods=["POST"])
def download_pdf():
    # Retrieve data from form
    revenue = request.form.get("revenue", "0")
    forecast = request.form.get("forecast", "0")
    
    # Parse lists (custom separator | used in template)
    insights_raw = request.form.get("insights", "")
    insights = [i for i in insights_raw.split('|') if i.strip()]
    
    top_products_raw = request.form.get("top_products", "")
    top_products = [p for p in top_products_raw.split('|') if p.strip()]
    
    top_sales_raw = request.form.get("top_sales", "")
    top_sales = [s for s in top_sales_raw.split('|') if s.strip()]

    # Setup PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    styles = getSampleStyleSheet()
    
    # Custom Styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#4f46e5'),
        spaceAfter=30,
        alignment=1 # Center
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#1e293b'),
        spaceBefore=20,
        spaceAfter=10,
        borderPadding=(0, 0, 5, 0),
        borderColor=colors.HexColor('#e2e8f0'),
        borderWidth=1,
        borderBottom=True
    )
    
    normal_style = styles["Normal"]
    normal_style.fontSize = 11
    normal_style.leading = 16

    # Build Content
    content = []
    
    # 1. Header
    content.append(Paragraph("Executive Business Report", title_style))
    content.append(Paragraph(f"Generated on: {datetime.datetime.now().strftime('%B %d, %Y')}", normal_style))
    content.append(Spacer(1, 20))
    
    # 2. Key Metrics Table
    data_metrics = [
        ["Total Revenue", "Forecast (Next Period)"],
        [f"INR {revenue}", f"INR {forecast}"]
    ]
    t_metrics = Table(data_metrics, colWidths=[200, 200])
    t_metrics.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8fafc')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#64748b')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, 1), colors.white),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, 1), 18),
        ('TEXTCOLOR', (0, 1), (0, 1), colors.HexColor('#10b981')), # Green for Rev
        ('TEXTCOLOR', (1, 1), (1, 1), colors.HexColor('#3b82f6')), # Blue for Forecast
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#f1f5f9'))
    ]))
    content.append(t_metrics)
    content.append(Spacer(1, 30))
    
    # 3. AI Insights
    content.append(Paragraph("AI Strategic Insights", heading_style))
    for insight in insights:
        bullet_text = f"•  {insight}"
        content.append(Paragraph(bullet_text, normal_style))
        content.append(Spacer(1, 8))
        
    content.append(Spacer(1, 20))
    
    # 4. Top Performing Strategy
    content.append(Paragraph("Top Product Performance", heading_style))
    
    if top_products and top_sales:
        table_data = [["Product Name", "Revenue Contribution"]]
        for p, s in zip(top_products, top_sales):
            try:
                val = float(s)
                val_fmt = f"INR {val:,.2f}"
            except:
                val_fmt = str(s)
            table_data.append([p, val_fmt])
            
        t = Table(table_data, colWidths=[300, 150])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4f46e5')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),
            ('GRID', (0, 0), (-1, -1), 1, colors.white),
        ]))
        content.append(t)
    
    # Build
    doc.build(content)
    
    buffer.seek(0)
    response = make_response(buffer.read())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "attachment; filename=AI_Strategic_Report.pdf"
    return response

if __name__ == "__main__":
    app.run(debug=True)
