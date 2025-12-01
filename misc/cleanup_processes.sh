#!/bin/bash
# Kill any stray Bird Detection and Motion processes
echo "🧹 Cleaning up Bird Detection and old Motion processes..."

# Kill web servers
pkill -f "server.py" && echo "✅ Killed web server processes" || echo "ℹ️  No web server processes found"

# Kill old Google Drive uploaders
pkill -f "google_drive_survey_uploader.py" && echo "✅ Killed old Google Drive uploaders" || echo "ℹ️  No old Drive uploaders found"

# Kill old Motion cleanup processes
pkill -f "daily_cleanup.py" && echo "✅ Killed old cleanup processes" || echo "ℹ️  No old cleanup processes found"

# Kill other old Motion processes
pkill -f "/home/jaysettle/JayModel/Motion/" && echo "✅ Killed old Motion processes" || echo "ℹ️  No old Motion processes found"

# Kill main apps (except current terminal)
ps aux | grep "python3 main.py" | grep -v grep | awk "{print \$2}" | while read pid; do
    if [ "$pid" != "$$" ]; then
        kill -9 $pid 2>/dev/null && echo "✅ Killed main.py process: $pid"
    fi
done

echo "🎯 Cleanup complete!"
echo "💡 You can now start a fresh instance: python3 main.py"