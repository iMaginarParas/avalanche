# FastAPI with Smart Contract Integration - Updated Version
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
class Config:
    AVALANCHE_RPC_URL = os.getenv("AVALANCHE_RPC_URL", "https://api.avax-test.network/ext/bc/C/rpc")
    PRIVATE_KEY = os.getenv("PRIVATE_KEY")
    CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "0xf44b769fa4e7b77e8e6070f91bea56ee59ee6236")
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    
    # Testnet stablecoin addresses
    USDC_ADDRESS = "0x5425890298aed601595a70AB815c96711a31Bc65"
    USDT_ADDRESS = "0x1f1E7c893855525b303f99bDf5c3c05BE09ca251"

config = Config()

# Create FastAPI app with conditional settings
if config.ENVIRONMENT == "production":
    app = FastAPI(
        title="Crypto Freelance Payment API",
        version="2.0.0",
        description="Blockchain-based freelance payment system with smart contract escrow",
        docs_url="/docs",
        redoc_url="/redoc"
    )
else:
    app = FastAPI(
        title="Crypto Freelance Payment API with Smart Contract", 
        version="2.0.0",
        description="Blockchain-based freelance payment system with smart contract escrow"
    )

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if config.ENVIRONMENT != "production" else ["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# Initialize Web3
try:
    w3 = Web3(Web3.HTTPProvider(config.AVALANCHE_RPC_URL))
    if not w3.is_connected():
        logger.error("Failed to connect to Avalanche network")
    else:
        logger.info(f"Connected to Avalanche network. Latest block: {w3.eth.block_number}")
except Exception as e:
    logger.error(f"Web3 connection error: {e}")
    w3 = None

# Smart Contract ABI (from the Solidity contract)
ESCROW_ABI = [
    {
        "inputs": [{"name": "_feeRecipient", "type": "address"}],
        "stateMutability": "nonpayable",
        "type": "constructor"
    },
    {
        "inputs": [],
        "name": "taskCounter",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
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
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
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
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=2000)
    amount: Decimal = Field(..., gt=0)
    currency: CurrencyType
    freelancer_address: str
    deadline: datetime

    class Config:
        json_encoders = {
            Decimal: str
        }

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

    class Config:
        json_encoders = {
            Decimal: str
        }

class ContractInteractionRequest(BaseModel):
    task_id: int

class UserRegistration(BaseModel):
    wallet_address: str
    email: Optional[str] = None
    is_freelancer: bool = False

class TaskMetadata(BaseModel):
    title: str
    description: str
    currency: CurrencyType

# Helper Functions with Improved Error Handling
def get_platform_account():
    """Get platform wallet account from private key"""
    if not config.PRIVATE_KEY:
        raise HTTPException(status_code=500, detail="Platform private key not configured")
    try:
        return w3.eth.account.from_key(config.PRIVATE_KEY)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Invalid private key: {str(e)}")

def get_escrow_contract() -> Contract:
    """Get escrow contract instance with better error handling"""
    if not w3:
        logger.error("Web3 not connected")
        raise HTTPException(status_code=500, detail="Web3 not connected")
    
    if not w3.is_connected():
        logger.error("Web3 connection lost")
        raise HTTPException(status_code=500, detail="Web3 connection lost")
    
    if not config.CONTRACT_ADDRESS:
        logger.error("Contract address not configured")
        raise HTTPException(status_code=500, detail="Contract address not configured")
    
    try:
        # Validate contract address format
        if not w3.is_address(config.CONTRACT_ADDRESS):
            raise ValueError("Invalid contract address format")
        
        contract = w3.eth.contract(address=config.CONTRACT_ADDRESS, abi=ESCROW_ABI)
        
        # Test the contract by calling a simple view function
        try:
            task_counter = contract.functions.taskCounter().call()
            logger.debug(f"Contract connection verified: {config.CONTRACT_ADDRESS}, task counter: {task_counter}")
        except Exception as test_error:
            logger.error(f"Contract test call failed: {test_error}")
            # Still return the contract instance, just warn about the test failure
            logger.warning(f"Contract might not be deployed or accessible: {test_error}")
        
        return contract
    except Exception as e:
        logger.error(f"Failed to connect to contract: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to connect to contract: {str(e)}")

def get_token_contract(currency: CurrencyType) -> Contract:
    """Get token contract instance with better error handling"""
    if not w3:
        raise HTTPException(status_code=500, detail="Web3 not connected")
    
    if not w3.is_connected():
        raise HTTPException(status_code=500, detail="Web3 connection lost")
    
    try:
        if currency == CurrencyType.USDC:
            address = config.USDC_ADDRESS
        elif currency == CurrencyType.USDT:
            address = config.USDT_ADDRESS
        else:
            raise ValueError(f"Invalid token currency: {currency}")
        
        if not w3.is_address(address):
            raise ValueError(f"Invalid token address for {currency}: {address}")
        
        contract = w3.eth.contract(address=address, abi=ERC20_ABI)
        
        # Test the contract by calling decimals (most ERC20 tokens have this)
        try:
            decimals = contract.functions.decimals().call()
            logger.debug(f"Token contract connection verified: {currency} at {address}, decimals: {decimals}")
        except Exception as test_error:
            logger.warning(f"Token contract test failed for {currency}: {test_error}")
            # Don't raise exception here as some tokens might not implement all functions
        
        return contract
    except Exception as e:
        logger.error(f"Failed to get token contract for {currency}: {e}")
        raise ValueError(f"Failed to get token contract for {currency}: {str(e)}")

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

def base_unit_to_token(base_amount: int, decimals: int) -> Decimal:
    """Convert base unit to token amount"""
    return Decimal(str(base_amount)) / Decimal(str(10 ** decimals))

def parse_contract_task(contract_task, task_metadata: dict) -> TaskResponse:
    """Parse contract task data into TaskResponse"""
    currency = task_metadata.get("currency", "AVAX")
    
    if currency == "AVAX":
        amount = wei_to_ether(contract_task[3])
    else:
        # Assuming 6 decimals for stablecoins
        amount = base_unit_to_token(contract_task[3], 6)
    
    return TaskResponse(
        id=contract_task[0],
        title=task_metadata.get("title", f"Task #{contract_task[0]}"),
        description=task_metadata.get("description", ""),
        client_address=contract_task[1],
        freelancer_address=contract_task[2],
        amount=amount,
        currency=currency,
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

# Improved Authentication
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    """Get current user from token (wallet address) with improved error handling"""
    try:
        token = credentials.credentials
        if not token:
            raise HTTPException(status_code=401, detail="No authentication token provided")
        
        wallet_address = token.lower()
        
        # Validate wallet address format
        if not wallet_address.startswith('0x') or len(wallet_address) != 42:
            raise HTTPException(status_code=401, detail="Invalid wallet address format")
        
        if w3 and not w3.is_address(wallet_address):
            raise HTTPException(status_code=401, detail="Invalid wallet address")
        
        # Get or create user
        if wallet_address not in users_db:
            user = User(wallet_address=wallet_address)
            users_db[wallet_address] = user
            logger.info(f"New user created in session: {wallet_address}")
        
        return users_db[wallet_address]
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

# API Endpoints

@app.get("/")
async def root():
    """Health check endpoint"""
    try:
        web3_status = "connected" if w3 and w3.is_connected() else "disconnected"
        latest_block = w3.eth.block_number if w3 and w3.is_connected() else "N/A"
        
        return {
            "message": "Crypto Freelance Payment API with Smart Contract",
            "status": "running",
            "environment": config.ENVIRONMENT,
            "contract_address": config.CONTRACT_ADDRESS,
            "network": "Avalanche Fuji Testnet",
            "web3_status": web3_status,
            "latest_block": latest_block,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "message": "Crypto Freelance Payment API with Smart Contract",
            "status": "running with errors",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

@app.get("/health")
async def health_check():
    """Detailed health check"""
    health_status = {
        "api": "healthy",
        "web3": "unhealthy",
        "contract": "unhealthy",
        "timestamp": datetime.utcnow().isoformat()
    }
    
    try:
        if w3 and w3.is_connected():
            health_status["web3"] = "healthy"
            health_status["latest_block"] = w3.eth.block_number
            
            # Check contract
            if config.CONTRACT_ADDRESS:
                try:
                    contract = get_escrow_contract()
                    # Try a simple view call to test contract
                    task_counter = contract.functions.taskCounter().call()
                    health_status["contract"] = "healthy"
                    health_status["task_counter"] = task_counter
                except Exception as contract_error:
                    health_status["contract"] = "unhealthy"
                    health_status["contract_error"] = str(contract_error)
    
    except Exception as e:
        health_status["error"] = str(e)
    
    return health_status

@app.get("/network/health")
async def network_health():
    """Detailed network health check"""
    health_info = {
        "timestamp": datetime.utcnow().isoformat(),
        "web3": {
            "initialized": w3 is not None,
            "connected": False,
            "latest_block": None,
            "chain_id": None,
            "gas_price": None
        },
        "contract": {
            "address": config.CONTRACT_ADDRESS,
            "accessible": False,
            "task_counter": None
        },
        "tokens": {
            "USDC": {"address": config.USDC_ADDRESS, "accessible": False},
            "USDT": {"address": config.USDT_ADDRESS, "accessible": False}
        }
    }
    
    # Test Web3 connection
    if w3:
        try:
            health_info["web3"]["connected"] = w3.is_connected()
            if health_info["web3"]["connected"]:
                health_info["web3"]["latest_block"] = w3.eth.block_number
                health_info["web3"]["chain_id"] = w3.eth.chain_id
                health_info["web3"]["gas_price"] = str(w3.eth.gas_price)
        except Exception as e:
            health_info["web3"]["error"] = str(e)
    
    # Test contract
    if config.CONTRACT_ADDRESS:
        try:
            contract = w3.eth.contract(address=config.CONTRACT_ADDRESS, abi=ESCROW_ABI)
            task_counter = contract.functions.taskCounter().call()
            health_info["contract"]["accessible"] = True
            health_info["contract"]["task_counter"] = task_counter
        except Exception as e:
            health_info["contract"]["error"] = str(e)
    
    # Test token contracts
    for currency in ["USDC", "USDT"]:
        try:
            token_contract = get_token_contract(CurrencyType(currency))
            decimals = token_contract.functions.decimals().call()
            health_info["tokens"][currency]["accessible"] = True
            health_info["tokens"][currency]["decimals"] = decimals
        except Exception as e:
            health_info["tokens"][currency]["error"] = str(e)
    
    return health_info

@app.get("/debug/profile/{wallet_address}")
async def debug_profile(wallet_address: str):
    """Debug endpoint to test each component of profile fetching"""
    debug_results = {
        "wallet_address": wallet_address,
        "timestamp": datetime.utcnow().isoformat(),
        "tests": {}
    }
    
    # Test 1: Web3 connection
    try:
        if w3 and w3.is_connected():
            debug_results["tests"]["web3_connection"] = {
                "status": "success",
                "latest_block": w3.eth.block_number,
                "chain_id": w3.eth.chain_id
            }
        else:
            debug_results["tests"]["web3_connection"] = {
                "status": "failed",
                "error": "Web3 not connected"
            }
    except Exception as e:
        debug_results["tests"]["web3_connection"] = {
            "status": "error",
            "error": str(e)
        }
    
    # Test 2: Contract connection
    try:
        contract = get_escrow_contract()
        task_counter = contract.functions.taskCounter().call()
        debug_results["tests"]["contract_connection"] = {
            "status": "success",
            "task_counter": task_counter
        }
    except Exception as e:
        debug_results["tests"]["contract_connection"] = {
            "status": "error", 
            "error": str(e)
        }
    
    # Test 3: Get client tasks
    try:
        contract = get_escrow_contract()
        client_tasks = contract.functions.getClientTasks(wallet_address).call()
        debug_results["tests"]["client_tasks"] = {
            "status": "success",
            "count": len(client_tasks),
            "task_ids": client_tasks
        }
    except Exception as e:
        debug_results["tests"]["client_tasks"] = {
            "status": "error",
            "error": str(e)
        }
    
    # Test 4: Get freelancer tasks
    try:
        contract = get_escrow_contract()
        freelancer_tasks = contract.functions.getFreelancerTasks(wallet_address).call()
        debug_results["tests"]["freelancer_tasks"] = {
            "status": "success", 
            "count": len(freelancer_tasks),
            "task_ids": freelancer_tasks
        }
    except Exception as e:
        debug_results["tests"]["freelancer_tasks"] = {
            "status": "error",
            "error": str(e)
        }
    
    # Test 5: Get AVAX balance
    try:
        balance_wei = w3.eth.get_balance(wallet_address)
        balance_avax = wei_to_ether(balance_wei)
        debug_results["tests"]["avax_balance"] = {
            "status": "success",
            "balance_wei": str(balance_wei),
            "balance_avax": str(balance_avax)
        }
    except Exception as e:
        debug_results["tests"]["avax_balance"] = {
            "status": "error",
            "error": str(e)
        }
    
    # Test 6: Get USDC balance
    try:
        usdc_contract = get_token_contract(CurrencyType.USDC)
        usdc_balance = usdc_contract.functions.balanceOf(wallet_address).call()
        debug_results["tests"]["usdc_balance"] = {
            "status": "success",
            "balance_raw": str(usdc_balance),
            "balance_formatted": str(base_unit_to_token(usdc_balance, 6))
        }
    except Exception as e:
        debug_results["tests"]["usdc_balance"] = {
            "status": "error",
            "error": str(e)
        }
    
    return debug_results

@app.post("/users/register", response_model=User)
async def register_user(user_data: UserRegistration):
    """Register a new user"""
    try:
        wallet_address = user_data.wallet_address.lower()
        
        if not wallet_address.startswith('0x') or len(wallet_address) != 42:
            raise HTTPException(status_code=400, detail="Invalid wallet address format")
        
        if w3 and not w3.is_address(wallet_address):
            raise HTTPException(status_code=400, detail="Invalid wallet address")
        
        if wallet_address in users_db:
            return users_db[wallet_address]
        
        user = User(
            wallet_address=wallet_address,
            email=user_data.email,
            is_freelancer=user_data.is_freelancer
        )
        
        users_db[wallet_address] = user
        logger.info(f"New user registered: {wallet_address}")
        return user
    
    except Exception as e:
        logger.error(f"User registration failed: {e}")
        raise HTTPException(status_code=400, detail=f"Registration failed: {str(e)}")

@app.get("/users/profile")
async def get_user_profile(current_user: User = Depends(get_current_user)):
    """Get current user profile with improved error handling"""
    try:
        logger.info(f"Fetching profile for user: {current_user.wallet_address}")
        
        # Initialize default values in case contract calls fail
        client_tasks = []
        freelancer_tasks = []
        balance_avax = Decimal("0")
        balances = {"AVAX": "0", "USDC": "0", "USDT": "0"}
        
        # Try to get contract and user task statistics
        try:
            contract = get_escrow_contract()
            
            # Get client tasks with individual error handling
            try:
                client_tasks = contract.functions.getClientTasks(current_user.wallet_address).call()
                logger.debug(f"Client tasks retrieved: {len(client_tasks)} tasks")
            except Exception as e:
                logger.warning(f"Failed to get client tasks for {current_user.wallet_address}: {e}")
            
            # Get freelancer tasks with individual error handling
            try:
                freelancer_tasks = contract.functions.getFreelancerTasks(current_user.wallet_address).call()
                logger.debug(f"Freelancer tasks retrieved: {len(freelancer_tasks)} tasks")
            except Exception as e:
                logger.warning(f"Failed to get freelancer tasks for {current_user.wallet_address}: {e}")
        
        except Exception as e:
            logger.warning(f"Contract interaction failed, using default values: {e}")
        
        # Get balance information with error handling
        try:
            if w3 and w3.is_connected():
                balance_wei = w3.eth.get_balance(current_user.wallet_address)
                balance_avax = wei_to_ether(balance_wei)
                balances["AVAX"] = str(balance_avax)
                logger.debug(f"AVAX balance retrieved: {balance_avax}")
        except Exception as e:
            logger.warning(f"Failed to get AVAX balance for {current_user.wallet_address}: {e}")
        
        # Try to get token balances with individual error handling
        try:
            usdc_contract = get_token_contract(CurrencyType.USDC)
            usdc_balance = usdc_contract.functions.balanceOf(current_user.wallet_address).call()
            balances["USDC"] = str(base_unit_to_token(usdc_balance, 6))
            logger.debug(f"USDC balance retrieved: {balances['USDC']}")
        except Exception as e:
            logger.warning(f"Failed to get USDC balance for {current_user.wallet_address}: {e}")
            balances["USDC"] = "0"
        
        try:
            usdt_contract = get_token_contract(CurrencyType.USDT)
            usdt_balance = usdt_contract.functions.balanceOf(current_user.wallet_address).call()
            balances["USDT"] = str(base_unit_to_token(usdt_balance, 6))
            logger.debug(f"USDT balance retrieved: {balances['USDT']}")
        except Exception as e:
            logger.warning(f"Failed to get USDT balance for {current_user.wallet_address}: {e}")
            balances["USDT"] = "0"
        
        # Construct response with all available data
        profile_response = {
            **current_user.dict(),
            "task_statistics": {
                "client_tasks_count": len(client_tasks),
                "freelancer_tasks_count": len(freelancer_tasks),
                "total_tasks": len(client_tasks) + len(freelancer_tasks)
            },
            "wallet_balances": balances
        }
        
        logger.info(f"Profile fetched successfully for {current_user.wallet_address}")
        return profile_response
    
    except Exception as e:
        logger.error(f"Get user profile failed for {current_user.wallet_address}: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to get profile: {str(e)}")

@app.post("/tasks/create")
async def create_task_instructions(
    task_data: TaskCreate,
    current_user: User = Depends(get_current_user)
):
    """Get instructions for creating a task on-chain"""
    try:
        if not w3 or not w3.is_address(task_data.freelancer_address):
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
        
        # Build transaction
        transaction_data = function_call.build_transaction({
            'from': current_user.wallet_address,
            'gas': gas_estimate,
            'gasPrice': gas_price,
            'nonce': w3.eth.get_transaction_count(current_user.wallet_address)
        })
        
        logger.info(f"Task creation instructions generated for user: {current_user.wallet_address}")
        
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
            "task_metadata": {
                "title": task_data.title,
                "description": task_data.description,
                "currency": task_data.currency.value
            },
            "gas_estimate": gas_estimate,
            "gas_price": gas_price,
            "estimated_cost_avax": wei_to_ether(gas_estimate * gas_price),
            "transaction_data": transaction_data
        }
    
    except Exception as e:
        logger.error(f"Create task instructions failed: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to generate instructions: {str(e)}")

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
                "gas_estimate": gas_estimate,
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
        logger.error(f"Fund instructions failed: {e}")
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
        logger.error(f"Mark delivered instructions failed: {e}")
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
        logger.error(f"Approve task instructions failed: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to get approval instructions: {str(e)}")

@app.post("/tasks/{task_id}/metadata")
async def update_task_metadata(
    task_id: int,
    metadata: TaskMetadata,
    current_user: User = Depends(get_current_user)
):
    """Update task metadata (stored off-chain)"""
    try:
        contract = get_escrow_contract()
        task_data = contract.functions.getTask(task_id).call()
        
        if task_data[1].lower() != current_user.wallet_address.lower():
            raise HTTPException(status_code=403, detail="Only task client can update metadata")
        
        task_metadata_db[task_id] = {
            "title": metadata.title,
            "description": metadata.description,
            "currency": metadata.currency.value
        }
        
        logger.info(f"Task {task_id} metadata updated by {current_user.wallet_address}")
        
        return {
            "message": "Task metadata updated",
            "task_id": task_id,
            "metadata": task_metadata_db[task_id]
        }
    
    except Exception as e:
        logger.error(f"Update metadata failed: {e}")
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
        currency = metadata.get("currency", "AVAX")
        
        # Convert amount based on currency
        if currency == "AVAX":
            amount = wei_to_ether(task_data[3])
        else:
            amount = base_unit_to_token(task_data[3], 6)
        
        return {
            "id": task_data[0],
            "client": task_data[1],
            "freelancer": task_data[2],
            "amount": str(amount),
            "amount_raw": str(task_data[3]),
            "token_address": task_data[4],
            "status": TaskStatus(task_data[5]).name,
            "status_code": task_data[5],
            "deadline": datetime.fromtimestamp(task_data[6]).isoformat(),
            "created_at": datetime.fromtimestamp(task_data[7]).isoformat(),
            "funded_at": datetime.fromtimestamp(task_data[8]).isoformat() if task_data[8] > 0 else None,
            "client_approved": task_data[9],
            "freelancer_delivered": task_data[10],
            "metadata": metadata,
            "currency": currency
        }
    
    except Exception as e:
        logger.error(f"Get task failed: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to get task: {str(e)}")

@app.get("/tasks/my")
async def get_my_tasks(current_user: User = Depends(get_current_user)):
    """Get tasks for current user with improved error handling"""
    try:
        tasks = []
        
        # Try to get tasks from contract
        try:
            contract = get_escrow_contract()
            
            # Get tasks where user is client
            client_task_ids = []
            try:
                client_task_ids = contract.functions.getClientTasks(current_user.wallet_address).call()
                logger.debug(f"Found {len(client_task_ids)} client tasks")
            except Exception as e:
                logger.warning(f"Failed to get client tasks: {e}")
            
            # Get tasks where user is freelancer
            freelancer_task_ids = []
            try:
                freelancer_task_ids = contract.functions.getFreelancerTasks(current_user.wallet_address).call()
                logger.debug(f"Found {len(freelancer_task_ids)} freelancer tasks")
            except Exception as e:
                logger.warning(f"Failed to get freelancer tasks: {e}")
            
            all_task_ids = list(set(client_task_ids + freelancer_task_ids))
            
            for task_id in all_task_ids:
                try:
                    task_data = contract.functions.getTask(task_id).call()
                    metadata = task_metadata_db.get(task_id, {})
                    currency = metadata.get("currency", "AVAX")
                    
                    # Convert amount based on currency
                    if currency == "AVAX":
                        amount = wei_to_ether(task_data[3])
                    else:
                        amount = base_unit_to_token(task_data[3], 6)
                    
                    task_info = {
                        "id": task_data[0],
                        "client": task_data[1],
                        "freelancer": task_data[2],
                        "amount": str(amount),
                        "token_address": task_data[4],
                        "status": TaskStatus(task_data[5]).name,
                        "status_code": task_data[5],
                        "deadline": datetime.fromtimestamp(task_data[6]).isoformat(),
                        "created_at": datetime.fromtimestamp(task_data[7]).isoformat(),
                        "funded_at": datetime.fromtimestamp(task_data[8]).isoformat() if task_data[8] > 0 else None,
                        "client_approved": task_data[9],
                        "freelancer_delivered": task_data[10],
                        "metadata": metadata,
                        "currency": currency,
                        "user_role": "client" if task_data[1].lower() == current_user.wallet_address.lower() else "freelancer"
                    }
                    tasks.append(task_info)
                except Exception as e:
                    logger.warning(f"Failed to get task {task_id}: {e}")
        
        except Exception as e:
            logger.warning(f"Contract interaction failed: {e}")
        
        return {
            "tasks": tasks,
            "total_count": len(tasks),
            "client_tasks": len([t for t in tasks if t.get("user_role") == "client"]),
            "freelancer_tasks": len([t for t in tasks if t.get("user_role") == "freelancer"])
        }
    
    except Exception as e:
        logger.error(f"Get my tasks failed: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to get tasks: {str(e)}")

@app.get("/contract/info")
async def get_contract_info():
    """Get contract information"""
    try:
        if not config.CONTRACT_ADDRESS:
            raise HTTPException(status_code=500, detail="Contract not deployed")
        
        # Basic contract info
        contract_info = {
            "contract_address": config.CONTRACT_ADDRESS,
            "network": "Avalanche Fuji Testnet",
            "rpc_url": config.AVALANCHE_RPC_URL,
            "supported_tokens": {
                "AVAX": "0x0000000000000000000000000000000000000000",
                "USDC": config.USDC_ADDRESS,
                "USDT": config.USDT_ADDRESS
            },
            "platform_fee": "2.5%",
            "web3_connected": w3.is_connected() if w3 else False
        }
        
        if w3 and w3.is_connected():
            contract_info["latest_block"] = w3.eth.block_number
            contract_info["gas_price"] = str(w3.eth.gas_price)
            contract_info["gas_price_gwei"] = str(w3.from_wei(w3.eth.gas_price, 'gwei'))
        
        return contract_info
    
    except Exception as e:
        logger.error(f"Get contract info failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get contract info: {str(e)}")

@app.get("/contract/stats")
async def get_contract_stats():
    """Get contract statistics"""
    try:
        # This would require additional view functions in the smart contract
        # For now, return basic stats from our stored data
        total_tasks = len(task_metadata_db)
        total_users = len(users_db)
        
        return {
            "total_tasks_with_metadata": total_tasks,
            "total_registered_users": total_users,
            "supported_currencies": [currency.value for currency in CurrencyType],
            "task_statuses": [status.name for status in TaskStatus]
        }
    
    except Exception as e:
        logger.error(f"Get contract stats failed: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to get stats: {str(e)}")

@app.get("/network/status")
async def get_network_status():
    """Get network status information"""
    try:
        if not w3:
            return {"status": "disconnected", "error": "Web3 not initialized"}
        
        if not w3.is_connected():
            return {"status": "disconnected", "error": "Not connected to network"}
        
        latest_block = w3.eth.block_number
        gas_price = w3.eth.gas_price
        chain_id = w3.eth.chain_id
        
        return {
            "status": "connected",
            "network": "Avalanche Fuji Testnet",
            "chain_id": chain_id,
            "latest_block": latest_block,
            "gas_price_wei": str(gas_price),
            "gas_price_gwei": str(w3.from_wei(gas_price, 'gwei')),
            "rpc_url": config.AVALANCHE_RPC_URL
        }
    
    except Exception as e:
        logger.error(f"Get network status failed: {e}")
        return {"status": "error", "error": str(e)}

@app.get("/setup/deployment-script")
async def get_deployment_script():
    """Get deployment script for the smart contract"""
    return {
        "message": "Smart contract deployment script",
        "solidity_contract": """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract FreelanceEscrow is ReentrancyGuard, Ownable {
    enum TaskStatus { CREATED, FUNDED, COMPLETED, DISPUTED, CANCELLED }
    
    struct Task {
        uint256 id;
        address client;
        address freelancer;
        uint256 amount;
        address token; // 0x0 for AVAX
        TaskStatus status;
        uint256 deadline;
        uint256 createdAt;
        uint256 fundedAt;
        bool clientApproved;
        bool freelancerDelivered;
    }
    
    uint256 public taskCounter;
    uint256 public platformFeePercent = 250; // 2.5%
    address public feeRecipient;
    
    mapping(uint256 => Task) public tasks;
    mapping(address => uint256[]) public clientTasks;
    mapping(address => uint256[]) public freelancerTasks;
    
    event TaskCreated(uint256 indexed taskId, address indexed client, address indexed freelancer, uint256 amount);
    event TaskFunded(uint256 indexed taskId, uint256 amount);
    event TaskCompleted(uint256 indexed taskId, uint256 freelancerAmount, uint256 platformFee);
    
    constructor(address _feeRecipient) {
        feeRecipient = _feeRecipient;
    }
    
    function createTask(
        address _freelancer,
        uint256 _amount,
        address _token,
        uint256 _deadline
    ) external returns (uint256) {
        require(_freelancer != address(0), "Invalid freelancer");
        require(_amount > 0, "Amount must be positive");
        require(_deadline > block.timestamp, "Invalid deadline");
        
        taskCounter++;
        
        tasks[taskCounter] = Task({
            id: taskCounter,
            client: msg.sender,
            freelancer: _freelancer,
            amount: _amount,
            token: _token,
            status: TaskStatus.CREATED,
            deadline: _deadline,
            createdAt: block.timestamp,
            fundedAt: 0,
            clientApproved: false,
            freelancerDelivered: false
        });
        
        clientTasks[msg.sender].push(taskCounter);
        freelancerTasks[_freelancer].push(taskCounter);
        
        emit TaskCreated(taskCounter, msg.sender, _freelancer, _amount);
        return taskCounter;
    }
    
    function fundTask(uint256 _taskId) external payable nonReentrant {
        Task storage task = tasks[_taskId];
        require(task.client == msg.sender, "Only client can fund");
        require(task.status == TaskStatus.CREATED, "Task not in created status");
        
        if (task.token == address(0)) {
            require(msg.value == task.amount, "Incorrect AVAX amount");
        } else {
            require(msg.value == 0, "No AVAX needed for token payment");
            IERC20(task.token).transferFrom(msg.sender, address(this), task.amount);
        }
        
        task.status = TaskStatus.FUNDED;
        task.fundedAt = block.timestamp;
        
        emit TaskFunded(_taskId, task.amount);
    }
    
    function markDelivered(uint256 _taskId) external {
        Task storage task = tasks[_taskId];
        require(task.freelancer == msg.sender, "Only freelancer can mark delivered");
        require(task.status == TaskStatus.FUNDED, "Task not funded");
        
        task.freelancerDelivered = true;
    }
    
    function approveTask(uint256 _taskId) external nonReentrant {
        Task storage task = tasks[_taskId];
        require(task.client == msg.sender, "Only client can approve");
        require(task.status == TaskStatus.FUNDED, "Task not funded");
        
        uint256 platformFee = (task.amount * platformFeePercent) / 10000;
        uint256 freelancerAmount = task.amount - platformFee;
        
        task.status = TaskStatus.COMPLETED;
        task.clientApproved = true;
        
        if (task.token == address(0)) {
            payable(task.freelancer).transfer(freelancerAmount);
            payable(feeRecipient).transfer(platformFee);
        } else {
            IERC20(task.token).transfer(task.freelancer, freelancerAmount);
            IERC20(task.token).transfer(feeRecipient, platformFee);
        }
        
        emit TaskCompleted(_taskId, freelancerAmount, platformFee);
    }
    
    function getTask(uint256 _taskId) external view returns (Task memory) {
        return tasks[_taskId];
    }
    
    function getClientTasks(address _client) external view returns (uint256[] memory) {
        return clientTasks[_client];
    }
    
    function getFreelancerTasks(address _freelancer) external view returns (uint256[] memory) {
        return freelancerTasks[_freelancer];
    }
}
        """,
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
        """,
        "environment_variables": {
            "PRIVATE_KEY": "your_private_key_here",
            "CONTRACT_ADDRESS": "deployed_contract_address_here"
        },
        "current_contract": config.CONTRACT_ADDRESS
    }

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    logger.error(f"HTTP {exc.status_code}: {exc.detail}")
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "status_code": exc.status_code,
            "message": exc.detail,
            "timestamp": datetime.utcnow().isoformat()
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}")
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "status_code": 500,
            "message": "Internal server error",
            "timestamp": datetime.utcnow().isoformat()
        }
    )

# Startup event
@app.on_event("startup")
async def startup_event():
    """Application startup event"""
    logger.info("Starting Crypto Freelance Payment API...")
    logger.info(f"Environment: {config.ENVIRONMENT}")
    logger.info(f"Contract Address: {config.CONTRACT_ADDRESS}")
    
    if w3 and w3.is_connected():
        logger.info(f"Connected to Avalanche network. Latest block: {w3.eth.block_number}")
    else:
        logger.warning("Not connected to Avalanche network!")
    
    if not config.PRIVATE_KEY:
        logger.warning("PRIVATE_KEY not set - some features will be unavailable")
    
    if not config.CONTRACT_ADDRESS:
        logger.warning("CONTRACT_ADDRESS not set - contract interactions will fail")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event"""
    logger.info("Shutting down Crypto Freelance Payment API...")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    uvicorn.run(
        "main:app",
        host=host, 
        port=port,
        log_level="info" if config.ENVIRONMENT == "production" else "debug",
        reload=False
    )