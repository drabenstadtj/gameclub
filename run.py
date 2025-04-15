import threading
import subprocess
import os
import signal
import sys

def run_flask():
    from web_app.app import app
    app.run(debug=False, port=5000, use_reloader=False)

# Start Flask server in a thread
flask_thread = threading.Thread(target=run_flask)
flask_thread.daemon = True  # Let it shut down automatically with the main program
flask_thread.start()

# Start the bot process
bot_process = subprocess.Popen(
    [sys.executable, "bot/bot.py"],
    stdout=sys.stdout,
    stderr=sys.stderr
)

try:
    bot_process.wait()
except KeyboardInterrupt:
    print("\n[!] Shutting down...")
    bot_process.send_signal(signal.SIGINT)
    bot_process.terminate()
    bot_process.wait()

    # Flask will stop since it's a daemon thread
    print("[✓] Shutdown complete.")
    sys.exit(0)
