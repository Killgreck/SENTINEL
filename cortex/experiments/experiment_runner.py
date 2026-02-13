"""
SENTINEL — Experiment Runner (Fase 4)
══════════════════════════════════════
Ejecuta grids de backtests variando agentes, símbolos y parámetros.
Guarda cada resultado en el ExperimentStore.

Uso:
    python3 -m cortex.experiments.experiment_runner
    python3 -m cortex.experiments.experiment_runner --agents statistical swing --symbols BTCUSDT ETHUSDT
    python3 -m cortex.experiments.experiment_runner --grid full
"""

import os
import sys
import argparse
import itertools
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from cortex.experiments.experiment_store import (
    ExperimentStore,
    ExperimentResult,
    generate_experiment_id,
)


# ═══════════════════════════════════════════
#  Experiment Grid Definitions
# ═══════════════════════════════════════════

PRESET_GRIDS = {
    "quick": {
        "agents": ["buy_hold", "statistical"],
        "symbols": ["BTCUSDT"],
        "intervals": ["1d"],
        "hold_penalty_rates": [0.05],
        "risk_per_trade_pcts": [0.1],
    },
    "standard": {
        "agents": ["buy_hold", "statistical", "swing", "contrarian"],
        "symbols": ["BTCUSDT"],
        "intervals": ["1d"],
        "hold_penalty_rates": [0.0, 0.05, 0.10],
        "risk_per_trade_pcts": [0.05, 0.1, 0.2],
    },
    "full": {
        "agents": ["buy_hold", "statistical", "swing", "contrarian", "llm"],
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        "intervals": ["1d"],
        "hold_penalty_rates": [0.0, 0.03, 0.05, 0.10],
        "risk_per_trade_pcts": [0.05, 0.1, 0.15, 0.2],
    },
}


def run_single_experiment(params: dict) -> dict:
    """
    Ejecuta un solo backtest como experimento independiente.
    Diseñado para ser compatible con ProcessPoolExecutor.
    """
    # Importar aquí para evitar problemas con multiprocessing
    import yaml
    from cortex.gym.data_loader import DataLoader
    from cortex.gym.environment import TradingEnvironment
    from cortex.metrics import MetricsEngine
    from cortex.backtester import create_agent

    agent_name = params["agent"]
    symbol = params["symbol"]
    interval = params["interval"]
    hold_penalty_rate = params.get("hold_penalty_rate", 0.05)
    risk_per_trade_pct = params.get("risk_per_trade_pct", 0.1)
    initial_capital = params.get("initial_capital", 100.0)
    fee_rate = params.get("fee_rate", 0.001)
    slippage = params.get("slippage", 0.0005)
    start_date = params.get("start_date")
    end_date = params.get("end_date")
    experiment_id = params.get("experiment_id", generate_experiment_id())

    try:
        # Cargar datos
        loader = DataLoader()
        data = loader.load_merged(symbol, interval, start_date=start_date, end_date=end_date)

        if data.empty:
            return {"error": f"No data for {symbol} {interval}", "experiment_id": experiment_id}

        # Crear agente
        agent = create_agent(agent_name)
        agent.reset()

        # Crear entorno
        env = TradingEnvironment(
            data=data,
            initial_capital=initial_capital,
            fee_rate=fee_rate,
            slippage=slippage,
            risk_per_trade_pct=risk_per_trade_pct,
            window_size=30,
            symbol=symbol,
            hold_penalty_rate=hold_penalty_rate,
        )

        # Correr simulación
        observation = env.reset()
        done = False
        while not done:
            action = agent.decide(observation)
            observation, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated

        # Métricas
        trade_pnls = []
        for fill in env.exchange.trade_history:
            if fill.side == "SELL":
                trade_pnls.append(fill.total_cost - fill.quantity * fill.price)
        if not trade_pnls and env.equity_curve:
            trade_pnls = [env.equity_curve[-1] - initial_capital]

        actual_start = str(data["timestamp"].iloc[0].date()) if hasattr(data["timestamp"].iloc[0], "date") else str(data["timestamp"].iloc[0])
        actual_end = str(data["timestamp"].iloc[-1].date()) if hasattr(data["timestamp"].iloc[-1], "date") else str(data["timestamp"].iloc[-1])

        metrics = MetricsEngine.calculate_all(
            strategy_name=agent.name,
            symbol=symbol,
            start_date=actual_start,
            end_date=actual_end,
            initial_capital=initial_capital,
            equity_curve=env.equity_curve,
            trade_pnls=trade_pnls,
            trade_log=env.get_step_log_df(),
        )

        return ExperimentResult(
            experiment_id=experiment_id,
            timestamp=datetime.now().isoformat(),
            agent_name=agent.name,
            symbol=symbol,
            interval=interval,
            start_date=actual_start,
            end_date=actual_end,
            initial_capital=initial_capital,
            fee_rate=fee_rate,
            slippage=slippage,
            hold_penalty_rate=hold_penalty_rate,
            risk_per_trade_pct=risk_per_trade_pct,
            final_value=metrics.final_value,
            total_pnl=metrics.total_pnl,
            total_return_pct=metrics.total_return_pct,
            sharpe_ratio=metrics.sharpe_ratio,
            max_drawdown_pct=metrics.max_drawdown_pct,
            total_trades=metrics.total_trades,
            win_rate=metrics.win_rate,
            profit_factor=metrics.profit_factor,
            score_final=env.score,
            total_hold_penalty=env.total_hold_penalty,
            extra_params=params.get("extra_params", {}),
        ).to_dict()

    except Exception as e:
        return {"error": str(e), "experiment_id": experiment_id, "agent": agent_name, "symbol": symbol}


def run_experiment_grid(
    agents: list = None,
    symbols: list = None,
    intervals: list = None,
    hold_penalty_rates: list = None,
    risk_per_trade_pcts: list = None,
    start_date: str = None,
    end_date: str = None,
    parallel: bool = False,
    max_workers: int = 4,
    store_mode: str = "local",
) -> list:
    """
    Ejecuta una grid de experimentos.

    Returns:
        Lista de ExperimentResult dicts
    """
    agents = agents or ["buy_hold", "statistical", "swing", "contrarian"]
    symbols = symbols or ["BTCUSDT"]
    intervals = intervals or ["1d"]
    hold_penalty_rates = hold_penalty_rates or [0.05]
    risk_per_trade_pcts = risk_per_trade_pcts or [0.1]

    # Generar todas las combinaciones
    combinations = list(itertools.product(
        agents, symbols, intervals, hold_penalty_rates, risk_per_trade_pcts
    ))

    total = len(combinations)
    print(f"\n🛡️  SENTINEL Experiment Grid")
    print(f"{'═' * 60}")
    print(f"  Agents:          {agents}")
    print(f"  Symbols:         {symbols}")
    print(f"  Hold Penalties:  {hold_penalty_rates}")
    print(f"  Risk/Trade:      {risk_per_trade_pcts}")
    print(f"  Total:           {total} experiments")
    print(f"  Mode:            {'Parallel' if parallel else 'Sequential'}")
    print(f"{'═' * 60}\n")

    # Preparar parámetros
    all_params = []
    for agent, symbol, interval, hp, rpt in combinations:
        all_params.append({
            "agent": agent,
            "symbol": symbol,
            "interval": interval,
            "hold_penalty_rate": hp,
            "risk_per_trade_pct": rpt,
            "start_date": start_date,
            "end_date": end_date,
            "experiment_id": generate_experiment_id(),
        })

    # Ejecutar
    results = []
    store = ExperimentStore(mode=store_mode)

    if parallel and total > 1:
        # Ejecución paralela
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(run_single_experiment, p): p for p in all_params}
            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()
                if "error" in result:
                    print(f"  ❌ [{i}/{total}] Error: {result['error']}")
                else:
                    exp = ExperimentResult(**result)
                    store.save(exp)
                    print(f"  ✅ [{i}/{total}] {exp.agent_name} | {exp.symbol} | "
                          f"PnL: ${exp.total_pnl:+.2f} | Score: {exp.score_final:.0f} | "
                          f"Sharpe: {exp.sharpe_ratio:.3f}")
                    results.append(result)
    else:
        # Ejecución secuencial
        for i, params in enumerate(all_params, 1):
            print(f"  🏃 [{i}/{total}] {params['agent']} | {params['symbol']} | "
                  f"penalty={params['hold_penalty_rate']} | risk={params['risk_per_trade_pct']}")

            result = run_single_experiment(params)

            if "error" in result:
                print(f"     ❌ Error: {result['error']}")
            else:
                exp = ExperimentResult(**result)
                store.save(exp)
                print(f"     ✅ PnL: ${exp.total_pnl:+.2f} | Score: {exp.score_final:.0f} | "
                      f"Sharpe: {exp.sharpe_ratio:.3f}")
                results.append(result)

    # Leaderboard
    print(f"\n{'═' * 80}")
    print(f"  🏆 LEADERBOARD (Top 10 by Sharpe Ratio)")
    print(f"{'═' * 80}")

    leaderboard = store.get_leaderboard(sort_by="sharpe_ratio", top_n=10)
    if leaderboard:
        print(f"  {'Rank':<5} {'Agent':<20} {'Symbol':<10} {'Sharpe':>8} {'PnL':>10} {'Score':>8} {'DDn':>8} {'Penalty':>8}")
        print(f"  {'─' * 75}")
        for rank, exp in enumerate(leaderboard, 1):
            print(f"  {rank:<5} {exp.agent_name:<20} {exp.symbol:<10} "
                  f"{exp.sharpe_ratio:>8.3f} ${exp.total_pnl:>+8.2f} "
                  f"{exp.score_final:>8.0f} {exp.max_drawdown_pct:>7.1f}% "
                  f"${exp.total_hold_penalty:>7.2f}")
    print(f"{'═' * 80}\n")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="🛡️ SENTINEL Experiment Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python3 -m cortex.experiments.experiment_runner --grid quick
  python3 -m cortex.experiments.experiment_runner --grid standard
  python3 -m cortex.experiments.experiment_runner --agents statistical swing --symbols BTCUSDT ETHUSDT
  python3 -m cortex.experiments.experiment_runner --grid full --parallel
        """
    )
    parser.add_argument("--grid", type=str, choices=["quick", "standard", "full"],
                        help="Preset grid (quick, standard, full)")
    parser.add_argument("--agents", nargs="+", default=None,
                        help="Agentes a evaluar")
    parser.add_argument("--symbols", nargs="+", default=None,
                        help="Símbolos a evaluar")
    parser.add_argument("--penalties", nargs="+", type=float, default=None,
                        help="Hold penalty rates a probar")
    parser.add_argument("--risks", nargs="+", type=float, default=None,
                        help="Risk per trade pcts a probar")
    parser.add_argument("--start", type=str, default=None)
    parser.add_argument("--end", type=str, default=None)
    parser.add_argument("--parallel", action="store_true",
                        help="Ejecutar en paralelo")
    parser.add_argument("--workers", type=int, default=4,
                        help="Número de workers paralelos")
    parser.add_argument("--dynamodb", action="store_true",
                        help="Guardar en DynamoDB además de local")
    parser.add_argument("--leaderboard", action="store_true",
                        help="Solo mostrar leaderboard de experimentos existentes")

    args = parser.parse_args()

    # Solo leaderboard
    if args.leaderboard:
        store = ExperimentStore()
        leaderboard = store.get_leaderboard(top_n=20)
        if not leaderboard:
            print("  No hay experimentos guardados aún.")
            return
        print(f"\n{'═' * 80}")
        print(f"  🏆 LEADERBOARD (Top 20)")
        print(f"{'═' * 80}")
        print(f"  {'Rank':<5} {'Agent':<20} {'Symbol':<10} {'Sharpe':>8} {'PnL':>10} {'Score':>8} {'DDn':>8}")
        print(f"  {'─' * 75}")
        for rank, exp in enumerate(leaderboard, 1):
            print(f"  {rank:<5} {exp.agent_name:<20} {exp.symbol:<10} "
                  f"{exp.sharpe_ratio:>8.3f} ${exp.total_pnl:>+8.2f} "
                  f"{exp.score_final:>8.0f} {exp.max_drawdown_pct:>7.1f}%")
        print(f"{'═' * 80}\n")
        return

    # Usar preset grid o parámetros customizados
    if args.grid:
        grid = PRESET_GRIDS[args.grid]
        agents = grid["agents"]
        symbols = grid["symbols"]
        intervals = grid["intervals"]
        penalties = grid["hold_penalty_rates"]
        risks = grid["risk_per_trade_pcts"]
    else:
        agents = args.agents
        symbols = args.symbols
        intervals = ["1d"]
        penalties = args.penalties
        risks = args.risks

    run_experiment_grid(
        agents=agents,
        symbols=symbols,
        intervals=intervals,
        hold_penalty_rates=penalties,
        risk_per_trade_pcts=risks,
        start_date=args.start,
        end_date=args.end,
        parallel=args.parallel,
        max_workers=args.workers,
        store_mode="dynamodb" if args.dynamodb else "local",
    )


if __name__ == "__main__":
    main()
