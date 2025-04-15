import threading
import subprocess
import os
import signal
import sys

def run_flask():
    # Run the Flask app using Gunicorn in production mode
    subprocess.run([
        sys.executable, "-m", "gunicorn",
        "-w", "4",
        "-b", "0.0.0.0:5000",
        "wsgi:app"
    ])

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
    print("[✓] Shutdown complete.")
    sys.exit(0)
