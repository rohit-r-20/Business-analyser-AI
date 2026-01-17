# 📊 Business Analyser AI

> **"Data needs to tell a story."**  
> Transform your raw Excel & CSV files into executive-level strategic reports in seconds.

## 🌐 Live Demo
**👉 [https://business-analyser-ai.vercel.app/](https://business-analyser-ai.vercel.app/) 👈**

![Business Dashboard](static/images/business_dashboard_background.png)

## 👋 What is this?
I built **Business Analyser AI** because I was tired of staring at boring spreadsheets solely to figure out "How did we do this month?".

This tool isn't just a dashboard; it's an **AI-powered analyst** that lives on your machine. You feed it chaotic sales data, and it gives you:
*   **Stunning Visuals**: A Glassmorphism UI that feels futuristic and premium.
*   **Smart Forecasts**: Uses Linear Regression to predict your next month's revenue using `scikit-learn`.
*   **Strategic Reports**: Generates a full PDF report with narrative insights, ready to be emailed to your boss.

---

## ✨ Features that shine
### 🎨 Glassmorphism UI
I ditched the boring corporate look for a modern, focused **Glass UI**. It features smooth animations, 3D hover effects, and a theme that makes data exciting to look at.

### 🧠 The Analytics Engine
Under the hood, it's not just summing numbers.
*   **Anomaly Detection**: Spots unusual high-value transactions.
*   **Trend Analysis**: Predicts future growth.
*   **Natural Language**: Writes bullet points about your business health (e.g., *"Top Performer: 'Monitor' contributes 30% of total sales"*).

### 📄 Executive PDF Export
One click generates a `AI_Strategic_Report.pdf`. It’s not a screenshot—it’s a professionally laid out document generated with **ReportLab**, complete with strategic tables and forecast metrics.

---

## 🚀 How to run it
Prerequisites: Python 3.10+

1.  **Clone the repo**
    ```bash
    git clone https://github.com/rohit-r-20/Business-analyser-AI.git
    cd Business-analyser-AI
    ```

2.  **Install dependencies**
    ```bash
    pip install flask pandas numpy scikit-learn reportlab openpyxl xlrd
    ```

3.  **Fire it up!**
    ```bash
    python app.py
    ```
    Visit `http://127.0.0.1:5000` in your browser.

---

## 📂 Supported Data
You don't need a specific template. The AI automatically scans your file for keywords like:
*   **Product**: `product`, `item`, `description`, `particular`
*   **Revenue**: `amount`, `total`, `value`, `net`, `price`
*   **Date**: `date`, `time` (optional, for forecasting)

Just drag and drop your `.csv`, `.xlsx`, or `.xls` and let it do the magic. 🪄

---

## 🛠 Tech Stack
*   **Backend**: Flask (Python)
*   **Intelligence**: Scikit-Learn (Linear Regression), NumPy, Pandas
*   **Frontend**: Vanilla CSS (Glassmorphism), Chart.js
*   **Reporting**: ReportLab (PDF Generation)

---

*Built by Rohit.*
