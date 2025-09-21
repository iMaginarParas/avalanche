# FastAPI with Smart Contract Integration
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from enum import Enum
import asyncio
import uuid
from datetime import datetime, timedelta
import json
import os
from decimal import Decimal
import logging

# Web3 integration
from web3 import Web3
from web3.contract import Contract

app = FastAPI(title="Crypto Freelance Payment API with Smart Contract", version="2.0.0")
security = HTTPBearer()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
class Config:
    AVALANCHE_RPC_URL = "https://api.avax-test.network/ext/bc/C/rpc"  # Testnet
    PRIVATE_KEY = os.getenv("PRIVATE_KEY")  # Platform wallet private key
    CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS")  # Deployed escrow contract
    
    # Testnet stablecoin addresses
    USDC_ADDRESS = "0x5425890298aed601595a70AB815c96711a31Bc65"
    USDT_ADDRESS = "0x1f1E7c893855525b303f99bDf5c3c05BE09ca251"

config = Config()

# Your deployed contract address
DEPLOYED_CONTRACT_ADDRESS = "0xf44b769fa4e7b77e8e6070f91bea56ee59ee6236"

# Initialize Web3
w3 = Web3(Web3.HTTPProvider(config.AVALANCHE_RPC_URL))

# Smart Contract ABI (from the Solidity contract)
ESCROW_ABI = [
    {
        "inputs": [{"name": "_feeRecipient", "type": "address"}],
        "stateMutability": "nonpayable",
        "type": "constructor"
    },
    {
        "inputs": [
            {"name": "_freelancer", "type": "address"},
            {"name": "_amount", "type": "uint256"},
            {"name": "_token", "type": "address"},
            {"name": "_deadline", "type": "uint256"}
        ],
        "name": "createTask",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"name": "_taskId", "type": "uint256"}],
        "name": "fundTask",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [{"name": "_taskId", "type": "uint256"}],
        "name": "markDelivered",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"name": "_taskId", "type": "uint256"}],
        "name": "approveTask",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"name": "_taskId", "type": "uint256"}],
        "name": "getTask",
        "outputs": [
            {
                "components": [
                    {"name": "id", "type": "uint256"},
                    {"name": "client", "type": "address"},
                    {"name": "freelancer", "type": "address"},
                    {"name": "amount", "type": "uint256"},
                    {"name": "token", "type": "address"},
                    {"name": "status", "type": "uint8"},
                    {"name": "deadline", "type": "uint256"},
                    {"name": "createdAt", "type": "uint256"},
                    {"name": "fundedAt", "type": "uint256"},
                    {"name": "clientApproved", "type": "bool"},
                    {"name": "freelancerDelivered", "type": "bool"}
                ],
                "name": "",
                "type": "tuple"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"name": "_client", "type": "address"}],
        "name": "getClientTasks",
        "outputs": [{"name": "", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"name": "_freelancer", "type": "address"}],
        "name": "getFreelancerTasks",
        "outputs": [{"name": "", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "taskId", "type": "uint256"},
            {"indexed": True, "name": "client", "type": "address"},
            {"indexed": True, "name": "freelancer", "type": "address"},
            {"name": "amount", "type": "uint256"}
        ],
        "name": "TaskCreated",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "taskId", "type": "uint256"},
            {"name": "amount", "type": "uint256"}
        ],
        "name": "TaskFunded",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "taskId", "type": "uint256"},
            {"name": "freelancerAmount", "type": "uint256"},
            {"name": "platformFee", "type": "uint256"}
        ],
        "name": "TaskCompleted",
        "type": "event"
    }
]

# ERC20 ABI for token operations
ERC20_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    }
]

# Enums
class TaskStatus(int, Enum):
    CREATED = 0
    FUNDED = 1
    COMPLETED = 2
    DISPUTED = 3
    CANCELLED = 4

class CurrencyType(str, Enum):
    AVAX = "AVAX"
    USDC = "USDC"
    USDT = "USDT"

# Pydantic Models
class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    wallet_address: str
    email: Optional[str] = None
    is_freelancer: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)

class TaskCreate(BaseModel):
    title: str
    description: str
    amount: Decimal
    currency: CurrencyType
    freelancer_address: str
    deadline: datetime

class TaskResponse(BaseModel):
    id: int
    title: str
    description: str
    client_address: str
    freelancer_address: str
    amount: Decimal
    currency: CurrencyType
    status: TaskStatus
    deadline: datetime
    created_at: datetime
    funded_at: Optional[datetime] = None
    client_approved: bool = False
    freelancer_delivered: bool = False

class ContractInteractionRequest(BaseModel):
    task_id: int

# Helper Functions
def get_platform_account():
    """Get platform wallet account from private key"""
    if not config.PRIVATE_KEY:
        raise HTTPException(status_code=500, detail="Platform private key not configured")
    return w3.eth.account.from_key(config.PRIVATE_KEY)

def get_escrow_contract() -> Contract:
    """Get escrow contract instance"""
    return w3.eth.contract(address=DEPLOYED_CONTRACT_ADDRESS, abi=ESCROW_ABI)

def get_token_contract(currency: CurrencyType) -> Contract:
    """Get token contract instance"""
    if currency == CurrencyType.USDC:
        return w3.eth.contract(address=config.USDC_ADDRESS, abi=ERC20_ABI)
    elif currency == CurrencyType.USDT:
        return w3.eth.contract(address=config.USDT_ADDRESS, abi=ERC20_ABI)
    else:
        raise ValueError(f"Invalid token currency: {currency}")

def get_token_address(currency: CurrencyType) -> str:
    """Get token contract address"""
    if currency == CurrencyType.AVAX:
        return "0x0000000000000000000000000000000000000000"  # Zero address for AVAX
    elif currency == CurrencyType.USDC:
        return config.USDC_ADDRESS
    elif currency == CurrencyType.USDT:
        return config.USDT_ADDRESS
    else:
        raise ValueError(f"Invalid currency: {currency}")

def wei_to_ether(wei_amount: int) -> Decimal:
    """Convert wei to ether"""
    return Decimal(str(wei_amount)) / Decimal("1000000000000000000")

def ether_to_wei(ether_amount: Decimal) -> int:
    """Convert ether to wei"""
    return int(ether_amount * Decimal("1000000000000000000"))

def token_to_base_unit(amount: Decimal, decimals: int) -> int:
    """Convert token amount to base unit"""
    return int(amount * (10 ** decimals))

def parse_contract_task(contract_task, task_metadata: dict) -> TaskResponse:
    """Parse contract task data into TaskResponse"""
    return TaskResponse(
        id=contract_task[0],
        title=task_metadata.get("title", f"Task #{contract_task[0]}"),
        description=task_metadata.get("description", ""),
        client_address=contract_task[1],
        freelancer_address=contract_task[2],
        amount=wei_to_ether(contract_task[3]) if task_metadata.get("currency") == "AVAX" else Decimal(str(contract_task[3])) / Decimal("1000000"),  # Assuming 6 decimals for stablecoins
        currency=task_metadata.get("currency", "AVAX"),
        status=TaskStatus(contract_task[5]),
        deadline=datetime.fromtimestamp(contract_task[6]),
        created_at=datetime.fromtimestamp(contract_task[7]),
        funded_at=datetime.fromtimestamp(contract_task[8]) if contract_task[8] > 0 else None,
        client_approved=contract_task[9],
        freelancer_delivered=contract_task[10]
    )

# In-memory storage for task metadata (use database in production)
users_db: Dict[str, User] = {}
task_metadata_db: Dict[int, dict] = {}

# Authentication
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    """Get current user from token"""
    token = credentials.credentials
    wallet_address = token.lower()
    
    if not w3.is_address(wallet_address):
        raise HTTPException(status_code=401, detail="Invalid wallet address")
    
    if wallet_address not in users_db:
        user = User(wallet_address=wallet_address)
        users_db[wallet_address] = user
    
    return users_db[wallet_address]

# API Endpoints

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "Crypto Freelance Payment API with Smart Contract",
        "status": "running",
        "contract_address": config.CONTRACT_ADDRESS,
        "network": "Avalanche Fuji Testnet"
    }

@app.post("/users/register")
async def register_user(wallet_address: str, email: Optional[str] = None, is_freelancer: bool = False):
    """Register a new user"""
    wallet_address = wallet_address.lower()
    
    if not w3.is_address(wallet_address):
        raise HTTPException(status_code=400, detail="Invalid wallet address")
    
    if wallet_address in users_db:
        return users_db[wallet_address]
    
    user = User(
        wallet_address=wallet_address,
        email=email,
        is_freelancer=is_freelancer
    )
    
    users_db[wallet_address] = user
    return user

@app.post("/tasks/create")
async def create_task_instructions(
    task_data: TaskCreate,
    current_user: User = Depends(get_current_user)
):
    """Get instructions for creating a task on-chain"""
    if not w3.is_address(task_data.freelancer_address):
        raise HTTPException(status_code=400, detail="Invalid freelancer address")
    
    contract = get_escrow_contract()
    token_address = get_token_address(task_data.currency)
    
    # Convert amount to appropriate units
    if task_data.currency == CurrencyType.AVAX:
        amount_wei = ether_to_wei(task_data.amount)
    else:
        # Assuming 6 decimals for stablecoins
        amount_wei = token_to_base_unit(task_data.amount, 6)
    
    deadline_timestamp = int(task_data.deadline.timestamp())
    
    # Build transaction data
    function_call = contract.functions.createTask(
        task_data.freelancer_address,
        amount_wei,
        token_address,
        deadline_timestamp
    )
    
    # Estimate gas
    try:
        gas_estimate = function_call.estimate_gas({'from': current_user.wallet_address})
        gas_price = w3.eth.gas_price
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Transaction simulation failed: {str(e)}")
    
    return {
        "message": "Task creation instructions",
        "contract_address": config.CONTRACT_ADDRESS,
        "function_name": "createTask",
        "parameters": {
            "freelancer": task_data.freelancer_address,
            "amount": str(amount_wei),
            "token": token_address,
            "deadline": deadline_timestamp
        },
        "gas_estimate": gas_estimate,
        "gas_price": gas_price,
        "transaction_data": function_call.build_transaction({
            'from': current_user.wallet_address,
            'gas': gas_estimate,
            'gasPrice': gas_price,
            'nonce': w3.eth.get_transaction_count(current_user.wallet_address)
        })
    }

@app.post("/tasks/{task_id}/fund-instructions")
async def get_fund_instructions(
    task_id: int,
    current_user: User = Depends(get_current_user)
):
    """Get instructions for funding a task"""
    try:
        contract = get_escrow_contract()
        task_data = contract.functions.getTask(task_id).call()
        
        if task_data[1].lower() != current_user.wallet_address.lower():
            raise HTTPException(status_code=403, detail="Only task client can fund")
        
        if task_data[5] != TaskStatus.CREATED.value:
            raise HTTPException(status_code=400, detail="Task is not in created status")
        
        # Get task metadata
        metadata = task_metadata_db.get(task_id, {})
        currency = metadata.get("currency", "AVAX")
        amount = task_data[3]
        
        if currency == "AVAX":
            # For AVAX, send value with transaction
            function_call = contract.functions.fundTask(task_id)
            gas_estimate = function_call.estimate_gas({
                'from': current_user.wallet_address,
                'value': amount
            })
            
            transaction_data = function_call.build_transaction({
                'from': current_user.wallet_address,
                'value': amount,
                'gas': gas_estimate,
                'gasPrice': w3.eth.gas_price,
                'nonce': w3.eth.get_transaction_count(current_user.wallet_address)
            })
            
            return {
                "message": "AVAX funding instructions",
                "contract_address": config.CONTRACT_ADDRESS,
                "function_name": "fundTask",
                "amount_avax": wei_to_ether(amount),
                "transaction_data": transaction_data
            }
        
        else:
            # For tokens, need approval first
            token_address = get_token_address(CurrencyType(currency))
            token_contract = get_token_contract(CurrencyType(currency))
            
            # Check current allowance
            allowance = token_contract.functions.allowance(
                current_user.wallet_address,
                config.CONTRACT_ADDRESS
            ).call()
            
            instructions = []
            
            if allowance < amount:
                # Need approval transaction first
                approve_call = token_contract.functions.approve(config.CONTRACT_ADDRESS, amount)
                approve_gas = approve_call.estimate_gas({'from': current_user.wallet_address})
                
                approve_tx = approve_call.build_transaction({
                    'from': current_user.wallet_address,
                    'gas': approve_gas,
                    'gasPrice': w3.eth.gas_price,
                    'nonce': w3.eth.get_transaction_count(current_user.wallet_address)
                })
                
                instructions.append({
                    "step": 1,
                    "description": f"Approve {currency} spending",
                    "contract_address": token_address,
                    "function_name": "approve",
                    "transaction_data": approve_tx
                })
            
            # Fund task transaction
            fund_call = contract.functions.fundTask(task_id)
            fund_gas = fund_call.estimate_gas({'from': current_user.wallet_address})
            
            fund_tx = fund_call.build_transaction({
                'from': current_user.wallet_address,
                'gas': fund_gas,
                'gasPrice': w3.eth.gas_price,
                'nonce': w3.eth.get_transaction_count(current_user.wallet_address) + (1 if allowance < amount else 0)
            })
            
            instructions.append({
                "step": 2 if allowance < amount else 1,
                "description": "Fund the task",
                "contract_address": config.CONTRACT_ADDRESS,
                "function_name": "fundTask",
                "transaction_data": fund_tx
            })
            
            return {
                "message": f"{currency} funding instructions",
                "currency": currency,
                "amount": amount,
                "current_allowance": allowance,
                "instructions": instructions
            }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get funding instructions: {str(e)}")

@app.post("/tasks/{task_id}/deliver")
async def mark_delivered_instructions(
    task_id: int,
    current_user: User = Depends(get_current_user)
):
    """Get instructions for marking task as delivered"""
    try:
        contract = get_escrow_contract()
        task_data = contract.functions.getTask(task_id).call()
        
        if task_data[2].lower() != current_user.wallet_address.lower():
            raise HTTPException(status_code=403, detail="Only freelancer can mark as delivered")
        
        if task_data[5] != TaskStatus.FUNDED.value:
            raise HTTPException(status_code=400, detail="Task is not funded")
        
        function_call = contract.functions.markDelivered(task_id)
        gas_estimate = function_call.estimate_gas({'from': current_user.wallet_address})
        
        transaction_data = function_call.build_transaction({
            'from': current_user.wallet_address,
            'gas': gas_estimate,
            'gasPrice': w3.eth.gas_price,
            'nonce': w3.eth.get_transaction_count(current_user.wallet_address)
        })
        
        return {
            "message": "Mark delivered instructions",
            "contract_address": config.CONTRACT_ADDRESS,
            "function_name": "markDelivered",
            "transaction_data": transaction_data
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get delivery instructions: {str(e)}")

@app.post("/tasks/{task_id}/approve")
async def approve_task_instructions(
    task_id: int,
    current_user: User = Depends(get_current_user)
):
    """Get instructions for approving task completion"""
    try:
        contract = get_escrow_contract()
        task_data = contract.functions.getTask(task_id).call()
        
        if task_data[1].lower() != current_user.wallet_address.lower():
            raise HTTPException(status_code=403, detail="Only client can approve task")
        
        if task_data[5] != TaskStatus.FUNDED.value:
            raise HTTPException(status_code=400, detail="Task is not funded")
        
        function_call = contract.functions.approveTask(task_id)
        gas_estimate = function_call.estimate_gas({'from': current_user.wallet_address})
        
        transaction_data = function_call.build_transaction({
            'from': current_user.wallet_address,
            'gas': gas_estimate,
            'gasPrice': w3.eth.gas_price,
            'nonce': w3.eth.get_transaction_count(current_user.wallet_address)
        })
        
        return {
            "message": "Approve task instructions",
            "contract_address": config.CONTRACT_ADDRESS,
            "function_name": "approveTask",
            "transaction_data": transaction_data
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get approval instructions: {str(e)}")

@app.post("/tasks/{task_id}/metadata")
async def update_task_metadata(
    task_id: int,
    title: str,
    description: str,
    currency: CurrencyType,
    current_user: User = Depends(get_current_user)
):
    """Update task metadata (stored off-chain)"""
    try:
        contract = get_escrow_contract()
        task_data = contract.functions.getTask(task_id).call()
        
        if task_data[1].lower() != current_user.wallet_address.lower():
            raise HTTPException(status_code=403, detail="Only task client can update metadata")
        
        task_metadata_db[task_id] = {
            "title": title,
            "description": description,
            "currency": currency.value
        }
        
        return {
            "message": "Task metadata updated",
            "task_id": task_id,
            "metadata": task_metadata_db[task_id]
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update metadata: {str(e)}")

@app.get("/tasks/{task_id}")
async def get_task(
    task_id: int,
    current_user: User = Depends(get_current_user)
):
    """Get task details"""
    try:
        contract = get_escrow_contract()
        task_data = contract.functions.getTask(task_id).call()
        
        # Check if user is authorized to view this task
        if current_user.wallet_address.lower() not in [task_data[1].lower(), task_data[2].lower()]:
            raise HTTPException(status_code=403, detail="Not authorized to view this task")
        
        metadata = task_metadata_db.get(task_id, {})
        
        return {
            "id": task_data[0],
            "client": task_data[1],
            "freelancer": task_data[2],
            "amount": str(task_data[3]),
            "token_address": task_data[4],
            "status": TaskStatus(task_data[5]).name,
            "deadline": datetime.fromtimestamp(task_data[6]).isoformat(),
            "created_at": datetime.fromtimestamp(task_data[7]).isoformat(),
            "funded_at": datetime.fromtimestamp(task_data[8]).isoformat() if task_data[8] > 0 else None,
            "client_approved": task_data[9],
            "freelancer_delivered": task_data[10],
            "metadata": metadata
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get task: {str(e)}")

@app.get("/tasks/my")
async def get_my_tasks(current_user: User = Depends(get_current_user)):
    """Get tasks for current user"""
    try:
        contract = get_escrow_contract()
        
        # Get tasks where user is client
        client_task_ids = contract.functions.getClientTasks(current_user.wallet_address).call()
        
        # Get tasks where user is freelancer
        freelancer_task_ids = contract.functions.getFreelancerTasks(current_user.wallet_address).call()
        
        all_task_ids = list(set(client_task_ids + freelancer_task_ids))
        
        tasks = []
        for task_id in all_task_ids:
            try:
                task_data = contract.functions.getTask(task_id).call()
                metadata = task_metadata_db.get(task_id, {})
                
                task_info = {
                    "id": task_data[0],
                    "client": task_data[1],
                    "freelancer": task_data[2],
                    "amount": str(task_data[3]),
                    "token_address": task_data[4],
                    "status": TaskStatus(task_data[5]).name,
                    "deadline": datetime.fromtimestamp(task_data[6]).isoformat(),
                    "created_at": datetime.fromtimestamp(task_data[7]).isoformat(),
                    "funded_at": datetime.fromtimestamp(task_data[8]).isoformat() if task_data[8] > 0 else None,
                    "client_approved": task_data[9],
                    "freelancer_delivered": task_data[10],
                    "metadata": metadata,
                    "user_role": "client" if task_data[1].lower() == current_user.wallet_address.lower() else "freelancer"
                }
                tasks.append(task_info)
            except Exception as e:
                logger.warning(f"Failed to get task {task_id}: {e}")
        
        return {"tasks": tasks}
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get tasks: {str(e)}")

@app.get("/contract/info")
async def get_contract_info():
    """Get contract information"""
    if not config.CONTRACT_ADDRESS:
        raise HTTPException(status_code=500, detail="Contract not deployed")
    
    try:
        contract = get_escrow_contract()
        
        # Get some basic contract info (you'd need to add these view functions to the contract)
        return {
            "contract_address": config.CONTRACT_ADDRESS,
            "network": "Avalanche Fuji Testnet",
            "supported_tokens": {
                "AVAX": "0x0000000000000000000000000000000000000000",
                "USDC": config.USDC_ADDRESS,
                "USDT": config.USDT_ADDRESS
            },
            "platform_fee": "2.5%"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get contract info: {str(e)}")

@app.get("/setup/deployment-script")
async def get_deployment_script():
    """Get deployment script for the smart contract"""
    return {
        "message": "Smart contract deployment script",
        "deployment_script": """
# Smart Contract Deployment Script

## Prerequisites:
1. Install dependencies:
   npm install @openzeppelin/contracts
   npm install hardhat @nomicfoundation/hardhat-toolbox

## Hardhat Config (hardhat.config.js):
require("@nomicfoundation/hardhat-toolbox");
require('dotenv').config();

module.exports = {
  solidity: "0.8.19",
  networks: {
    fuji: {
      url: "https://api.avax-test.network/ext/bc/C/rpc",
      accounts: [process.env.PRIVATE_KEY]
    }
  }
};

## Deploy Script (scripts/deploy.js):
const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deploying with account:", deployer.address);

  const FreelanceEscrow = await hre.ethers.getContractFactory("FreelanceEscrow");
  const escrow = await FreelanceEscrow.deploy(deployer.address); // Fee recipient

  await escrow.deployed();
  console.log("FreelanceEscrow deployed to:", escrow.address);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

## Deploy Command:
npx hardhat run scripts/deploy.js --network fuji

## After deployment, set the CONTRACT_ADDRESS environment variable!
        """,
        "environment_variables": {
            "PRIVATE_KEY": "your_private_key_here",
            "CONTRACT_ADDRESS": "deployed_contract_address_here"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)