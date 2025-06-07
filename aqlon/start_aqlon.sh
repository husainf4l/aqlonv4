#!/bin/bash
# AQLON v3 Startup Script
# This script starts the AQLON server and optionally runs a full workflow test

# Set script directory as working directory
cd "$(dirname "$0")"

# Check for Python and required dependencies
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required but not found. Please install Python 3."
    exit 1
fi

# Function to check if server is running
check_server() {
    curl -s http://localhost:8000/api/v1/agent/status > /dev/null
    return $?
}

# Start the AQLON server
echo "Starting AQLON server..."
python3 server.py &
SERVER_PID=$!

# Wait for server to start
echo "Waiting for server to initialize..."
MAX_TRIES=30
TRIES=0
while ! check_server && [ $TRIES -lt $MAX_TRIES ]; do
    sleep 1
    TRIES=$((TRIES + 1))
    echo -n "."
done
echo ""

if [ $TRIES -eq $MAX_TRIES ]; then
    echo "Server failed to start within the expected time."
    kill $SERVER_PID 2>/dev/null
    exit 1
fi

echo "AQLON server is running at http://localhost:8000/"
echo "Dashboard available at http://localhost:8000/dashboard"

# If --test flag is provided, run the full workflow test
if [ "$1" == "--test" ]; then
    echo "Running full workflow test..."
    python3 test_full_workflow.py
    TEST_RESULT=$?
    
    if [ $TEST_RESULT -eq 0 ]; then
        echo "Test completed successfully."
    else
        echo "Test failed with exit code $TEST_RESULT."
    fi
fi

# Keep server running if --keep flag is provided
if [ "$1" == "--keep" ] || [ "$2" == "--keep" ]; then
    echo "Press Ctrl+C to stop the server..."
    # Wait for the server process
    wait $SERVER_PID
else
    # If no --keep flag, end the server if it was started by this script
    if [ -n "$SERVER_PID" ]; then
        echo "Stopping AQLON server..."
        kill $SERVER_PID
    fi
fi
