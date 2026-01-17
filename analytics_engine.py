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
