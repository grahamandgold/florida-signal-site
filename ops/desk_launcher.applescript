-- Florida Signal Desk one-click launcher
do shell script "/bin/bash '/Users/gillfillan/Documents/FL SIGNAL SITE BUILD/ops/launch_local.sh' > /tmp/fsdesk_launch.log 2>&1"
do shell script "open -a 'Google Chrome' 'http://127.0.0.1:8788/data.html' 'http://127.0.0.1:8788/' 'http://127.0.0.1:4173/fort-lauderdale/'"
