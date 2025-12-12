#!/bin/bash
# Watch analysis logs in real-time

echo "================================================================================"
echo "API Security Capture Analyzer - Live Analysis Monitor"
echo "================================================================================"
echo ""
echo "Watching for analysis activity..."
echo "Run your browser extension now and watch the analysis in real-time!"
echo ""
echo "================================================================================"
echo ""

tail -f uvicorn.log | grep --line-buffered -E "\[(FeatureExtractor|MicroserviceIdentifier|BBM)\]|HTTP"

