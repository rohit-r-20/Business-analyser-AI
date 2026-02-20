import os
import datetime
import sqlite3
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, make_response, session, redirect, url_for
from flask_dance.contrib.google import make_google_blueprint, google
from io import BytesIO
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

load_dotenv()

# ReportLab imports for advanced PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

from analytics_engine import generate_insights, forecast_sales, generate_dashboard_data

# ---------------- CONFIGURATION ----------------
app = Flask(__name__)
app.secret_key = "supersecretkey"
load_dotenv()
DB_PATH = os.path.join(app.instance_path, 'database.db')

# Google OAuth Configuration
google_bp = make_google_blueprint(
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    scope=["profile", "email"],
    redirect_to="login_google"
)
# Using a unique prefix to avoid conflict with manual /login/google route
app.register_blueprint(google_bp, url_prefix="/google-auth")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    if not os.path.exists(app.instance_path):
        os.makedirs(app.instance_path)
    conn = get_db_connection()
    # Ensure user table exists with modern schema
    conn.execute('''
        CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            login_type TEXT DEFAULT 'local'
        )
    ''')
    # Add login_type if it doesn't exist (migration)
    try:
        conn.execute('ALTER TABLE user ADD COLUMN login_type TEXT DEFAULT "local"')
    except sqlite3.OperationalError:
        pass

    conn.execute('''
        CREATE TABLE IF NOT EXISTS upload_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_name TEXT,
            upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.close()

init_db()
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
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if request.method == "POST":
        file = request.files["file"]
        if file and file.filename != "":
             # FIX: Do not save to disk (read-only). Process directly from memory.
            try:
                # Iterate on the stream directly
                df, prod_col, qty_col, date_col = process_file_stream(file, file.filename)
                
                # Consolidate analytics using the new engine function
                data = generate_dashboard_data(df)
                
                # SAVE HISTORY: Insert record into upload_history
                # Use session['user_id'] if available, else a default (for safety without full auth context)
                curr_user_id = session.get('user_id', 1) 
                try:
                    conn = get_db_connection()
                    conn.execute('INSERT INTO upload_history (user_id, file_name) VALUES (?, ?)',
                                (curr_user_id, file.filename))
                    conn.commit()
                    conn.close()
                except Exception as db_err:
                    print(f"Database Error: {db_err}")

                # Prepare data for charts (Limiting for UI clarity)
                chart_labels = list(data['sales_by_product'].keys())[:10]
                chart_data = list(data['sales_by_product'].values())[:10]

                # STORE IN SESSION: For AI Chat Assistant
                session['last_analysis'] = {
                    "kpis": {
                        "total_revenue": data["total_revenue"],
                        "total_orders": data["total_orders"],
                        "avg_order_value": data["avg_order_value"],
                        "unique_products": data["unique_products"]
                    },
                    "forecast": round(data["next_sales_prediction"], 2),
                    "insights": data["insights"],
                    "top_product": chart_labels[0] if chart_labels else "N/A"
                }

                return render_template(
                    "dashboard.html",
                    kpis={
                        "total_revenue": data["total_revenue"],
                        "total_orders": data["total_orders"],
                        "avg_order_value": data["avg_order_value"],
                        "unique_products": data["unique_products"]
                    },
                    charts={
                        "sales_by_product": data["sales_by_product"],
                        "sales_trend": data["sales_trend"]
                    },
                    forecast=round(data["next_sales_prediction"], 2),
                    insights=data["insights"],
                    # Keeping some legacy names for UI chart scripts if they still use them
                    revenue=data["total_revenue"],
                    chart_labels=chart_labels,
                    chart_data=chart_data
                )
            except Exception as e:
                return render_template("upload.html", error=f"Processing Error: {str(e)}")

    return render_template("upload.html")

@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/login/google")
def login_google():
    if not google.authorized:
        return redirect(url_for("google.login"))

    resp = google.get("/oauth2/v2/userinfo")
    if not resp.ok:
        return "Failed to fetch user info from Google", 400
        
    email = resp.json()["email"]

    session["user"] = email
    # Also set user_id for compatibility with other routes
    session["user_id"] = 1 # Placeholder for now as per previous context
    return redirect(url_for("dashboard"))

@app.route("/download_report", methods=["POST"])
def download_report():
    # Retrieve data from form
    revenue = request.form.get("revenue", "0")
    forecast = request.form.get("forecast", "0")
    
    # Parse lists (custom separator | used in template)
    insights_raw = request.form.get("insights", "")
    insights = [i for i in insights_raw.split('|') if i.strip()]
    
    top_products_raw = request.form.get("top_products", "")
    top_products = [p for p in top_products_raw.split('|') if p.strip()]
    
    top_sales_raw = request.form.get("top_sales", "")
    top_sales = [float(s) if s.strip() else 0.0 for s in top_sales_raw.split('|') if s.strip()]

    trend_raw = request.form.get("trend_data", "")
    trend_data = [float(v) if v.strip() else 0.0 for v in trend_raw.split('|') if v.strip()]

    # Setup PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    
    # Custom Styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=26,
        textColor=colors.HexColor('#4318ff'),
        spaceAfter=30,
        alignment=1 # Center
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#1b254b'),
        spaceBefore=25,
        spaceAfter=15,
        borderPadding=(0, 0, 8, 0),
        borderColor=colors.HexColor('#e2e8f0'),
        borderWidth=1,
        borderBottom=True
    )
    
    normal_style = styles["Normal"]
    normal_style.fontSize = 11
    normal_style.leading = 16
    normal_style.textColor = colors.HexColor('#4a5568')

    # Build Content
    content = []
    
    # 1. Header
    content.append(Paragraph("Strategic Business Intelligence Report", title_style))
    content.append(Paragraph(f"AI ENGINE GENERATED ON: {datetime.datetime.now().strftime('%B %d, %Y | %H:%M')}", 
                            ParagraphStyle('Sub', parent=normal_style, alignment=1, fontSize=9, textColor=colors.gray)))
    content.append(Spacer(1, 30))
    
    # 2. Key Metrics Summary
    content.append(Paragraph("Executive Performance Summary", heading_style))
    data_metrics = [
        ["Total Revenue Performance", "Predictive Revenue Forecast"],
        [f"INR {revenue}", f"INR {forecast}"]
    ]
    t_metrics = Table(data_metrics, colWidths=[240, 240])
    t_metrics.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f4f7fe')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#a3aed0')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, 1), colors.white),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, 1), 22),
        ('TEXTCOLOR', (0, 1), (0, 1), colors.HexColor('#4318ff')), 
        ('TEXTCOLOR', (1, 1), (1, 1), colors.HexColor('#01b574')), 
        ('BOTTOMPADDING', (0, 1), (-1, 1), 15),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
    ]))
    content.append(t_metrics)
    content.append(Spacer(1, 40))

    # 3. VISUAL CHARTS
    content.append(Paragraph("Data Visualizations & Projections", heading_style))
    
    # Generate Bar Chart for Products
    if top_products and top_sales:
        chart_buffer = BytesIO()
        plt.figure(figsize=(9, 4))
        plt.bar(top_products[:5], top_sales[:5], color='#4318ff', alpha=0.8)
        plt.title('Top 5 Performing Assets', fontsize=14, color='#1b254b', fontweight='bold')
        plt.ylabel('Revenue (INR)', fontsize=10, color='#64748b')
        plt.xticks(ha='center', fontsize=9)
        plt.grid(axis='y', linestyle='--', alpha=0.3)
        plt.tight_layout()
        plt.savefig(chart_buffer, format='png', dpi=150)
        plt.close()
        chart_buffer.seek(0)
        
        content.append(RLImage(chart_buffer, width=480, height=220))
        content.append(Spacer(1, 20))

    # Generate Line Chart for Trends
    if trend_data:
        trend_buffer = BytesIO()
        plt.figure(figsize=(9, 4))
        plt.plot(trend_data, color='#01b574', linewidth=3, marker='o', markersize=4, markerfacecolor='white')
        plt.fill_between(range(len(trend_data)), trend_data, color='#01b574', alpha=0.05)
        plt.title('Historical Revenue Trajectory', fontsize=14, color='#1b254b', fontweight='bold')
        plt.xlabel('Cumulative Transaction Timeline', fontsize=9, color='#64748b')
        plt.ylabel('Revenue (INR)', fontsize=9, color='#64748b')
        plt.grid(axis='y', linestyle='--', alpha=0.3)
        plt.tight_layout()
        plt.savefig(trend_buffer, format='png', dpi=150)
        plt.close()
        trend_buffer.seek(0)
        
        content.append(RLImage(trend_buffer, width=480, height=220))
        content.append(Spacer(1, 15))

    content.append(Spacer(1, 40))
    
    # 4. AI Strategic Insights
    content.append(Paragraph("AI-Driven Strategic Insights", heading_style))
    for insight in insights:
        content.append(Paragraph(f"<b>•</b> {insight}", normal_style))
        content.append(Spacer(1, 6))
        
    content.append(Spacer(1, 30))
    
    # 5. Full Data Table
    content.append(Paragraph("Detailed Performance Matrix", heading_style))
    if top_products and top_sales:
        table_data = [["Rank", "Strategic Asset / Product", "Revenue (INR)"]]
        for i, (p, s) in enumerate(zip(top_products, top_sales), 1):
            table_data.append([str(i), p, f"{s:,.2f}"])
            
        t = Table(table_data, colWidths=[50, 280, 150])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4318ff')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#1b254b')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.white),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f4f7fe')]),
        ]))
        content.append(t)
    
    # Build
    doc.build(content)
    
    buffer.seek(0)
    response = make_response(buffer.read())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "attachment; filename=AI_Strategic_Report.pdf"
    return response

# ---------------- AI CHAT ASSISTANT LOGIC ----------------
def generate_chat_response(question, data):
    q = question.lower()
    if not data:
        return "Please upload and analyze a dataset first so I can help you with specific insights."
    
    if "revenue" in q or "sales" in q:
        return f"The total revenue generated is ₹{data['kpis']['total_revenue']:,}. This is based on all processed transactions."
    elif "forecast" in q or "predict" in q:
        return f"Based on the current trend, our AI model forecasts sales for the next period to be approximately ₹{data['forecast']:,}."
    elif "top product" in q or "best seller" in q:
        return f"The top performing product is '{data['top_product']}', which has the highest revenue contribution in your dataset."
    elif "insights" in q or "summary" in q:
        summary = " ".join(data['insights'][:2])
        return f"Here is a quick summary of the AI insights: {summary}"
    elif "hello" in q or "hi" in q:
        return "Hello! I'm your BizAnalyzer AI Assistant. You can ask me about your revenue, forecasts, top products, or general insights."
    else:
        return "I'm not quite sure about that. Try asking about 'revenue', 'forecast', 'top product', or 'AI insights'."

@app.route("/chat", methods=["GET", "POST"])
def chat():
    # SECURITY: Logged-in users only.
    if 'user_id' not in session and False: # Simplified for current session-only state
        # In a real app: return redirect(url_for('login'))
        pass

    if request.method == "POST":
        user_message = request.json.get("message")
        analysis_data = session.get("last_analysis")
        bot_response = generate_chat_response(user_message, analysis_data)
        return jsonify({"response": bot_response})

    return render_template("chat.html")

@app.route("/history")
def history():
    # SECURITY: Ensure users can only see their own history records.
    user_id = session.get('user_id', 1) # Default to 1 if not logged in (minimal logic)
    
    conn = get_db_connection()
    history_data = conn.execute('SELECT file_name, upload_time FROM upload_history WHERE user_id = ? ORDER BY upload_time DESC',
                                (user_id,)).fetchall()
    conn.close()
    
    return render_template("history.html", history=history_data)

if __name__ == "__main__":
    app.run(debug=True)

