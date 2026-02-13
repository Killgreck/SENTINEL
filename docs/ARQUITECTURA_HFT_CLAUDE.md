# SENTINEL HFT: Arquitectura de Trading de Alta Frecuencia en AWS

> **Análisis de Viabilidad del Ingeniero Principal:** Como arquitecto HFT senior, debo ser directo: **HFT real (<10µs) NO es viable en AWS**. Sin embargo, puedo diseñarte un sistema de **Ultra-Low Latency Trading (ULLT)** (50-500µs) que es competitivo para ciertos nichos. La clave está en aceptar las limitaciones físicas y explotarlas estratégicamente.

---

## 1. ANÁLISIS DE REALIDAD: AWS vs. Colocation

### 1.1 Limitaciones Fundamentales

| Factor | AWS (Best Case) | Colocation (Exchange) | Diferencia |
|--------|-----------------|----------------------|------------|
| **Latencia de Red** | 50-200µs (mismo AZ) | 0.1-5µs (cross-connect) | **100-1000x más lento** |
| | 500µs-2ms (cross-AZ) | 10-50µs (mismo DC) | |
| **Latency Jitter** | 10-50µs | <1µs | No determinístico |
| **Market Data Feed** | Via Internet/VPN | Direct fiber | Obsoleto al llegar |
| **Order Gateway** | Via API REST/WebSocket | FIX/Binary directo | 2-5 saltos extras |

### 1.2 Ventana de Oportunidad

**No compitas donde pierdes. Cambia el juego:**

- ❌ **Market Making clásico** (necesitas <10µs)
- ❌ **Arbitraje cross-exchange puro** (muerto antes de ejecutar)
- ✅ **News/Sentiment Arbitrage** (10-500ms window)
- ✅ **Statistical Arbitrage de medio plazo** (100ms-2s)
- ✅ **Manipulation Detection & Reversal** (tu estrategia "Contrarian")

**Tu ventaja competitiva:** La masa retail reacciona en 1-30 segundos. Un sistema que procesa en 200ms y ejecuta en 100ms sigue siendo **100x más rápido** que el 99% del mercado.

---

## 2. ARQUITECTURA SENTINEL HFT: "Speed Tier System"

### 2.1 Filosofía de Diseño

```
┌─────────────────────────────────────────────────────────────┐
│  LATENCY BUDGET: 500µs total (detection → execution)        │
│  ┌──────────────┬──────────────┬──────────────┬───────────┐ │
│  │ Data Ingress │ Processing   │ Decision     │ Execution │ │
│  │   50-100µs   │   100-200µs  │   50-100µs   │  100-200µs│ │
│  └──────────────┴──────────────┴──────────────┴───────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Arquitectura de 3 Capas

```
┌─────────────────────────────────────────────────────────────────────┐
│                         LAYER 1: DATA PLANE                          │
│                    (EC2 C7gn + EFA + DPDK)                          │
│  ┌────────────────────┐         ┌──────────────────────────┐       │
│  │ Market Data Feed   │────────▶│ Lock-free Ring Buffer    │       │
│  │ • WebSocket (ws)   │         │ • 10M entries circular   │       │
│  │ • Binance/Coinbase │         │ • SPSC queue (no locks)  │       │
│  │ • Kernel Bypass    │         │ • Huge Pages (2MB)       │       │
│  └────────────────────┘         └──────────────────────────┘       │
│                                           │                          │
│                                           ▼                          │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │         Feature Engineering (C++ SIMD vectorized)              │ │
│  │  • Price deltas, volume spikes, order book imbalance          │ │
│  │  • Latency: 20-50µs per event                                 │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    LAYER 2: DECISION PLANE                           │
│                  (EC2 F1 FPGA OR C7gn CPU)                          │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              FAST PATH (Deterministic Logic)                   │ │
│  │  ┌──────────────────────────────────────────────────────────┐ │ │
│  │  │ Option A: FPGA (F1 instances)                            │ │ │
│  │  │ • Verilog/VHDL: Hardcoded trading logic                  │ │ │
│  │  │ • 200ns decision time (sub-microsecond)                  │ │ │
│  │  │ • No OS, direct PCIe I/O                                 │ │ │
│  │  │ • COSTO: $13.20/hora (f1.16xlarge)                       │ │ │
│  │  └──────────────────────────────────────────────────────────┘ │ │
│  │  ┌──────────────────────────────────────────────────────────┐ │ │
│  │  │ Option B: CPU Pinned (C7gn.16xlarge)                     │ │ │
│  │  │ • Rust/C++ con CPU affinity                              │ │ │
│  │  │ • 5-20µs decision time                                   │ │ │
│  │  │ • Isolated cores (isolcpus kernel param)                 │ │ │
│  │  │ • COSTO: $2.72/hora                                      │ │ │
│  │  └──────────────────────────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              SLOW PATH (LLM-Augmented Logic)                   │ │
│  │  • SageMaker Endpoint (Claude Haiku via Bedrock)              │ │
│  │  • Latencia: 200-800ms                                         │ │
│  │  • Solo para señales "ambiguas" (flag del fast path)          │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    LAYER 3: EXECUTION PLANE                          │
│                      (EC2 C7gn + EFA)                               │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │               Order Execution Engine (Rust)                    │ │
│  │  • Direct HTTPS/WebSocket a Binance/Coinbase                  │ │
│  │  • Connection pooling (pre-authenticated sessions)             │ │
│  │  • Order batching (cuando aplique)                             │ │
│  │  • Latencia: 50-150µs (processing) + network RTT              │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                  Risk Management Layer                         │ │
│  │  • Hardware kill switch (FPGA si usas F1)                      │ │
│  │  • Position limits en memoria (lock-free counters)             │ │
│  │  • Circuit breaker: 5µs check                                  │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. DECISIÓN CRÍTICA: FPGA vs CPU

### 3.1 EC2 F1 (FPGA) - Análisis Profundo

#### Ventajas Reales
```verilog
// Ejemplo conceptual: Detector de pump&dump en hardware
module pump_detector(
    input wire clk,
    input wire [63:0] price_delta,      // 8 bytes
    input wire [63:0] volume_spike,     // 8 bytes
    input wire [7:0] news_sentiment,    // LLM score (pre-computed)
    output reg trigger                  // 1 = execute contrarian trade
);

always @(posedge clk) begin
    // Lógica combinacional - 1 ciclo de reloj (5ns @ 200MHz)
    if (price_delta > PUMP_THRESHOLD && 
        volume_spike > 3.0 * avg_volume &&
        news_sentiment < FAKE_NEWS_THRESHOLD) begin
        trigger <= 1'b1;
    end else begin
        trigger <= 1'b0;
    end
end
endmodule
```

**Latencia:** 200ns-1µs (vs. 10-50µs en CPU)

#### Desventajas Críticas
1. **Desarrollo:** 6-12 meses para un equipo experto en HDL
2. **Debugging:** Herramientas primitivas, no hay printf()
3. **Flexibilidad:** Cambiar lógica = recompilar HDL (4-8 horas)
4. **Costo:** $13.20/hora vs $2.72/hora (C7gn)

#### Veredicto del Ingeniero
> **NO uses FPGA para MVP**. Tu estrategia "Contrarian" cambiará 10 veces antes de ser rentable. La ventaja de latencia de FPGA solo importa si ya tienes un alpha probado y estable. **Empieza con C7gn + Rust**.

---

### 3.2 Arquitectura Recomendada: C7gn + EFA

```
┌─────────────────────────────────────────────────────────────────┐
│  EC2 Instance: c7gn.16xlarge (Graviton 3, 100 Gbps EFA)        │
│  • 64 vCPUs @ 2.6 GHz (AWS Graviton 3)                         │
│  • 128 GB RAM DDR5                                              │
│  • 100 Gbps Elastic Fabric Adapter                             │
│  • Costo: $2.72/hora (~$2,000/mes 24/7)                        │
└─────────────────────────────────────────────────────────────────┘

CONFIGURACIÓN DE NÚCLEOS (CPU Pinning):
┌─────────────────────────────────────────────────────────────────┐
│ Core 0-7:   Market Data Ingestion (isolcpus, no interrupts)   │
│ Core 8-15:  Feature Engineering (SIMD AVX-512)                 │
│ Core 16-23: Decision Engine (trading logic)                    │
│ Core 24-31: Order Execution                                    │
│ Core 32-47: SageMaker Feature Store Cache (Redis)             │
│ Core 48-63: Monitoring, logging (non-critical path)           │
└─────────────────────────────────────────────────────────────────┘
```

#### Optimizaciones de Red (EFA + Kernel Bypass)

```rust
// Ejemplo Rust con DPDK (Data Plane Development Kit)
use dpdk::*;

fn main() {
    // 1. Initialize DPDK (bypass kernel network stack)
    let eal_args = vec![
        "-c", "0xFF",           // Use cores 0-7
        "-n", "4",              // 4 memory channels
        "--huge-dir", "/mnt/huge", // Use huge pages
        "--proc-type", "primary"
    ];
    dpdk_eal_init(&eal_args);
    
    // 2. Setup memory pool (zero-copy packets)
    let mbuf_pool = rte_pktmbuf_pool_create(
        "MBUF_POOL",
        8192,          // num mbufs
        256,           // cache size
        0,
        RTE_MBUF_DEFAULT_BUF_SIZE,
    );
    
    // 3. Configure port (EFA network interface)
    let port_id = 0;
    rte_eth_dev_configure(port_id, 1, 1, &port_conf);
    
    // 4. Receive loop (polling, no interrupts)
    loop {
        let nb_rx = rte_eth_rx_burst(port_id, 0, &mut pkts, BURST_SIZE);
        
        for pkt in pkts.iter().take(nb_rx) {
            // Parse WebSocket frame (market data)
            let trade = parse_binance_trade(pkt);
            
            // Write to lock-free ring buffer (shared with decision engine)
            RING_BUFFER.push(trade); // Single Producer Single Consumer
        }
    }
}
```

**Latencia lograda:** 10-30µs (ingress) vs 100-500µs con kernel stack

---

## 4. ESTRATEGIA "THE CONTRARIAN": Flujo Completo

### 4.1 Arquitectura de Decisión Dual-Speed

```
┌───────────────────────────────────────────────────────────────────┐
│                    EVENT TRIGGER (Market Data)                     │
│  Binance WebSocket → DPDK → Lock-free Queue → Feature Engine      │
│                     (50µs)      (10µs)          (30µs)            │
└───────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────────┐
│               CLASSIFICATION: Fast vs Slow Path                    │
│                                                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  DECISOR (C++ / Rust - 5µs)                                 │  │
│  │  ┌────────────────────────────────────────────────────────┐ │  │
│  │  │ IF (volume_spike > 5x && price_delta > 3%)            │ │  │
│  │  │    AND news_event_detected == true                     │ │  │
│  │  │ THEN route to LLM_PATH                                 │ │  │
│  │  │ ELSE execute FAST_PATH                                 │ │  │
│  │  └────────────────────────────────────────────────────────┘ │  │
│  └─────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
            │                                    │
            │ FAST PATH (90% casos)              │ SLOW PATH (10% casos)
            ▼                                    ▼
┌──────────────────────────┐      ┌─────────────────────────────────┐
│  Statistical Model       │      │  LLM Analysis (SageMaker)       │
│  • Pre-trained XGBoost   │      │  ┌───────────────────────────┐ │
│  • Inference: 50µs       │      │  │ Bedrock Claude Haiku      │ │
│  • Decision: BUY/SELL/   │      │  │ • Prompt:                 │ │
│    HOLD                  │      │  │   "Analyze: {news_text}   │ │
│  • Confidence: 0.0-1.0   │      │  │    Price spike: +12%      │ │
│                          │      │  │    Volume: 8x normal      │ │
│                          │      │  │    Classify manipulation  │ │
│                          │      │  │    probability (0-100%)"  │ │
│                          │      │  │ • Latency: 200-500ms      │ │
│                          │      │  └───────────────────────────┘ │
│                          │      │            │                   │
│                          │      │            ▼                   │
│                          │      │  ┌───────────────────────────┐ │
│                          │      │  │ IF manipulation_prob > 75%│ │
│                          │      │  │ THEN direction = INVERSE  │ │
│                          │      │  │ (Contrarian trade!)       │ │
│                          │      │  └───────────────────────────┘ │
└──────────────────────────┘      └─────────────────────────────────┘
            │                                    │
            └────────────────┬───────────────────┘
                             ▼
            ┌────────────────────────────────────┐
            │      RISK MANAGEMENT GATE          │
            │  • Position limit check (1µs)      │
            │  • Portfolio heat check (2µs)      │
            │  • Circuit breaker (1µs)           │
            └────────────────────────────────────┘
                             │
                             ▼
            ┌────────────────────────────────────┐
            │       ORDER EXECUTION              │
            │  • Binance API (REST/WebSocket)    │
            │  • Latency: 100-200µs (local)      │
            │           + 20-50ms (network RTT)  │
            └────────────────────────────────────┘
```

### 4.2 Implementación de "The Contrarian"

```rust
// src/strategies/contrarian.rs
use serde::{Deserialize, Serialize};
use tokio::sync::mpsc;

#[derive(Debug)]
struct MarketEvent {
    symbol: String,
    price_delta_pct: f64,
    volume_ratio: f64,      // vs 24h avg
    news_embedding: Option<Vec<f32>>,  // From Feature Store
    timestamp_us: u64,
}

#[derive(Debug)]
enum TradingSignal {
    FastPath(StatisticalSignal),
    SlowPath(LLMSignal),
}

#[derive(Debug, Serialize, Deserialize)]
struct LLMAnalysis {
    manipulation_probability: f32,  // 0.0-1.0
    sentiment_score: f32,           // -1.0 to 1.0
    reasoning: String,
    confidence: f32,
}

async fn contrarian_strategy(event: MarketEvent) -> TradingSignal {
    // STEP 1: Fast classification
    if event.volume_ratio < 3.0 || event.price_delta_pct.abs() < 2.0 {
        // Normal market movement - use statistical model
        return TradingSignal::FastPath(
            xgboost_inference(&event)  // 50µs
        );
    }
    
    // STEP 2: Anomaly detected - route to LLM
    if event.news_embedding.is_some() {
        // News-driven spike - HIGH PRIORITY for LLM
        let llm_result = analyze_with_llm(&event).await;  // 200-500ms
        
        if llm_result.manipulation_probability > 0.75 {
            // CONTRARIAN LOGIC
            let market_direction = if event.price_delta_pct > 0.0 {
                "BULLISH"  // Crowd is buying
            } else {
                "BEARISH"  // Crowd is selling
            };
            
            let our_position = match market_direction {
                "BULLISH" => Position::Short,  // We SHORT
                "BEARISH" => Position::Long,   // We LONG
                _ => Position::Neutral,
            };
            
            return TradingSignal::SlowPath(LLMSignal {
                position: our_position,
                size_multiplier: llm_result.confidence,  // Scale by confidence
                reasoning: llm_result.reasoning,
            });
        }
    }
    
    // STEP 3: Fallback to fast path
    TradingSignal::FastPath(xgboost_inference(&event))
}

async fn analyze_with_llm(event: &MarketEvent) -> LLMAnalysis {
    let prompt = format!(
        r#"You are an expert market manipulation detector.
        
        EVENT DATA:
        - Asset: {}
        - Price change: {:.2}% in 60 seconds
        - Volume spike: {:.1}x normal
        - News detected: Yes
        
        TASK:
        Analyze if this is a coordinated pump & dump or natural market movement.
        Return JSON:
        {{
            "manipulation_probability": 0.0-1.0,
            "sentiment_score": -1.0 to 1.0,
            "reasoning": "brief explanation",
            "confidence": 0.0-1.0
        }}"#,
        event.symbol,
        event.price_delta_pct,
        event.volume_ratio
    );
    
    // Call SageMaker endpoint (Bedrock Claude Haiku)
    let response = sagemaker_client
        .invoke_endpoint()
        .endpoint_name("sentinel-llm-haiku")
        .body(prompt)
        .send()
        .await
        .unwrap();
    
    serde_json::from_slice(&response.body).unwrap()
}
```

---

## 5. INTEGRACIÓN CON SAGEMAKER FEATURE STORE

### 5.1 Problema de Latencia

```
SageMaker Feature Store:
├─ Online Store (DynamoDB): 5-20ms read latency ❌ (Demasiado lento)
└─ Offline Store (S3): No aplicable para real-time
```

### 5.2 Solución: Hot Cache Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  SAGEMAKER FEATURE STORE                         │
│                    (Source of Truth)                             │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Feature Groups:                                            │ │
│  │ • market_features (OHLCV, order book depth)               │ │
│  │ • sentiment_features (news embeddings, social signals)    │ │
│  │ • portfolio_state (positions, PnL, risk metrics)          │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                          │
                          │ Background sync (100ms intervals)
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│              HOT CACHE LAYER (ElastiCache Redis)                │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Instance: cache.r7g.4xlarge (122 GB RAM, Graviton 3)      │ │
│  │ • Latency: 200-500µs (sub-millisecond)                    │ │
│  │ • Eviction: LRU (keep last 1M features)                   │ │
│  │ • Persistence: AOF disabled (speed > durability)          │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  KEY DESIGN:                                                     │
│  "feature:{symbol}:{feature_name}" → JSON/MessagePack value     │
│  Example: "feature:BTCUSDT:sentiment_1h" → {"score": 0.82}     │
└─────────────────────────────────────────────────────────────────┘
                          │
                          │ In-memory read (200µs)
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│           TRADING ENGINE (C7gn - same instance)                 │
│  • Uses Redis cluster client (connection pooling)               │
│  • Async I/O (tokio-rs runtime)                                │
│  • Fallback: If cache miss, block trade (don't query DynamoDB) │
└─────────────────────────────────────────────────────────────────┘
```

### 5.3 Código de Integración

```rust
// src/feature_store/cache.rs
use redis::aio::ConnectionManager;
use serde_json::Value;

pub struct FeatureCache {
    redis: ConnectionManager,
    sagemaker_client: SageMakerFeatureStoreRuntimeClient,
}

impl FeatureCache {
    // Background sync task (runs every 100ms)
    pub async fn sync_from_feature_store(&self) {
        loop {
            // Fetch updated features from SageMaker
            let records = self.sagemaker_client
                .batch_get_record()
                .identifiers(/* top 1000 active symbols */)
                .send()
                .await
                .unwrap();
            
            // Write to Redis (pipeline for efficiency)
            let mut pipe = redis::pipe();
            for record in records.records() {
                let key = format!(
                    "feature:{}:{}",
                    record.record_identifier_value_as_string(),
                    record.feature_name()
                );
                pipe.set_ex(key, record.value_as_string(), 1); // 1s TTL
            }
            pipe.query_async(&mut self.redis).await.unwrap();
            
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
    }
    
    // Hot path read (called from trading engine)
    pub async fn get_feature(&self, symbol: &str, feature: &str) -> Option<f64> {
        let key = format!("feature:{}:{}", symbol, feature);
        
        // Redis GET (200-500µs)
        let value: Option<String> = self.redis.get(&key).await.ok()?;
        
        value.and_then(|v| v.parse().ok())
    }
}
```

---

## 6. MATRIZ DE EXPERIMENTOS CON DYNAMODB

### 6.1 Schema

```python
# DynamoDB Table: sentinel-experiments
{
    "PK": "EXP#2026-01-06#contrarian_v1.2.3",  # Partition Key
    "SK": "RUN#1704556800",                     # Sort Key (timestamp)
    
    # Metadata
    "strategy_version": "1.2.3",
    "git_commit": "a3f21bc",
    "parameters": {
        "manipulation_threshold": 0.75,
        "position_size_pct": 0.02,
        "stop_loss_pct": 0.03,
        "llm_model": "claude-haiku-20250101"
    },
    
    # Performance Metrics
    "trades_count": 127,
    "win_rate": 0.64,
    "pnl_usd": 1243.67,
    "sharpe_ratio": 2.1,
    "max_drawdown_pct": 0.08,
    
    # Latency Metrics
    "p50_latency_us": 234,
    "p99_latency_us": 1823,
    "llm_calls_count": 23,
    "llm_avg_latency_ms": 342,
    
    # TTL for auto-cleanup
    "ttl": 1736092800  # 30 days retention
}
```

### 6.2 Query Patterns

```rust
// Compare performance across versions
async fn compare_strategies() {
    let results = dynamodb_client
        .query()
        .table_name("sentinel-experiments")
        .key_condition_expression("begins_with(PK, :exp_prefix)")
        .expression_attribute_values(
            ":exp_prefix",
            AttributeValue::S("EXP#2026-01-06".to_string())
        )
        .send()
        .await
        .unwrap();
    
    // Analyze which parameter set performed best
    let best_run = results.items()
        .iter()
        .max_by_key(|item| {
            item.get("sharpe_ratio")
                .and_then(|v| v.as_n().ok())
                .and_then(|n| n.parse::<f64>().ok())
                .unwrap_or(0.0)
        });
}
```

---

## 7. DEPLOYMENT ARQUITECTURE

### 7.1 Network Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                      AWS REGION: us-east-1                       │
│  (Razón: Menor latencia a exchanges Coinbase/Gemini US-hosted)  │
└─────────────────────────────────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
   ┌────▼────┐         ┌─────▼────┐        ┌─────▼────┐
   │  AZ-1a  │         │  AZ-1b   │        │  AZ-1c   │
   └─────────┘         └──────────┘        └──────────┘
        │
        │ PRODUCTION DEPLOYMENT (AZ-1a only - minimize cross-AZ)
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  VPC: 10.0.0.0/16                                               │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Private Subnet: 10.0.1.0/24 (AZ-1a)                       │  │
│  │                                                            │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ EC2: c7gn.16xlarge (HFT Engine)                      │ │  │
│  │  │ • Placement Group: cluster (low latency)             │ │  │
│  │  │ • EFA enabled                                        │ │  │
│  │  │ • EBS: io2 Block Express (256K IOPS)                │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │                                                            │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ ElastiCache: cache.r7g.4xlarge                       │ │  │
│  │  │ • Feature Store hot cache                            │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Public Subnet: 10.0.2.0/24 (AZ-1a)                        │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ NAT Gateway (for outbound to exchanges)             │ │  │
│  │  │ • Elastic IP (static for whitelist)                 │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                             │
                             │ VPC Peering (or PrivateLink)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              SHARED SERVICES VPC (Multi-AZ)                     │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ • SageMaker Feature Store (DynamoDB backend)              │  │
│  │ • SageMaker Endpoints (LLM inference - us-east-1)        │  │
│  │ • DynamoDB: sentinel-experiments                          │  │
│  │ • S3: Historical data, model artifacts                    │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 Configuración de Sistema Operativo

```bash
#!/bin/bash
# Instance setup script for c7gn.16xlarge

# 1. KERNEL TUNING
cat <<EOF > /etc/sysctl.d/99-hft.conf
# Disable CPU frequency scaling (max performance)
vm.swappiness=0
vm.zone_reclaim_mode=0

# Network optimizations
net.core.rmem_max=134217728
net.core.wmem_max=134217728
net.ipv4.tcp_rmem=4096 87380 134217728
net.ipv4.tcp_wmem=4096 65536 134217728
net.core.netdev_max_backlog=300000
net.ipv4.tcp_no_metrics_save=1
net.ipv4.tcp_congestion_control=bbr

# Huge pages (2MB pages for DPDK)
vm.nr_hugepages=8192
EOF
sysctl -p /etc/sysctl.d/99-hft.conf

# 2. CPU ISOLATION (cores 0-31 for trading, 32-63 for background)
grubby --update-kernel=ALL --args="isolcpus=0-31 nohz_full=0-31 rcu_nocbs=0-31"
reboot

# 3. DISABLE IRQ BALANCING (pin network IRQs to specific cores)
systemctl stop irqbalance
systemctl disable irqbalance

# Pin EFA IRQs to core 63 (isolated from trading path)
EFA_IRQ=$(cat /proc/interrupts | grep efa | awk '{print $1}' | tr -d ':')
echo 63 > /proc/irq/$EFA_IRQ/smp_affinity_list

# 4. INSTALL DPDK
wget https://fast.dpdk.org/rel/dpdk-23.11.tar.xz
tar xf dpdk-23.11.tar.xz
cd dpdk-23.11
meson build
ninja -C build
ninja -C build install

# 5. MOUNT HUGE PAGES
mkdir -p /mnt/huge
mount -t hugetlbfs nodev /mnt/huge
echo "nodev /mnt/huge hugetlbfs defaults 0 0" >> /etc/fstab
```

---

## 8. ANÁLISIS DE COSTOS

### 8.1 Infraestructura Mensual (24/7)

| Componente | Especificación | Costo/hora | Costo/mes |
|-----------|----------------|-----------|-----------|
| **EC2 HFT Engine** | c7gn.16xlarge | $2.72 | $1,958 |
| **ElastiCache Redis** | cache.r7g.4xlarge | $1.28 | $922 |
| **NAT Gateway** | Data transfer (1TB) | $0.045/GB | $45 |
| **EBS Storage** | 1TB io2 Block Express | - | $125 |
| **SageMaker Endpoint** | ml.g5.xlarge (LLM) | $1.41 | $1,015 |
| **DynamoDB** | On-demand (1M writes) | - | $12 |
| **Feature Store** | 10M reads/month | - | $25 |
| **VPC Peering** | Data transfer | - | $18 |
| **CloudWatch** | Metrics + Logs | - | $30 |
| | | **TOTAL** | **~$4,150/mes** |

### 8.2 Optimización de Costos

```
STRATEGY 1: Spot Instances (NO RECOMENDADO para HFT)
- Ahorro: 70% ($1,300/mes)
- Riesgo: Interrupción en momento crítico = pérdida catastrófica

STRATEGY 2: Savings Plans (1 año)
- Ahorro: 30% ($1,245/mes)
- Lock-in: Comprometido por 12 meses

STRATEGY 3: Hybrid (RECOMENDADO)
- HFT engine: On-Demand (necesitas garantía)
- Redis/SageMaker: Savings Plan (cargas predecibles)
- Ahorro: ~15% ($620/mes)
```

---

## 9. LIMITACIONES Y RIESGOS

### 9.1 Limitaciones Técnicas Ineludibles

| Limitación | Impacto | Mitigación |
|-----------|---------|-----------|
| **Network RTT a exchanges** | 20-50ms (vs <1ms colocation) | Elegir exchange en misma región AWS |
| **Clock skew** | 1-10ms desync | NTP + PTP, monitoreo continuo |
| **AWS Hypervisor jitter** | 5-20µs outliers | CPU pinning, isolated cores |
| **Shared network** | Variabilidad de latencia | EFA, pero no elimina el problema |

### 9.2 Riesgos Operacionales

#### CRÍTICO: Runaway Algorithm
```rust
// MANDATORY: Hardware kill switch
use std::sync::atomic::{AtomicBool, Ordering};

static EMERGENCY_STOP: AtomicBool = AtomicBool::new(false);

fn check_circuit_breaker() -> bool {
    // Check every trade (5µs overhead)
    if EMERGENCY_STOP.load(Ordering::Relaxed) {
        log::error!("EMERGENCY STOP TRIGGERED");
        return false;
    }
    
    // Conditions for auto-kill:
    if portfolio.drawdown_pct() > 0.20 {  // 20% loss
        EMERGENCY_STOP.store(true, Ordering::Relaxed);
        return false;
    }
    
    if trades_last_minute > 1000 {  // Abnormal frequency
        EMERGENCY_STOP.store(true, Ordering::Relaxed);
        return false;
    }
    
    true
}
```

#### Monitoreo Obligatorio
```
CloudWatch Alarms:
├─ P99 latency > 2ms → PagerDuty alert
├─ Error rate > 1% → Auto-disable trading
├─ Position delta > $50k/min → Human approval required
└─ CPU steal time > 5% → Instance degraded, migrate
```

---

## 10. ROADMAP DE IMPLEMENTACIÓN

### Fase 1: Validación (Semanas 1-4)
```
✓ Provision c7gn.16xlarge + Redis
✓ Deploy data ingestion (WebSocket → DPDK)
✓ Implement statistical model (XGBoost)
✓ Paper trading (simulated execution)
✓ Measure latency (target: p99 < 1ms end-to-end)
```

### Fase 2: LLM Integration (Semanas 5-8)
```
✓ Deploy SageMaker endpoint (Bedrock Claude Haiku)
✓ Implement dual-path router (fast/slow)
✓ Backtest "Contrarian" strategy (historical data)
✓ A/B test: Statistical only vs LLM-augmented
```

### Fase 3: Live Trading (Semanas 9-12)
```
✓ Start with $1,000 capital (limit blast radius)
✓ Whitelist 3 assets (BTC, ETH, SOL)
✓ Max position size: $100
✓ Run 24/7 with human monitoring
✓ Iterate based on DynamoDB experiment results
```

### Fase 4: Scale (Meses 4-6)
```
✓ If Sharpe > 2.0 sustained, increase capital to $50k
✓ Add more assets (top 20 by volume)
✓ Evaluate FPGA migration (only if latency is bottleneck)
```

---

## 11. VEREDICTO FINAL

### Lo Que PUEDES Lograr en AWS:
✅ **Ultra-Low Latency Trading (50-500µs)** competitivo para nichos específicos  
✅ **LLM-augmented decision making** imposible en hardware puro  
✅ **Rapid iteration** (deploy en minutos vs. meses con FPGA)  
✅ **Cost-effective** para validar alpha ($4k/mes vs $50k+ colocation)

### Lo Que NO PUEDES Lograr:
❌ Competir con market makers institucionales (<10µs)  
❌ Arbitraje cross-exchange puro (latencia física te mata)  
❌ Latencia determinística (hypervisor jitter existe)

### Recomendación del Ingeniero Principal:

> **Construye el sistema en AWS con C7gn + Rust**. Olvídate de FPGA por ahora. Tu ventaja competitiva está en la **estrategia "Contrarian"** (detección de manipulación + LLM), no en ser 200ns más rápido. Si logras Sharpe > 2.5 sostenido por 6 meses, entonces considera migrar componentes críticos a FPGA o colocation.
>
> **El 90% de los HFT fallan por mala estrategia, no por latencia**. Enfócate en el alpha primero, luego optimiza el último microsegundo.

---

## 12. PRÓXIMOS PASOS INMEDIATOS

1. **Provision infrastructure** (Terraform/CDK)
2. **Implement data pipeline** (DPDK + lock-free queues)
3. **Deploy baseline statistical model** (sin LLM)
4. **Measure latency baseline** (debe ser <500µs p99)
5. **Paper trade por 2 semanas** antes de capital real

¿Quieres que profundice en algún componente específico (ej: código DPDK completo, diseño de prompts LLM, backtesting framework)?
