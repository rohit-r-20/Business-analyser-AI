import pandas as pd
import numpy as np

def generate_insights(df, revenue):
    """Generates AI-style narrative insights."""
    insights = []
    
    # 1. Revenue Insight
    insights.append(f"Total revenue generated is ₹{revenue:,.2f}.")

    # 2. Top Product Insight (Robust Check)
    # Find product column using keywords
    prod_col = next((c for c in df.columns if any(k in c.lower() for k in ['product', 'item', 'description'])), None)
    amt_col = 'amount' # We standardized this in app.py
    
    if prod_col and amt_col in df.columns:
        # Check if amount is numeric
        if pd.api.types.is_numeric_dtype(df[amt_col]):
            top_prod = df.groupby(prod_col)[amt_col].sum().idxmax()
            top_val = df.groupby(prod_col)[amt_col].sum().max()
            if revenue > 0:
                share = (top_val / revenue) * 100
                insights.append(f"Top Performer: '{top_prod}' contributes {share:.1f}% of total sales.")
            else:
                insights.append(f"Top Performer: '{top_prod}' is the highest selling item.")

    # 3. Anomaly / High Value Transactions
    if 'amount' in df.columns and pd.api.types.is_numeric_dtype(df['amount']):
        avg_txn = df['amount'].mean()
        if avg_txn > 0:
            high_count = df[df['amount'] > 2 * avg_txn].shape[0]
            if high_count > 0:
                insights.append(f"Detected {high_count} transactions significantly higher than the average ticket size (₹{avg_txn:.2f}).")

    return insights

def forecast_sales(df):
    """
    Predicts next period sales using Linear Regression (switched to numpy for performance).
    Requires a date column. If no date, uses index as proxy for time.
    """
    if 'amount' not in df.columns:
        return 0.0

    # Try to find a date column
    date_col = next((c for c in df.columns if any(k in c.lower() for k in ['date', 'time', 'day'])), None)
    
    data = df.copy()
    
    # Preprocessing
    if date_col:
        try:
            data[date_col] = pd.to_datetime(data[date_col], errors='coerce')
            data = data.dropna(subset=[date_col])
            data = data.sort_values(date_col)
        except:
            pass 

    # Prepare X (Time) and y (Sales)
    # Use index as time proxy
    try:
        y = pd.to_numeric(data['amount'], errors='coerce').fillna(0).values
        x = np.arange(len(y))  # 0, 1, 2, ...
        
        if len(y) < 2:
            return 0.0

        # Replace sklearn.linear_model.LinearRegression with numpy.polyfit
        # Degree 1 = Linear (mx + c)
        slope, intercept = np.polyfit(x, y, 1)
        
        # Predict next step
        next_index = len(y)
        prediction = (slope * next_index) + intercept
        
        return max(0.0, prediction) 
    except:
        return 0.0

def generate_dashboard_data(df):
    """
    Consolidates KPI metrics, chart data, forecasts, and insights into 
    a single dictionary for the dashboard UI.
    """
    # 1. Identify key columns consistent with existing logic
    prod_col = next((c for c in df.columns if any(k in c.lower() for k in ['product', 'item', 'description'])), None)
    
    # 2. KPI Metrics
    total_revenue = float(df['amount'].sum()) if 'amount' in df.columns else 0.0
    total_orders = int(len(df))
    avg_order_value = total_revenue / total_orders if total_orders > 0 else 0.0
    unique_products = int(df[prod_col].nunique()) if prod_col else 0
    
    # 3. Chart Data
    # Sales by Product
    sales_by_product = {}
    if prod_col and 'amount' in df.columns:
        sales_by_product = df.groupby(prod_col)['amount'].sum().sort_values(ascending=False).to_dict()
    
    # Sales Trend (sorted by date if possible, otherwise index)
    date_col = next((c for c in df.columns if any(k in c.lower() for k in ['date', 'time', 'day'])), None)
    if date_col and 'amount' in df.columns:
        try:
            temp_df = df.copy()
            temp_df[date_col] = pd.to_datetime(temp_df[date_col], errors='coerce')
            temp_df = temp_df.dropna(subset=[date_col]).sort_values(date_col)
            sales_trend = temp_df['amount'].tolist()
        except:
            sales_trend = df['amount'].tolist()
    else:
        sales_trend = df['amount'].tolist() if 'amount' in df.columns else []

    # 4. Consolidate into final dictionary
    dashboard_data = {
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "avg_order_value": round(avg_order_value, 2),
        "unique_products": unique_products,
        "sales_by_product": sales_by_product,
        "sales_trend": sales_trend,
        "next_sales_prediction": forecast_sales(df),
        "insights": generate_insights(df, total_revenue)
    }
    
    return dashboard_data
