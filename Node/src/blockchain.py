# pylint: disable=W0201, R0913, C0301
"""Classes that define the blockchain functionality"""
import json
import time
from hashlib import sha256


class Block:
    """
    Class for individual blocks
    """
    def __init__(self, index, transactions, timestamp, previous_hash, nonce=0, difficulty=0, miner=""):
        self.index = index
        self.transactions = transactions
        self.timestamp = timestamp
        self.hash = None
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.difficulty = difficulty
        self.miner = miner

    def compute_hash(self):
        """
        A function that returns the hash of the block contents.
        """
        block_string = json.dumps(self.__dict__, sort_keys=True)
        return sha256(block_string.encode()).hexdigest()


class Blockchain:
    """
       Class that holds multiple blocks and aligns them by hash
    """
    difficulty = 4

    def __init__(self):
        self.unconfirmed_transactions = []
        self.chain = []

    def create_genesis_block(self):
        """
        A function that generates the genesis block and appends it to
        the chain. The block has index 0, previous_hash as 0, and
        a valid hash.
        """
        genesis_block = Block(0, [], time.time(), "0", difficulty=self.difficulty)
        genesis_block.hash = self.proof_of_work(genesis_block)
        self.chain.append(genesis_block)

    @property
    def last_block(self):
        """getter for last block"""
        return self.chain[-1]

    def add_block(self, block, proof):
        """
        A function that adds the block to the chain after verification.
        Verification includes:
            * Checking if the proof is valid.
            * The previous_hash referred in the block and the hash of
              latest block in the chain match.
        """
        previous_hash = self.last_block.hash if len(self.chain) > 0 else '0'
        if previous_hash != block.previous_hash:
            return False

        if not Blockchain.is_valid_proof(block, proof):
            return False

        block.hash = proof
        self.chain.append(block)
        return True

    @staticmethod
    def proof_of_work(block):
        """
        Function that tries different values of nonce to get a hash
        that satisfies the difficulty criteria.
        """
        block.nonce = 0
        computed_hash = block.compute_hash()
        while not computed_hash.startswith("0" * Blockchain.difficulty):
            block.nonce += 1
            computed_hash = block.compute_hash()

        return computed_hash

    def add_new_transaction(self, transaction):
        """Append new transactions to the stack"""
        transaction["hash"] = sha256(json.dumps(transaction).encode()).hexdigest()
        self.unconfirmed_transactions.append(transaction)
        return True

    @classmethod
    def is_valid_proof(cls, block, block_hash):
        """
        Check if block_hash is valid hash of block and satisfies
        the difficulty criteria.
        """
        return (block_hash.startswith("0" * Blockchain.difficulty) and
                block_hash == block.compute_hash())

    @classmethod
    def check_chain_validity(cls, chain) -> bool:
        """Test integrity of the blockchain"""
        result = True
        previous_hash = "0"

        for block in chain:
            block_hash = block["hash"] # stored hash to see if modified
            block["hash"] = ""
            if not cls.is_valid_proof(block, block_hash) or \
                    previous_hash != block["previous_hash"]:
                result = False
                break
            block["hash"], previous_hash = block_hash, block_hash

        return result

    def mine(self, miner) -> bool:
        """
        This function serves as an interface to add the pending
        transactions to the blockchain by adding them to the block
        and figuring out Proof Of Work.
        """
        if not self.unconfirmed_transactions:
            return False

        last_block = self.last_block
        new_block = Block(index=last_block.index + 1,
                          transactions=self.unconfirmed_transactions,
                          timestamp=time.time(),
                          previous_hash=last_block.hash,
                          difficulty=self.difficulty,
                          miner=miner)
        proof = self.proof_of_work(new_block)
        self.add_block(new_block, proof)
        self.unconfirmed_transactions = []

        return True
