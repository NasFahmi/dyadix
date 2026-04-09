import os
import ccxt
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class BybitService:
    def __init__(self):
        """
        Initialize BybitService by retrieving API keys from .env
        and instantiating the CCXT Bybit object.
        """
        self.api_key = os.getenv("BYBIT_API_KEY")
        self.secret_key = os.getenv("BYBIT_SECRET_KEY")
        
        # Check if keys are actually present
        if not self.api_key or not self.secret_key:
            print("Warning: BYBIT_API_KEY or BYBIT_SECRET_KEY is missing in .env")
        
        # Initialize CCXT Bybit instance
        self.exchange = ccxt.bybit({
            'apiKey': self.api_key,
            'secret': self.secret_key,
            'enableRateLimit': True,
        })
        
    def get_ohlcv(self, symbol: str, timeframe: str = '1h', limit: int = 100):
        """
        Fetch OHLCV data for a specific symbol.
        
        :param symbol: Trading pair symbol, e.g., 'BTC/USDT'
        :param timeframe: Timeframe interval, e.g., '1m', '1h', '1d'
        :param limit: Number of candles to return (default 100)
        :return: List of OHLCV data [[timestamp, open, high, low, close, volume], ...]
        """
        try:
            print(f"Fetching OHLCV for {symbol} on {timeframe} timeframe...")
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            return ohlcv
        except Exception as e:
            print(f"Error fetching OHLCV for {symbol}: {e}")
            return None

if __name__ == "__main__":
    # Test execution
    service = BybitService()
    
    # Check balance as an authenticated test
    try:
        print("Checking account balance to verify API Keys functionality...")
        service.exchange.fetch_balance()
        print("API keys are valid. Successfully connected to Bybit.")
    except Exception as e:
        print(f"Failed to authenticate using API keys. Ensure keys are valid and have appropriate permissions.")
        print(f"Error details: {e}")
        print("\nProceeding to test OHLCV (which might still work for public data)...")
    
    # Test getting OHLCV for BTC/USDT
    print("\n--- Testing OHLCV Data Retrieval ---")
    data = service.get_ohlcv("BTC/USDT", timeframe="1h", limit=5)
    
    if data:
        print(f"\nSuccessfully fetched {len(data)} OHLCV candles:")
        print("Format: [Timestamp, Open, High, Low, Close, Volume]")
        for candle in data:
            print(candle)
    else:
        print("Failed to fetch OHLCV data.")
