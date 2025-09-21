from flask import Flask, jsonify
from web3 import Web3

app = Flask(__name__)
w3 = Web3()

@app.route("/create_account", methods=["GET"])
def create_account():
    account = w3.eth.account.create()
    return jsonify({
        "address": account.address,
        "private_key": account.key.hex()
    })

if __name__ == "__main__":
    app.run(port=5000)
c