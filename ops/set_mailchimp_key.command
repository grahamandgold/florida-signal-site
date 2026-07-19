#!/bin/bash
# Florida Signal — save your Mailchimp API key privately (never touches the repo).
echo ""
echo "  FLORIDA SIGNAL · Mailchimp setup"
echo "  Paste your Mailchimp API key below and press Return."
echo "  (The key is invisible while you paste — that's normal.)"
echo ""
read -s -p "  API key: " KEY
echo ""
if [ -z "$KEY" ]; then echo "  Nothing entered — run me again."; exit 1; fi
umask 077
cat > "$HOME/.florida_signal_mailchimp_env" <<EOF
export MAILCHIMP_API_KEY='$KEY'
export MAILCHIMP_SERVER_PREFIX='us2'
export MAILCHIMP_AUDIENCE_ID='123540d751'
EOF
echo "  Saved privately to your home folder."
echo "  Now click the Florida Signal Desk icon to relaunch — signups will sync."
sleep 4
