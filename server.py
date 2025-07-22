from flask import Flask, render_template, send_from_directory
import os

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)

@app.route("/plots/<path:filename>")
def plot_files(filename):
    return send_from_directory("static", filename)

@app.route("/csv/<path:filename>")
def csv_files(filename):
    return send_from_directory("static", filename)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)
