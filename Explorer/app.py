"""
export FLASK_APP=app.py
export FLASK_DEBUG=1
flask run --port 5000

or just python app.py
"""
# pylint: disable=global-statement, line-too-long, invalid-name

import datetime
import json
from http import HTTPStatus
import random

import requests
from flask import Flask, redirect, render_template, request

app = Flask(__name__)

CONNECTED_NODE_ADDRESS = "http://127.0.0.1:8000" # main node

blockchain_copy = {
  "length": 0,
  "chain": [],
  "peer_list": []
}

def get_blockchain_data():
    """
    Function that queries the most recent blockchain data
    """
    try:
        response = requests.get(f"{CONNECTED_NODE_ADDRESS}/chain", timeout=3)
        if response.status_code == HTTPStatus.OK:
            chain = json.loads(response.json())
            global blockchain_copy
            if chain["length"] == blockchain_copy["length"]:
                return
            blockchain_copy = chain
    except Exception: # too generic i know...
        pass


def get_latest_blocks() -> list:
    """
    returns the 10 most recent blocks
    """
    return sorted(blockchain_copy["chain"],
                  key=lambda k: k["index"],
                  reverse=True)[:10]


def get_peer_list() -> list:
    """
    returns the current peer list
    (should be a separate route on the nodes though...)
    """
    return blockchain_copy["peer_list"]


# Flask routes
@app.route("/")
def index():
    """
    landing page for the explorer
    shows:
      - current stats of the network
      - last 10 blocks
    """
    get_blockchain_data()
    return render_template("index.html",
                           blocks=get_latest_blocks(),
                           blocks_len=len(blockchain_copy["chain"]),
                           txn_len=sum(i for i in list(map(lambda x: len(x["transactions"]), blockchain_copy["chain"])))
                           )


@app.route("/add")
def blockchain_landing():
    return render_template("submit.html", peers=get_peer_list())


@app.route("/peers")
def peer_list():
    return render_template("peers.html", peers=get_peer_list())


@app.route("/block/<int:block_id>")
def show_block(block_id):
    block = next(x for x in blockchain_copy["chain"] if x["index"] == block_id)
    blockdata = {
      "ID / Height": block["index"],
      "Timestamp": timestamp_to_string(block["timestamp"]),
      "Hash": block["hash"],
      "Previous Hash": block["previous_hash"],
      "Transactions": len(block["transactions"]),
      "Difficulty": block["difficulty"],
      "Miner": block["miner"]
    }
    return render_template("block.html",
                           blockdata=blockdata,
                           transactions=list(map(lambda x: x["hash"], block["transactions"])),
                           index=block["index"],
                           last=block["index"] == blockchain_copy["length"] - 1)


@app.route("/txn/<txn_hash>")
def show_txn(txn_hash=None):
    transactions = list(map(lambda x: x["transactions"], blockchain_copy["chain"]))
    flat_transactions = [item for sublist in transactions for item in sublist]
    transaction = next(x for x in flat_transactions if x["hash"] == txn_hash)
    txdata = {
      "Timestamp": timestamp_to_string(transaction["timestamp"]),
      "Author": transaction["author"],
      "Content": transaction["content"],
      "Hash": transaction["hash"]
    }
    return render_template("txn.html", txn=txdata)


@app.route("/submit", methods=["POST"])
def submit_textarea():
    """
    Endpoint to create a new transaction via our application.
    This endpoint would not be here for the final product as
    the explorer should only output data from the network
    """
    if not bool(request.form["author"]) or not bool(request.form["content"]):
        return redirect("/add")
    post_content = request.form["content"]
    author = request.form["author"]

    # Submit a transaction
    connected_node = random.choice(blockchain_copy["peer_list"])
    if bool(request.form["node"]):
        connected_node = request.form["node"]
    requests.post(url=f"{connected_node}/new_transaction",
                  json={ "author": author, "content": post_content },
                  headers={"Content-type": "application/json"},
                  timeout=3)

    return redirect("/add")


def timestamp_to_string(epoch_time):
    """helper function for time formatting"""
    return datetime.datetime.fromtimestamp(epoch_time).strftime("%Y-%m-%d %H:%M:%S")

if __name__ == '__main__':
    app.run(port=5000)
