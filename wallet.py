from web3 import Web3

# Connect to Fuji Testnet RPC
w3 = Web3(Web3.HTTPProvider("https://api.avax-test.network/ext/bc/C/rpc"))

address = "0x431f29378432579D7dbFdd6A69a091076C5b7a75"  # your wallet address

balance = w3.eth.get_balance(address)
print("Balance in AVAX:", w3.from_wei(balance, "ether"))
