import hashlib
import json
import requests

from datetime import time
from urllib.parse import urlparse
from uuid import uuid4

from flask import Flask, jsonify, request


class BlockChain(object):
    def __init__(self):
        self.chain = []
        self.current_transactions = []
        self.nodes = set()

        # genesis block
        self.new_block(previous_hash=1, proof=100)

    def new_block(self, proof, previous_hash=None):
        block = {
            'index': len(self.chain) + 1,
            'timestamp': str(time()),
            'transactions': self.current_transactions[:],
            'proof': proof,
            'previous_hash': previous_hash or self.hash(self.chain[-1])
        }
        self.chain.append(block)
        return block

    def new_transaction(self, sender, recipient, amount):
        self.current_transactions.append({
            'sender': sender,
            'recipient': recipient,
            'amount': amount
        })
        return self.last_block['index'] + 1

    def proof_of_work(self, last_proof):
        """
        Simplified version. Find a number p, such that hash(p*last_proof) ends with 4 zeros
        :param last_proof:
        :return:
        """
        proof = 0
        while self.is_valid_proof(proof*last_proof) is False:
            proof += 1
        return proof

    @staticmethod
    def is_valid_proof(number):
        return (hashlib.sha256(str(number).encode()).hexdigest())[:4] == "0000"

    def register_node(self, address):
        self.nodes.add(urlparse(address).netloc)

    def valid_chain(self, chain):
        """
        Validates chain by checking hash & proof.
        :param chain:
        :return:
        """
        last_block = chain[0]

        for block in chain[1:]:
            if block['previous_hash'] != self.hash(last_block):
                print("Mismatch of hashes", block, last_block, self.hash(last_block))
                return False
            if not self.is_valid_proof(block['proof']*last_block['proof']):
                print("Mismatch of proofs", block, last_block)
                return False
            last_block = block

        return True

    def resolve_conflicts(self):
        """
        Consensus mechanism for ensuring that longest chain always wins
        :return:
        """
        max_chain = len(self.chain)
        new_chain_found = False

        for neighbor in self.nodes:
            response = requests.get('http://' + neighbor + '/chain')
            if response.status_code != 200 or response.json()['length'] < max_chain:
                continue

            cur_chain = response.json()['chain']

            if self.valid_chain(cur_chain):
                self.chain = cur_chain
                new_chain_found = True

        return new_chain_found

    @staticmethod
    def hash(block):
        # As hash depends on ordering of result in json.dumps, we added sort_keys
        block_string = json.dumps(block, sort_keys=True, indent=4, default=str).encode()
        return hashlib.sha256(block_string).hexdigest()

    @property
    def last_block(self):
        return self.chain[-1]

# Instantiate our Node

app = Flask(__name__)

node_identifier = str(uuid4()).replace('-', '')

blockchain = BlockChain()


@app.route('/mine', methods=['GET'])
def mine():
    last_block = blockchain.last_block
    last_proof = last_block['proof']
    proof = blockchain.proof_of_work(last_proof)
    blockchain.new_transaction(
        sender="0",
        recipient=node_identifier,
        amount=1
    )

    block = blockchain.new_block(proof, blockchain.hash(last_block))

    response = {
        'message': 'New block forged',
        'index': block['index'],
        'transactions': block['transactions'],
        'proof': block['proof'],
        'previous_hash': block['previous_hash']
    }

    return jsonify(response), 200


@app.route('/transactions/new', methods=['GET'])
def new_transaction():
    values = request.get_json()
    required = ['sender', 'recipient', 'amount']

    if not all(k in values for k in required):
        return "Missing Values", 400

    # Create a new transaction
    index = blockchain.new_transaction(values['sender'], values['recipient'], values['amount'])
    response = {'message': 'Transaction will be added to Block ' + str(index)}
    return jsonify(response), 201


@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain)
    }
    return jsonify(response), 200


@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values = request.get_json()
    nodes = values.get('nodes')

    if nodes is None:
        return "Error: Please supply a valid list of nodes", 400

    for node in nodes:
        blockchain.register_node(node)

    response = {
        'message': 'New nodes have been added!',
        'total_nodes': list(blockchain.nodes)
    }

    return jsonify(response), 201


@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = blockchain.resolve_conflicts()
    result = "New chain detected" if replaced else "Old chain retained!"
    return jsonify({'message': result, 'chain': blockchain.chain}), 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)

