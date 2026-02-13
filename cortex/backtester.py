"""
SENTINEL Cortex — Backtester
══════════════════════════════
Orquestador de backtests: conecta DataLoader + Environment + Agent + Metrics.

Uso:
    python3 -m cortex.backtester --agent buy_hold --symbol BTCUSDT
    python3 -m cortex.backtester --agent statistical --symbol BTCUSDT --start 2023-01-01
    python3 -m cortex.backtester --agent llm --symbol BTCUSDT --output results/llm.csv
"""

import os
import sys
import yaml
import argparse
import pandas as pd
from datetime import datetime

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from cortex.gym.data_loader import DataLoader
from cortex.gym.environment import TradingEnvironment
from cortex.metrics import MetricsEngine, BacktestResult


def load_config(config_path: str) -> dict:
    """Carga configuración YAML."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def create_agent(agent_name: str, config: dict = None):
    """Factory para crear agentes por nombre."""
    agent_name = agent_name.lower().replace("-", "_")

    if agent_name == "buy_hold":
        from cortex.agents.buy_hold_agent import BuyHoldAgent
        return BuyHoldAgent()

    elif agent_name == "statistical":
        from cortex.agents.statistical_agent import StatisticalAgent
        return StatisticalAgent()

    elif agent_name == "llm":
        from cortex.agents.llm_agent import LLMAgent
        model = config.get("models", {}).get("fast_path", "claude-3-haiku") if config else "claude-3-haiku"
        return LLMAgent(offline_mode=True)

    elif agent_name == "swing":
        from cortex.strategies.swing import SwingStrategy
        return SwingStrategy()

    elif agent_name == "contrarian":
        from cortex.strategies.contrarian import ContrarianStrategy
        return ContrarianStrategy()

    else:
        raise ValueError(
            f"Agente desconocido: '{agent_name}'. "
            f"Opciones: buy_hold, statistical, llm, swing, contrarian"
        )


def run_backtest(
    agent_name: str,
    symbol: str = "BTCUSDT",
    interval: str = "1d",
    start_date: str = None,
    end_date: str = None,
    config_path: str = None,
    output_path: str = None,
    verbose: bool = True,
) -> BacktestResult:
    """
    Ejecuta un backtest completo.

    Args:
        agent_name: Nombre del agente ("buy_hold", "statistical", "llm", "swing", "contrarian")
        symbol: Símbolo del activo
        interval: Intervalo temporal
        start_date: Fecha inicio (YYYY-MM-DD)
        end_date: Fecha fin (YYYY-MM-DD)
        config_path: Path al config.yaml
        output_path: Path para guardar CSV de resultados
        verbose: Imprimir progreso

    Returns:
        BacktestResult con métricas completas
    """
    if verbose:
        print(f"\n🛡️  SENTINEL Backtest")
        print(f"{'═' * 50}")
        print(f"  Agent:    {agent_name}")
        print(f"  Symbol:   {symbol}")
        print(f"  Interval: {interval}")
        if start_date:
            print(f"  Start:    {start_date}")
        if end_date:
            print(f"  End:      {end_date}")
        print(f"{'═' * 50}\n")

    # Cargar config
    config = {}
    if config_path and os.path.exists(config_path):
        config = load_config(config_path)
    else:
        default_config = os.path.join(PROJECT_ROOT, "cortex", "gym", "config.yaml")
        if os.path.exists(default_config):
            config = load_config(default_config)

    sim_config = config.get("simulation", {})
    initial_capital = sim_config.get("initial_capital_usd", 100.0)
    fee_rate = sim_config.get("fee_rate", 0.001)
    slippage = sim_config.get("slippage", 0.0005)
    risk_per_trade = config.get("logic", {}).get("risk_per_trade_pct", 0.1)
    hold_penalty_rate = config.get("logic", {}).get("hold_penalty_rate", 0.05)

    # Cargar datos
    if verbose:
        print("  📊 Cargando datos...")
    loader = DataLoader()
    data = loader.load_merged(symbol, interval, start_date=start_date, end_date=end_date)

    if data.empty:
        raise ValueError(f"No hay datos para {symbol} {interval}")

    if verbose:
        print(f"  ✅ {len(data)} filas cargadas")
        print(f"     {data['timestamp'].iloc[0]} → {data['timestamp'].iloc[-1]}\n")

    # Crear agente
    agent = create_agent(agent_name, config)
    agent.reset()

    # Crear entorno
    env = TradingEnvironment(
        data=data,
        initial_capital=initial_capital,
        fee_rate=fee_rate,
        slippage=slippage,
        risk_per_trade_pct=risk_per_trade,
        window_size=30,
        symbol=symbol,
        hold_penalty_rate=hold_penalty_rate,
    )

    # Correr simulación
    if verbose:
        print(f"  🏃 Ejecutando backtest con {agent.name}...")

    observation = env.reset()
    done = False
    step = 0

    while not done:
        action = agent.decide(observation)
        observation, reward, terminated, truncated, info = env.step(action)
        done = terminated or truncated
        step += 1

        # Progreso cada 10% de pasos
        if verbose and step % max(1, env.total_steps // 10) == 0:
            pct = step / env.total_steps * 100
            pv = info.get("portfolio_value", 0)
            sc = info.get("score", 0)
            print(f"     [{pct:5.1f}%] Step {step}/{env.total_steps} | Portfolio: ${pv:.2f} | Score: {sc:.0f}")

    # Calcular métricas
    if verbose:
        print(f"\n  📈 Calculando métricas...")

    # Recolectar trade PnLs del exchange
    trade_pnls = []
    for fill in env.exchange.trade_history:
        if fill.side == "SELL":
            trade_pnls.append(fill.total_cost - fill.quantity * fill.price)

    # Si no hay trades de venta, usar la equity curve para PnL
    if not trade_pnls and env.equity_curve:
        trade_pnls = [env.equity_curve[-1] - initial_capital]

    actual_start = str(data["timestamp"].iloc[0].date()) if hasattr(data["timestamp"].iloc[0], "date") else str(data["timestamp"].iloc[0])
    actual_end = str(data["timestamp"].iloc[-1].date()) if hasattr(data["timestamp"].iloc[-1], "date") else str(data["timestamp"].iloc[-1])

    result = MetricsEngine.calculate_all(
        strategy_name=agent.name,
        symbol=symbol,
        start_date=actual_start,
        end_date=actual_end,
        initial_capital=initial_capital,
        equity_curve=env.equity_curve,
        trade_pnls=trade_pnls,
        trade_log=env.get_step_log_df(),
    )

    # Imprimir resultados
    if verbose:
        print(f"\n{'═' * 50}")
        print(f"  📊 RESULTADOS: {agent.name} | {symbol}")
        print(f"{'═' * 50}")
        print(f"  Capital Inicial: ${result.initial_capital:.2f}")
        print(f"  Capital Final:   ${result.final_value:.2f}")
        print(f"  PnL:             ${result.total_pnl:+.2f} ({result.total_return_pct:+.1f}%)")
        print(f"  Sharpe Ratio:    {result.sharpe_ratio:.3f}")
        print(f"  Max Drawdown:    {result.max_drawdown_pct:.1f}%")
        print(f"  Trades:          {result.total_trades}")
        print(f"  Win Rate:        {result.win_rate:.1f}%")
        print(f"  Profit Factor:   {result.profit_factor:.2f}")
        print(f"  {'─' * 46}")
        print(f"  🏆 Score Final:  {env.score:.0f}/1000")
        print(f"  💸 Hold Penalty: ${env.total_hold_penalty:.2f} total")
        print(f"{'═' * 50}\n")

    # Guardar resultados
    if output_path:
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
        trade_log = env.get_step_log_df()
        trade_log.to_csv(output_path, index=False)
        if verbose:
            print(f"  💾 Resultados guardados en: {output_path}")

    return result


def compare_agents(
    agents: list,
    symbol: str = "BTCUSDT",
    interval: str = "1d",
    start_date: str = None,
    end_date: str = None,
    config_path: str = None,
) -> pd.DataFrame:
    """
    Ejecuta múltiples backtests y compara resultados.

    Args:
        agents: Lista de nombres de agentes
        symbol: Símbolo
        interval: Intervalo
        start_date: Fecha inicio
        end_date: Fecha fin

    Returns:
        DataFrame con comparación
    """
    results = []

    for agent_name in agents:
        print(f"\n{'─' * 60}")
        result = run_backtest(
            agent_name=agent_name,
            symbol=symbol,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
            config_path=config_path,
            output_path=f"results/{agent_name}_{symbol}.csv",
        )
        results.append(result.to_dict())

    # Crear tabla comparativa
    comparison = pd.DataFrame(results)
    columns_order = [
        "strategy_name", "total_return_pct", "sharpe_ratio",
        "max_drawdown_pct", "total_trades", "win_rate",
        "profit_factor", "final_value",
    ]
    comparison = comparison[[c for c in columns_order if c in comparison.columns]]

    print(f"\n\n{'═' * 80}")
    print(f"  📊 COMPARACIÓN DE ESTRATEGIAS | {symbol}")
    print(f"{'═' * 80}")
    print(comparison.to_string(index=False))
    print(f"{'═' * 80}\n")

    return comparison


def main():
    parser = argparse.ArgumentParser(
        description="🛡️ SENTINEL Backtester",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python3 -m cortex.backtester --agent buy_hold
  python3 -m cortex.backtester --agent statistical --symbol ETHUSDT
  python3 -m cortex.backtester --agent swing --start 2023-06-01
  python3 -m cortex.backtester --compare buy_hold statistical swing contrarian
        """
    )
    parser.add_argument("--agent", type=str, default="buy_hold",
                        help="Agente a usar (buy_hold, statistical, llm, swing, contrarian)")
    parser.add_argument("--symbol", type=str, default="BTCUSDT",
                        help="Símbolo (default: BTCUSDT)")
    parser.add_argument("--interval", type=str, default="1d",
                        help="Intervalo (1d, 1h)")
    parser.add_argument("--start", type=str, default=None,
                        help="Fecha inicio (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None,
                        help="Fecha fin (YYYY-MM-DD)")
    parser.add_argument("--config", type=str, default=None,
                        help="Path al config.yaml")
    parser.add_argument("--output", type=str, default=None,
                        help="Path para guardar CSV")
    parser.add_argument("--compare", nargs="+", default=None,
                        help="Comparar múltiples agentes")

    args = parser.parse_args()

    if args.compare:
        compare_agents(
            agents=args.compare,
            symbol=args.symbol,
            interval=args.interval,
            start_date=args.start,
            end_date=args.end,
            config_path=args.config,
        )
    else:
        run_backtest(
            agent_name=args.agent,
            symbol=args.symbol,
            interval=args.interval,
            start_date=args.start,
            end_date=args.end,
            config_path=args.config,
            output_path=args.output or f"results/{args.agent}_{args.symbol}.csv",
        )


if __name__ == "__main__":
    main()
