from flask import Flask, request, jsonify
import subprocess

app = Flask(__name__)

@app.route('/run-ab', methods=['POST'])
def run_ab():
    data = request.json
    url = data.get('url')
    total_requests = data.get('total_requests', 1000)
    concurrency = data.get('concurrency', 10)

    ab_command = f"ab -n {total_requests} -c {concurrency} {url}"
    
    try:
        result = subprocess.run(ab_command, shell=True, check=True, text=True, capture_output=True)
        return jsonify({"output": result.stdout})
    except subprocess.CalledProcessError as e:
        return jsonify({"error": e.output}), 500

