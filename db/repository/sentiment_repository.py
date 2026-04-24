import logging
from db.database import SessionLocal
from db.models import Sentiment, SourceType

logger = logging.getLogger(__name__)

class SentimentRepository:
    @staticmethod
    def save_sentiment(result: dict, asset: str = "BTC"):
        """
        Simpan hasil analisis sentimen ke database secara modular.
        """
        try:
            db = SessionLocal()
            try:
                new_sentiment = Sentiment(
                    asset=asset,
                    source_type=SourceType.news, # Default news
                    sentiment_score=float(result.get("sentiment_score", 0)),
                    summary=result.get("overall_context_summary"),
                    raw_data=result
                )
                db.add(new_sentiment)
                db.commit()
                logger.info(f"✅ Sentiment for {asset} saved to PostgreSQL (via Repository)")
                return True
            except Exception as db_err:
                logger.error(f"Failed to save sentiment to DB: {db_err}")
                db.rollback()
                return False
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error in SentimentRepository: {e}")
            return False
