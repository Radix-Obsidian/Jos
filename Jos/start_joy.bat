@echo off
cd /d C:\Users\autre\OneDrive\Desktop\CascadeProjects\windsurf-project\Jos
if not exist logs mkdir logs
python web_dashboard.py >> logs\joy_dashboard.log 2>&1
