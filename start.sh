#!/bin/bash
cd /Users/Admin/WorkBuddy/video-curator
lsof -ti:8080 2>/dev/null | xargs kill -9 2>/dev/null
git pull --quiet 2>/dev/null
python3 app.py
