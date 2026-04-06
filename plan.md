dyadix/
│
├── config/
│   ├── settings.yaml
│   ├── api_keys.yaml
│
├── data/
│   ├── raw/ -> bucket to save data raw retrival
│   │   ├── market/
│   │   ├── sentiment/
│   │
│   ├── processed/ -> bucket to save data processing
│   │   ├── features/
│   │   ├── context/
│
├── services/
│   ├── market/
│   │   ├── binance_service.py -> data retrival
│   │   ├── bybit_service.py -> data retrival
│   │
│   ├── sentiment/
│   │   ├── news_service.py -> data retrival
│   │   ├── fear_greed_service.py -> data retrival
│
├── features/ -> feature engineering
│   ├── technical/
│   │   ├── trend.py
│   │   ├── structure.py
│   │   ├── momentum.py
│   │
│   ├── derivatives/
│   │   ├── funding.py
│   │   ├── open_interest.py
│   │   ├── risk.py
│   │
│   ├── liquidity/
│   │   ├── sweep.py
│   │   ├── equal_levels.py
│   │
│   ├── sentiment/
│   │   ├── news_analysis.py
│   │   ├── aggregation.py
│
├── aggregation/ -> context building
│   ├── context_builder.py
│   ├── conflict_detector.py
│
├── decision/ -> decision engine
│   ├── rule_engine.py
│   ├── llm_engine.py
│   ├── decision_engine.py
│
├── schemas/ -> schema definition LLM validation output
│   ├── context_schema.json
│   ├── decision_schema.json
│
├── pipelines/ -> ORCHESTRATION
│   ├── main_pipeline.py
│   ├── market_pipeline.py
│   ├── sentiment_pipeline.py
│
├── utils/
│   ├── logger.py
│   ├── time_utils.py
│
├── tests/
│   ├── test_features.py
│   ├── test_decision.py
│
├── main.py
└── README.md