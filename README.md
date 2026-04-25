https://github.com/Sambhavvn/System-Optimizer-for-PC/blob/main/LISCENSE
SystemOptimizer
A modern Windows system optimization and monitoring application built with Python and CustomTkinter. Features real-time hardware monitoring, intelligent system cleaning, game mode optimization, CPU benchmarking, and comprehensive system reporting.

Features
Real-time Hardware Monitoring — Live CPU, GPU, and memory usage tracking with visual gauges and charts
System Cleaner — Safely removes temp files, clears Recycle Bin, and frees memory by trimming working sets
Game Mode — Automatically switches to high-performance power plan and closes background apps
CPU Benchmark — Multi-core prime calculation benchmark to measure system performance
AI Optimization — Smart recommendations based on system analysis
Power Management — Control Windows power plans directly from the app
System Tray Integration — Minimize to tray for background monitoring
Comprehensive Reports — Generate detailed system health reports
Screenshots
(Add screenshots of your dashboard here)

Requirements
OS: Windows 10/11 (64-bit)
Python: 3.8+
Privileges: Administrator (for full functionality)
Installation
bash
# Clone the repository
git clone https://github.com/yourusername/SystemOptimizer.git
cd SystemOptimizer
 
# Create virtual environment
python -m venv venv
 
# Install dependencies
venv\Scripts\pip install -r requirements.txt
 
# Run the application
venv\Scripts\python -m src.app.main
Dependencies
Package	Purpose
customtkinter	Modern GUI framework
psutil	System monitoring
WMI	Windows hardware info
pywin32	Windows API access
Pillow	Image processing
loguru	Logging
numpy, pandas, scikit-learn	Data analysis (optional)
Architecture
SystemOptimizer/
├── src/app/
│   ├── main.py              # Entry point with UAC elevation
│   ├── core/                # Core modules (collector, power, logger)
│   ├── services/            # Business logic (cleaner, benchmark, game mode)
│   ├── ui/                  # GUI components (dashboard, widgets, pages)
│   └── system_tray.py       # Tray integration
├── logs/                    # Application logs
├── reports/                 # Generated reports
└── requirements.txt
Key Components
Collector — Gathers real-time system metrics (CPU, GPU, RAM, disk)
CleanerService — Safe cleanup of temp files and memory optimization
GameModeService — Performance optimization for gaming
BenchmarkService — CPU stress testing with prime calculations
PowerManager — Windows power plan management via WMI
Safety Features
Automatic UAC elevation on startup
Safe process termination (user apps only, never system services)
Protected system directories excluded from cleanup
Comprehensive logging for troubleshooting
