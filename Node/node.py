"""Node/Miner Endpoint"""
# pylint: disable=global-statement, line-too-long, invalid-name, E1121
import json
import random
import sys
import threading
import time
from hashlib import sha224
from http import HTTPStatus

import hug
import requests

from src.blockchain import Block, Blockchain
from src.util import Proxy_request

address = "127.0.0.1"
port = 8000
random.seed(time.time())
nonce = str(random.random())
node_hash = None

@hug.not_found()
def not_found_handler():
    """
    Handler for undefined requests
    (mostly there to prevent unforseen stuff)
    """
    return "Not Found"

# Init Blockchain
blockchain = Blockchain()
blockchain.create_genesis_block()
peers = set()

@hug.post("/new_transaction")
def new_transaction(author, content) -> tuple:
    """
    Endpoint to add a new transaction based on required fields.
    """
    if not author or not content:
        return "Invalid transaction data", HTTPStatus.BAD_REQUEST

    transaction = {
      "author":author,
      "content": content,
      "timestamp": time.time()
    }

    res = blockchain.add_new_transaction(transaction)
    if res:
        return "Success", HTTPStatus.CREATED
    return "Not allowed", HTTPStatus.FORBIDDEN


### API ###
@hug.get("/chain")
def get_chain() -> object:
    """
    Endpoint to return the current nodes copy of the chain.

    Returns:
        JSON: Blockchain data
    """
    chain_data = []
    for block in blockchain.chain:
        chain_data.append(block.__dict__)
    return json.dumps({"length": len(chain_data),
                       "chain": chain_data,
                       "peer_list": list(peers)})


@hug.post("/register_node")
def register_new_peers(node_address):
    """
    Endpoint to add new peers to the network
    """
    if not node_address:
        return "Invalid data", HTTPStatus.BAD_REQUEST
    peers.add(node_address)
    return get_chain()


@hug.post("/register_with")
def register_with_existing_node(request, node_address):
    """
    Internally calls the `register_node` endpoint to
    register current node with the node specified in the
    request, and sync the blockchain as well as peer data.
    """
    if not node_address:
        return "Invalid data", HTTPStatus.BAD_REQUEST
    data = {"node_address": f"http://{request.host}:{request.port}"}
    response = requests.post(node_address + "/register_node",
                             data=json.dumps(data),
                             headers={"Content-Type": "application/json"},
                             timeout=3)
    if response.status_code == HTTPStatus.OK:
        data = json.loads(response.json())
        global blockchain
        blockchain = create_chain_from_dump(data["chain"])
        peers.update(data["peer_list"])
        return "Registration successful", HTTPStatus.OK
    return response.content, response.status_code


@hug.post("/add_block")
def verify_and_add_block(blockdump):
    """
    Endpoint to add a block mined by someone else to the node's chain.
    The block is first verified by the node and then added to the chain.
    """
    block = Block(blockdump["index"],
                  blockdump["transactions"],
                  blockdump["timestamp"],
                  blockdump["previous_hash"],
                  blockdump["nonce"],
                  blockdump["difficulty"],
                  blockdump["miner"]
                  )
    proof = blockdump["hash"]
    added = blockchain.add_block(block, proof)

    if not added:
        return "The block was discarded by the node", HTTPStatus.FORBIDDEN
    return "Block added to the chain", HTTPStatus.CREATED


@hug.get("/pending_tx")
def get_pending_tx():
    """Endpoint to query unconfirmed transactions"""
    return json.dumps(blockchain.unconfirmed_transactions)


### internally used functions ###
def create_chain_from_dump(chain_dump) -> Blockchain:
    """
    Function to generate a new blockchain from the response of another node

    Args:
        chain_dump (list): List of Block Objects
    Raises:
        Exception: Raised if chain has been tampered with
    Returns:
        Blockchain: newly generated Blockchain
    """
    generated_blockchain = Blockchain()
    for idx, block_data in enumerate(chain_dump):
        block = Block(block_data["index"],
                      block_data["transactions"],
                      block_data["timestamp"],
                      "0" if idx == 0 else block_data["previous_hash"],
                      block_data["nonce"],
                      block_data["difficulty"],
                      block_data["miner"]
                      )
        proof = block_data["hash"]
        added = generated_blockchain.add_block(block, proof)
        if not added:
            raise Exception("The chain dump has been tampered with!")
    return generated_blockchain


def consensus() -> bool:
    """
    If a longer valid chain is found,
    the current chain is simply replaced with it.
    """
    global blockchain
    longest_chain = None
    current_len = len(blockchain.chain)

    for node in peers:
        if node == f"http://{address}:{port}":
            continue # skip self
        response = requests.get(f"{node}/chain", timeout=10)
        data = json.loads(response.json())
        length = data["length"]
        chain = data["chain"]
        if length > current_len and blockchain.check_chain_validity(chain): # check validity geht nicht
            current_len = length
            longest_chain = chain

    if longest_chain:
        blockchain = longest_chain


def announce_new_block(block):
    """
    A function to announce to the network once a block has been mined.
    Other blocks can simply verify the proof of work and add it to their
    respective chains.
    """
    for peer in peers:
        if peer == f"http://{address}:{port}":
            continue # skip self
        requests.post(url=f"{peer}/add_block",
                      data=json.dumps({"blockdump": block.__dict__}),
                      headers={"Content-Type": "application/json"},
                      timeout=5)


def startup_script(server_port):
    """
    Starts the server.
    If the port is not the default port (8000) the server will try to
    register itself with the main node.

    Args:
        server_port (int): Application port on which the server will be hosted
    """
    own_address = f"http://{address}:{server_port}"
    main_node = "http://127.0.0.1:8000"
    node_string = own_address + nonce
    global node_hash
    node_hash = sha224(node_string.encode()).hexdigest()
    peers.add(own_address)
    if server_port != 8000:
        request_data = Proxy_request(address, server_port)
        register_with_existing_node(request_data, main_node)
        # make oneself known
        for peer in peers:
            if peer not in (own_address, main_node):
                requests.post(
                    url=f"{peer}/update_peers",
                    data=json.dumps({"node_address": own_address}),
                    headers={"Content-Type": "application/json"},
                    timeout=5)
    # start mining in parallel
    mining_threat = threading.Thread(target=local_mining)
    mining_threat.daemon=True
    mining_threat.start()
    # final step ist to start the server
    hug.API(__name__).http.serve(port=server_port, display_intro=False)


@hug.post("/update_peers")
def update_peer_list(node_address):
    """
    stupidly adds an ip to the peer list (needs authentication)

    Args:
        node_address (str): address to be added
    """
    if not node_address:
        return "Invalid data", HTTPStatus.BAD_REQUEST
    peers.update({node_address})


def local_mining():
    """
    If unconfirmed transactions exist, try to mine a block.
    Tries every n seconds and on success automatically
    syncs with the other nodes
    """
    while True:
        time.sleep(random.randint(5,9))
        transactions = blockchain.mine(node_hash)
        if not transactions:
            continue
        # find longest chain & announce new block to all peers
        chain_length = len(blockchain.chain)
        consensus()
        if chain_length == len(blockchain.chain):
            announce_new_block(blockchain.last_block)
        print(f"Block #{blockchain.last_block.index} is mined by '{node_hash}'.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    startup_script(port)
