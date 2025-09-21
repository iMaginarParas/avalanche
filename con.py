from fastapi import FastAPI
from web3 import Web3

app = FastAPI()
w3 = Web3(Web3.HTTPProvider("https://mainnet.infura.io/v3/YOUR_INFURA_KEY"))
contract_address = "0xf44b769fa4e7b77e8e6070f91bea56ee59ee6236"
abi = [...]  # Contract ABI

contract = w3.eth.contract(address=contract_address, abi=abi)

@app.get("/check-balance/{address}")
def check_balance(address: str):
    try:
        return {"balance": contract.functions.balanceOf(address).call()}
    except Exception as e:
        return {"error": str(e)}
