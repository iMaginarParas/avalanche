from web3 import Web3
import json

w3 = Web3(Web3.HTTPProvider("https://api.avax-test.network/ext/bc/C/rpc"))

# Convert to checksum address
contract_address = Web3.to_checksum_address("0xf44b769fa4e7b77e8e6070f91bea56ee59ee6236")

# Load ABI from file
with open("build/FreelanceEscrow.abi") as f:
    abi = json.load(f)

contract = w3.eth.contract(address=contract_address, abi=abi)
print("Contract loaded:", contract.address)
