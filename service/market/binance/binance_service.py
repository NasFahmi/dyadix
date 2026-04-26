import os
import ccxt
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class BinanceService:
    def __init__(self):
        """
        Initialize BinanceService by retrieving API keys from .env
        and instantiating the CCXT Binance object.
        """
        self.api_key = os.getenv("BINANCE_API_KEY")
        self.secret_key = os.getenv("BINANCE_SECRET_KEY")
        
        # Check if keys are actually present
        if not self.api_key or not self.secret_key:
            print("Warning: BINANCE_API_KEY or BINANCE_SECRET_KEY is missing in .env")
        
        # Initialize CCXT Binance instance
        self.exchange = ccxt.binance({
            'apiKey': self.api_key,
            'secret': self.secret_key,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future', # Set to USDT-M Futures
                'adjustForTimeDifference': True,
                'recvWindow': 60000,
            }
        })
        try:
            self.exchange.load_time_difference()
        except:
            pass
        
    def fetch_ohlcv(self, symbol: str, timeframe: str = '1h', limit: int = 100):
        """
        Fetch OHLCV data for a specific symbol as pandas DataFrame.
        
        :param symbol: Trading pair symbol, e.g., 'BTC/USDT'
        :param timeframe: Timeframe interval, e.g., '1m', '1h', '1d'
        :param limit: Number of candles to return (default 100)
        :return: pandas DataFrame containing OHLCV
        """
        import pandas as pd
        try:
            print(f"Fetching OHLCV for {symbol} on {timeframe} timeframe from Binance...")
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if not ohlcv:
                return pd.DataFrame()
                
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            return df
        except Exception as e:
            import pandas as pd
            print(f"Error fetching OHLCV for {symbol} from Binance: {e}")
            return pd.DataFrame()

if __name__ == "__main__":
    # Test execution
    service = BinanceService()
    
    # Check balance as an authenticated test
    try:
        print("Checking account balance to verify API Keys functionality...")
        service.exchange.fetch_balance()
        print("API keys are valid. Successfully connected to Binance.")
    except Exception as e:
        print(f"Failed to authenticate using API keys. Ensure keys are valid and have appropriate permissions.")
        print(f"Error details: {e}")
        print("\nProceeding to test OHLCV (which might still work for public data)...")
    
    # Test getting OHLCV for BTC/USDT
    print("\n--- Testing OHLCV Data Retrieval ---")
    data = service.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=5)
    
    if data is not None and not data.empty:
        print(f"\nSuccessfully fetched {len(data)} OHLCV candles (DataFrame):")
        print(data.head())
    else:
        print("Failed to fetch OHLCV data.")
