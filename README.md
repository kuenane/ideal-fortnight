# UK 49s Intelligence Dashboard

The **UK 49s Intelligence Dashboard** is a powerful, Flask-based web application designed for scraping, analyzing, and visualizing results from the UK 49s Lunchtime and Teatime lottery draws. It provides users with deep insights through historical data analysis, mathematical set generation, and custom lotto calculations.

## Key Features

- **Advanced Web Scraping**: Automatically captures all draw results and data tables from the official 49s source.
- **In-Depth Analysis**:
  - **Hot & Cold Numbers**: Identifies the most and least frequent balls.
  - **Distribution Charts**: Visualizes ball frequency, ending digits, and color band distributions.
  - **Arithmetic Set Generation**: Generates potential combinations (S1, S2, S3, S5) using sophisticated mathematical formulas.
- **Lotto Calculations**: Real-time calculation of variables $x_1$ through $x_9$ and $v, w, x, y, z$ based on the latest draw results.
- **PDF Export**: Allows users to download generated number combinations and sets as a professional PDF report.
- **Responsive Dark Theme**: A modern, single-page dashboard designed for both desktop and mobile use.

## Getting Started

### Prerequisites

- Python 3.8+
- pip (Python package installer)

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/kuenane/ideal-fortnight.git
   cd ideal-fortnight
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

### Running the Application

1. **Start the Flask server**:
   ```bash
   python app.py
   ```

2. **Access the Dashboard**:
   Open your web browser and navigate to:
   `http://localhost:5000`

## Project Structure

- `app.py`: The main application logic (Scraper, Analyser, and Flask Web Server).
- `requirements.txt`: List of required Python packages (`flask`, `requests`, `beautifulsoup4`, `fpdf2`).
- `README.md`: Project documentation and setup guide.

## Disclaimer

Lotteries are games of chance. The suggestions and calculations provided by this dashboard are for informational and entertainment purposes only. Past results do not guarantee future outcomes. Please play responsibly.

---
Created by Lebohang Kuenane.
